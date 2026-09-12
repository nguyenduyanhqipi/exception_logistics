import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import axios from "axios";
import { useState } from "react";
import { apiClient } from "../api/client";
import { BarChart, type ChartSeries } from "../components/BarChart";
import { PERIOD_TABS, PeriodPicker, subPeriodLabel, type PeriodType } from "../components/PeriodPicker";
import { localToday } from "../exceptionForm";
import { exceptionGroupLabel, subTypeLabel } from "../labels";
import { EXCEPTION_STATUS_LABEL } from "../statusLabels";

// Trang "Báo cáo tổng quan" — redesign 2026-09-08 (đợt code 5, Pha 5,
// reports_dashboard_redesign.md).
//
// Cả trang chạy trên ĐÚNG 1 bộ lọc kỳ: trước đây mỗi bảng tự chốt khung thời
// gian riêng ("30 ngày gần nhất") nên KPI và bảng xu hướng nói về 2 khoảng khác
// nhau mà không chỗ nào nói ra.

function errorMessage(query: UseQueryResult<unknown>): string {
  if (axios.isAxiosError(query.error) && query.error.response?.status === 403) {
    return "Bạn không có quyền truy cập báo cáo này.";
  }
  return "Không tải được dữ liệu.";
}

interface Kpi {
  total_exceptions: number;
  by_severity: Record<string, number>;
  by_status: Record<string, number>;
  resolved_rate: number | null;
  avg_resolution_minutes: number | null;
  /** Giải thích giới hạn của `avg_resolution_minutes` — backend gửi kèm để nhãn
   *  trên UI và bản chất con số không lệch nhau khi query đổi. */
  avg_resolution_minutes_note: string;
  avg_settlement_minutes: number | null;
  on_time_rate: number | null;
  outcome_count: number;
  total_actual_cost: number;
  total_estimated_cost: number;
  cost_accuracy_rate: number | null;
  cost_avg_diff_pct: number | null;
  cost_sample_size: number;
  ai_option_rate: number | null;
  ai_called_exceptions: number;
}

interface SubTypeRow {
  sub_type: string;
  count: number;
  actual_cost: number;
  handling_minutes: number;
  handling_minutes_avg: number | null;
}

interface GroupRow {
  group: string;
  count: number;
  actual_cost: number;
  handling_minutes: number;
  handling_minutes_avg: number | null;
  sub_types: SubTypeRow[];
}

interface Bucket {
  key: string;
  label: string;
  total: number;
  by_group: Record<string, number>;
  actual_cost: number;
}

interface PeriodPayload {
  period: { type: string; anchor: string; start: string; end: string; label: string };
  kpi: Kpi;
  by_group: GroupRow[];
  buckets: Bucket[];
}

interface SummaryResponse extends PeriodPayload {
  sub_types_by_group: Record<string, string[]>;
  compare?: PeriodPayload;
}

interface LlmUsageResponse {
  days: number;
  usage_by_date: { date: string; calls: number; tokens_in: number; tokens_out: number; cost_usd: number; success_rate: number | null }[];
  calls_today: number;
}

const GROUP_COLORS: Record<string, string> = {
  delay: "#2563eb",
  road_block: "#f97316",
  customer_reject: "#dc2626",
  customer_change: "#7c3aed",
  vehicle_issue: "#0891b2",
};

function pct(v: number | null | undefined): string {
  return v === null || v === undefined ? "-" : `${(v * 100).toFixed(0)}%`;
}
function vnd(v: number | null | undefined): string {
  return v === null || v === undefined ? "-" : `${Math.round(v).toLocaleString("vi-VN")}đ`;
}
function minutes(v: number | null | undefined): string {
  return v === null || v === undefined ? "-" : `${v} phút`;
}

