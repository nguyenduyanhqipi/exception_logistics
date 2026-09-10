import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { apiClient, apiErrorMessage } from "../api/client";
import type { OutcomeInfo } from "../api/types";

// Form nhập/sửa KẾT QUẢ THỰC TẾ (việc 2, 2026-09-04).
//
// Trước đây form này chỉ hiện đúng 1 lần ngay sau khi xác nhận phương án (dựa
// vào local state `decisionId` của trang), rời trang là mất luôn cơ hội nhập.
// Nay nó là 1 khu vực cố định trên trang chi tiết, mở lại được bất cứ lúc nào
// từ trạng thái "Chưa có kết quả", và dùng lại chính nó để SỬA kết quả đã ghi.
//
// REDESIGN 2026-09-08 (Claude outputs/dot_code_5/outcome_form_redesign.md):
// form có 2 KIỂU, chọn theo sub_type của ngoại lệ.
// - Kiểu TIẾN ĐỘ (9/11 sub_type): giữ nguyên y hệt bộ field cũ.
// - Kiểu KHÁCH TỪ CHỐI (customer_absent + customer_dispute): bỏ hẳn câu "đúng
//   giờ/muộn giờ" — hàng còn chưa giao được thì câu đó không có gì để trả lời —
//   thay bằng "kết quả cuối cùng là gì".

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

// 2 sub_type dùng form kiểu KHÁCH TỪ CHỐI. Gộp chung 1 hình dạng chứ không tách
// riêng: cả 2 cùng bản chất "không giao được ngay lần đầu"; khác biệt giữa
// "không có người nhận" và "có mặt nhưng tranh chấp" đã nằm ở câu hỏi phụ lúc
// NHẬP ngoại lệ (dispute_type), lặp lại ở đây là hỏi 2 lần cùng 1 chuyện.
export const REJECTION_SUB_TYPES = ["customer_absent", "customer_dispute"];

/** PHẢI khớp backend/schemas/decision.py::RESOLUTION_TYPES. */
export const RESOLUTION_OPTIONS: { key: string; label: string }[] = [
  { key: "redelivered", label: "Giao lại thành công" },
  { key: "returned_to_depot", label: "Trả hàng về kho" },
  { key: "cancelled", label: "Khách huỷ đơn" },
  { key: "other", label: "Khác (ghi rõ ở ghi chú)" },
];

export function resolutionTypeLabel(key: string | null | undefined): string {
  if (!key) return "-";
  return RESOLUTION_OPTIONS.find((o) => o.key === key)?.label ?? key;
}

/** Ngoại lệ đang xét có dùng form kiểu KHÁCH TỪ CHỐI không.
 *
 * Nhận cả DANH SÁCH sub_type vì quyết định phối hợp (combined mode) gộp nhiều
 * ngoại lệ vào 1 outcome duy nhất: chỉ dùng kiểu khách-từ-chối khi MỌI thành
 * viên đều thuộc kiểu đó — nhóm lẫn 1 ngoại lệ tiến độ thì câu hỏi đúng vẫn là
 * "đúng giờ hay muộn", không thể trả lời bằng "đã giao lại hay trả về kho". */
export function isRejectionOutcome(subTypes: string[]): boolean {
  return subTypes.length > 0 && subTypes.every((st) => REJECTION_SUB_TYPES.includes(st));
}

// Mốc thời gian đem ra so sánh khác nhau theo nhóm ngoại lệ: khách CHỦ ĐỘNG đổi
// giờ/địa điểm thì so với kế hoạch ban đầu là vô nghĩa (chính khách đã bỏ mốc
// đó), phải so với mốc mới đã thống nhất.
function milestoneLabels(subType: string | undefined) {
  if (subType === "change_time" || subType === "change_location") {
    return {
      question: "Kết quả so với giờ/địa điểm MỚI đã thống nhất với khách",
      late: "Muộn so với mốc mới",
      delayLabel: "Muộn bao nhiêu phút so với mốc mới đã thống nhất?",
    };
  }
  return {
    question: "Kết quả giao hàng",
    late: "Muộn giờ",
    delayLabel: "Muộn bao nhiêu phút?",
  };
}

interface OutcomeFormProps {
  decisionId: string;
  /** sub_type của (các) ngoại lệ thuộc quyết định này — chọn kiểu form + nhãn mốc. */
  subTypes: string[];
  /** Có giá trị = đang SỬA kết quả đã ghi; null = nhập mới. */
  existing?: OutcomeInfo | null;
  onDone: () => void;
  onCancel?: () => void;
  /** Query key cần làm mới sau khi lưu (trang chi tiết hoặc trang nhóm). */
  invalidateKeys?: unknown[][];
}

