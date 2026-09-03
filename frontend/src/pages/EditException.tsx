import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiClient, apiErrorMessage } from "../api/client";
import type { ExceptionDetail, Schedule } from "../api/types";
import {
  ANSWER_TO_SUBTYPE,
  EXTRA_FIELD,
  GROUP_QUESTIONS,
  SUBTYPE_TO_ANSWER,
  showsCustomerDelayTolerance,
} from "../exceptionForm";

// Form SỬA 1 ngoại lệ đã tạo (việc 5). Dùng CHUNG bộ câu hỏi với form tạo
// (exceptionForm.ts) nhưng KHÔNG cho đổi chuyến: đổi `schedule_id` không phải
// "sửa thông tin nhập sai" mà là một ngoại lệ khác hẳn — backend cũng không
// nhận field đó (schemas/exception.py::ExceptionUpdate).

export function EditException() {
  const { exceptionId } = useParams<{ exceptionId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["exception", exceptionId],
    queryFn: async () => (await apiClient.get<ExceptionDetail>(`/api/exceptions/${exceptionId}`)).data,
    enabled: !!exceptionId,
  });

  const { data: schedules } = useQuery({
    queryKey: ["schedules"],
    queryFn: async () => (await apiClient.get<Schedule[]>("/api/schedules")).data,
  });
  const schedule = useMemo(
    () => schedules?.find((s) => s.schedule_id === data?.schedule_id),
    [schedules, data?.schedule_id],
  );

  const [group, setGroup] = useState("");
  const [answerKey, setAnswerKey] = useState("");
  const [depotOnTime, setDepotOnTime] = useState<boolean | null>(null);
  const [hasInjury, setHasInjury] = useState<boolean | null>(null);
  const [extraValue, setExtraValue] = useState("");
  const [fromStopOrder, setFromStopOrder] = useState<number | "">("");
  const [affectsWholeRoute, setAffectsWholeRoute] = useState(true);
  const [toStopOrder, setToStopOrder] = useState<number | "">("");
  const [delayMinutes, setDelayMinutes] = useState("0");
  const [area, setArea] = useState("");
  const [description, setDescription] = useState("");
  const [customerAcceptedDelayAnswer, setCustomerAcceptedDelayAnswer] = useState<"" | "yes" | "no" | "unknown">("");
  const [customerAcceptedDelayMinInput, setCustomerAcceptedDelayMinInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  // Nạp giá trị hiện tại vào form đúng 1 lần. `input_context` là nguồn chính
  // (lưu nguyên tín hiệu đã nhập lúc tạo); ngoại lệ tạo TRƯỚC khi có cột đó
  // thì suy `group`/`answer_key` ngược từ `sub_type` (ánh xạ song ánh) và để
  // trống các ô số liệu — banner bên dưới nhắc người dùng nhập lại.
  useEffect(() => {
    if (!data || loaded) return;
    const ctx = (data.input_context ?? {}) as Record<string, unknown>;
    const fallback = SUBTYPE_TO_ANSWER[data.sub_type];
    const g = (ctx.exception_group as string) || data.exception_group || fallback?.group || "";
    const a = (ctx.answer_key as string) || fallback?.answerKey || "";
    setGroup(g);
    setAnswerKey(a);
    setDepotOnTime(typeof ctx.depot_on_time === "boolean" ? ctx.depot_on_time : null);
    setHasInjury(typeof ctx.has_injury === "boolean" ? ctx.has_injury : null);

    const subType = a && g ? ANSWER_TO_SUBTYPE[g]?.[a] : null;
    const ef = subType ? EXTRA_FIELD[subType] : null;
    const rawExtra = ef ? ctx[ef.key] : null;
    setExtraValue(rawExtra === null || rawExtra === undefined ? "" : String(rawExtra));

    setFromStopOrder(typeof ctx.from_stop_order === "number" ? ctx.from_stop_order : "");
    const to = ctx.to_stop_order;
    setAffectsWholeRoute(to === null || to === undefined);
    setToStopOrder(typeof to === "number" ? to : "");
    setDelayMinutes(typeof ctx.delay_minutes === "number" ? String(ctx.delay_minutes) : "0");

    setArea(data.area ?? "");
    // Ghi chú người dùng gõ nằm ở `input_context.description`;
    // `data.description` đã bị nối thêm `description_note` do rule engine sinh.
    setDescription((ctx.description as string) ?? data.description ?? "");
    if (data.customer_accepted_delay_min !== null && data.customer_accepted_delay_min !== undefined) {
      setCustomerAcceptedDelayAnswer("yes");
      setCustomerAcceptedDelayMinInput(String(data.customer_accepted_delay_min));
    }
    setLoaded(true);
  }, [data, loaded]);

  const subType = group && answerKey ? ANSWER_TO_SUBTYPE[group]?.[answerKey] : null;
  const extraField = subType ? EXTRA_FIELD[subType] : null;
  const showDepotFollowUp = subType === "late_departure" && !!schedule?.planned_departure_time;
  const showInjuryFollowUp = subType === "accident";
  const showCustomerDelayTolerance = showsCustomerDelayTolerance(group);
  const missingContext = !!data && !data.input_context;

  function resetGroupChoice(newGroup: string) {
    setGroup(newGroup);
    setAnswerKey("");
    setDepotOnTime(null);
    setHasInjury(null);
    setExtraValue("");
    setCustomerAcceptedDelayAnswer("");
    setCustomerAcceptedDelayMinInput("");
    setAffectsWholeRoute(newGroup !== "customer_reject" && newGroup !== "customer_change");
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!group || !answerKey || fromStopOrder === "") return;
    setError(null);
    setSubmitting(true);
    try {
      const payload: Record<string, unknown> = {
        exception_group: group,
        answer_key: answerKey,
        from_stop_order: fromStopOrder,
        to_stop_order: affectsWholeRoute ? null : toStopOrder || null,
        delay_minutes: Number(delayMinutes) || 0,
        area: area || null,
        description: description || null,
      };
      if (depotOnTime !== null) payload.depot_on_time = depotOnTime;
      if (hasInjury !== null) payload.has_injury = hasInjury;
      if (extraField && extraValue !== "") {
        payload[extraField.key] = extraField.type === "boolean" ? extraValue === "true" : Number(extraValue);
      }
      if (showCustomerDelayTolerance && customerAcceptedDelayAnswer === "yes" && customerAcceptedDelayMinInput !== "") {
        payload.customer_accepted_delay_min = Number(customerAcceptedDelayMinInput) || 0;
      }

      await apiClient.put(`/api/exceptions/${exceptionId}`, payload);
      queryClient.invalidateQueries({ queryKey: ["exception", exceptionId] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-today"] });
      queryClient.invalidateQueries({ queryKey: ["exceptions-history"] });
      navigate(`/exceptions/${exceptionId}`);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (isLoading) return <div className="loading-spinner">Đang tải...</div>;
  if (isError || !data) {
    return (
      <div className="page">
        <h1>Sửa ngoại lệ</h1>
        <div className="card">
          <div className="error-banner">Không tải được ngoại lệ này.</div>
        </div>
      </div>
    );
  }

  if (data.status === "resolved") {
    return (
      <div className="page">
        <h1>Sửa ngoại lệ</h1>
        <div className="card">
          <div className="error-banner">
            Ngoại lệ này đã xử lý xong (resolved) — không sửa được nữa để giữ đúng số liệu KPI đã chốt.
          </div>
          <button type="button" className="secondary" onClick={() => navigate(-1)}>
            Quay lại
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <h1>Sửa ngoại lệ — Xe {data.vehicle_id ?? "-"}</h1>
      <form onSubmit={handleSubmit} className="card">
        {error && <div className="error-banner">{error}</div>}
        <div className="success-banner" style={{ background: "#eff6ff", color: "#1e40af", borderColor: "#bfdbfe" }}>
          Lưu xong, hệ thống sẽ tính lại mức độ nghiêm trọng và cho AI phân tích lại từ đầu — các phương án cũ
          (dựa trên thông tin sai) sẽ bị bỏ.
        </div>
        {missingContext && (
          <div className="error-banner" style={{ background: "#fffbeb", color: "#92400e", borderColor: "#fde68a" }}>
            Ngoại lệ này được tạo trước khi hệ thống lưu lại các số liệu đã nhập, nên một số ô bên dưới đang trống.
            Vui lòng điền lại đúng số liệu trước khi lưu — để trống đồng nghĩa với "không có số liệu đó" và mức độ
            nghiêm trọng sẽ được tính lại mà thiếu tín hiệu này.
          </div>
        )}

        {schedule && (
          <div className="form-field">
            <label>Chuyến (không đổi được)</label>
            <div className="drill-muted">
              {schedule.vehicle_id} — {schedule.shift_date} {schedule.shift_label} (chuyến {schedule.trip_sequence})
            </div>
          </div>
        )}

        <div className="form-field">
          <label>1. Loại ngoại lệ</label>
          <div className="radio-group">
            {Object.entries(GROUP_QUESTIONS).map(([key, cfg]) => (
              <label key={key} className={`radio-option ${group === key ? "selected" : ""}`}>
                <input type="radio" name="group" checked={group === key} onChange={() => resetGroupChoice(key)} />
                {cfg.label}
              </label>
            ))}
          </div>
        </div>

        {group && (
          <div className="form-field">
            <label>2. {GROUP_QUESTIONS[group].question}</label>
            <div className="radio-group">
              {GROUP_QUESTIONS[group].options.map((opt) => (
                <label key={opt.key} className={`radio-option ${answerKey === opt.key ? "selected" : ""}`}>
                  <input
                    type="radio"
                    name="answer"
                    checked={answerKey === opt.key}
                    onChange={() => {
                      setAnswerKey(opt.key);
                      setDepotOnTime(null);
                      setHasInjury(null);
                      setExtraValue("");
                    }}
                  />
                  {opt.label}
                </label>
              ))}
            </div>
          </div>
        )}

        {showDepotFollowUp && answerKey === "chua_xuat_phat" && (
          <div className="form-field">
            <label>Xe/tài xế có mặt tại kho đúng giờ không?</label>
            <div className="radio-group">
              <label className={`radio-option ${depotOnTime === true ? "selected" : ""}`}>
                <input type="radio" checked={depotOnTime === true} onChange={() => setDepotOnTime(true)} />
                Có (đến kho đúng giờ nhưng xuất phát trễ)
              </label>
              <label className={`radio-option ${depotOnTime === false ? "selected" : ""}`}>
                <input type="radio" checked={depotOnTime === false} onChange={() => setDepotOnTime(false)} />
                Không (bản thân đến kho đã trễ)
              </label>
            </div>
          </div>
        )}

        {showInjuryFollowUp && (
          <div className="form-field">
            <label>Có ai bị thương không?</label>
            <div className="radio-group">
              <label className={`radio-option ${hasInjury === true ? "selected" : ""}`}>
                <input type="radio" checked={hasInjury === true} onChange={() => setHasInjury(true)} />
                Có
              </label>
              <label className={`radio-option ${hasInjury === false ? "selected" : ""}`}>
                <input type="radio" checked={hasInjury === false} onChange={() => setHasInjury(false)} />
                Không
              </label>
            </div>
          </div>
        )}

        {extraField && (
          <div className="form-field">
            <label>{extraField.label}</label>
            {extraField.type === "number" ? (
              <input
                type="number"
                min={0}
                value={extraValue}
                onChange={(e) => {
                  setExtraValue(e.target.value);
                  if (subType === "late_departure") setDelayMinutes(e.target.value);
                }}
              />
            ) : (
              <div className="radio-group">
                <label className={`radio-option ${extraValue === "true" ? "selected" : ""}`}>
                  <input type="radio" checked={extraValue === "true"} onChange={() => setExtraValue("true")} />
                  Có
                </label>
                <label className={`radio-option ${extraValue === "false" ? "selected" : ""}`}>
                  <input type="radio" checked={extraValue === "false"} onChange={() => setExtraValue("false")} />
                  Không
                </label>
              </div>
            )}
          </div>
        )}

        {schedule && answerKey && (
          <>
            <div className="form-field">
              <label>3. Điểm giao/nhận bị ảnh hưởng từ</label>
              <select value={fromStopOrder} onChange={(e) => setFromStopOrder(Number(e.target.value))} required>
                <option value="">-- Chọn điểm --</option>
                {schedule.stops.map((st) => (
                  <option key={st.stop_id} value={st.stop_order}>
                    #{st.stop_order} — {st.address} ({st.order_id})
                  </option>
                ))}
              </select>
            </div>
            <div className="form-field">
              <label>
                <input
                  type="checkbox"
                  checked={affectsWholeRoute}
                  onChange={(e) => setAffectsWholeRoute(e.target.checked)}
                />{" "}
                Ảnh hưởng dây chuyền đến hết chuyến
              </label>
              {!affectsWholeRoute && (
                <select value={toStopOrder} onChange={(e) => setToStopOrder(Number(e.target.value))}>
                  <option value="">-- Đến điểm --</option>
                  {schedule.stops.map((st) => (
                    <option key={st.stop_id} value={st.stop_order}>
                      #{st.stop_order} — {st.address}
                    </option>
                  ))}
                </select>
              )}
            </div>
            <div className="form-field">
              <label>Số phút trễ tại các điểm bị ảnh hưởng (nếu có)</label>
              <input
                type="number"
                min={0}
                value={delayMinutes}
                disabled={subType === "late_departure"}
                onFocus={(e) => e.target.select()}
                onChange={(e) => setDelayMinutes(e.target.value)}
              />
              {subType === "late_departure" && (
                <span className="hint">Tự động lấy theo số phút trễ xuất phát ở trên.</span>
              )}
            </div>
          </>
        )}

        {showCustomerDelayTolerance && (
          <div className="form-field">
            <label>Khách có thể chấp nhận trễ hơn SLA không?</label>
            <div className="radio-group">
              <label className={`radio-option ${customerAcceptedDelayAnswer === "yes" ? "selected" : ""}`}>
                <input
                  type="radio"
                  checked={customerAcceptedDelayAnswer === "yes"}
                  onChange={() => setCustomerAcceptedDelayAnswer("yes")}
                />
                Có
              </label>
              <label className={`radio-option ${customerAcceptedDelayAnswer === "no" ? "selected" : ""}`}>
                <input
                  type="radio"
                  checked={customerAcceptedDelayAnswer === "no"}
                  onChange={() => {
                    setCustomerAcceptedDelayAnswer("no");
                    setCustomerAcceptedDelayMinInput("");
                  }}
                />
                Không
              </label>
              <label className={`radio-option ${customerAcceptedDelayAnswer === "unknown" ? "selected" : ""}`}>
                <input
                  type="radio"
                  checked={customerAcceptedDelayAnswer === "unknown"}
                  onChange={() => {
                    setCustomerAcceptedDelayAnswer("unknown");
                    setCustomerAcceptedDelayMinInput("");
                  }}
                />
                Không rõ
              </label>
            </div>
            {customerAcceptedDelayAnswer === "yes" && (
              <div style={{ marginTop: 10 }}>
                <label>Khách chấp nhận trễ tối đa bao nhiêu phút so với SLA?</label>
                <input
                  type="number"
                  min={0}
                  value={customerAcceptedDelayMinInput}
                  onFocus={(e) => e.target.select()}
                  onChange={(e) => setCustomerAcceptedDelayMinInput(e.target.value)}
                />
              </div>
            )}
          </div>
        )}

        <div className="form-field">
          <label>Khu vực xe đang ở</label>
          <input value={area} onChange={(e) => setArea(e.target.value)} placeholder="VD: Cầu Giấy" />
        </div>
        <div className="form-field">
          <label>Ghi chú thêm (không dùng để phân loại)</label>
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
        </div>

        <div style={{ display: "flex", gap: 8 }}>
          <button
            type="submit"
            className="primary"
            disabled={submitting || !group || !answerKey || fromStopOrder === ""}
          >
            {submitting ? "Đang lưu..." : "Lưu thay đổi"}
          </button>
          <button type="button" className="secondary" onClick={() => navigate(-1)}>
            Hủy
          </button>
        </div>
      </form>
    </div>
  );
}