/** Như `minutes()` nhưng đổi sang giờ/ngày khi con số lớn — "1056.9 phút" đọc
 *  không ra được là gần 18 tiếng. Dùng cho chỉ số giải quyết thực tế (thường
 *  tính bằng ngày), chỉ số ra quyết định vẫn để nguyên phút. */
function duration(v: number | null | undefined): string {
  if (v === null || v === undefined) return "-";
  if (v < 90) return `${Math.round(v)} phút`;
  if (v < 1440) return `${(v / 60).toFixed(1)} giờ`;
  return `${(v / 1440).toFixed(1)} ngày`;
}

export function ManagerDashboard() {
  const today = localToday();
  const [type, setType] = useState<PeriodType>("month");
  const [anchorA, setAnchorA] = useState(today);
  const [anchorB, setAnchorB] = useState(today);
  const [compareOn, setCompareOn] = useState(false);
  const [withBuckets, setWithBuckets] = useState(false);
  const [splitByGroup, setSplitByGroup] = useState(false);
  const [openGroup, setOpenGroup] = useState<string | null>(null);

  // Bộ lọc chỉ ÁP DỤNG khi bấm "Xem báo cáo": đổi tab/ngày mà gọi API ngay sẽ
  // bắn một loạt request trung gian vô nghĩa (đổi tháng rồi mới đổi năm).
  const [applied, setApplied] = useState({ type, anchorA, anchorB: null as string | null, withBuckets: false });

  const summary = useQuery({
    queryKey: ["reports-summary", applied],
    queryFn: async () => {
      const params = new URLSearchParams({
        period_type: applied.type,
        anchor: applied.anchorA,
        with_buckets: String(applied.withBuckets),
      });
      if (applied.anchorB) params.set("compare_anchor", applied.anchorB);
      return (await apiClient.get<SummaryResponse>(`/api/reports/summary?${params}`)).data;
    },
  });
  const llmUsage = useQuery({
    queryKey: ["reports-llm-usage"],
    queryFn: async () => (await apiClient.get<LlmUsageResponse>("/api/reports/llm-usage")).data,
  });

  function apply() {
    setApplied({ type, anchorA, anchorB: compareOn ? anchorB : null, withBuckets });
  }

  // Bấm 2 nút "So sánh"/"Xem chi tiết theo..." áp dụng NGAY, không đợi "Xem báo
  // cáo" — khác `apply()` (dùng cho việc đổi kỳ/ngày, cố tình phải bấm thủ công
  // để tránh bắn API liên tục lúc đang chọn), 2 công tắc này chỉ có đúng 1 cú
  // bấm nên áp dụng ngay không có rủi ro request thừa.
  function applyToggle(overrides: Partial<{ compareOn: boolean; withBuckets: boolean }>) {
    const nextCompareOn = overrides.compareOn ?? compareOn;
    const nextWithBuckets = overrides.withBuckets ?? withBuckets;
    setApplied({ type, anchorA, anchorB: nextCompareOn ? anchorB : null, withBuckets: nextWithBuckets });
  }

  const data = summary.data;
  const a = data?.kpi;
  const b = data?.compare?.kpi;
  const subLabel = subPeriodLabel(type);

  return (
    <div className="page">
      <h1>Báo cáo tổng quan</h1>

      <div className="card">
        <div className="radio-group" style={{ marginBottom: 12 }}>
          {PERIOD_TABS.map((t) => (
            <label key={t.key} className={`radio-option ${type === t.key ? "selected" : ""}`}>
              <input
                type="radio"
                checked={type === t.key}
                onChange={() => {
                  setType(t.key);
                  // Kỳ con không còn nghĩa khi chuyển về tab Ngày.
                  if (t.key === "day") setWithBuckets(false);
                }}
              />
              {t.label}
            </label>
          ))}
        </div>

        <div style={{ display: "flex", gap: 20, flexWrap: "wrap", alignItems: "flex-start" }}>
          <PeriodPicker type={type} anchor={anchorA} onAnchorChange={setAnchorA} title={compareOn ? "Kỳ A" : "Kỳ báo cáo"} />
          {compareOn && <PeriodPicker type={type} anchor={anchorB} onAnchorChange={setAnchorB} title="Kỳ B (so sánh)" />}
        </div>

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", marginTop: 8 }}>
          <button type="button" className="primary" onClick={apply}>
            Xem báo cáo
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => {
              const next = !compareOn;
              setCompareOn(next);
              applyToggle({ compareOn: next });
            }}
          >
            {compareOn ? "Tắt so sánh" : "So sánh với kỳ khác"}
          </button>
          {subLabel && (
            <button
              type="button"
              className="secondary"
              onClick={() => {
                const next = !withBuckets;
                setWithBuckets(next);
                applyToggle({ withBuckets: next });
              }}
            >
              {withBuckets ? `Ẩn chi tiết theo ${subLabel}` : `Xem chi tiết theo ${subLabel}`}
            </button>
          )}
          {data && <span className="hint">Đang xem: {data.period.label}{data.compare ? ` · so với ${data.compare.period.label}` : ""}</span>}
        </div>
      </div>

      {summary.isLoading && <div className="loading-spinner">Đang tải...</div>}
      {summary.isError && <div className="error-banner">{errorMessage(summary)}</div>}

      {a && (
        <div className="card">
          <h2 style={{ marginTop: 0 }}>KPI</h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 16 }}>
            <Stat label="Tổng ngoại lệ" value={a.total_exceptions} compare={b?.total_exceptions} higherIsBetter={null} />
            <Stat label="Tỷ lệ đã xử lý" value={pct(a.resolved_rate)} raw={a.resolved_rate} compareRaw={b?.resolved_rate} higherIsBetter />
            {/* Đợt 12, việc 4: 2 chỉ số thời gian KHÁC NHAU, tên cũ "Thời gian
                xử lý TB" không nói rõ đang đo tới mốc nào. */}
            <Stat
              label="TB thời gian ra quyết định"
              value={minutes(a.avg_resolution_minutes)}
              raw={a.avg_resolution_minutes}
              compareRaw={b?.avg_resolution_minutes}
              higherIsBetter={false}
              hint="Từ lúc báo tới lúc chốt phương án · chỉ quyết định riêng lẻ"
              hintTitle={a.avg_resolution_minutes_note}
            />
            <Stat
              label="TB thời gian giải quyết thực tế"
              value={duration(a.avg_settlement_minutes)}
              raw={a.avg_settlement_minutes}
              compareRaw={b?.avg_settlement_minutes}
              higherIsBetter={false}
              hint="Tính tới lúc ghi nhận kết quả"
              hintTitle="Tính tới lúc ghi nhận kết quả — có thể trễ hơn lúc việc thực sự xong nếu nhập kết quả muộn. Cùng giới hạn: chưa tính quyết định gộp nhiều ngoại lệ."
            />
            <Stat label="Tỷ lệ giao đúng hạn" value={pct(a.on_time_rate)} raw={a.on_time_rate} compareRaw={b?.on_time_rate} higherIsBetter />
            <Stat label="Tổng chi phí thực tế" value={vnd(a.total_actual_cost)} raw={a.total_actual_cost} compareRaw={b?.total_actual_cost} higherIsBetter={false} />
            {/* Mục 6.1: tỷ lệ SINH PHƯƠNG ÁN thành công — chỉ số chất lượng sản
                phẩm, khác hẳn "tỷ lệ gọi API thành công" ở bảng Chi phí AI. */}
            <Stat
              label="Tỷ lệ sinh phương án thành công"
              value={pct(a.ai_option_rate)}
              raw={a.ai_option_rate}
              compareRaw={b?.ai_option_rate}
              higherIsBetter
              hint={`${a.ai_called_exceptions} ngoại lệ có gọi AI`}
            />
            {/* Mục 5: thay cả bảng "so sánh chi phí ước tính vs thực tế" bằng 1 số. */}
            <Stat
              label="Độ chính xác ước tính chi phí AI"
              value={pct(a.cost_accuracy_rate)}
              raw={a.cost_accuracy_rate}
              compareRaw={b?.cost_accuracy_rate}
              higherIsBetter
              hint={`sai số TB ${pct(a.cost_avg_diff_pct)} · ${a.cost_sample_size} quyết định`}
            />
          </div>

          <div style={{ marginTop: 16, display: "flex", gap: 24, flexWrap: "wrap" }}>
            <span>Cảnh báo: <span className="badge badge-warning">{a.by_severity.warning}</span></span>
            <span>Nghiêm trọng: <span className="badge badge-serious">{a.by_severity.serious}</span></span>
            <span>Khẩn cấp: <span className="badge badge-critical">{a.by_severity.critical}</span></span>
          </div>
          {/* "Tỷ lệ đã xử lý" chỉ đếm ngoại lệ ĐÃ CÓ kết quả thực tế (xem
              backend/api/decisions.py) — bày phân bố trạng thái để quản lý thấy
              rõ bao nhiêu ca đang kẹt ở "chờ nhập kết quả". */}
          <div style={{ marginTop: 12, display: "flex", gap: 24, flexWrap: "wrap" }}>
            {Object.entries(a.by_status).map(([key, count]) => (
              <span key={key}>
                {EXCEPTION_STATUS_LABEL[key] ?? key}: <span className={`badge badge-${key}`}>{count}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {a && b && data && (
        <div className="card">
          <h2 style={{ marginTop: 0 }}>So sánh 2 kỳ</h2>
          {/* Mỗi ĐƠN VỊ một biểu đồ riêng: gộp tiền, phút và % vào chung 1 trục
              là biểu đồ vô nghĩa — cột tiền triệu sẽ dìm mọi cột còn lại thành
              vạch phẳng. */}
          <h3>Số ngoại lệ</h3>
          <BarChart
            categories={["Tổng ngoại lệ", "Đã có kết quả"]}
            series={comparePair(data, [a.total_exceptions, a.outcome_count], [b.total_exceptions, b.outcome_count])}
            format={(v) => String(Math.round(v))}
          />
          {/* Cột CHỒNG (không phải cột đôi như các biểu đồ so sánh khác ở đây):
              mỗi kỳ là 1 cột, chia màu theo 5 nhóm — nhờ vậy tổng chiều cao cột
              đọc thẳng ra "Tổng ngoại lệ" của kỳ đó, vừa so được tổng vừa so
              được cơ cấu từng nhóm trong cùng một hình. */}
          <h3>Số ngoại lệ theo loại</h3>
          <BarChart
            categories={[data.period.label, data.compare!.period.label]}
            stacked
            series={Object.keys(GROUP_COLORS).map((g) => ({
              label: exceptionGroupLabel(g),
              color: GROUP_COLORS[g],
              values: [
                data.by_group.find((x) => x.group === g)?.count ?? 0,
                data.compare!.by_group.find((x) => x.group === g)?.count ?? 0,
              ],
            }))}
            format={(v) => String(Math.round(v))}
          />
          <h3>Chi phí thực tế</h3>
          <BarChart
            categories={["Chi phí thực tế"]}
            series={comparePair(data, [a.total_actual_cost], [b.total_actual_cost])}
            format={vnd}
          />
          <h3>TB thời gian ra quyết định</h3>
          <BarChart
            categories={["Phút/ca"]}
            series={comparePair(data, [a.avg_resolution_minutes ?? 0], [b.avg_resolution_minutes ?? 0])}
            format={(v) => `${Math.round(v)}′`}
          />
          <h3>Các tỷ lệ (%)</h3>
          <BarChart
            categories={["Đúng hạn", "Sinh phương án", "Chính xác ước tính"]}
            series={comparePair(
              data,
              [(a.on_time_rate ?? 0) * 100, (a.ai_option_rate ?? 0) * 100, (a.cost_accuracy_rate ?? 0) * 100],
              [(b.on_time_rate ?? 0) * 100, (b.ai_option_rate ?? 0) * 100, (b.cost_accuracy_rate ?? 0) * 100],
            )}
            format={(v) => `${Math.round(v)}%`}
          />
        </div>
      )}

      {data && withBuckets && data.buckets.length > 0 && (
        <div className="card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
            <h2 style={{ margin: 0 }}>Chi tiết theo {subLabel}</h2>
            <label className="hint" style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <input type="checkbox" checked={splitByGroup} onChange={(e) => setSplitByGroup(e.target.checked)} />
              Tách theo loại ngoại lệ
            </label>
          </div>
          <h3>Số ngoại lệ</h3>
          <BarChart
            categories={data.buckets.map((x) => x.label)}
            stacked={splitByGroup}
            series={
              splitByGroup
                ? Object.keys(GROUP_COLORS).map((g) => ({
                    label: exceptionGroupLabel(g),
                    color: GROUP_COLORS[g],
                    values: data.buckets.map((x) => x.by_group[g] ?? 0),
                  }))
                : [{ label: "Số ngoại lệ", color: "#2563eb", values: data.buckets.map((x) => x.total) }]
            }
            format={(v) => String(Math.round(v))}
          />
          <h3>Chi phí thực tế</h3>
          <BarChart
            categories={data.buckets.map((x) => x.label)}
            series={[{ label: "Chi phí thực tế", color: "#0891b2", values: data.buckets.map((x) => x.actual_cost) }]}
            format={vnd}
          />
        </div>
      )}

      {data && (
        <div className="card">
          <h2 style={{ marginTop: 0 }}>Ngoại lệ theo loại</h2>
          {data.by_group.length === 0 && <p className="drill-muted">Kỳ này chưa có ngoại lệ nào.</p>}
          {data.by_group.length > 0 && (
            <table className="list-table">
              <thead>
                <tr>
                  <th>Nhóm ngoại lệ</th>
                  <th>Số lần</th>
                  {data.compare && <th>Kỳ B</th>}
                  {data.compare && <th>Chênh lệch</th>}
                  <th>Tổng chi phí thực tế</th>
                  <th>Thời gian xử lý (tổng · TB/ca)</th>
                </tr>
              </thead>
              <tbody>
                {data.by_group.map((g) => {
                  const bg = data.compare?.by_group.find((x) => x.group === g.group);
                  const open = openGroup === g.group;
                  return [
                    <tr key={g.group} onClick={() => setOpenGroup(open ? null : g.group)} style={{ cursor: "pointer" }}>
                      <td>
                        <span style={{ color: "#9ca3af" }}>{open ? "▾" : "▸"}</span> {exceptionGroupLabel(g.group)}
                      </td>
                      <td>{g.count}</td>
                      {data.compare && <td>{bg?.count ?? 0}</td>}
                      {data.compare && <td>{delta(g.count, bg?.count ?? 0)}</td>}
                      <td>{vnd(g.actual_cost)}</td>
                      <td>
                        {minutes(g.handling_minutes)}
                        <span className="drill-muted"> · {minutes(g.handling_minutes_avg)}</span>
                      </td>
                    </tr>,
                    open ? (
                      <tr key={g.group + "-sub"} className="drill-row">
                        <td colSpan={data.compare ? 6 : 4}>
                          <table className="list-table">
                            <tbody>
                              {g.sub_types.map((s) => (
                                <tr key={s.sub_type}>
                                  <td style={{ paddingLeft: 24 }}>{subTypeLabel(s.sub_type)}</td>
                                  <td>{s.count}</td>
                                  <td>{vnd(s.actual_cost)}</td>
                                  <td>
                                    {minutes(s.handling_minutes)}
                                    <span className="drill-muted"> · {minutes(s.handling_minutes_avg)}</span>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </td>
                      </tr>
                    ) : null,
                  ];
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

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
                    {/* Mục 6.2: đổi nhãn cho rõ đây là chỉ số KỸ THUẬT theo từng
                        lượt HTTP (tính cả retry/timeout), không phải tỷ lệ sinh
                        phương án thành công ở khối KPI. */}
                    <th>Tỷ lệ gọi API thành công</th>
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
            <p className="hint">
              Tỷ lệ này đếm theo TỪNG lượt gọi API (1 lần phân tích hỏng sinh tới 3 dòng lỗi do cơ chế thử lại), nên
              luôn thấp hơn "Tỷ lệ sinh phương án thành công" ở khối KPI — đó mới là con số nói lên dispatcher có
              phương án để chọn hay không.
            </p>
          </>
        )}
      </div>
    </div>
  );
}

function comparePair(data: SummaryResponse, aValues: number[], bValues: number[]): ChartSeries[] {
  return [
    { label: data.period.label, color: "#2563eb", values: aValues },
    { label: data.compare!.period.label, color: "#9ca3af", values: bValues },
  ];
}

/** Chênh lệch tuyệt đối giữa 2 kỳ, dạng "+3" / "-2". Không tô màu ở bảng theo
 *  loại: nhiều/ít ngoại lệ hơn không tự nó là tốt hay xấu. */
function delta(a: number, b: number) {
  const d = a - b;
  if (d === 0) return <span className="drill-muted">0</span>;
  return <span>{d > 0 ? `+${d}` : d}</span>;
}

function Stat({
  label,
  value,
  raw,
  compare,
  compareRaw,
  higherIsBetter,
  hint,
  hintTitle,
}: {
  label: string;
  value: string | number;
  raw?: number | null;
  compare?: number;
  compareRaw?: number | null;
  higherIsBetter?: boolean | null;
  hint?: string;
  /** Chú thích ĐẦY ĐỦ hiện khi rê chuột; `hint` chỉ là bản rút gọn đủ chỗ trong ô. */
  hintTitle?: string;
}) {
  const current = raw ?? (typeof value === "number" ? value : null);
  const previous = compareRaw ?? compare ?? null;
  let diffNode = null;
  if (current !== null && current !== undefined && previous !== null && previous !== undefined) {
    const diff = current - previous;
    const pctDiff = previous !== 0 ? (diff / Math.abs(previous)) * 100 : null;
    // Màu theo Ý NGHĨA chứ không theo dấu: chi phí và thời gian xử lý TĂNG là
    // xấu, còn các tỷ lệ chất lượng tăng là tốt. `higherIsBetter = null` -> chỉ
    // số trung tính (số ngoại lệ), không tô màu.
    const good = higherIsBetter === null || higherIsBetter === undefined ? null : higherIsBetter ? diff > 0 : diff < 0;
    const color = diff === 0 || good === null ? "#6b7280" : good ? "#16a34a" : "#dc2626";
    diffNode = (
      <div style={{ fontSize: 12, color }}>
        {diff === 0 ? "±0" : `${diff > 0 ? "▲" : "▼"} ${Math.abs(Math.round(diff * 100) / 100).toLocaleString("vi-VN")}`}
        {pctDiff !== null && diff !== 0 ? ` (${pctDiff > 0 ? "+" : ""}${pctDiff.toFixed(0)}%)` : ""}
      </div>
    );
  }
  return (
    <div>
      <div style={{ fontSize: 12, color: "#6b7280", textTransform: "uppercase" }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700 }}>{value}</div>
      {diffNode}
      {hint && (
        <div style={{ fontSize: 11, color: "#9ca3af" }} title={hintTitle ?? hint}>
          {hint}
        </div>
      )}
    </div>
  );
}
