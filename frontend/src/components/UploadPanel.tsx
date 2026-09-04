import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import axios from "axios";
import { apiClient } from "../api/client";

// Ô upload Excel dùng chung cho cả 2 tab của trang "Xe & Kế hoạch".
// Tách khỏi ExcelUpload.tsx cũ khi gộp 2 mục nav "Nhập kế hoạch" + "Upload
// Excel" lại làm một (2026-09-04).
//
// Bố cục 1 HÀNG NGANG duy nhất (label + ô chọn file + nút) thay vì xếp dọc như
// bản cũ — ở tab "Nhập kế hoạch" nó nằm ngay trên form nhập tay khá dài, chiếm
// dọc thêm nữa thì form bị đẩy xuống quá sâu.

export type SheetKind = "vehicles" | "schedules";

function extractErrors(err: unknown): string[] {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (detail && typeof detail === "object" && Array.isArray(detail.errors)) return detail.errors;
    if (typeof detail === "string") return [detail];
  }
  return ["Có lỗi không xác định xảy ra khi upload."];
}

export function UploadPanel({ kind }: { kind: SheetKind }) {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [result, setResult] = useState<Record<string, number> | null>(null);

  const endpoint = kind === "vehicles" ? "/api/vehicles/upload" : "/api/schedules/upload";

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
      else queryClient.invalidateQueries({ queryKey: ["schedules"] });
    } catch (err) {
      setErrors(extractErrors(err));
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="card">
      {/* Trái -> phải: tiêu đề, ô chọn file, nút. Bỏ chữ "Sheet ..." ở cuối
          hàng (2026-09-04) — tên sheet là chi tiết của file mẫu, không phải
          thứ người dùng cần đọc mỗi lần upload. */}
      <div className="upload-row">
        <h2 className="upload-row-title">Tải từ Excel</h2>
        <div className="upload-row-file">
          <label htmlFor={`upload-${kind}`}>Chọn file excel</label>
          <input
            id={`upload-${kind}`}
            type="file"
            accept=".xlsx"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setErrors([]);
              setResult(null);
            }}
          />
        </div>
        <button type="button" className="primary" disabled={!file || uploading} onClick={handleUpload}>
          {uploading ? "Đang tải lên..." : "Tải lên"}
        </button>
      </div>

      {errors.length > 0 && (
        <div className="error-banner" style={{ marginTop: 12 }}>
          <strong>Tải lên thất bại — {errors.length} lỗi cần sửa:</strong>
          <ul style={{ margin: "8px 0 0", paddingLeft: 20 }}>
            {errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </div>
      )}

      {result && (
        <div className="success-banner" style={{ marginTop: 12 }}>
          Tải lên thành công: {Object.entries(result).map(([k, v]) => `${k}=${v}`).join(", ")}
        </div>
      )}
    </div>
  );
}
