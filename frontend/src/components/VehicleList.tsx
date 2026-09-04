import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { apiClient, apiErrorMessage } from "../api/client";
import type { Vehicle } from "../api/types";
import { VEHICLE_STATUS_LABEL } from "../statusLabels";

// Bảng danh mục xe (upload Excel + sửa/xoá từng dòng) — chuyển nguyên từ
// ExcelUpload.tsx sang đây khi gộp 2 mục nav thành trang "Xe & Kế hoạch"
// (2026-09-04), thêm ô tìm kiếm và nhãn trạng thái tiếng Việt.

interface VehicleEditState {
  driver_name: string;
  driver_phone: string;
  max_payload_kg: string;
  vehicle_type: string;
  cost_per_km: string;
  status: string;
}

function toEditState(v: Vehicle): VehicleEditState {
  return {
    driver_name: v.driver_name,
    driver_phone: v.driver_phone,
    max_payload_kg: String(v.max_payload_kg),
    vehicle_type: v.vehicle_type ?? "",
    cost_per_km: v.cost_per_km !== null ? String(v.cost_per_km) : "",
    status: v.status,
  };
}

/** Chuỗi gộp mọi trường tìm kiếm được của 1 xe.
 *
 * Có CẢ `status` thô ("active") lẫn nhãn tiếng Việt ("Hoạt động") để gõ kiểu
 * nào cũng ra — người dùng thấy nhãn tiếng Việt trên bảng nên sẽ gõ theo nó,
 * nhưng dữ liệu thật vẫn là "active"/"inactive". */
function haystack(v: Vehicle): string {
  return [
    v.vehicle_id,
    v.driver_name,
    v.driver_phone,
    String(v.max_payload_kg),
    v.vehicle_type ?? "",
    v.status,
    VEHICLE_STATUS_LABEL[v.status] ?? "",
  ]
    .join(" ")
    .toLowerCase();
}

