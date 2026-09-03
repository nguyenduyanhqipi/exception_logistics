import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { apiClient, apiErrorMessage } from "../api/client";
import type {
  DashboardOpenException,
  DashboardShift,
  DashboardToday,
  DashboardTrip,
  DashboardVehicle,
  Stop,
} from "../api/types";
import { ExceptionActionsMenu } from "../components/ExceptionActionsMenu";
import { subTypeLabel } from "../labels";
import { EXCEPTION_STATUS_LABEL as STATUS_LABEL, SEVERITY_LABEL } from "../statusLabels";

const SHIFT_LABEL: Record<string, string> = { ca_sang: "Ca sáng", ca_chieu: "Ca chiều", ca_dem: "Ca đêm" };
const PRIORITY_LABEL: Record<string, string> = { thuong: "Thường", vip: "VIP", hop_dong_phat: "Hợp đồng phạt" };

function shiftLabel(s: string) {
  return SHIFT_LABEL[s] ?? s;
}

/** "01:40:00" -> "01:40". Backend trả giờ dạng ISO đầy đủ sau khi 1 đơn được
 *  sửa qua `POST /api/schedules/{id}/stops` (pydantic `time` serialize kèm
 *  giây), trong khi dữ liệu nhập từ Excel là "01:40" — cắt về cùng 1 dạng để
 *  bảng không lúc thế này lúc thế kia. */
function hhmm(t: string | null | undefined): string {
  if (!t) return "-";
  return t.length > 5 ? t.slice(0, 5) : t;
}

/** Ngoại lệ đang mở gắn với 1 đơn cụ thể: cùng chuyến VÀ (khoanh trúng
 *  stop_id/order_id, HOẶC chưa khoanh vùng được điểm nào — `affected_stop_ids`
 *  rỗng nghĩa là ảnh hưởng cả chuyến, xem api/dashboard.py). */
function exceptionsForStop(vehicle: DashboardVehicle, trip: DashboardTrip, stop: Stop): DashboardOpenException[] {
  return vehicle.open_exceptions.filter(
    (e) =>
      e.schedule_id === trip.schedule_id &&
      (e.affected_stop_ids.length === 0 ||
        e.affected_stop_ids.includes(stop.stop_id) ||
        e.affected_order_ids.includes(stop.order_id)),
  );
}

// --- Tìm kiếm (việc 3) -------------------------------------------------------

interface VehicleMatch {
  vehicle: DashboardVehicle;
  /** 2 = khớp trực tiếp biển số/tài xế, 1 = khớp gián tiếp qua mã đơn hàng. */
  rank: number;
  /** Tỷ lệ độ dài chuỗi tìm / độ dài chuỗi khớp — dài hơn (gần đúng hơn) xếp trên. */
  closeness: number;
  /** Nhánh cần bung sẵn để thấy ngay đơn khớp (chỉ khi khớp qua mã đơn). */
  autoShift: string | null;
  autoTrip: string | null;
  autoStops: string[];
}

/** Lọc + xếp hạng xe theo chuỗi tìm kiếm.
 *
 * - So khớp substring, không phân biệt hoa/thường, trên biển số, tên tài xế và
 *   mã đơn hàng của MỌI đơn (kể cả đơn nằm trong chuyến đang thu gọn).
 * - Xe không khớp gì bị ẩn hẳn.
 * - Khớp trực tiếp (biển số/tài xế) xếp trên khớp gián tiếp qua đơn hàng; cùng
 *   loại thì chuỗi khớp càng sát (ít ký tự thừa) càng lên trên.
 */
