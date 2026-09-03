import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiClient } from "../api/client";
import type { ExceptionSummary } from "../api/types";
import { subTypeLabel } from "../labels";

const SEVERITY_LABEL: Record<string, string> = { warning: "Cảnh báo", serious: "Nghiêm trọng", critical: "Khẩn cấp" };
const STATUS_LABEL: Record<string, string> = {
  pending: "Chờ xử lý",
  analyzing: "Đang phân tích",
  awaiting_decision: "Chờ xác nhận",
  resolved: "Đã xử lý",
};

export function Dashboard() {
  const navigate = useNavigate();
  const [statusFilter, setStatusFilter] = useState("");
  const [severityFilter, setSeverityFilter] = useState("");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["exceptions", statusFilter, severityFilter],
    queryFn: async () => {
      const params: Record<string, string> = {};
      if (statusFilter) params.status_filter = statusFilter;
      if (severityFilter) params.severity_filter = severityFilter;
      const res = await apiClient.get<ExceptionSummary[]>("/api/exceptions", { params });
      return res.data;
    },
    refetchInterval: 5000,
  });

  function openException(exc: ExceptionSummary) {
    if (exc.group_id) navigate(`/exception-groups/${exc.group_id}`);
    else navigate(`/exceptions/${exc.exception_id}`);
  }

  return (
    <div className="page">
      <h1>Danh sách ngoại lệ</h1>

      <div className="filters">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Tất cả trạng thái</option>
          <option value="pending">Chờ xử lý</option>
          <option value="analyzing">Đang phân tích</option>
          <option value="awaiting_decision">Chờ xác nhận</option>
          <option value="resolved">Đã xử lý</option>
        </select>
        <select value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)}>
          <option value="">Tất cả mức độ</option>
          <option value="warning">Cảnh báo</option>
          <option value="serious">Nghiêm trọng</option>
          <option value="critical">Khẩn cấp</option>
        </select>
      </div>

      <div className="card" style={{ padding: 0 }}>
        {isLoading && <div className="loading-spinner">Đang tải danh sách...</div>}
        {isError && <div className="error-banner" style={{ margin: 16 }}>Không tải được danh sách ngoại lệ.</div>}
        {data && data.length === 0 && <div className="loading-spinner">Chưa có ngoại lệ nào.</div>}
        {data && data.length > 0 && (
          <table className="list-table">
            <thead>
              <tr>
                <th>Xe</th>
                <th>Loại</th>
                <th>Khu vực</th>
                <th>Mức độ</th>
                <th>Trạng thái</th>
                <th>Nhóm</th>
              </tr>
            </thead>
            <tbody>
              {data.map((exc) => (
                <tr key={exc.exception_id} onClick={() => openException(exc)}>
                  <td>{exc.vehicle_id ?? "-"}</td>
                  <td>{subTypeLabel(exc.sub_type)}</td>
                  <td>{exc.area ?? "-"}</td>
                  <td>
                    {exc.severity && (
                      <span className={`badge badge-${exc.severity}`}>{SEVERITY_LABEL[exc.severity]}</span>
                    )}
                  </td>
                  <td>
                    <span className={`badge badge-${exc.status}`}>{STATUS_LABEL[exc.status]}</span>
                  </td>
                  <td>{exc.group_id ? "Nhóm ghép" : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
