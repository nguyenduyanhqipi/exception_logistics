import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiClient } from "../api/client";
import type {
  DashboardOpenException,
  DashboardToday,
  DashboardTrip,
  DashboardVehicle,
  Stop,
} from "../api/types";
import { subTypeLabel } from "../labels";

const SEVERITY_LABEL: Record<string, string> = { warning: "Cảnh báo", serious: "Nghiêm trọng", critical: "Khẩn cấp" };
const STATUS_LABEL: Record<string, string> = {
  pending: "Chờ xử lý",
  analyzing: "Đang phân tích",
  awaiting_decision: "Chờ xác nhận",
  resolved: "Đã xử lý",
};
const SHIFT_LABEL: Record<string, string> = { ca_sang: "Ca sáng", ca_chieu: "Ca chiều", ca_dem: "Ca đêm" };
const PRIORITY_LABEL: Record<string, string> = { thuong: "Thường", vip: "VIP", hop_dong_phat: "Hợp đồng phạt" };

function shiftLabel(s: string) {
  return SHIFT_LABEL[s] ?? s;
}

// Ngoại lệ đang mở gắn với 1 đơn cụ thể: cùng chuyến VÀ (khoanh trúng
// stop_id/order_id, HOẶC chưa khoanh vùng được điểm nào — `affected_stop_ids`
// rỗng nghĩa là ảnh hưởng cả chuyến, xem api/dashboard.py).
function exceptionsForStop(vehicle: DashboardVehicle, trip: DashboardTrip, stop: Stop): DashboardOpenException[] {
  return vehicle.open_exceptions.filter(
    (e) =>
      e.schedule_id === trip.schedule_id &&
      (e.affected_stop_ids.length === 0 ||
        e.affected_stop_ids.includes(stop.stop_id) ||
        e.affected_order_ids.includes(stop.order_id)),
  );
}

