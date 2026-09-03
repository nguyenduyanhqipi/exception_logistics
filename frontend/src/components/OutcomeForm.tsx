import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { apiClient, apiErrorMessage } from "../api/client";
import type { OutcomeInfo } from "../api/types";

// Form nhập/sửa KẾT QUẢ THỰC TẾ (việc 2, 2026-09-04).
//
// Trước đây form này chỉ hiện đúng 1 lần ngay sau khi xác nhận phương án (dựa
// vào local state `decisionId` của trang), rời trang là mất luôn cơ hội nhập.
// Nay nó là 1 khu vực cố định trên trang chi tiết, mở lại được bất cứ lúc nào
// từ trạng thái "Chưa có kết quả", và dùng lại chính nó để SỬA kết quả đã ghi.

/** 180000 -> "180.000". Nhập chi phí là số VNĐ nguyên (KHÔNG phải nghìn đồng),
 *  chỉ thêm dấu chấm ngăn cách khi hiển thị; giá trị gửi API vẫn là số thật. */
function groupThousands(digits: string): string {
  if (!digits) return "";
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

function onlyDigits(raw: string): string {
  return raw.replace(/\D/g, "").replace(/^0+(?=\d)/, "");
}

export function formatVnd(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return `${groupThousands(String(Math.round(value)))}đ`;
}

interface OutcomeFormProps {
  decisionId: string;
  /** Có giá trị = đang SỬA kết quả đã ghi; null = nhập mới. */
  existing?: OutcomeInfo | null;
  onDone: () => void;
  onCancel?: () => void;
  /** Query key cần làm mới sau khi lưu (trang chi tiết hoặc trang nhóm). */
  invalidateKeys?: unknown[][];
}

export function OutcomeForm({ decisionId, existing, onDone, onCancel, invalidateKeys = [] }: OutcomeFormProps) {
  const queryClient = useQueryClient();
  const editing = !!existing;
  // Đã ghi nhận là MUỘN thì không cho quay về ĐÚNG GIỜ (backend cũng chặn,
  // api/decisions.py::update_outcome) — khoá luôn lựa chọn ở UI cho rõ ràng.
  const lockedLate = editing && existing?.delivered_on_time === false;

  const [deliveredOnTime, setDeliveredOnTime] = useState<boolean | null>(
    existing ? existing.delivered_on_time : null,
  );
  const [delayMinutes, setDelayMinutes] = useState(
    existing?.delay_minutes != null ? String(existing.delay_minutes) : "",
  );
  const [actualCostDigits, setActualCostDigits] = useState(
    existing?.actual_cost != null ? String(Math.round(existing.actual_cost)) : "",
  );
  const [notes, setNotes] = useState(existing?.notes ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);

  const missingOnTime = deliveredOnTime === null;
  const missingDelay = deliveredOnTime === false && (delayMinutes === "" || Number(delayMinutes) <= 0);
  const missingCost = actualCostDigits === "";
  const invalid = missingOnTime || missingDelay || missingCost;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (invalid) return;
    setError(null);
    setSubmitting(true);
    try {
      const body = {
        delivered_on_time: deliveredOnTime,
        // Đúng giờ thì KHÔNG được gửi delay_minutes (backend từ chối).
        delay_minutes: deliveredOnTime === false ? Number(delayMinutes) : null,
        actual_cost: Number(actualCostDigits),
        notes: notes || null,
      };
      if (editing) {
        await apiClient.patch(`/api/outcomes/${existing!.outcome_id}`, body);
      } else {
        await apiClient.post("/api/outcomes", { decision_id: decisionId, ...body });
      }
      for (const key of invalidateKeys) {
        await queryClient.invalidateQueries({ queryKey: key });
      }
      onDone();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="card" style={{ background: "#f9fafb" }}>
      <h2 style={{ marginTop: 0 }}>{editing ? "Sửa kết quả thực tế" : "Nhập kết quả thực tế"}</h2>
      {error && <div className="error-banner">{error}</div>}
      {lockedLate && (
        <div className="drill-muted" style={{ marginBottom: 10 }}>
          Đơn này đã ghi nhận là giao muộn — không đổi lại thành đúng giờ được, chỉ sửa số phút muộn, chi phí và ghi
          chú.
        </div>
      )}

      <div className="form-field">
        <label>
          Kết quả giao hàng <span className="required-mark">*</span>
        </label>
        <div className="radio-group">
          <label
            className={`radio-option ${deliveredOnTime === true ? "selected" : ""} ${lockedLate ? "disabled" : ""}`}
          >
            <input
              type="radio"
              checked={deliveredOnTime === true}
              disabled={lockedLate}
              onChange={() => {
                setDeliveredOnTime(true);
                setDelayMinutes("");
              }}
            />
            Đúng giờ
          </label>
          <label className={`radio-option ${deliveredOnTime === false ? "selected" : ""}`}>
            <input type="radio" checked={deliveredOnTime === false} onChange={() => setDeliveredOnTime(false)} />
            Muộn giờ
          </label>
        </div>
        {touched && missingOnTime && <span className="field-error">Vui lòng chọn đúng giờ hay muộn giờ.</span>}
      </div>

      {deliveredOnTime === false && (
        <div className="form-field">
          <label>
            Muộn bao nhiêu phút? <span className="required-mark">*</span>
          </label>
          <input
            type="number"
            min={1}
            step={1}
            value={delayMinutes}
            onFocus={(e) => e.target.select()}
            onChange={(e) => setDelayMinutes(e.target.value.replace(/\D/g, ""))}
          />
          {touched && missingDelay && <span className="field-error">Nhập số phút muộn (số nguyên lớn hơn 0).</span>}
        </div>
      )}

      <div className="form-field">
        <label>
          Chi phí thực tế (VNĐ) <span className="required-mark">*</span>
        </label>
        <input
          inputMode="numeric"
          value={groupThousands(actualCostDigits)}
          placeholder="VD: 180.000"
          onChange={(e) => setActualCostDigits(onlyDigits(e.target.value))}
        />
        <span className="hint">Nhập số tiền thật bằng VNĐ. Nhập 0 nếu không phát sinh chi phí.</span>
        {touched && missingCost && <span className="field-error">Vui lòng nhập chi phí thực tế (0 nếu không có).</span>}
      </div>

      <div className="form-field">
        <label>Ghi chú (tuỳ chọn)</label>
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
      </div>

      <div style={{ display: "flex", gap: 8 }}>
        <button type="submit" className="primary" disabled={submitting || invalid}>
          {submitting ? "Đang lưu..." : editing ? "Lưu kết quả" : "Xác nhận hoàn thành"}
        </button>
        {onCancel && (
          <button type="button" className="secondary" disabled={submitting} onClick={onCancel}>
            Hủy
          </button>
        )}
      </div>
      {invalid && <div className="field-error" style={{ marginTop: 8 }}>Còn thiếu thông tin bắt buộc (*).</div>}
    </form>
  );
}
