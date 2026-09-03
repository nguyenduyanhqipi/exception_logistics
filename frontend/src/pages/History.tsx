import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiClient } from "../api/client";
import { ExceptionActionsMenu } from "../components/ExceptionActionsMenu";
import type { ExceptionSummary } from "../api/types";
import { subTypeLabel } from "../labels";
import { EXCEPTION_STATUS_LABEL as STATUS_LABEL, SEVERITY_LABEL } from "../statusLabels";

// Bảng danh sách phẳng CHUYỂN NGUYÊN từ Dashboard cũ sang đây (cùng cột, cùng
// bộ lọc). Phạm vi: mọi ngoại lệ ĐÃ CÓ QUYẾT ĐỊNH — gồm "awaiting_outcome"
// (đã chốt phương án, chưa nhập kết quả) và "resolved" (đã có kết quả). Từ
// 2026-09-04 hai trạng thái này tách nhau (xem backend/api/decisions.py) nên
// trang này không còn chỉ có mỗi "resolved".
const HISTORY_STATUSES = "awaiting_outcome,resolved";

export function History() {
  const navigate = useNavigate();
  const [severityFilter, setSeverityFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["exceptions-history", severityFilter, statusFilter],
    queryFn: async () => {
      const params: Record<string, string> = { status_filter: statusFilter || HISTORY_STATUSES };
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
      <h1>Lịch sử ngoại lệ đã quyết định</h1>

      <div className="filters">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Tất cả (đã quyết định)</option>
          <option value="awaiting_outcome">Chưa có kết quả</option>
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
        {data && data.length === 0 && <div className="loading-spinner">Chưa có ngoại lệ nào đã quyết định.</div>}
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
                <th style={{ width: 90 }}>Thao tác</th>
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
                  <td>
                    {/* Menu sửa/xoá tự ẩn khi ngoại lệ đã có quyết định — mọi
                        dòng ở trang này đều thế, nên thực tế chỉ hiện chú
                        thích bên dưới. */}
                    <ExceptionActionsMenu
                      exceptionId={exc.exception_id}
                      status={exc.status}
                      subTypeLabel={subTypeLabel(exc.sub_type)}
                    />
                    <span className="drill-muted">Đã chốt</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