export function Dashboard() {
  const navigate = useNavigate();
  // Drill-down dạng accordion 4 tầng: xe -> ca -> chuyến -> đơn. Mỗi tầng chỉ
  // mở 1 mục tại một thời điểm để bảng không phình quá dài.
  const [openVehicle, setOpenVehicle] = useState<string | null>(null);
  const [openShift, setOpenShift] = useState<string | null>(null);
  const [openTrip, setOpenTrip] = useState<string | null>(null);
  const [openStop, setOpenStop] = useState<string | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["dashboard-today"],
    queryFn: async () => (await apiClient.get<DashboardToday>("/api/dashboard/today")).data,
    refetchInterval: 5000,
  });

  function openException(exc: DashboardOpenException) {
    if (exc.group_id) navigate(`/exception-groups/${exc.group_id}`);
    else navigate(`/exceptions/${exc.exception_id}`);
  }

  function toggleVehicle(vehicleId: string) {
    const next = openVehicle === vehicleId ? null : vehicleId;
    setOpenVehicle(next);
    setOpenShift(null);
    setOpenTrip(null);
    setOpenStop(null);
  }

  const vehicles = data?.vehicles ?? [];
  const totalOpen = vehicles.reduce((n, v) => n + v.open_exceptions.length, 0);
  const totalOrders = vehicles.reduce((n, v) => n + v.today_order_count, 0);

  return (
    <div className="page">
      <h1>Hoạt động hôm nay</h1>
      {data && (
        <p className="drill-summary">
          Ngày {data.shift_date} · Ca hiện tại: <strong>{shiftLabel(data.current_shift_label)}</strong> ·{" "}
          {vehicles.length} xe · {totalOrders} đơn · {totalOpen} ngoại lệ đang mở
        </p>
      )}

      <div className="card" style={{ padding: 0 }}>
        {isLoading && <div className="loading-spinner">Đang tải hoạt động hôm nay...</div>}
        {isError && <div className="error-banner" style={{ margin: 16 }}>Không tải được hoạt động hôm nay.</div>}
        {data && vehicles.length === 0 && (
          <div className="loading-spinner">
            Hôm nay chưa có xe nào có kế hoạch chạy. Nhập kế hoạch ở mục "Nhập kế hoạch" hoặc "Upload Excel".
          </div>
        )}
        {data && vehicles.length > 0 && (
          <table className="list-table">
            <thead>
              <tr>
                <th style={{ width: 28 }}></th>
                <th>Xe</th>
                <th>Tài xế</th>
                <th>Đơn ca hiện tại</th>
                <th>Trạng thái</th>
                <th style={{ width: 140 }}>Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {vehicles.map((v) => (
                <VehicleRows
                  key={v.vehicle_id}
                  vehicle={v}
                  expanded={openVehicle === v.vehicle_id}
                  onToggle={() => toggleVehicle(v.vehicle_id)}
                  openShift={openShift}
                  setOpenShift={(s) => {
                    setOpenShift(s);
                    setOpenTrip(null);
                    setOpenStop(null);
                  }}
                  openTrip={openTrip}
                  setOpenTrip={(t) => {
                    setOpenTrip(t);
                    setOpenStop(null);
                  }}
                  openStop={openStop}
                  setOpenStop={setOpenStop}
                  onOpenException={openException}
                  onQuickCreate={() => navigate(`/exceptions/new?vehicle_id=${encodeURIComponent(v.vehicle_id)}`)}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

interface VehicleRowsProps {
  vehicle: DashboardVehicle;
  expanded: boolean;
  onToggle: () => void;
  openShift: string | null;
  setOpenShift: (s: string | null) => void;
  openTrip: string | null;
  setOpenTrip: (t: string | null) => void;
  openStop: string | null;
  setOpenStop: (s: string | null) => void;
  onOpenException: (exc: DashboardOpenException) => void;
  onQuickCreate: () => void;
}

function VehicleRows({
  vehicle: v,
  expanded,
  onToggle,
  openShift,
  setOpenShift,
  openTrip,
  setOpenTrip,
  openStop,
  setOpenStop,
  onOpenException,
  onQuickCreate,
}: VehicleRowsProps) {
  return (
    <>
      <tr onClick={onToggle}>
        <td style={{ color: "#9ca3af" }}>{expanded ? "▾" : "▸"}</td>
        <td>
          <strong>{v.vehicle_id}</strong>
          {v.vehicle_type && <span className="drill-muted"> · {v.vehicle_type}</span>}
        </td>
        <td>
          {v.driver_name ?? "-"}
          {v.driver_phone && <span className="drill-muted"> · {v.driver_phone}</span>}
        </td>
        <td>
          {v.current_shift_order_count} đơn
          <span className="drill-muted"> (hôm nay: {v.today_order_count})</span>
        </td>
        <td>
          {v.open_exceptions.length === 0 ? (
            <span className="badge badge-ok">Ổn định</span>
          ) : (
            <div className="drill-exc-list">
              {v.open_exceptions.map((exc) => (
                <button
                  key={exc.exception_id}
                  type="button"
                  className="drill-exc-chip"
                  onClick={(e) => {
                    e.stopPropagation();
                    onOpenException(exc);
                  }}
                >
                  {exc.severity && (
                    <span className={`badge badge-${exc.severity}`}>{SEVERITY_LABEL[exc.severity]}</span>
                  )}
                  <span>{subTypeLabel(exc.sub_type)}</span>
                  <span className="drill-muted">({STATUS_LABEL[exc.status] ?? exc.status})</span>
                </button>
              ))}
            </div>
          )}
        </td>
        <td>
          <button
            type="button"
            className="primary drill-quick-btn"
            onClick={(e) => {
              e.stopPropagation();
              onQuickCreate();
            }}
          >
            + Ngoại lệ
          </button>
        </td>
      </tr>

      {expanded && (
        <tr className="drill-row">
          <td colSpan={6}>
            {v.shifts.length === 0 && <div className="drill-empty">Xe này hôm nay không có ca chạy nào.</div>}
            {v.shifts.map((sh) => {
              const shiftKey = `${v.vehicle_id}::${sh.shift_label}`;
              const shiftOpen = openShift === shiftKey;
              return (
                <div className="drill-level" key={shiftKey}>
                  <button
                    type="button"
                    className="drill-head"
                    onClick={() => setOpenShift(shiftOpen ? null : shiftKey)}
                  >
                    {shiftOpen ? "▾" : "▸"} {shiftLabel(sh.shift_label)}
                    <span className="drill-muted">
                      {" "}
                      · {sh.trip_count} chuyến · {sh.order_count} đơn
                    </span>
                  </button>

                  {shiftOpen &&
                    sh.trips.map((trip) => {
                      const tripOpen = openTrip === trip.schedule_id;
                      const tripExc = v.open_exceptions.filter((e) => e.schedule_id === trip.schedule_id);
                      return (
                        <div className="drill-level" key={trip.schedule_id}>
                          <button
                            type="button"
                            className="drill-head"
                            onClick={() => setOpenTrip(tripOpen ? null : trip.schedule_id)}
                          >
                            {tripOpen ? "▾" : "▸"} Chuyến {trip.trip_sequence}
                            <span className="drill-muted">
                              {" "}
                              · {trip.order_count} đơn
                              {trip.planned_departure_time ? ` · xuất phát ${trip.planned_departure_time}` : ""}
                            </span>
                            {tripExc.length > 0 && (
                              <span className="badge badge-pending" style={{ marginLeft: 8 }}>
                                {tripExc.length} ngoại lệ mở
                              </span>
                            )}
                          </button>

                          {tripOpen && (
                            <div className="drill-level">
                              {trip.stops.length === 0 && (
                                <div className="drill-empty">Chuyến này chưa có đơn nào.</div>
                              )}
                              {trip.stops.map((stop) => {
                                const stopOpen = openStop === stop.stop_id;
                                const stopExc = exceptionsForStop(v, trip, stop);
                                return (
                                  <div key={stop.stop_id}>
                                    <button
                                      type="button"
                                      className="drill-head"
                                      onClick={() => setOpenStop(stopOpen ? null : stop.stop_id)}
                                    >
                                      {stopOpen ? "▾" : "▸"} #{stop.stop_order} · {stop.order_id}
                                      <span className="drill-muted">
                                        {" "}
                                        · {stop.address} · ETA {stop.eta} · SLA {stop.sla_deadline}
                                      </span>
                                      {stopExc.length > 0 && (
                                        <span className="badge badge-critical" style={{ marginLeft: 8 }}>
                                          Có ngoại lệ
                                        </span>
                                      )}
                                    </button>

                                    {stopOpen && (
                                      <div className="drill-detail">
                                        <dl className="drill-dl">
                                          <div>
                                            <dt>Mã đơn</dt>
                                            <dd>{stop.order_id}</dd>
                                          </div>
                                          <div>
                                            <dt>Loại điểm</dt>
                                            <dd>{stop.stop_type === "lay_hang" ? "Lấy hàng" : "Giao hàng"}</dd>
                                          </div>
                                          <div>
                                            <dt>Địa chỉ</dt>
                                            <dd>{stop.address}</dd>
                                          </div>
                                          <div>
                                            <dt>Khu vực</dt>
                                            <dd>{stop.area}</dd>
                                          </div>
                                          <div>
                                            <dt>Khách hàng</dt>
                                            <dd>
                                              {stop.customer_name}
                                              {stop.customer_phone ? ` · ${stop.customer_phone}` : ""}
                                            </dd>
                                          </div>
                                          <div>
                                            <dt>ETA</dt>
                                            <dd>{stop.eta}</dd>
                                          </div>
                                          <div>
                                            <dt>Hạn SLA</dt>
                                            <dd>{stop.sla_deadline}</dd>
                                          </div>
                                          <div>
                                            <dt>Ưu tiên</dt>
                                            <dd>{PRIORITY_LABEL[stop.priority_tier] ?? stop.priority_tier}</dd>
                                          </div>
                                          <div>
                                            <dt>Khối lượng</dt>
                                            <dd>{stop.volume_kg != null ? `${stop.volume_kg} kg` : "-"}</dd>
                                          </div>
                                          <div>
                                            <dt>Ghi chú</dt>
                                            <dd>{stop.notes || "-"}</dd>
                                          </div>
                                        </dl>

                                        {stopExc.length > 0 && (
                                          <div className="drill-stop-exc">
                                            <div className="drill-muted" style={{ marginBottom: 6 }}>
                                              Ngoại lệ đang mở gắn với đơn này:
                                            </div>
                                            {stopExc.map((exc) => (
                                              <button
                                                key={exc.exception_id}
                                                type="button"
                                                className="drill-exc-chip"
                                                onClick={() => onOpenException(exc)}
                                              >
                                                {exc.severity && (
                                                  <span className={`badge badge-${exc.severity}`}>
                                                    {SEVERITY_LABEL[exc.severity]}
                                                  </span>
                                                )}
                                                <span>{subTypeLabel(exc.sub_type)}</span>
                                                <span className="drill-muted">
                                                  ({STATUS_LABEL[exc.status] ?? exc.status}) — xem/xử lý
                                                </span>
                                              </button>
                                            ))}
                                          </div>
                                        )}
                                      </div>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      );
                    })}
                </div>
              );
            })}
          </td>
        </tr>
      )}
    </>
  );
}