function matchVehicles(vehicles: DashboardVehicle[], rawQuery: string): VehicleMatch[] {
  const q = rawQuery.trim().toLowerCase();
  if (!q) return vehicles.map((v) => ({ vehicle: v, rank: 0, closeness: 0, autoShift: null, autoTrip: null, autoStops: [] }));

  const out: VehicleMatch[] = [];
  for (const v of vehicles) {
    const plate = v.vehicle_id.toLowerCase();
    const driver = (v.driver_name ?? "").toLowerCase();
    const directHits = [plate, driver].filter((s) => s.includes(q));

    let autoShift: string | null = null;
    let autoTrip: string | null = null;
    const autoStops: string[] = [];
    let bestOrder = 0;
    for (const sh of v.shifts) {
      for (const trip of sh.trips) {
        for (const stop of trip.stops) {
          if (!stop.order_id?.toLowerCase().includes(q)) continue;
          autoStops.push(stop.stop_id);
          if (autoShift === null) {
            autoShift = sh.shift_label;
            autoTrip = trip.schedule_id;
          }
          bestOrder = Math.max(bestOrder, q.length / stop.order_id.length);
        }
      }
    }

    if (directHits.length > 0) {
      const closeness = Math.max(...directHits.map((s) => q.length / s.length));
      // Xe khớp trực tiếp thì KHÔNG tự bung — người dùng đang tìm cái xe, không
      // phải một đơn cụ thể bên trong nó.
      out.push({ vehicle: v, rank: 2, closeness, autoShift: null, autoTrip: null, autoStops: [] });
    } else if (autoStops.length > 0) {
      out.push({ vehicle: v, rank: 1, closeness: bestOrder, autoShift, autoTrip, autoStops });
    }
  }

  out.sort((a, b) => b.rank - a.rank || b.closeness - a.closeness || a.vehicle.vehicle_id.localeCompare(b.vehicle.vehicle_id));
  return out;
}

// -----------------------------------------------------------------------------

