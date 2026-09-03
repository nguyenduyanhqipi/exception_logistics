// Popup xác nhận 2 lựa chọn Có/Không cho các hành động xoá (việc 4, việc 5).
// Dùng thay cho `window.confirm` vì confirm của trình duyệt chỉ có OK/Cancel
// tiếng Anh theo locale máy, không đặt được nhãn "Có"/"Không" như yêu cầu.

interface ConfirmDialogProps {
  title: string;
  message: string;
  /** Nhãn nút đồng ý — mặc định "Có". */
  confirmLabel?: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  title,
  message,
  confirmLabel = "Có",
  busy = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <h3 className="modal-title">{title}</h3>
        <p className="modal-message">{message}</p>
        <div className="modal-actions">
          <button type="button" className="danger" disabled={busy} onClick={onConfirm}>
            {busy ? "Đang xử lý..." : confirmLabel}
          </button>
          <button type="button" className="secondary" disabled={busy} onClick={onCancel}>
            Không
          </button>
        </div>
      </div>
    </div>
  );
}
