import { useNavigate } from "react-router-dom";
import type { BlockingException } from "../api/types";
import { subTypeLabel } from "../labels";
import { EXCEPTION_STATUS_LABEL, SEVERITY_LABEL } from "../statusLabels";

// Mục "Ngoại lệ chưa hoàn thành" ở ĐẦU Dashboard (2026-09-04).
//
// Tách khỏi "Hoạt động hôm nay" vì 2 mục trả lời 2 câu hỏi khác nhau:
// - "Hoạt động hôm nay" = hôm nay chạy những gì (lọc theo shift_date).
// - Mục này = việc còn dở phải xử lý, BẤT KỂ thuộc ngày nào — ngoại lệ chờ
//   quyết định từ hôm kia mà lọc theo ngày hôm nay thì biến mất khỏi màn hình.
//
// Chuyến xuất hiện ở đây bị loại khỏi accordion "Hoạt động hôm nay"
// (`locked_schedule_ids`) để không hiện trùng; các chuyến khác của cùng xe vẫn
// hiện bình thường ở dưới.

const SHIFT_LABEL: Record<string, string> = { ca_sang: "Ca sáng", ca_chieu: "Ca chiều", ca_dem: "Ca đêm" };

function hhmm(t: string | null | undefined): string {
  if (!t) return "-";
  return t.length > 5 ? t.slice(0, 5) : t;
}

export function BlockingExceptions({ items }: { items: BlockingException[] }) {
  const navigate = useNavigate();

  if (items.length === 0) return null;

  function open(exc: BlockingException) {
    if (exc.group_id) navigate(`/exception-groups/${exc.group_id}`);
    else navigate(`/exceptions/${exc.exception_id}`);
  }

  return (
    <div className="card blocking-card">
      <div className="section-head">
        <h2 style={{ margin: 0 }}>Ngoại lệ chưa hoàn thành</h2>
        <span className="drill-muted">
          {items.length} ngoại lệ đang chờ xử lý (mọi ngày, không chỉ hôm nay)
        </span>
      </div>

      {items.map((exc) => (
        <div key={exc.exception_id} className="blocking-item" onClick={() => open(exc)} role="button" tabIndex={0}
          onKeyDown={(e) => { if (e.key === "Enter") open(exc); }}>
          <div className="blocking-item-head">
            <strong>Xe {exc.vehicle_id}</strong>
            {exc.driver_name && <span className="drill-muted"> · {exc.driver_name}</span>}
            {exc.severity && (
              <span className={`badge badge-${exc.severity}`}>{SEVERITY_LABEL[exc.severity] ?? exc.severity}</span>
            )}
            <span>{subTypeLabel(exc.sub_type)}</span>
            <span className={`badge badge-${exc.status}`}>
              {EXCEPTION_STATUS_LABEL[exc.status] ?? exc.status}
            </span>
            <span className="drill-muted">
              {exc.shift_date} · {SHIFT_LABEL[exc.shift_label] ?? exc.shift_label} · chuyến {exc.trip_sequence}
            </span>
          </div>

          {exc.orders.length === 0 ? (
            <div className="drill-muted">Chuyến này chưa có đơn nào.</div>
          ) : (
            <table className="list-table stops-mini-table">
              <thead>
                <tr>
                  <th>Đơn hàng bị ảnh hưởng</th>
                  <th>Địa chỉ</th>
                  <th>ETA</th>
                  <th>Hạn SLA</th>
                </tr>
              </thead>
              <tbody>
                {exc.orders.map((o) => (
                  <tr key={o.stop_id}>
                    <td>
                      #{o.stop_order} · <strong>{o.order_id}</strong>
                    </td>
                    <td>{o.address}</td>
                    <td>{hhmm(o.eta)}</td>
                    <td>{hhmm(o.sla_deadline)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ))}
    </div>
  );
}
