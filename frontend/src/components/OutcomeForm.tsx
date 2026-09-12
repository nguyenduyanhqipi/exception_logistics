import { useLayoutEffect, useRef, useState, type ChangeEvent, type FormEvent } from "react";
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

// Đơn vị nhập số phút trễ (đợt 12, việc 1). DB vẫn LUÔN lưu bằng PHÚT — đơn vị
// chỉ tồn tại ở ô NHẬP, quy đổi ngay lúc submit, không lưu lại lựa chọn đơn vị.
type DelayUnit = "minutes" | "hours" | "days";
const DELAY_UNIT_TO_MINUTES: Record<DelayUnit, number> = { minutes: 1, hours: 60, days: 1440 };

// Mốc thời gian đem ra so sánh KHÔNG suy ra được từ sub_type (đợt 12, việc 3).
// Trước đây chỉ change_time/change_location được đặc cách so với "mốc mới đã
// thống nhất", 9 sub_type còn lại luôn so với kế hoạch gốc — sai khi một ngoại
// lệ khác cũng đẻ ra mốc mới (vd tai nạn -> đưa hàng về kho + hẹn lại khách).
// Nay dispatcher tự chọn mốc mỗi lần nhập; sub_type chỉ quyết định GIÁ TRỊ MẶC
// ĐỊNH của lựa chọn đó.
type DelayBaseline = "original" | "agreed_new";

// Ghim vào đầu Ghi chú khi mốc là "mốc mới" (lựa chọn này không có cột riêng
// trong DB). Cắt lại đúng tiền tố này lúc SỬA để không nối chồng tiền tố lần 2.
const BASELINE_NOTE_PREFIX = "[So với mốc mới đã thống nhất với khách]";