export function Dashboard() {
  const navigate = useNavigate();
  // Drill-down dạng accordion 4 tầng: xe -> ca -> chuyến -> đơn. Mỗi tầng chỉ
  // mở 1 mục tại một thời điểm để bảng không phình quá dài.
  const [openVehicle, setOpenVehicle] = useState<string | null>(null);
  const [openShift, setOpenShift] = useState<string | null>(null);
  const [openTrip, setOpenTrip] = useState<string | null>(null);
  const [openStop, setOpenStop] = useState<string | null>(null);
  const [query, setQuery] = useState("");

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

  function resetSearch() {
    // Xoá ô tìm kiếm -> về đúng Dashboard mặc định (thu gọn hết).
    setQuery("");
    setOpenVehicle(null);
    setOpenShift(null);
    setOpenTrip(null);
    setOpenStop(null);
  }

  const vehicles = data?.vehicles ?? [];
  const matches = useMemo(() => matchVehicles(vehicles, query), [vehicles, query]);
  const searching = query.trim().length > 0;

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

      <div className="search-bar">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Tìm theo biển số xe, tên tài xế hoặc mã đơn hàng..."
          aria-label="Tìm xe, tài xế hoặc đơn hàng"
        />
        {searching && (
          <button type="button" className="secondary" onClick={resetSearch}>
            Xoá tìm kiếm
          </button>
        )}
      </div>
      {searching && (
        <p className="drill-summary">
          {matches.length === 0
            ? `Không có xe/tài xế/đơn hàng nào khớp "${query.trim()}".`
            : `${matches.length} xe khớp "${query.trim()}".`}
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
        {data && vehicles.length > 0 && matches.length === 0 && (
          <div className="loading-spinner">Không tìm thấy kết quả nào. Xoá bớt ký tự để mở rộng tìm kiếm.</div>
        )}
        {data && matches.length > 0 && (
          <table className="list-table">
            <thead>
              <tr>
                <th style={{ width: 28 }}></th>
                <th>Xe</th>
                <th>Tài xế</th>
                <th>Đơn ca hiện tại</th>
                <th>Trạng thái</th>
                <th style={{ width: 150 }}>Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {matches.map((m) => (
                <VehicleRows
                  key={m.vehicle.vehicle_id}
                  vehicle={m.vehicle}
                  match={m}
                  expanded={openVehicle === m.vehicle.vehicle_id || m.autoStops.length > 0}
                  onToggle={() => toggleVehicle(m.vehicle.vehicle_id)}
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
                  onQuickCreate={() =>
                    navigate(`/exceptions/new?vehicle_id=${encodeURIComponent(m.vehicle.vehicle_id)}`)
                  }
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
  match: VehicleMatch;
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
  match,
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
  // Khi tìm thấy đơn hàng trong 1 chuyến đang thu gọn, nhánh xe -> ca -> chuyến
  // -> đơn đó tự bung để thấy ngay (việc 3), không bắt bấm mở từng cấp.
  const isShiftOpen = (label: string) => openShift === `${v.vehicle_id}::${label}` || match.autoShift === label;
  const isTripOpen = (scheduleId: string) => openTrip === scheduleId || match.autoTrip === scheduleId;
  const isStopOpen = (stopId: string) => openStop === stopId || match.autoStops.includes(stopId);

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
                <span key={exc.exception_id} className="drill-exc-row">
                  <button
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
                  <ExceptionActionsMenu
                    exceptionId={exc.exception_id}
                    status={exc.status}
                    subTypeLabel={subTypeLabel(exc.sub_type)}
                  />
                </span>
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
            {v.shifts.map((sh: DashboardShift) => {
              const shiftKey = `${v.vehicle_id}::${sh.shift_label}`;
              const shiftOpen = isShiftOpen(sh.shift_label);
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
                      const tripOpen = isTripOpen(trip.schedule_id);
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
                              {trip.planned_departure_time
                                ? ` · xuất phát ${hhmm(trip.planned_departure_time)}`
                                : ""}
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
                                const stopOpen = isStopOpen(stop.stop_id);
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
                                        · {stop.address} · ETA {hhmm(stop.eta)} · SLA {hhmm(stop.sla_deadline)}
                                      </span>
                                      {stopExc.length > 0 && (
                                        <span className="badge badge-critical" style={{ marginLeft: 8 }}>
                                          Có ngoại lệ
                                        </span>
                                      )}
                                    </button>

                                    {stopOpen && (
                                      <StopDetail
                                        scheduleId={trip.schedule_id}
                                        stop={stop}
                                        exceptions={stopExc}
                                        onOpenException={onOpenException}
                                      />
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

interface StopDetailProps {
  scheduleId: string;
  stop: Stop;
  exceptions: DashboardOpenException[];
  onOpenException: (exc: DashboardOpenException) => void;
}

function StopDetail({ scheduleId, stop, exceptions, onOpenException }: StopDetailProps) {
  const [editing, setEditing] = useState(false);

  if (editing) {
    return <StopEditForm scheduleId={scheduleId} stop={stop} onDone={() => setEditing(false)} />;
  }

  return (
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
          <dd>{hhmm(stop.eta)}</dd>
        </div>
        <div>
          <dt>Hạn SLA</dt>
          <dd>{hhmm(stop.sla_deadline)}</dd>
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

      <div style={{ marginTop: 12 }}>
        <button type="button" className="secondary" onClick={() => setEditing(true)}>
          Sửa đơn hàng
        </button>
      </div>

      {exceptions.length > 0 && (
        <div className="drill-stop-exc">
          <div className="drill-muted" style={{ marginBottom: 6 }}>
            Ngoại lệ đang mở gắn với đơn này:
          </div>
          {exceptions.map((exc) => (
            <span key={exc.exception_id} className="drill-exc-row">
              <button type="button" className="drill-exc-chip" onClick={() => onOpenException(exc)}>
                {exc.severity && <span className={`badge badge-${exc.severity}`}>{SEVERITY_LABEL[exc.severity]}</span>}
                <span>{subTypeLabel(exc.sub_type)}</span>
                <span className="drill-muted">({STATUS_LABEL[exc.status] ?? exc.status}) — xem/xử lý</span>
              </button>
              <ExceptionActionsMenu
                exceptionId={exc.exception_id}
                status={exc.status}
                subTypeLabel={subTypeLabel(exc.sub_type)}
              />
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/** Sửa 1 đơn hàng đã nhập sai (việc 2).
 *
 * Gọi lại đúng endpoint có sẵn `POST /api/schedules/{id}/stops` — khớp theo
 * `stop_order` nên là UPDATE tại chỗ, không sinh dòng mới.
 *
 * QUAN TRỌNG: backend dựng lại stop TỪ ĐẦU theo payload (`_stop_to_dict`),
 * field nào không gửi coi như bị xoá. Nên payload phải mang theo CẢ những
 * field form này không hiển thị (sla_penalty, cargo_type, lat/lng,
 * loading_duration_min) lấy nguyên từ stop hiện tại.
 */
function StopEditForm({ scheduleId, stop, onDone }: { scheduleId: string; stop: Stop; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    stop_type: stop.stop_type,
    address: stop.address,
    area: stop.area,
    order_id: stop.order_id,
    customer_name: stop.customer_name,
    customer_phone: stop.customer_phone,
    eta: hhmm(stop.eta),
    sla_deadline: hhmm(stop.sla_deadline),
    priority_tier: stop.priority_tier,
    volume_kg: stop.volume_kg != null ? String(stop.volume_kg) : "",
    notes: stop.notes ?? "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function set(field: keyof typeof form, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await apiClient.post(`/api/schedules/${scheduleId}/stops`, {
        stop_order: stop.stop_order,
        stop_type: form.stop_type,
        address: form.address,
        area: form.area,
        order_id: form.order_id,
        customer_name: form.customer_name,
        customer_phone: form.customer_phone,
        eta: form.eta,
        sla_deadline: form.sla_deadline,
        priority_tier: form.priority_tier,
        volume_kg: form.volume_kg === "" ? null : Number(form.volume_kg),
        notes: form.notes || null,
        // Giữ nguyên các field form không hiển thị (xem ghi chú ở đầu hàm).
        loading_duration_min: stop.loading_duration_min ?? null,
        sla_penalty: stop.sla_penalty ?? null,
        cargo_type: stop.cargo_type ?? "normal",
        lat: stop.lat ?? null,
        lng: stop.lng ?? null,
      });
      await queryClient.invalidateQueries({ queryKey: ["dashboard-today"] });
      await queryClient.invalidateQueries({ queryKey: ["schedules"] });
      onDone();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="drill-detail" onSubmit={handleSubmit}>
      {error && <div className="error-banner">{error}</div>}
      <div className="drill-muted" style={{ marginBottom: 10 }}>
        Sửa đơn #{stop.stop_order} của chuyến này. Thứ tự điểm giao (#{stop.stop_order}) không đổi.
      </div>
      <div className="drill-edit-grid">
        <div className="form-field">
          <label>Mã đơn hàng</label>
          <input value={form.order_id} onChange={(e) => set("order_id", e.target.value)} required />
        </div>
        <div className="form-field">
          <label>Loại điểm</label>
          <select value={form.stop_type} onChange={(e) => set("stop_type", e.target.value)}>
            <option value="giao_hang">Giao hàng</option>
            <option value="lay_hang">Lấy hàng</option>
          </select>
        </div>
        <div className="form-field">
          <label>Địa chỉ</label>
          <input value={form.address} onChange={(e) => set("address", e.target.value)} required />
        </div>
        <div className="form-field">
          <label>Khu vực</label>
          <input value={form.area} onChange={(e) => set("area", e.target.value)} required />
        </div>
        <div className="form-field">
          <label>Tên khách hàng</label>
          <input value={form.customer_name} onChange={(e) => set("customer_name", e.target.value)} required />
        </div>
        <div className="form-field">
          <label>SĐT khách</label>
          <input value={form.customer_phone} onChange={(e) => set("customer_phone", e.target.value)} required />
        </div>
        <div className="form-field">
          <label>ETA</label>
          <input type="time" value={form.eta} onChange={(e) => set("eta", e.target.value)} required />
        </div>
        <div className="form-field">
          <label>Hạn SLA</label>
          <input type="time" value={form.sla_deadline} onChange={(e) => set("sla_deadline", e.target.value)} required />
        </div>
        <div className="form-field">
          <label>Mức ưu tiên</label>
          <select value={form.priority_tier} onChange={(e) => set("priority_tier", e.target.value)}>
            <option value="thuong">Thường</option>
            <option value="vip">VIP</option>
            <option value="hop_dong_phat">Hợp đồng phạt</option>
          </select>
        </div>
        <div className="form-field">
          <label>Khối lượng (kg)</label>
          <input type="number" min={0} value={form.volume_kg} onChange={(e) => set("volume_kg", e.target.value)} />
        </div>
        <div className="form-field" style={{ gridColumn: "1 / -1" }}>
          <label>Ghi chú</label>
          <input value={form.notes} onChange={(e) => set("notes", e.target.value)} />
        </div>
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
        <button type="submit" className="primary" disabled={saving}>
          {saving ? "Đang lưu..." : "Lưu đơn hàng"}
        </button>
        <button type="button" className="secondary" disabled={saving} onClick={onDone}>
          Hủy
        </button>
      </div>
    </form>
  );
}
