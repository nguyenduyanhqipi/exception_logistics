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

// Bảng danh sách phẳng CHUYỂN NGUYÊN từ Dashboard cũ sang đây (cùng cột, cùng
// bộ lọc), chỉ khác phạm vi: luôn ghim `status_filter=resolved`. Ngoại lệ đang
// mở nay thuộc về Dashboard "hoạt động hôm nay", không lặp lại ở đây.
export function History() {
  const navigate = useNavigate();
  const [severityFilter, setSeverityFilter] = useState("");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["exceptions-history", severityFilter],
    queryFn: async () => {
      const params: Record<string, string> = { status_filter: "resolved" };
      if (severityFilter) params.severity_filter = severityFilter;
      const res = await apiClient.get<ExceptionSummary[]>("/api/exceptions", { params });
      return res.data;
    },
    refetchInterval: 15000,
  });

  function openException(exc: ExceptionSummary) {
    if (exc.group_id) navigate(`/exception-groups/${exc.group_id}`);
    else navigate(`/exceptions/${exc.exception_id}`);
  }

  return (
    <div className="page">
      <h1>Lịch sử ngoại lệ đã xử lý</h1>

      <div className="filters">
        {/* Bộ lọc trạng thái giữ lại đúng vị trí cũ nhưng khoá cứng ở "Đã xử
            lý" — trang này theo định nghĩa chỉ chứa ngoại lệ đã xử lý xong. */}
        <select value="resolved" disabled title="Trang Lịch sử chỉ hiện ngoại lệ đã xử lý">
          <option value="resolved">Trạng thái: Đã xử lý</option>
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
        {data && data.length === 0 && <div className="loading-spinner">Chưa có ngoại lệ nào đã xử lý.</div>}
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
