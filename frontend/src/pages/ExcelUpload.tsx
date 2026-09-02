import { useState } from "react";
import axios from "axios";
import { apiClient } from "../api/client";

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
    </div>
  );
}
