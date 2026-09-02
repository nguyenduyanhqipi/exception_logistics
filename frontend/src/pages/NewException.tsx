import { useQuery } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { apiClient, apiErrorMessage } from "../api/client";
import type { Schedule } from "../api/types";

// Câu hỏi trắc nghiệm theo mục 5.1 — answer_key PHẢI khớp đúng
// backend/core/rule_engine.py::ANSWER_TO_SUBTYPE, không tự đặt tên khác.
const GROUP_QUESTIONS: Record<string, { label: string; question: string; options: { key: string; label: string }[] }> = {
  delay: {
    label: "Trễ giờ",
    question: "Xe đã xuất phát chưa?",
    options: [
      { key: "chua_xuat_phat", label: "Chưa xuất phát / xuất phát muộn hơn giờ kế hoạch" },
      { key: "dang_boc_do_cham", label: "Đã xuất phát, đang chậm tại điểm bốc/dỡ hàng" },
      { key: "dang_di_chuyen_cham_khong_ro_ly_do", label: "Đã xuất phát, đang di chuyển nhưng chậm không rõ lý do / mất liên lạc tài xế" },
    ],
  },
  road_block: {
    label: "Chặn đường",
    question: "Tình trạng đường hiện tại?",
    options: [
      { key: "un_tac_van_di_duoc", label: "Ùn tắc nhưng xe vẫn nhích được" },
      { key: "chan_hoan_toan", label: "Đường chặn hoàn toàn / cấm đường / ngập / tai nạn chắn ngang" },
    ],
  },
  customer_reject: {
    label: "Khách từ chối nhận hàng",
    question: "Vấn đề tại điểm giao là gì?",
    options: [
      { key: "khong_co_nguoi_nhan", label: "Không có ai nhận hàng" },
      { key: "tu_choi_nhan_tranh_chap", label: "Khách có mặt nhưng từ chối nhận (tranh chấp hàng/giá/chất lượng)" },
      { key: "sai_dia_chi", label: "Địa chỉ sai / không tìm thấy / không tồn tại" },
    ],
  },
  customer_change: {
    label: "Khách đổi yêu cầu",
    question: "Khách yêu cầu thay đổi gì?",
    options: [
      { key: "doi_gio_nhan", label: "Đổi giờ nhận hàng" },
      { key: "doi_dia_diem", label: "Đổi địa điểm giao" },
      { key: "huy_don", label: "Hủy đơn" },
    ],
  },
  vehicle_issue: {
    label: "Sự cố xe",
    question: "Mức độ hư hỏng xe?",
    options: [
      { key: "hong_nhe_van_chay_duoc", label: "Xe vẫn chạy được, sự cố nhỏ (non hơi, đèn báo lỗi...)" },
      { key: "hong_nang_phai_dung", label: "Xe không chạy được, phải dừng hẳn, cần xe thay thế" },
      { key: "tai_nan", label: "Có va chạm / tai nạn giao thông" },
    ],
  },
};

const ANSWER_TO_SUBTYPE: Record<string, Record<string, string>> = {
  delay: { chua_xuat_phat: "late_departure", dang_boc_do_cham: "slow_loading", dang_di_chuyen_cham_khong_ro_ly_do: "unknown_delay" },
  road_block: { un_tac_van_di_duoc: "traffic_jam", chan_hoan_toan: "road_closed" },
  customer_reject: { khong_co_nguoi_nhan: "customer_absent", tu_choi_nhan_tranh_chap: "customer_dispute", sai_dia_chi: "wrong_address" },
  customer_change: { doi_gio_nhan: "change_time", doi_dia_diem: "change_location", huy_don: "cancel_order" },
  vehicle_issue: { hong_nhe_van_chay_duoc: "minor_breakdown", hong_nang_phai_dung: "major_breakdown", tai_nan: "accident" },
};

// sub_type nào cần thêm 1 số liệu định lượng để rule engine tính severity (mục 5.2).
const EXTRA_FIELD: Record<string, { key: string; label: string; type: "number" | "boolean" }> = {
  late_departure: { key: "departure_delay_min", label: "Số phút trễ xuất phát so với kế hoạch", type: "number" },
  unknown_delay: { key: "driver_contact_lost_min", label: "Số phút mất liên lạc với tài xế", type: "number" },
  traffic_jam: { key: "estimated_traffic_duration_min", label: "Thời gian tắc đường ước tính (phút)", type: "number" },
  customer_absent: { key: "is_repeat_delivery", label: "Đây có phải lần giao lại (lần 2 trở lên) không?", type: "boolean" },
  wrong_address: { key: "new_address_distance_km", label: "Địa chỉ mới cách địa chỉ cũ bao xa (km)?", type: "number" },
  change_time: { key: "has_time_conflict", label: "Giờ mới có xung đột với điểm giao khác cùng chuyến không?", type: "boolean" },
  change_location: { key: "new_location_distance_km", label: "Địa điểm mới cách tuyến hiện tại bao xa (km)?", type: "number" },
  minor_breakdown: { key: "estimated_repair_min", label: "Thời gian sửa ước tính (phút)", type: "number" },
};

