import type { OptionItem } from "../api/types";

// Phương án "giả" do worker sinh khi AI lỗi/hết hạn mức (mục 8) — khớp đúng
// `MANUAL_FALLBACK_DESCRIPTION` ở backend/worker/job_processor.py. Nó chỉ là
// chỗ giữ chỗ để dispatcher có option_id mà ghi đè, KHÔNG phải phương án thật:
// xác nhận nó = chốt một "quyết định" rỗng rồi tính vào KPI như thật, nên ẩn
// hẳn nút xác nhận trên đúng thẻ này (việc 4, 2026-09-04).
const FALLBACK_PREFIX = "[AI không khả dụng]";

function isAiFallback(opt: OptionItem): boolean {
  return opt.description.startsWith(FALLBACK_PREFIX);
}

interface Props {
  options: OptionItem[];
  confirming: string | null;
  onConfirm: (optionId: string) => void;
  overrideNote: string;
  onOverrideNoteChange: (note: string) => void;
}

export function OptionList({ options, confirming, onConfirm, overrideNote, onOverrideNoteChange }: Props) {
  if (options.length === 0) {
    return <p style={{ color: "#6b7280" }}>Chưa có phương án nào.</p>;
  }

  const sorted = [...options].sort((a, b) => (a.rank ?? 999) - (b.rank ?? 999));
  const allFallback = sorted.every(isAiFallback);

  return (
    <div>
      {sorted.map((opt) => (
        <div key={opt.option_id} className={`option-card ${opt.rank === 1 ? "best" : ""}`}>
          {opt.rank && <div className="option-rank">{opt.rank === 1 ? "★ Đề xuất tốt nhất" : `Xếp hạng #${opt.rank}`}</div>}
          <p>{opt.description}</p>
          <div className="option-meta">
            {opt.cost_estimate !== null && <span>Chi phí: {opt.cost_estimate.toLocaleString("vi-VN")}đ</span>}
            {opt.time_estimate_minutes !== null && <span>Thời gian: {opt.time_estimate_minutes} phút</span>}
            {opt.sla_risk_remaining !== null && <span>Rủi ro SLA: {(opt.sla_risk_remaining * 100).toFixed(0)}%</span>}
          </div>
          {opt.llm_explanation && <div className="option-explanation">{opt.llm_explanation}</div>}
          {isAiFallback(opt) ? (
            <div className="drill-muted" style={{ marginTop: 10 }}>
              Đây không phải phương án xử lý — hãy bấm "Thử lại phân tích AI" hoặc "Tự nhập phương án khác" bên dưới.
            </div>
          ) : (
            <button
              type="button"
              className="primary"
              style={{ marginTop: 10 }}
              disabled={confirming === opt.option_id}
              onClick={() => onConfirm(opt.option_id)}
            >
              {confirming === opt.option_id ? "Đang xác nhận..." : "Chọn phương án này"}
            </button>
          )}
        </div>
      ))}
      <div className="form-field" hidden={allFallback}>
        <label>Ghi chú nếu ghi đè đề xuất (tuỳ chọn)</label>
        <input value={overrideNote} onChange={(e) => onOverrideNoteChange(e.target.value)} placeholder="VD: chọn phương án khác vì lý do..." />
      </div>
    </div>
  );
}
