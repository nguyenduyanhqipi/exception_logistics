import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiClient, apiErrorMessage } from "../api/client";
import type { ExceptionDetail as ExceptionDetailType } from "../api/types";
import { usePolling } from "../hooks/usePolling";
import { OptionList } from "../components/OptionList";
import { OutcomeForm } from "../components/OutcomeForm";
import { ExceptionActionsMenu } from "../components/ExceptionActionsMenu";
import { subTypeLabel } from "../labels";

export function ExceptionDetail() {
  const { exceptionId } = useParams<{ exceptionId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState<string | null>(null);
  const [overrideNote, setOverrideNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [decisionId, setDecisionId] = useState<string | null>(null);

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["exception", exceptionId],
    queryFn: async () => (await apiClient.get<ExceptionDetailType>(`/api/exceptions/${exceptionId}`)).data,
    enabled: !!exceptionId,
  });

  const jobActive = data?.job?.status === "pending" || data?.job?.status === "running";
  usePolling(() => refetch(), 2000, jobActive);

  if (isLoading || !data) return <div className="loading-spinner">Đang tải...</div>;

  if (data.group_id) {
    navigate(`/exception-groups/${data.group_id}`, { replace: true });
    return null;
  }

  async function handleConfirm(optionId: string) {
    setError(null);
    setConfirming(optionId);
    try {
      const res = await apiClient.post("/api/decisions", {
        exception_id: exceptionId,
        selected_option_id: optionId,
        override_note: overrideNote || null,
      });
      setDecisionId(res.data.decision_id);
      queryClient.invalidateQueries({ queryKey: ["exception", exceptionId] });
      refetch();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setConfirming(null);
    }
  }

  return (
    <div className="page">
      <h1 style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span>
          Ngoại lệ: {subTypeLabel(data.sub_type)} — Xe {data.vehicle_id ?? "-"}
        </span>
        <ExceptionActionsMenu
          exceptionId={exceptionId!}
          status={data.status}
          subTypeLabel={subTypeLabel(data.sub_type)}
          onDeleted={() => navigate("/")}
        />
      </h1>

      {error && <div className="error-banner">{error}</div>}

      <div className="card">
        <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
          <div>
            <strong>Mức độ:</strong> {data.severity && <span className={`badge badge-${data.severity}`}>{data.severity}</span>}
          </div>
          <div>
            <strong>Trạng thái:</strong> <span className={`badge badge-${data.status}`}>{data.status}</span>
          </div>
          <div>
            <strong>Khu vực:</strong> {data.area ?? "-"}
          </div>
        </div>
        {data.description && (
          <p style={{ marginTop: 10, color: "#4b5563" }}>{data.description}</p>
        )}
      </div>

      {data.impact_analysis && data.impact_analysis.affected_stops.length > 0 && (
        <div className="card">
          <h2>Tác động</h2>
          <table className="stops-mini-table">
            <thead>
              <tr>
                <th>Đơn hàng</th>
                <th>Giờ đến dự kiến mới (ETA)</th>
                <th>Hạn chót (SLA)</th>
                <th>Trễ (phút)</th>
                <th>Vi phạm SLA?</th>
              </tr>
            </thead>
            <tbody>
              {data.impact_analysis.affected_stops.map((s) => (
                <tr key={s.stop_id}>
                  <td>{s.order_id}</td>
                  <td>{s.new_eta}</td>
                  <td>{s.sla_deadline}</td>
                  <td>{s.delay_minutes}</td>
                  <td>{s.sla_breach ? "⚠️ Có" : "Không"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="card">
        <h2>Phương án xử lý</h2>
        {jobActive && <div className="loading-spinner">Đang chờ AI phân tích... (trang tự làm mới)</div>}
        {data.job?.status === "failed" && <div className="error-banner">Job xử lý bị lỗi: {data.job.error}</div>}
        {data.job?.error && data.job.status === "done" && (
          <div className="error-banner">AI không khả dụng lúc phân tích: {data.job.error}. Vui lòng đánh giá và chọn/nhập phương án thủ công bên dưới.</div>
        )}

        {!jobActive && data.status !== "resolved" && (
          <>
            <OptionList
              options={data.options}
              confirming={confirming}
              onConfirm={handleConfirm}
              overrideNote={overrideNote}
              onOverrideNoteChange={setOverrideNote}
            />
            <ManualOptionForm exceptionId={exceptionId!} onAdded={() => refetch()} />
          </>
        )}

        {data.status === "resolved" && (
          <div className="success-banner">Ngoại lệ đã được xử lý xong.</div>
        )}
      </div>

      {decisionId && <OutcomeForm decisionId={decisionId} />}
    </div>
  );
}

function ManualOptionForm({ exceptionId, onAdded }: { exceptionId: string; onAdded: () => void }) {
  const [description, setDescription] = useState("");
  const [cost, setCost] = useState("");
  const [minutes, setMinutes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await apiClient.post(`/api/exceptions/${exceptionId}/manual-option`, {
        description,
        cost_estimate: cost ? Number(cost) : null,
        time_estimate_minutes: minutes ? Number(minutes) : null,
      });
      setDescription("");
      setCost("");
      setMinutes("");
      setOpen(false);
      onAdded();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) {
    return (
      <button type="button" className="secondary" onClick={() => setOpen(true)}>
        + Tự nhập phương án khác
      </button>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="card" style={{ background: "#f9fafb" }}>
      {error && <div className="error-banner">{error}</div>}
      <div className="form-field">
        <label>Mô tả phương án</label>
        <textarea required value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
      </div>
      <div style={{ display: "flex", gap: 12 }}>
        <div className="form-field" style={{ flex: 1 }}>
          <label>Chi phí ước tính (VNĐ)</label>
          <input type="number" value={cost} onChange={(e) => setCost(e.target.value)} />
        </div>
        <div className="form-field" style={{ flex: 1 }}>
          <label>Thời gian ước tính (phút)</label>
          <input type="number" value={minutes} onChange={(e) => setMinutes(e.target.value)} />
        </div>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <button type="submit" className="primary" disabled={submitting}>
          Thêm phương án
        </button>
        <button type="button" className="secondary" onClick={() => setOpen(false)}>
          Hủy
        </button>
      </div>
    </form>
  );
}