export function NewException() {
  const navigate = useNavigate();
  const { data: schedules } = useQuery({
    queryKey: ["schedules"],
    queryFn: async () => (await apiClient.get<Schedule[]>("/api/schedules")).data,
    // Chỉ hiện chuyến từ hôm nay trở đi — bảng schedules còn chứa dữ liệu lịch
    // sử giả (scripts/seed_historical_exceptions.py) để làm phong phú báo cáo
    // Giai đoạn 9, không phải chuyến đang chạy thật; lẫn vào dropdown này sẽ
    // làm dispatcher khó tìm đúng chuyến đang cần khai báo ngoại lệ.
    select: (data: Schedule[]) => {
      const today = new Date().toISOString().slice(0, 10);
      return data.filter((s) => s.shift_date >= today);
    },
  });

  const [scheduleId, setScheduleId] = useState("");
  const [group, setGroup] = useState("");
  const [answerKey, setAnswerKey] = useState("");
  const [depotOnTime, setDepotOnTime] = useState<boolean | null>(null);
  const [hasInjury, setHasInjury] = useState<boolean | null>(null);
  const [extraValue, setExtraValue] = useState<string>("");
  const [fromStopOrder, setFromStopOrder] = useState<number | "">("");
  const [affectsWholeRoute, setAffectsWholeRoute] = useState(true);
  const [toStopOrder, setToStopOrder] = useState<number | "">("");
  const [delayMinutes, setDelayMinutes] = useState(0);
  const [area, setArea] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const schedule = useMemo(() => schedules?.find((s) => s.schedule_id === scheduleId), [schedules, scheduleId]);
  const subType = group && answerKey ? ANSWER_TO_SUBTYPE[group]?.[answerKey] : null;
  const extraField = subType ? EXTRA_FIELD[subType] : null;
  const showDepotFollowUp = subType === "late_departure" && !!schedule?.planned_departure_time;
  const showInjuryFollowUp = subType === "accident";

  function resetGroupChoice(newGroup: string) {
    setGroup(newGroup);
    setAnswerKey("");
    setDepotOnTime(null);
    setHasInjury(null);
    setExtraValue("");
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!scheduleId || !group || !answerKey || fromStopOrder === "") return;
    setError(null);
    setSubmitting(true);
    try {
      const payload: Record<string, unknown> = {
        schedule_id: scheduleId,
        exception_group: group,
        answer_key: answerKey,
        from_stop_order: fromStopOrder,
        to_stop_order: affectsWholeRoute ? null : toStopOrder || null,
        delay_minutes: delayMinutes,
        area: area || null,
        description: description || null,
      };
      if (depotOnTime !== null) payload.depot_on_time = depotOnTime;
      if (hasInjury !== null) payload.has_injury = hasInjury;
      if (extraField && extraValue !== "") {
        payload[extraField.key] = extraField.type === "boolean" ? extraValue === "true" : Number(extraValue);
      }

      const res = await apiClient.post("/api/exceptions", payload);
      navigate(`/exceptions/${res.data.exception_id}`);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page">
      <h1>Nhập ngoại lệ mới</h1>
      <form onSubmit={handleSubmit} className="card">
        {error && <div className="error-banner">{error}</div>}

        <div className="form-field">
          <label>1. Chọn chuyến</label>
          <select value={scheduleId} onChange={(e) => setScheduleId(e.target.value)} required>
            <option value="">-- Chọn chuyến --</option>
            {schedules?.map((s) => (
              <option key={s.schedule_id} value={s.schedule_id}>
                {s.vehicle_id} — {s.shift_date} {s.shift_label} (chuyến {s.trip_sequence})
              </option>
            ))}
          </select>
        </div>

        {schedule && schedule.stops.length > 0 && (
          <div className="form-field">
            <label>Các điểm giao trong chuyến</label>
            <table className="stops-mini-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Địa chỉ</th>
                  <th>Đơn hàng</th>
                  <th>ETA</th>
                  <th>Hạn SLA</th>
                </tr>
              </thead>
              <tbody>
                {schedule.stops.map((st) => (
                  <tr key={st.stop_id}>
                    <td>{st.stop_order}</td>
                    <td>{st.address}</td>
                    <td>{st.order_id}</td>
                    <td>{st.eta}</td>
                    <td>{st.sla_deadline}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {scheduleId && (
          <div className="form-field">
            <label>2. Loại ngoại lệ</label>
            <div className="radio-group">
              {Object.entries(GROUP_QUESTIONS).map(([key, cfg]) => (
                <label key={key} className={`radio-option ${group === key ? "selected" : ""}`}>
                  <input type="radio" name="group" checked={group === key} onChange={() => resetGroupChoice(key)} />
                  {cfg.label}
                </label>
              ))}
            </div>
          </div>
        )}

        {group && (
          <div className="form-field">
            <label>3. {GROUP_QUESTIONS[group].question}</label>
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
                  // late_departure: trễ xuất phát N phút nghĩa là MỌI điểm phía
                  // sau cũng trễ đúng N phút đó (mục 15, kịch bản 1) — cùng 1 con
                  // số, không phải 2 input độc lập, tự đồng bộ để tránh dispatcher
                  // quên điền ô "delay_minutes" bên dưới.
                  if (subType === "late_departure") setDelayMinutes(Number(e.target.value) || 0);
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
              <label>4. Điểm giao bị ảnh hưởng từ</label>
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
                <input type="checkbox" checked={affectsWholeRoute} onChange={(e) => setAffectsWholeRoute(e.target.checked)} /> Ảnh
                hưởng dây chuyền đến hết chuyến
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
                onChange={(e) => setDelayMinutes(Number(e.target.value))}
              />
              {subType === "late_departure" && (
                <span className="hint">Tự động lấy theo số phút trễ xuất phát ở trên.</span>
              )}
            </div>
          </>
        )}

        <div className="form-field">
          <label>Khu vực xe đang ở</label>
          <input value={area} onChange={(e) => setArea(e.target.value)} placeholder="VD: Cầu Giấy" />
        </div>
        <div className="form-field">
          <label>Ghi chú thêm (không dùng để phân loại)</label>
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
        </div>

        <button type="submit" className="primary" disabled={submitting || !scheduleId || !group || !answerKey || fromStopOrder === ""}>
          {submitting ? "Đang gửi..." : "Tạo ngoại lệ"}
        </button>
      </form>
    </div>
  );
}
