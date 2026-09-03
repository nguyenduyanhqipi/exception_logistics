import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import axios from "axios";
import { apiClient } from "../api/client";

function errorMessage(query: UseQueryResult<unknown>): string {
  if (axios.isAxiosError(query.error) && query.error.response?.status === 403) {
    return "Bạn không có quyền truy cập báo cáo này.";
  }
  return "Không tải được dữ liệu.";
}

interface KpiResponse {
  total_exceptions: number;
  by_severity: Record<string, number>;
  by_status: Record<string, number>;
  resolved_rate: number | null;
  avg_resolution_minutes: number | null;
  on_time_rate: number | null;
  total_estimated_cost: number;
  total_actual_cost: number;
}

interface TrendsResponse {
  days: number;
  trend: { date: string; total: number; by_group: Record<string, number> }[];
}

interface CostAccuracyResponse {
  items: { decision_id: string; estimated_cost: number; actual_cost: number; diff: number; diff_pct: number | null }[];
  count: number;
  avg_diff_pct: number | null;
}

interface LlmUsageResponse {
  days: number;
  usage_by_date: { date: string; calls: number; tokens_in: number; tokens_out: number; cost_usd: number; success_rate: number | null }[];
  calls_today: number;
}

function pct(v: number | null): string {
  return v === null ? "-" : `${(v * 100).toFixed(0)}%`;
}

export function ManagerDashboard() {
  const kpi = useQuery({ queryKey: ["reports-kpi"], queryFn: async () => (await apiClient.get<KpiResponse>("/api/reports/kpi")).data });
  const trends = useQuery({ queryKey: ["reports-trends"], queryFn: async () => (await apiClient.get<TrendsResponse>("/api/reports/trends")).data });
  const costAccuracy = useQuery({
    queryKey: ["reports-cost-accuracy"],
    queryFn: async () => (await apiClient.get<CostAccuracyResponse>("/api/reports/cost-accuracy")).data,
  });
  const llmUsage = useQuery({ queryKey: ["reports-llm-usage"], queryFn: async () => (await apiClient.get<LlmUsageResponse>("/api/reports/llm-usage")).data });

  return (
    <div className="page">
      <h1>Báo cáo tổng quan</h1>

      <div className="card">
        <h2>KPI</h2>
        {kpi.isLoading && <div className="loading-spinner">Đang tải...</div>}
        {kpi.isError && <div className="error-banner">{errorMessage(kpi)}</div>}
        {kpi.data && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 16 }}>
            <Stat label="Tổng ngoại lệ" value={kpi.data.total_exceptions} />
            <Stat label="Tỷ lệ đã xử lý" value={pct(kpi.data.resolved_rate)} />
            <Stat label="Thời gian xử lý TB" value={kpi.data.avg_resolution_minutes !== null ? `${kpi.data.avg_resolution_minutes} phút` : "-"} />
            <Stat label="Tỷ lệ giao đúng hạn" value={pct(kpi.data.on_time_rate)} />
            <Stat label="Tổng chi phí ước tính" value={`${kpi.data.total_estimated_cost.toLocaleString("vi-VN")}đ`} />
            <Stat label="Tổng chi phí thực tế" value={`${kpi.data.total_actual_cost.toLocaleString("vi-VN")}đ`} />
          </div>
        )}
        {kpi.data && (
          <div style={{ marginTop: 16, display: "flex", gap: 24 }}>
            <span>Cảnh báo: <span className="badge badge-warning">{kpi.data.by_severity.warning}</span></span>
            <span>Nghiêm trọng: <span className="badge badge-serious">{kpi.data.by_severity.serious}</span></span>
            <span>Khẩn cấp: <span className="badge badge-critical">{kpi.data.by_severity.critical}</span></span>
          </div>
        )}
      </div>

      <div className="card">
        <h2>Xu hướng ngoại lệ (30 ngày)</h2>
        {trends.isLoading && <div className="loading-spinner">Đang tải...</div>}
        {trends.isError && <div className="error-banner">{errorMessage(trends)}</div>}
        {trends.data && trends.data.trend.length === 0 && <p style={{ color: "#6b7280" }}>Chưa có dữ liệu.</p>}
        {trends.data && trends.data.trend.length > 0 && (
          <table className="list-table">
            <thead>
              <tr>
                <th>Ngày</th>
                <th>Tổng</th>
                <th>Theo loại</th>
              </tr>
            </thead>
            <tbody>
              {trends.data.trend.map((row) => (
                <tr key={row.date}>
                  <td>{row.date}</td>
                  <td>{row.total}</td>
                  <td>{Object.entries(row.by_group).map(([g, c]) => `${g}: ${c}`).join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h2>So sánh chi phí ước tính vs thực tế</h2>
        {costAccuracy.isLoading && <div className="loading-spinner">Đang tải...</div>}
        {costAccuracy.isError && <div className="error-banner">{errorMessage(costAccuracy)}</div>}
        {costAccuracy.data && costAccuracy.data.count === 0 && <p style={{ color: "#6b7280" }}>Chưa có dữ liệu.</p>}
        {costAccuracy.data && costAccuracy.data.count > 0 && (
          <>
            <p>
              Sai số trung bình: <strong>{pct(costAccuracy.data.avg_diff_pct)}</strong> ({costAccuracy.data.count} quyết định có kết quả)
            </p>
            <table className="list-table">
              <thead>
                <tr>
                  <th>Ước tính</th>
                  <th>Thực tế</th>
                  <th>Chênh lệch</th>
                </tr>
              </thead>
              <tbody>
                {costAccuracy.data.items.map((it) => (
                  <tr key={it.decision_id}>
                    <td>{it.estimated_cost.toLocaleString("vi-VN")}đ</td>
                    <td>{it.actual_cost.toLocaleString("vi-VN")}đ</td>
                    <td>{pct(it.diff_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>

      <div className="card">
        <h2>Chi phí sử dụng AI</h2>
        {llmUsage.isLoading && <div className="loading-spinner">Đang tải...</div>}
        {llmUsage.isError && <div className="error-banner">{errorMessage(llmUsage)}</div>}
        {llmUsage.data && (
          <>
            <p>
              Lượt gọi hôm nay: <strong>{llmUsage.data.calls_today}</strong> / 100
            </p>
            {llmUsage.data.usage_by_date.length > 0 && (
              <table className="list-table">
                <thead>
                  <tr>
                    <th>Ngày</th>
                    <th>Lượt gọi</th>
                    <th>Token vào/ra</th>
                    <th>Chi phí ($)</th>
                    <th>Tỷ lệ thành công</th>
                  </tr>
                </thead>
                <tbody>
                  {llmUsage.data.usage_by_date.map((row) => (
                    <tr key={row.date}>
                      <td>{row.date}</td>
                      <td>{row.calls}</td>
                      <td>{row.tokens_in} / {row.tokens_out}</td>
                      <td>${row.cost_usd}</td>
                      <td>{pct(row.success_rate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <div style={{ fontSize: 12, color: "#6b7280", textTransform: "uppercase" }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700 }}>{value}</div>
    </div>
  );
}
