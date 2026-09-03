import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import axios from "axios";
import { apiClient, apiErrorMessage } from "../api/client";
import type { Vehicle } from "../api/types";

type SheetKind = "vehicles" | "schedules";

function extractErrors(err: unknown): string[] {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (detail && typeof detail === "object" && Array.isArray(detail.errors)) return detail.errors;
    if (typeof detail === "string") return [detail];
  }
  return ["Có lỗi không xác định xảy ra khi upload."];
}

function UploadPanel({ kind }: { kind: SheetKind }) {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [result, setResult] = useState<Record<string, number> | null>(null);

  const endpoint = kind === "vehicles" ? "/api/vehicles/upload" : "/api/schedules/upload";
  const title = kind === "vehicles" ? "Danh_muc_xe" : "Ke_hoach_giao_hang";

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    setErrors([]);
    setResult(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await apiClient.post(endpoint, formData, { headers: { "Content-Type": "multipart/form-data" } });
      setResult(res.data);
      setFile(null);
      if (kind === "vehicles") queryClient.invalidateQueries({ queryKey: ["vehicles"] });
    } catch (err) {
      setErrors(extractErrors(err));
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="card">
      <h2>Sheet {title}</h2>
      <input type="file" accept=".xlsx" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setErrors([]); setResult(null); }} />
      <div style={{ marginTop: 10 }}>
        <button type="button" className="primary" disabled={!file || uploading} onClick={handleUpload}>
          {uploading ? "Đang upload..." : "Upload"}
        </button>
      </div>

      {errors.length > 0 && (
        <div className="error-banner" style={{ marginTop: 12 }}>
          <strong>Upload thất bại — {errors.length} lỗi cần sửa:</strong>
          <ul style={{ margin: "8px 0 0", paddingLeft: 20 }}>
            {errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </div>
      )}

      {result && (
        <div className="success-banner" style={{ marginTop: 12 }}>
          Upload thành công: {Object.entries(result).map(([k, v]) => `${k}=${v}`).join(", ")}
        </div>
      )}
    </div>
  );
}

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
    if (!window.confirm(`Xoá xe ${vehicle.vehicle_id}? Xe sẽ chuyển sang trạng thái ngừng hoạt động (inactive), không xoá hẳn khỏi hệ thống.`)) return;
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
            <option value="active">active</option>
            <option value="inactive">inactive</option>
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
      <td>{vehicle.status}</td>
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

function VehicleList() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["vehicles"],
    queryFn: async () => (await apiClient.get<Vehicle[]>("/api/vehicles")).data,
  });

  return (
    <div className="card">
      <h2>Danh sách xe hiện có</h2>
      {isLoading && <div className="loading-spinner">Đang tải...</div>}
      {isError && <div className="error-banner">Không tải được danh sách xe.</div>}
      {data && data.length === 0 && <p style={{ color: "#6b7280" }}>Chưa có xe nào.</p>}
      {data && data.length > 0 && (
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
            {data.map((v) => (
              <VehicleRow key={v.vehicle_id} vehicle={v} />
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export function ExcelUpload() {
  const [tab, setTab] = useState<SheetKind>("vehicles");

  return (
    <div className="page">
      <h1>Upload dữ liệu từ Excel</h1>
      <div className="filters">
        <button type="button" className={tab === "vehicles" ? "primary" : "secondary"} onClick={() => setTab("vehicles")}>
          Danh mục xe
        </button>
        <button type="button" className={tab === "schedules" ? "primary" : "secondary"} onClick={() => setTab("schedules")}>
          Kế hoạch giao hàng
        </button>
      </div>
      <UploadPanel key={tab} kind={tab} />
      {tab === "vehicles" && <VehicleList />}
    </div>
  );
}
