import { useState } from "react";
import type { DecisionInfo, OutcomeInfo } from "../api/types";
import { OutcomeForm, formatVnd, resolutionTypeLabel } from "./OutcomeForm";

// Khối "Phương án đã chọn + Quyết định + Kết quả thực tế" (việc 3, 2026-09-04).
//
// Trước đây ngoại lệ đã xử lý xong chỉ hiện đúng 1 dòng banner "Ngoại lệ đã
// được xử lý xong." — không đủ để quản lý đối chiếu hay nhân viên làm bằng
// chứng. Dùng chung cho trang chi tiết ngoại lệ và trang nhóm combined mode.

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

interface ResolutionPanelProps {
  decision: DecisionInfo | null;
  outcome: OutcomeInfo | null;
  /** sub_type của (các) ngoại lệ thuộc quyết định này — quyết định form nhập kết
   *  quả dùng kiểu nào (xem OutcomeForm.tsx::isRejectionOutcome). */
  subTypes: string[];
  /** Query key cần làm mới sau khi lưu kết quả. */
  invalidateKeys: unknown[][];
}

export function ResolutionPanel({ decision, outcome, subTypes, invalidateKeys }: ResolutionPanelProps) {
  const [entering, setEntering] = useState(false);
  const [editingOutcome, setEditingOutcome] = useState(false);

  if (!decision) return null;
  const option = decision.selected_option;

  return (
    <>
      <div className="card">
        <h2 style={{ marginTop: 0 }}>Phương án đã chọn</h2>
        {option ? (
          <>
            <p style={{ marginTop: 0, fontSize: 15 }}>{option.description}</p>
            <dl className="drill-dl">
              <div>
                <dt>Chi phí ước tính</dt>
                <dd>{formatVnd(option.cost_estimate)}</dd>
              </div>
              <div>
                <dt>Thời gian ước tính</dt>
                <dd>{option.time_estimate_minutes != null ? `${option.time_estimate_minutes} phút` : "-"}</dd>
              </div>
              <div>
                <dt>Rủi ro SLA còn lại</dt>
                <dd>
                  {option.sla_risk_remaining != null ? `${Math.round(option.sla_risk_remaining * 100)}%` : "-"}
                </dd>
              </div>
              <div>
                <dt>Điểm xếp hạng</dt>
                <dd>{option.score != null ? option.score.toFixed(3) : "-"}</dd>
              </div>
            </dl>
            {option.llm_explanation && (
              <div className="resolution-note">
                <div className="drill-muted" style={{ marginBottom: 4 }}>
                  Lý do AI đề xuất:
                </div>
                {option.llm_explanation}
              </div>
            )}
          </>
        ) : (
          <div className="drill-muted">Không tìm thấy phương án đã chọn.</div>
        )}

        <div className="resolution-sep" />
        <dl className="drill-dl">
          <div>
            <dt>Người xác nhận</dt>
            <dd>{decision.confirmed_by_name ?? "-"}</dd>
          </div>
          <div>
            <dt>Thời điểm xác nhận</dt>
            <dd>{formatDateTime(decision.confirmed_at)}</dd>
          </div>
          <div>
            <dt>Phạm vi</dt>
            <dd>{decision.is_group_decision ? "Quyết định phối hợp cho cả nhóm" : "Ngoại lệ đơn lẻ"}</dd>
          </div>
        </dl>
        {decision.override_note && (
          <div className="resolution-note">
            <div className="drill-muted" style={{ marginBottom: 4 }}>
              Ghi chú khi chọn khác đề xuất (override):
            </div>
            {decision.override_note}
          </div>
        )}
      </div>

      <div className="card">
        <h2 style={{ marginTop: 0 }}>Kết quả thực tế</h2>

        {!outcome && !entering && (
          <>
            <div className="warning-banner">
              Chưa có kết quả thực tế. Ngoại lệ chỉ được tính là đã xử lý xong sau khi nhập kết quả.
            </div>
            <button type="button" className="primary" onClick={() => setEntering(true)}>
              Nhập kết quả
            </button>
          </>
        )}

        {!outcome && entering && (
          <OutcomeForm
            decisionId={decision.decision_id}
            subTypes={subTypes}
            onDone={() => setEntering(false)}
            onCancel={() => setEntering(false)}
            invalidateKeys={invalidateKeys}
          />
        )}

        {outcome && !editingOutcome && (
          <>
            <dl className="drill-dl">
              <div>
                {/* Kết quả kiểu "khách từ chối nhận hàng" không có khái niệm đúng
                    giờ/muộn giờ — hiện đúng thứ đã hỏi thay vì in "-" khó hiểu. */}
                <dt>{outcome.resolution_type ? "Kết quả cuối cùng" : "Giao hàng"}</dt>
                <dd>
                  {outcome.resolution_type ? (
                    <>
                      <span className="badge">{resolutionTypeLabel(outcome.resolution_type)}</span>
                      {outcome.delay_minutes != null && ` · trễ ${outcome.delay_minutes} phút so với lần giao đầu`}
                    </>
                  ) : (
                    <>
                      {outcome.delivered_on_time === true && <span className="badge badge-ok">Đúng giờ</span>}
                      {outcome.delivered_on_time === false && (
                        <span className="badge badge-serious">
                          Muộn giờ{outcome.delay_minutes != null ? ` · ${outcome.delay_minutes} phút` : ""}
                        </span>
                      )}
                      {outcome.delivered_on_time === null && "-"}
                    </>
                  )}
                </dd>
              </div>
              <div>
                <dt>Chi phí thực tế</dt>
                <dd>{formatVnd(outcome.actual_cost)}</dd>
              </div>
              <div>
                <dt>Người nhập</dt>
                <dd>{outcome.recorded_by_name ?? "-"}</dd>
              </div>
              <div>
                <dt>Thời điểm nhập</dt>
                <dd>{formatDateTime(outcome.recorded_at)}</dd>
              </div>
            </dl>
            {outcome.notes && (
              <div className="resolution-note">
                <div className="drill-muted" style={{ marginBottom: 4 }}>
                  Ghi chú:
                </div>
                {outcome.notes}
              </div>
            )}
            {/* Gap 1 (đợt code 5): hết hạn khoá sửa thì ẨN HẲN nút, không phải làm
                mờ — nút mờ vẫn khiến người dùng đi tìm cách bấm cho được. Trạng
                thái này do backend tính (`editable`), frontend không tự suy. */}
            {outcome.editable ? (
              <div style={{ marginTop: 12 }}>
                <button type="button" className="secondary" onClick={() => setEditingOutcome(true)}>
                  Sửa kết quả
                </button>
              </div>
            ) : (
              <div className="drill-muted" style={{ marginTop: 12 }}>
                Đã quá hạn sửa kết quả theo cấu hình của công ty — số liệu này đã chốt vào KPI.
              </div>
            )}
          </>
        )}

        {outcome && editingOutcome && (
          <OutcomeForm
            decisionId={decision.decision_id}
            subTypes={subTypes}
            existing={outcome}
            onDone={() => setEditingOutcome(false)}
            onCancel={() => setEditingOutcome(false)}
            invalidateKeys={invalidateKeys}
          />
        )}
      </div>
    </>
  );
}
