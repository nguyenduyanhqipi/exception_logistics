import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiClient, apiErrorMessage } from "../api/client";
import type { ExceptionGroupDetail } from "../api/types";
import { usePolling } from "../hooks/usePolling";
import { OptionList } from "../components/OptionList";
import { ResolutionPanel } from "../components/ResolutionPanel";
import { subTypeLabel } from "../labels";
import { EXCEPTION_STATUS_LABEL, SEVERITY_LABEL } from "../statusLabels";

export function ExceptionGroup() {
  const { groupId } = useParams<{ groupId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState<string | null>(null);
  const [overrideNote, setOverrideNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["exception-group", groupId],
    queryFn: async () => (await apiClient.get<ExceptionGroupDetail>(`/api/exceptions/groups/${groupId}`)).data,
    enabled: !!groupId,
  });

  const jobActive = data?.job?.status === "pending" || data?.job?.status === "running";
  usePolling(() => refetch(), 2000, jobActive);

  if (isLoading || !data) return <div className="loading-spinner">Đang tải...</div>;

  async function handleConfirm(optionId: string) {
    setError(null);
    setConfirming(optionId);
    try {
      await apiClient.post("/api/decisions", {
        group_id: groupId,
        selected_option_id: optionId,
        override_note: overrideNote || null,
      });
      // Giống trang chi tiết ngoại lệ đơn (việc 2): xác nhận xong về thẳng
      // Dashboard, nhập kết quả thực tế là một lượt riêng.
      queryClient.invalidateQueries({ queryKey: ["dashboard-today"] });
      queryClient.invalidateQueries({ queryKey: ["exceptions-history"] });
      navigate("/");
    } catch (err) {
      setError(apiErrorMessage(err));
      setConfirming(null);
    }
  }

  const decided = data.status === "awaiting_outcome" || data.status === "resolved";

  return (
    <div className="page">
      <h1>Nhóm ngoại lệ liên quan ({data.exceptions.length} ngoại lệ)</h1>
      <p style={{ color: "#6b7280" }}>
        Các ngoại lệ dưới đây dùng chung tài nguyên (cùng xe/tài xế/điểm giao hoặc cùng cần xe thay thế) nên được xử lý bằng
        <strong> một quyết định phối hợp duy nhất</strong> thay vì 2 kế hoạch độc lập giẫm chân nhau.
      </p>

      {error && <div className="error-banner">{error}</div>}

      {data.exceptions.map((exc) => (
        <div key={exc.exception_id} className="card">
          <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
            <strong>Xe {exc.vehicle_id}</strong>
            <span>{subTypeLabel(exc.sub_type)}</span>
            {exc.severity && (
              <span className={`badge badge-${exc.severity}`}>{SEVERITY_LABEL[exc.severity] ?? exc.severity}</span>
            )}
            <span>{exc.area}</span>
            <span className={`badge badge-${exc.status}`}>{EXCEPTION_STATUS_LABEL[exc.status] ?? exc.status}</span>
          </div>
          {exc.description && <p style={{ color: "#4b5563", marginTop: 8 }}>{exc.description}</p>}
        </div>
      ))}

      {!decided && (
        <div className="card">
          <h2>Phương án xử lý phối hợp</h2>
          {jobActive && <div className="loading-spinner">Đang chờ AI phân tích... (trang tự làm mới)</div>}
          {data.job?.status === "failed" && <div className="error-banner">Job xử lý bị lỗi: {data.job.error}</div>}
          {data.job?.error && data.job.status === "done" && (
            <div className="error-banner">AI không khả dụng lúc phân tích: {data.job.error}. Vui lòng đánh giá và chọn phương án phù hợp.</div>
          )}

          {!jobActive && (
            <OptionList
              options={data.options}
              confirming={confirming}
              onConfirm={handleConfirm}
              overrideNote={overrideNote}
              onOverrideNoteChange={setOverrideNote}
            />
          )}
        </div>
      )}

      {decided && (
        <ResolutionPanel
          decision={data.decision}
          outcome={data.outcome}
          invalidateKeys={[["exception-group", groupId], ["dashboard-today"], ["exceptions-history"]]}
        />
      )}
    </div>
  );
}