function VehicleRow({ vehicle }: { vehicle: Vehicle }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<VehicleEditState>(() => toEditState(vehicle));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function startEdit() {
    setForm(toEditState(vehicle));
    setError(null);
    setEditing(true);
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      await apiClient.put(`/api/vehicles/${vehicle.vehicle_id}`, {
        driver_name: form.driver_name,
        driver_phone: form.driver_phone,
        max_payload_kg: Number(form.max_payload_kg),
        vehicle_type: form.vehicle_type || null,
        cost_per_km: form.cost_per_km ? Number(form.cost_per_km) : null,
        // Giá trị gửi API vẫn là "active"/"inactive", chỉ nhãn hiển thị là
        // tiếng Việt — backend (schedules.py::upload_schedules,
        // ScheduleInput) so khớp theo giá trị thô này.
        status: form.status,
      });
      queryClient.invalidateQueries({ queryKey: ["vehicles"] });
      setEditing(false);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (
      !window.confirm(
        `Xoá xe ${vehicle.vehicle_id}? Xe sẽ chuyển sang trạng thái Tạm ngừng, không xoá hẳn khỏi hệ thống.`,
      )
    )
      return;
    setSaving(true);
    setError(null);
    try {
      await apiClient.delete(`/api/vehicles/${vehicle.vehicle_id}`);
      queryClient.invalidateQueries({ queryKey: ["vehicles"] });
    } catch (err) {
      setError(apiErrorMessage(err));
      setSaving(false);
    }
  }

  if (editing) {
    return (
      <tr>
        <td>{vehicle.vehicle_id}</td>
        <td><input value={form.driver_name} onChange={(e) => setForm({ ...form, driver_name: e.target.value })} style={{ width: 110 }} /></td>
        <td><input value={form.driver_phone} onChange={(e) => setForm({ ...form, driver_phone: e.target.value })} style={{ width: 100 }} /></td>
        <td><input type="number" value={form.max_payload_kg} onChange={(e) => setForm({ ...form, max_payload_kg: e.target.value })} style={{ width: 80 }} /></td>
        <td><input value={form.vehicle_type} onChange={(e) => setForm({ ...form, vehicle_type: e.target.value })} style={{ width: 90 }} /></td>
        <td><input type="number" value={form.cost_per_km} onChange={(e) => setForm({ ...form, cost_per_km: e.target.value })} style={{ width: 80 }} /></td>
        <td>
          <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
            <option value="active">Hoạt động</option>
            <option value="inactive">Tạm ngừng</option>
          </select>
        </td>
        <td style={{ whiteSpace: "nowrap" }}>
          {error && <div className="error-banner" style={{ margin: "4px 0", padding: 6, fontSize: 12 }}>{error}</div>}
          <button type="button" className="primary" disabled={saving} onClick={handleSave} style={{ marginRight: 6 }}>
            Lưu
          </button>
          <button type="button" className="secondary" disabled={saving} onClick={() => setEditing(false)}>
            Hủy
          </button>
        </td>
      </tr>
    );
  }

  return (
    <tr>
      <td>{vehicle.vehicle_id}</td>
      <td>{vehicle.driver_name}</td>
      <td>{vehicle.driver_phone}</td>
      <td>{vehicle.max_payload_kg}</td>
      <td>{vehicle.vehicle_type ?? "-"}</td>
      <td>{vehicle.cost_per_km !== null ? `${vehicle.cost_per_km.toLocaleString("vi-VN")}đ` : "-"}</td>
      <td>
        <span className={`badge badge-${vehicle.status === "active" ? "ok" : "pending"}`}>
          {VEHICLE_STATUS_LABEL[vehicle.status] ?? vehicle.status}
        </span>
      </td>
      <td style={{ whiteSpace: "nowrap" }}>
        {error && <div className="error-banner" style={{ margin: "4px 0", padding: 6, fontSize: 12 }}>{error}</div>}
        <button type="button" className="secondary" disabled={saving} onClick={startEdit} style={{ marginRight: 6 }}>
          Sửa
        </button>
        <button type="button" className="secondary" disabled={saving} onClick={handleDelete}>
          Xoá
        </button>
      </td>
    </tr>
  );
}

export function VehicleList() {
  const [query, setQuery] = useState("");
  const { data, isLoading, isError } = useQuery({
    queryKey: ["vehicles"],
    queryFn: async () => (await apiClient.get<Vehicle[]>("/api/vehicles")).data,
  });

  // Lọc substring không phân biệt hoa/thường trên mọi cột; xe không khớp bị
  // ẩn hẳn khỏi bảng (giống ô tìm kiếm ở Dashboard), không làm mờ.
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q || !data) return data;
    return data.filter((v) => haystack(v).includes(q));
  }, [data, query]);

  return (
    <div className="card">
      <div className="section-head">
        <h2 style={{ margin: 0 }}>Danh sách xe hiện có</h2>
        <input
          type="search"
          className="section-search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Tìm biển số, tài xế, SĐT, tải trọng, loại xe, trạng thái..."
          aria-label="Tìm xe trong danh mục"
        />
      </div>
      {isLoading && <div className="loading-spinner">Đang tải...</div>}
      {isError && <div className="error-banner">Không tải được danh sách xe.</div>}
      {data && data.length === 0 && <p style={{ color: "#6b7280" }}>Chưa có xe nào.</p>}
      {data && data.length > 0 && filtered && filtered.length === 0 && (
        <p style={{ color: "#6b7280" }}>Không có xe nào khớp "{query.trim()}".</p>
      )}
      {filtered && filtered.length > 0 && (
        <table className="list-table">
          <thead>
            <tr>
              <th>Biển số / Mã xe</th>
              <th>Tài xế</th>
              <th>SĐT</th>
              <th>Tải trọng (kg)</th>
              <th>Loại xe</th>
              <th>Chi phí/km</th>
              <th>Trạng thái</th>
              <th>Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((v) => (
              <VehicleRow key={v.vehicle_id} vehicle={v} />
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