function delayLabels(baseline: DelayBaseline) {
  return baseline === "agreed_new"
    ? { late: "Muộn so với mốc mới", delayLabel: "Muộn bao nhiêu so với mốc mới đã thống nhất với khách?" }
    : { late: "Muộn giờ", delayLabel: "Muộn bao nhiêu so với kế hoạch/SLA ban đầu?" };
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

  // Đã ghi nhận là MUỘN thì không cho quay về ĐÚNG GIỜ (backend cũng chặn,
  // api/decisions.py::update_outcome) — khoá luôn lựa chọn ở UI cho rõ ràng.
  const lockedLate = editing && existing?.delivered_on_time === false;

  const [deliveredOnTime, setDeliveredOnTime] = useState<boolean | null>(
    existing ? existing.delivered_on_time : null,
  );
  // Mặc định "mốc mới" cho change_time/change_location (thường đúng ngay từ đầu
  // vì khách chủ động đổi giờ/địa điểm), mặc định "kế hoạch gốc" cho các
  // sub_type còn lại — dispatcher tự đổi lại nếu ca cụ thể của họ khác thường lệ
  // (vd accident có hẹn lại khách thì bấm sang "mốc mới").
  const [delayBaseline, setDelayBaseline] = useState<DelayBaseline>(
    existing?.notes?.startsWith(BASELINE_NOTE_PREFIX)
      ? "agreed_new"
      : subTypes.length === 1 && (subTypes[0] === "change_time" || subTypes[0] === "change_location")
        ? "agreed_new"
        : "original",
  );
  const [resolutionType, setResolutionType] = useState<string | null>(existing?.resolution_type ?? null);
  const [delayMinutes, setDelayMinutes] = useState(
    existing?.delay_minutes != null ? String(existing.delay_minutes) : "",
  );
  // Khi SỬA thì luôn hiện lại theo PHÚT (đúng như DB lưu) — không đoán ngược đơn
  // vị đã gõ lần đầu (không lưu, cũng không cần).
  const [delayUnit, setDelayUnit] = useState<DelayUnit>("minutes");
  // "Giao muộn nhưng không quy đổi ra được con số chính xác" (vd trả hàng về kho,
  // chưa hẹn được ngày giao lại). Bật lại đúng trạng thái đã lưu khi SỬA: outcome
  // kiểu tiến độ, muộn giờ, mà delay_minutes trống thì chính là ca này.
  const [delayUnknown, setDelayUnknown] = useState(
    !!existing &&
      existing.resolution_type === null &&
      existing.delivered_on_time === false &&
      existing.delay_minutes == null,
  );
  const [actualCostDigits, setActualCostDigits] = useState(
    existing?.actual_cost != null ? String(Math.round(existing.actual_cost)) : "",
  );
  const costInputRef = useRef<HTMLInputElement | null>(null);
  // Ghi lại "đã gõ xong bao nhiêu CHỮ SỐ trước con trỏ" ngay lúc onChange (tính
  // trên giá trị thô, trước khi định dạng lại) — không ghi vị trí KÝ TỰ vì dấu
  // chấm ngăn cách chèn thêm vào chuỗi hiển thị sẽ làm lệch vị trí đó.
  const pendingCostCursorDigits = useRef<number | null>(null);

  useLayoutEffect(() => {
    if (pendingCostCursorDigits.current === null) return;
    const el = costInputRef.current;
    if (el) {
      const formatted = groupThousands(actualCostDigits);
      let pos = 0;
      let digitsSeen = 0;
      while (pos < formatted.length && digitsSeen < pendingCostCursorDigits.current) {
        if (formatted[pos] !== ".") digitsSeen++;
        pos++;
      }
      el.setSelectionRange(pos, pos);
    }
    pendingCostCursorDigits.current = null;
  }, [actualCostDigits]);

  function handleCostChange(e: ChangeEvent<HTMLInputElement>) {
    const input = e.target;
    const cursor = input.selectionStart ?? input.value.length;
    pendingCostCursorDigits.current = onlyDigits(input.value.slice(0, cursor)).length;
    setActualCostDigits(onlyDigits(input.value));
  }
  // Bỏ tiền tố mốc ra khỏi ô Ghi chú lúc SỬA — nó là thứ form tự ghim vào, không
  // phải chữ dispatcher gõ; giữ lại thì lưu lần 2 sẽ ra 2 tiền tố chồng nhau.
  const [notes, setNotes] = useState(
    (existing?.notes ?? "").startsWith(BASELINE_NOTE_PREFIX)
      ? existing!.notes!.slice(BASELINE_NOTE_PREFIX.length).trim()
      : (existing?.notes ?? ""),
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);

  const missingResolution = rejection && resolutionType === null;
  const missingOnTime = !rejection && deliveredOnTime === null;
  // Kiểu tiến độ: muộn giờ thì BẮT BUỘC số phút. Kiểu khách-từ-chối: số phút chỉ
  // là thông tin thêm khi giao lại được, không bắt buộc.
  const missingDelay =
    !rejection &&
    deliveredOnTime === false &&
    (delayUnknown ? notes.trim() === "" : delayMinutes === "" || Number(delayMinutes) <= 0);
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
      // Lựa chọn mốc KHÔNG có cột riêng trong DB (quyết định không đổi schema).
      // Ghim nó vào đầu Ghi chú để đọc lại còn biết con số phút được đo từ đâu.
      const notesToSend =
        !rejection && deliveredOnTime === false && delayBaseline === "agreed_new" && !delayUnknown
          ? `${BASELINE_NOTE_PREFIX} ${notes}`.trim()
          : notes;
      const body = rejection
        ? {
            // Kiểu khách-từ-chối KHÔNG gửi delivered_on_time (backend từ chối):
            // form không hỏi câu đó, tự suy ra một giá trị là bịa số liệu KPI.
            delivered_on_time: null,
            delay_minutes: resolutionType === "redelivered" && delayMinutes !== "" ? Number(delayMinutes) : null,
            actual_cost: Number(actualCostDigits),
            resolution_type: resolutionType,
            notes: notesToSend || null,
          }
        : {
            delivered_on_time: deliveredOnTime,
            // Đúng giờ thì KHÔNG được gửi delay_minutes (backend từ chối).
            delay_minutes:
              deliveredOnTime === false
                ? delayUnknown
                  ? null
                  : Number(delayMinutes) * DELAY_UNIT_TO_MINUTES[delayUnit]
                : null,
            actual_cost: Number(actualCostDigits),
            resolution_type: null,
            notes: notesToSend || null,
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
              {delayLabels(delayBaseline).late}
            </label>
          </div>
          {touched && missingOnTime && <span className="field-error">Vui lòng chọn đúng giờ hay muộn giờ.</span>}
        </div>
      )}

      {showDelayInput && !rejection && (
        <div className="form-field">
          <label>Mốc thời gian tham chiếu</label>
          <div className="radio-group">
            <label className={`radio-option ${delayBaseline === "original" ? "selected" : ""}`}>
              <input
                type="radio"
                checked={delayBaseline === "original"}
                onChange={() => setDelayBaseline("original")}
              />
              Kế hoạch/SLA ban đầu
            </label>
            <label className={`radio-option ${delayBaseline === "agreed_new" ? "selected" : ""}`}>
              <input
                type="radio"
                checked={delayBaseline === "agreed_new"}
                onChange={() => setDelayBaseline("agreed_new")}
              />
              Giờ/địa điểm mới đã thống nhất với khách
            </label>
          </div>
          <span className="hint">Chỉ ảnh hưởng CÁCH HỎI ở đây, không gửi lên hệ thống — tự nhớ khi đọc lại ghi chú.</span>
        </div>
      )}

      {showDelayInput && (
        <div className="form-field">
          <label>
            {rejection ? "Trễ bao nhiêu phút so với lần giao đầu tiên?" : delayLabels(delayBaseline).delayLabel}
            {rejection ? <span className="hint"> (không bắt buộc)</span> : <span className="required-mark"> *</span>}
          </label>
          {!rejection && (
            <label style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
              <input
                type="checkbox"
                checked={delayUnknown}
                onChange={(e) => {
                  setDelayUnknown(e.target.checked);
                  if (e.target.checked) setDelayMinutes("");
                }}
              />
              Không xác định được chính xác (ghi rõ lý do ở Ghi chú bên dưới)
            </label>
          )}
          {!delayUnknown && (
            <div style={{ display: "flex", gap: 8 }}>
              <input
                type="number"
                min={1}
                step={1}
                value={delayMinutes}
                onFocus={(e) => e.target.select()}
                onChange={(e) => setDelayMinutes(e.target.value.replace(/\D/g, ""))}
              />
              {!rejection && (
                // Đổi đơn vị giữa chừng thì XOÁ số đã gõ (coi như gõ lại từ đầu)
                // thay vì tự quy đổi qua lại — tránh làm tròn sai lệch âm thầm.
                <select
                  value={delayUnit}
                  onChange={(e) => {
                    setDelayUnit(e.target.value as DelayUnit);
                    setDelayMinutes("");
                  }}
                >
                  <option value="minutes">phút</option>
                  <option value="hours">giờ</option>
                  <option value="days">ngày</option>
                </select>
              )}
            </div>
          )}
          {touched && missingDelay && (
            <span className="field-error">
              {delayUnknown
                ? "Ghi rõ lý do ở Ghi chú khi không xác định được số phút trễ."
                : "Nhập số lớn hơn 0."}
            </span>
          )}
        </div>
      )}

      <div className="form-field">
        <label>
          Chi phí thực tế (VNĐ) <span className="required-mark">*</span>
        </label>
        {/* onFocus select-all: SỬA 1 kết quả đã có sẵn chi phí mà gõ đè thì số
            mới bị CHÈN vào giữa số cũ ("222" + gõ "250000" -> 222.250.000) chứ
            không thay thế — không phải lỗi định dạng/con trỏ (logic đó đã fix ở
            đợt 9). Mọi ô số khác trong 2 form đều đã có dòng này, riêng ô này
            thiếu. */}
        <input
          ref={costInputRef}
          inputMode="numeric"
          value={groupThousands(actualCostDigits)}
          placeholder="VD: 180.000"
          onFocus={(e) => e.target.select()}
          onChange={handleCostChange}
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
