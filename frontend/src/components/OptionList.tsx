import type { OptionItem } from "../api/types";

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
          <button
            type="button"
            className="primary"
            style={{ marginTop: 10 }}
            disabled={confirming === opt.option_id}
            onClick={() => onConfirm(opt.option_id)}
          >
            {confirming === opt.option_id ? "Đang xác nhận..." : "Chọn phương án này"}
          </button>
        </div>
      ))}
      <div className="form-field">
        <label>Ghi chú nếu ghi đè đề xuất (tuỳ chọn)</label>
        <input value={overrideNote} onChange={(e) => onOverrideNoteChange(e.target.value)} placeholder="VD: chọn phương án khác vì lý do..." />
      </div>
    </div>
  );
}
