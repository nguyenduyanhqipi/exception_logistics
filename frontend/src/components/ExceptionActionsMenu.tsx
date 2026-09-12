import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { apiClient, apiErrorMessage } from "../api/client";
import { ConfirmDialog } from "./ConfirmDialog";

// Menu 3 chấm Sửa/Xoá cho 1 ngoại lệ (việc 5). Dùng chung ở Dashboard,
// /history và ExceptionDetail.
//
// Ẩn ĐÚNG ở `resolved` — khớp lại ranh giới backend
// (api/exceptions.py::_load_editable_exception): đã có kết quả thực tế thì
// thôi, vì `outcomes.decision_id` là FK NOT NULL, xoá quyết định là mất luôn
// số liệu KPI đã chốt.
//
// TRƯỚC ĐÂY file này còn ẩn cả ở `awaiting_outcome` với lý do "đã có
// decisions.selected_option_id trỏ vào 1 option, xoá là vỡ khoá ngoại". Lý do
// đó hết hiệu lực từ Quyết định 4 (2026-09-08): backend nới tới
// `awaiting_outcome` và tự huỷ quyết định treo bằng `_discard_pending_decision()`
// trước khi xoá option/ngoại lệ. Frontend quên cập nhật theo nên dispatcher lỡ
// bấm xác nhận phương án cho 1 ngoại lệ nhập nhầm là hết đường sửa/xoá.

interface ExceptionActionsMenuProps {
  exceptionId: string;
  status: string;
  subTypeLabel: string;
  /** Gọi sau khi xoá xong — thường để điều hướng khỏi trang chi tiết. */
  onDeleted?: () => void;
}

export function ExceptionActionsMenu({ exceptionId, status, subTypeLabel, onDeleted }: ExceptionActionsMenuProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wrapRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  if (status === "resolved") return null;

  async function handleDelete() {
    setBusy(true);
    setError(null);
    try {
      await apiClient.delete(`/api/exceptions/${exceptionId}`);
      setConfirming(false);
      queryClient.invalidateQueries({ queryKey: ["dashboard-today"] });
      queryClient.invalidateQueries({ queryKey: ["exceptions-history"] });
      queryClient.invalidateQueries({ queryKey: ["exception", exceptionId] });
      onDeleted?.();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="row-menu" ref={wrapRef} onClick={(e) => e.stopPropagation()}>
      <button
        type="button"
        className="row-menu-trigger"
        title="Thao tác khác"
        aria-label="Thao tác khác"
        onClick={() => setOpen((v) => !v)}
      >
        ⋯
      </button>
      {open && (
        <span className="row-menu-list">
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              navigate(`/exceptions/${exceptionId}/edit`);
            }}
          >
            Sửa
          </button>
          <button
            type="button"
            className="row-menu-danger"
            onClick={() => {
              setOpen(false);
              setConfirming(true);
            }}
          >
            Xoá
          </button>
        </span>
      )}
      {error && <span className="row-menu-error">{error}</span>}
      {confirming && (
        <ConfirmDialog
          title="Xoá ngoại lệ này?"
          message={`Ngoại lệ "${subTypeLabel}" sẽ bị xoá khỏi danh sách (xoá mềm, dữ liệu vẫn còn trong hệ thống để đối chiếu). Bạn có chắc không?`}
          confirmLabel="Có, xoá"
          busy={busy}
          onConfirm={handleDelete}
          onCancel={() => setConfirming(false)}
        />
      )}
    </span>
  );
}
