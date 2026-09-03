import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { apiClient, apiErrorMessage } from "../api/client";
import { ConfirmDialog } from "../components/ConfirmDialog";

interface Vehicle {
  vehicle_id: string;
  driver_name: string;
  status: string;
}

interface StopForm {
  stop_order: number;
  stop_type: string;
  address: string;
  area: string;
  order_id: string;
  customer_name: string;
  customer_phone: string;
  eta: string;
  sla_deadline: string;
  priority_tier: string;
}

function emptyStop(order: number): StopForm {
  return { stop_order: order, stop_type: "giao_hang", address: "", area: "", order_id: "", customer_name: "", customer_phone: "", eta: "", sla_deadline: "", priority_tier: "thuong" };
}

export function ScheduleInput() {
  const navigate = useNavigate();
  const { data: vehicles } = useQuery({
    queryKey: ["vehicles"],
    queryFn: async () => (await apiClient.get<Vehicle[]>("/api/vehicles")).data,
  });

  const [vehicleId, setVehicleId] = useState("");
  const [shiftDate, setShiftDate] = useState("");
  const [shiftLabel, setShiftLabel] = useState("ca_sang");
  const [tripSequence, setTripSequence] = useState(1);
  const [depotArrivalTime, setDepotArrivalTime] = useState("");
  const [depotLoadingDurationMin, setDepotLoadingDurationMin] = useState("");
  const [stops, setStops] = useState<StopForm[]>([emptyStop(1)]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function updateStop(index: number, field: keyof StopForm, value: string | number) {
    setStops((prev) => prev.map((s, i) => (i === index ? { ...s, [field]: value } : s)));
  }

  function addStop() {
    setStops((prev) => [...prev, emptyStop(prev.length + 1)]);
  }

  function removeStop(index: number) {
    setStops((prev) => prev.filter((_, i) => i !== index).map((s, i) => ({ ...s, stop_order: i + 1 })));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await apiClient.post("/api/schedules", {
        vehicle_id: vehicleId,
        shift_date: shiftDate,
        shift_label: shiftLabel,
        trip_sequence: tripSequence,
        depot_arrival_time: depotArrivalTime || null,
        depot_loading_duration_min: depotLoadingDurationMin ? Number(depotLoadingDurationMin) : null,
        stops,
      });
      navigate("/");
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page">
      <h1>Nhập kế hoạch chuyến mới</h1>
      <DeleteScheduleByShift />
      <form onSubmit={handleSubmit} className="card">
        {error && <div className="error-banner">{error}</div>}

        <div style={{ display: "flex", gap: 16 }}>
          <div className="form-field" style={{ flex: 1 }}>
            <label>Xe</label>
            <select value={vehicleId} onChange={(e) => setVehicleId(e.target.value)} required>
              <option value="">-- Chọn xe --</option>
              {vehicles?.filter((v) => v.status === "active").map((v) => (
                <option key={v.vehicle_id} value={v.vehicle_id}>
                  {v.vehicle_id} — {v.driver_name}
                </option>
              ))}
            </select>
          </div>
          <div className="form-field" style={{ flex: 1 }}>
            <label>Ngày chạy</label>
            <input type="date" value={shiftDate} onChange={(e) => setShiftDate(e.target.value)} required />
          </div>
          <div className="form-field" style={{ flex: 1 }}>
            <label>Ca</label>
            <select value={shiftLabel} onChange={(e) => setShiftLabel(e.target.value)}>
              <option value="ca_sang">Ca sáng</option>
              <option value="ca_chieu">Ca chiều</option>
              <option value="ca_dem">Ca đêm</option>
            </select>
          </div>
          <div className="form-field" style={{ width: 100 }}>
            <label>Chuyến số</label>
            <input type="number" min={1} value={tripSequence} onChange={(e) => setTripSequence(Number(e.target.value))} />
          </div>
        </div>

        <div style={{ display: "flex", gap: 16 }}>
          <div className="form-field" style={{ flex: 1 }}>
            <label>Giờ có mặt tại kho (tuỳ chọn)</label>
            <input type="time" value={depotArrivalTime} onChange={(e) => setDepotArrivalTime(e.target.value)} />
          </div>
          <div className="form-field" style={{ flex: 1 }}>
            <label>Phút bốc hàng dự kiến tại kho (tuỳ chọn)</label>
            <input type="number" min={0} value={depotLoadingDurationMin} onChange={(e) => setDepotLoadingDurationMin(e.target.value)} />
          </div>
        </div>

        <h2>Điểm giao ({stops.length})</h2>
        {stops.map((stop, i) => (
          <div key={i} className="card" style={{ background: "#f9fafb" }}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <strong>Điểm #{stop.stop_order}</strong>
              {stops.length > 1 && (
                <button type="button" className="secondary" onClick={() => removeStop(i)}>
                  Xoá
                </button>
              )}
            </div>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              <div className="form-field" style={{ flex: "1 1 140px" }}>
                <label>Loại điểm</label>
                <select value={stop.stop_type} onChange={(e) => updateStop(i, "stop_type", e.target.value)}>
                  <option value="giao_hang">Giao hàng</option>
                  <option value="lay_hang">Lấy hàng</option>
                </select>
              </div>
              <div className="form-field" style={{ flex: "2 1 220px" }}>
                <label>Địa chỉ</label>
                <input value={stop.address} onChange={(e) => updateStop(i, "address", e.target.value)} required />
              </div>
              <div className="form-field" style={{ flex: "1 1 140px" }}>
                <label>Khu vực</label>
                <input value={stop.area} onChange={(e) => updateStop(i, "area", e.target.value)} required />
              </div>
              <div className="form-field" style={{ flex: "1 1 140px" }}>
                <label>Mã đơn hàng</label>
                <input value={stop.order_id} onChange={(e) => updateStop(i, "order_id", e.target.value)} required />
              </div>
              <div className="form-field" style={{ flex: "1 1 140px" }}>
                <label>Tên khách hàng</label>
                <input value={stop.customer_name} onChange={(e) => updateStop(i, "customer_name", e.target.value)} required />
              </div>
              <div className="form-field" style={{ flex: "1 1 140px" }}>
                <label>SĐT khách</label>
                <input value={stop.customer_phone} onChange={(e) => updateStop(i, "customer_phone", e.target.value)} required />
              </div>
              <div className="form-field" style={{ flex: "1 1 100px" }}>
                <label>ETA</label>
                <input type="time" value={stop.eta} onChange={(e) => updateStop(i, "eta", e.target.value)} required />
              </div>
              <div className="form-field" style={{ flex: "1 1 100px" }}>
                <label>Hạn SLA</label>
                <input type="time" value={stop.sla_deadline} onChange={(e) => updateStop(i, "sla_deadline", e.target.value)} required />
              </div>
              <div className="form-field" style={{ flex: "1 1 140px" }}>
                <label>Mức ưu tiên</label>
                <select value={stop.priority_tier} onChange={(e) => updateStop(i, "priority_tier", e.target.value)}>
                  <option value="thuong">Thường</option>
                  <option value="vip">VIP</option>
                  <option value="hop_dong_phat">Hợp đồng phạt</option>
                </select>
              </div>
            </div>
          </div>
        ))}
        <button type="button" className="secondary" onClick={addStop}>
          + Thêm điểm giao
        </button>

        <div style={{ marginTop: 16 }}>
          <button type="submit" className="primary" disabled={submitting || !vehicleId || !shiftDate}>
            {submitting ? "Đang lưu..." : "Tạo chuyến"}
          </button>
        </div>
      </form>
    </div>
  );
}


const SHIFT_OPTIONS = [
  { value: "ca_sang", label: "Ca sáng" },
  { value: "ca_chieu", label: "Ca chiều" },
  { value: "ca_dem", label: "Ca đêm" },
];

/** Xoá TOÀN BỘ kế hoạch của 1 ngày + 1 ca (việc 4).
 *
 * Backend (`DELETE /api/schedules?shift_date=&shift_label=`) chặn nếu còn
 * ngoại lệ trỏ tới bất kỳ chuyến nào trong nhóm — thông báo lỗi 409 trả về đã
 * ghi rõ số lượng và cách xử lý, hiển thị nguyên văn cho người dùng.
 */
function DeleteScheduleByShift() {
  const queryClient = useQueryClient();
  const [shiftDate, setShiftDate] = useState("");
  const [shiftLabel, setShiftLabel] = useState("ca_sang");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  const shiftText = SHIFT_OPTIONS.find((o) => o.value === shiftLabel)?.label ?? shiftLabel;

  async function handleDelete() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await apiClient.delete("/api/schedules", {
        params: { shift_date: shiftDate, shift_label: shiftLabel },
      });
      setConfirming(false);
      const vehicles: string[] = res.data.vehicles ?? [];
      setResult(
        `Đã xoá ${res.data.deleted} chuyến của ngày ${shiftDate} ${shiftText}` +
          (vehicles.length > 0 ? ` (xe: ${vehicles.join(", ")}).` : "."),
      );
      queryClient.invalidateQueries({ queryKey: ["schedules"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-today"] });
    } catch (err) {
      setConfirming(false);
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h2 style={{ marginTop: 0 }}>Xoá kế hoạch theo ngày + ca</h2>
      <p className="drill-muted" style={{ marginTop: 0 }}>
        Xoá toàn bộ chuyến của mọi xe trong đúng ngày và ca đã chọn. Không xoá được nếu còn ngoại lệ đang gắn với
        các chuyến đó.
      </p>
      {error && <div className="error-banner">{error}</div>}
      {result && <div className="success-banner">{result}</div>}
      <div style={{ display: "flex", gap: 16, alignItems: "flex-end", flexWrap: "wrap" }}>
        <div className="form-field" style={{ flex: "1 1 180px", marginBottom: 0 }}>
          <label>Ngày cần xoá</label>
          <input type="date" value={shiftDate} onChange={(e) => setShiftDate(e.target.value)} />
        </div>
        <div className="form-field" style={{ flex: "1 1 160px", marginBottom: 0 }}>
          <label>Ca</label>
          <select value={shiftLabel} onChange={(e) => setShiftLabel(e.target.value)}>
            {SHIFT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <button type="button" className="danger" disabled={!shiftDate || busy} onClick={() => setConfirming(true)}>
          Xoá kế hoạch
        </button>
      </div>

      {confirming && (
        <ConfirmDialog
          title="Xoá kế hoạch?"
          message={`Toàn bộ chuyến của MỌI XE trong ngày ${shiftDate} — ${shiftText} sẽ bị xoá khỏi hệ thống (xoá mềm). Bạn có chắc không?`}
          confirmLabel="Có, xoá"
          busy={busy}
          onConfirm={handleDelete}
          onCancel={() => setConfirming(false)}
        />
      )}
    </div>
  );
}
