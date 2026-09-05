import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { apiClient, apiErrorMessage } from "../api/client";

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

// Form nhập kế hoạch thủ công. Từ 2026-09-04 nó là NỬA DƯỚI của tab "Nhập kế
// hoạch" trong trang "Xe & Kế hoạch" (Operations.tsx) — nên không tự bọc
// `.page`/`<h1>` nữa, trang cha lo phần đó. Nút "Xoá kế hoạch" đã chuyển lên
// header Dashboard (Dashboard.tsx::DeleteScheduleMenu).
export function ScheduleForm() {
  const navigate = useNavigate();
  const { data: vehicles } = useQuery({
    queryKey: ["vehicles"],
    queryFn: async () => (await apiClient.get<Vehicle[]>("/api/vehicles")).data,
  });

  const [vehicleId, setVehicleId] = useState("");
  const [shiftDate, setShiftDate] = useState("");
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
          <div className="form-field" style={{ width: 100 }}>
            <label>Chuyến thứ mấy trong ngày</label>
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
  );
}