export function OutcomeForm({
  decisionId,
  subTypes,
  existing,
  onDone,
  onCancel,
  invalidateKeys = [],
}: OutcomeFormProps) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const editing = !!existing;
  // Khi SỬA, kiểu form phải theo đúng kiểu của bản ghi đã lưu chứ không theo
  // sub_type hiện tại: backend cấm đổi qua lại giữa 2 kiểu, mà sub_type thì có
  // thể đã bị sửa sau khi outcome được ghi.
  const rejection = editing ? existing!.resolution_type !== null : isRejectionOutcome(subTypes);
  const labels = milestoneLabels(subTypes.length === 1 ? subTypes[0] : undefined);

  // Đã ghi nhận là MUỘN thì không cho quay về ĐÚNG GIỜ (backend cũng chặn,
  // api/decisions.py::update_outcome) — khoá luôn lựa chọn ở UI cho rõ ràng.
  const lockedLate = editing && existing?.delivered_on_time === false;

  const [deliveredOnTime, setDeliveredOnTime] = useState<boolean | null>(
    existing ? existing.delivered_on_time : null,
  );
  const [resolutionType, setResolutionType] = useState<string | null>(existing?.resolution_type ?? null);
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

  const missingResolution = rejection && resolutionType === null;
  const missingOnTime = !rejection && deliveredOnTime === null;
  // Kiểu tiến độ: muộn giờ thì BẮT BUỘC số phút. Kiểu khách-từ-chối: số phút chỉ
  // là thông tin thêm khi giao lại được, không bắt buộc.
  const missingDelay = !rejection && deliveredOnTime === false && (delayMinutes === "" || Number(delayMinutes) <= 0);
  const missingCost = actualCostDigits === "";
  const invalid = missingResolution || missingOnTime || missingDelay || missingCost;

  const showDelayInput = rejection ? resolutionType === "redelivered" : deliveredOnTime === false;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (invalid) return;
    setError(null);
    setSubmitting(true);
    try {
      const body = rejection
        ? {
            // Kiểu khách-từ-chối KHÔNG gửi delivered_on_time (backend từ chối):
            // form không hỏi câu đó, tự suy ra một giá trị là bịa số liệu KPI.
            delivered_on_time: null,
            delay_minutes: resolutionType === "redelivered" && delayMinutes !== "" ? Number(delayMinutes) : null,
            actual_cost: Number(actualCostDigits),
            resolution_type: resolutionType,
            notes: notes || null,
          }
        : {
            delivered_on_time: deliveredOnTime,
            // Đúng giờ thì KHÔNG được gửi delay_minutes (backend từ chối).
            delay_minutes: deliveredOnTime === false ? Number(delayMinutes) : null,
            actual_cost: Number(actualCostDigits),
            resolution_type: null,
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
      // Việc 2 (2026-09-04): nhập kết quả LẦN ĐẦU là bước cuối của luồng xử lý
      // -> quay về Dashboard làm việc tiếp. SỬA kết quả thì người dùng đang đi
      // từ trang Lịch sử vào, trả họ về đúng chỗ đó thay vì ném sang Dashboard.
      navigate(editing ? "/history" : "/");
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
      {lockedLate && !rejection && (
        <div className="drill-muted" style={{ marginBottom: 10 }}>
          Đơn này đã ghi nhận là giao muộn — không đổi lại thành đúng giờ được, chỉ sửa số phút muộn, chi phí và ghi
          chú.
        </div>
      )}

      {rejection ? (
        <div className="form-field">
          <label>
            Kết quả cuối cùng? <span className="required-mark">*</span>
          </label>
          <div className="radio-group">
            {RESOLUTION_OPTIONS.map((opt) => (
              <label key={opt.key} className={`radio-option ${resolutionType === opt.key ? "selected" : ""}`}>
                <input
                  type="radio"
                  checked={resolutionType === opt.key}
                  onChange={() => {
                    setResolutionType(opt.key);
                    // Đổi sang lựa chọn không có ý nghĩa thời gian -> bỏ luôn số
                    // phút đã gõ, tránh gửi lên một con số vô nghĩa.
                    if (opt.key !== "redelivered") setDelayMinutes("");
                  }}
                />
                {opt.label}
              </label>
            ))}
          </div>
          {touched && missingResolution && <span className="field-error">Vui lòng chọn kết quả cuối cùng.</span>}
        </div>
      ) : (
        <div className="form-field">
          <label>
            {labels.question} <span className="required-mark">*</span>
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
              {labels.late}
            </label>
          </div>
          {touched && missingOnTime && <span className="field-error">Vui lòng chọn đúng giờ hay muộn giờ.</span>}
        </div>
      )}

      {showDelayInput && (
        <div className="form-field">
          <label>
            {rejection ? "Trễ bao nhiêu phút so với lần giao đầu tiên?" : labels.delayLabel}
            {rejection ? <span className="hint"> (không bắt buộc)</span> : <span className="required-mark"> *</span>}
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
        <span className="hint">
          {rejection
            ? "Chi phí thật đã phát sinh để xử lý (phí giao lại / chở hàng về kho / xử lý huỷ đơn). Nhập 0 nếu không phát sinh."
            : "Nhập số tiền thật bằng VNĐ. Nhập 0 nếu không phát sinh chi phí."}
        </span>
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
