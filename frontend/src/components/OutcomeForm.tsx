import { useState, type FormEvent } from "react";
import { apiClient, apiErrorMessage } from "../api/client";

export function OutcomeForm({ decisionId }: { decisionId: string }) {
  const [deliveredOnTime, setDeliveredOnTime] = useState<boolean | null>(null);
  const [actualCost, setActualCost] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await apiClient.post("/api/outcomes", {
        decision_id: decisionId,
        delivered_on_time: deliveredOnTime,
        actual_cost: actualCost ? Number(actualCost) : null,
        notes: notes || null,
      });
      setSubmitted(true);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (submitted) {
    return <div className="success-banner">Đã ghi nhận kết quả thực tế. Cảm ơn bạn!</div>;
  }

  return (
    <form onSubmit={handleSubmit} className="card">
      <h2>Nhập kết quả thực tế</h2>
      {error && <div className="error-banner">{error}</div>}
      <div className="form-field">
        <label>Giao hàng đúng hạn?</label>
        <div className="radio-group">
          <label className={`radio-option ${deliveredOnTime === true ? "selected" : ""}`}>
            <input type="radio" checked={deliveredOnTime === true} onChange={() => setDeliveredOnTime(true)} />
            Đúng hạn
          </label>
          <label className={`radio-option ${deliveredOnTime === false ? "selected" : ""}`}>
            <input type="radio" checked={deliveredOnTime === false} onChange={() => setDeliveredOnTime(false)} />
            Trễ hạn
          </label>
        </div>
      </div>
      <div className="form-field">
        <label>Chi phí thực tế (VNĐ)</label>
        <input type="number" value={actualCost} onChange={(e) => setActualCost(e.target.value)} />
      </div>
      <div className="form-field">
        <label>Ghi chú</label>
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
      </div>
      <button type="submit" className="primary" disabled={submitting}>
        {submitting ? "Đang lưu..." : "Lưu kết quả"}
      </button>
    </form>
  );
}
