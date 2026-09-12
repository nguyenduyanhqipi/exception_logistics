import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { apiClient, apiErrorMessage } from "../api/client";
import type { Schedule } from "../api/types";
import { FollowUpFields } from "../components/FollowUpFields";
import {
  ANSWER_TO_SUBTYPE,
  DEPARTURE_DELAY_KEYS,
  DERIVED_FIELDS,
  GROUP_QUESTIONS,
  localToday,
  missingRequiredFollowUp,
  showsCustomerDelayTolerance,
} from "../exceptionForm";

export function NewException() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  // Xe được chọn sẵn khi bấm "+ Ngoại lệ" từ Dashboard (việc 1).
  const prefillVehicleId = searchParams.get("vehicle_id");
  const { data: schedulesRaw } = useQuery({
    queryKey: ["schedules"],
    queryFn: async () => (await apiClient.get<Schedule[]>("/api/schedules")).data,
  });

  // Ngày hôm nay theo giờ ĐỊA PHƯƠNG (không phải UTC) — xem localToday().
  const today = localToday();
  // Chỉ hiện chuyến từ hôm nay trở đi — bảng schedules còn chứa dữ liệu lịch
  // sử giả (scripts/seed_historical_exceptions.py) để làm phong phú báo cáo
  // Giai đoạn 9, không phải chuyến đang chạy thật; lẫn vào dropdown này sẽ
  // làm dispatcher khó tìm đúng chuyến đang cần khai báo ngoại lệ.
  //
  // QUYẾT ĐỊNH CÓ CHỦ ĐÍCH (không phải bug): nếu không có chuyến nào cho hôm
  // nay, KHÔNG fallback sang ngày khác — chặn hẳn việc tạo ngoại lệ mới. Một
  // ngoại lệ luôn phải gắn với 1 chuyến ĐANG chạy hôm nay; cho tạo nhầm lên
  // 1 chuyến của ngày cũ (kể cả kèm banner cảnh báo) sẽ ghi sai dữ liệu thật
  // vào hệ thống. Bản trước từng fallback + banner để không chặn demo khi
  // seed data lệch ngày — nay đổi hẳn sang chặn cứng, vế "seed data chưa
  // refresh" phải được xử lý bằng cách nhập kế hoạch/seed lại đúng ngày, không
  // phải bằng cách nới lỏng phía frontend.
  const schedules = useMemo(() => schedulesRaw?.filter((s) => s.shift_date >= today), [schedulesRaw, today]);
  const noScheduleToday = schedules !== undefined && schedules.length === 0;

  const [scheduleId, setScheduleId] = useState("");
  const [group, setGroup] = useState("");
  const [answerKey, setAnswerKey] = useState("");
  // Câu trả lời của MỌI câu hỏi phụ, gom vào 1 chỗ theo tên field backend
  // (exceptionForm.ts::FOLLOW_UPS). Trước đây mỗi câu hỏi 1 useState riêng —
  // thêm câu hỏi là thêm state + thêm dòng reset + thêm dòng payload, quên 1
  // trong 3 là sinh bug im lặng.
  const [followUps, setFollowUps] = useState<Record<string, unknown>>({});
  const [fromStopOrder, setFromStopOrder] = useState<number | "">("");
  const [affectsWholeRoute, setAffectsWholeRoute] = useState(true);
  const [toStopOrder, setToStopOrder] = useState<number | "">("");
  // String state (không phải number) cho input number có kiểm soát — nếu để
  // useState(0) thì React giữ nguyên "0" hiển thị trong ô, gõ tiếp bị NỐI vào
  // sau ("30" → hiển thị "030") thay vì thay thế, vì input DOM đang hiển thị
  // "0" theo đúng giá trị React truyền vào, không phải placeholder.
  const [delayMinutes, setDelayMinutes] = useState("0");
  // Đợt 13: dispatcher CHƯA ước tính được trễ bao lâu (mất liên lạc tài xế, xe
  // kẹt chưa biết bao giờ thông). Gửi kèm payload để impact_analyzer để
  // new_eta/sla_breach = null thay vì suy ra "không vi phạm" từ 0 phút.
  const [delayUnknown, setDelayUnknown] = useState(false);
  const [area, setArea] = useState("");
  const [description, setDescription] = useState("");
  // Mục F — khách chấp nhận trễ hơn SLA bao nhiêu (hỏi 2 bước, optional). CHỈ
  // tác động ranker.py, KHÔNG đụng impact_analysis/sla_breach thật (xem
  // backend/core/ranker.py::_apply_customer_tolerance).
  const [customerAcceptedDelayAnswer, setCustomerAcceptedDelayAnswer] = useState<"" | "yes" | "no" | "unknown">("");
  const [customerAcceptedDelayMinInput, setCustomerAcceptedDelayMinInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const schedule = useMemo(() => schedules?.find((s) => s.schedule_id === scheduleId), [schedules, scheduleId]);

  // Prefill xe từ query string `?vehicle_id=` (việc 1). Form vẫn chọn theo
  // `schedule_id` — chỉ đặt GIÁ TRỊ BAN ĐẦU của dropdown "Chọn chuyến" sang
  // chuyến của đúng xe đó, ưu tiên chuyến trong ca hiện tại, rồi tới chuyến
  // sớm nhất còn lại của xe. Xe không có chuyến nào -> để trống như cũ.
  // Chỉ chạy 1 lần (khi dropdown còn trống) để không ghi đè lựa chọn tay.
  useEffect(() => {
    if (!prefillVehicleId || scheduleId || !schedules) return;
    const ofVehicle = schedules.filter((s) => s.vehicle_id === prefillVehicleId);
    if (ofVehicle.length === 0) return;
    // Không còn "ca": ưu tiên chuyến của HÔM NAY, không có thì lấy chuyến sớm
    // nhất còn lại của xe.
    const byToday = ofVehicle.filter((s) => s.shift_date === today);
    const pool = byToday.length > 0 ? byToday : ofVehicle;
    const picked = [...pool].sort(
      (a, b) => a.shift_date.localeCompare(b.shift_date) || a.trip_sequence - b.trip_sequence,
    )[0];
    setScheduleId(picked.schedule_id);
  }, [prefillVehicleId, scheduleId, schedules, today]);
  const subType = group && answerKey ? ANSWER_TO_SUBTYPE[group]?.[answerKey] : null;
  const delayUnknownEffective = delayUnknown && subType !== "late_departure";
  // Chỉ nhóm ngoại lệ có khả năng gây TRỄ mới cần hỏi khách có chấp nhận trễ
  // không — customer_reject/customer_change là vấn đề tại điểm giao/đổi yêu
  // cầu, không phải trễ tiến độ, hỏi câu này ở đó không có ý nghĩa.
  const showCustomerDelayTolerance = showsCustomerDelayTolerance(group);

  function resetGroupChoice(newGroup: string) {
    setGroup(newGroup);
    setAnswerKey("");
    setFollowUps({});
    setDelayUnknown(false);
    setCustomerAcceptedDelayAnswer("");
    setCustomerAcceptedDelayMinInput("");
    // customer_reject/customer_change chỉ ảnh hưởng ĐÚNG 1 điểm giao theo
    // đúng thiết kế impact_analyzer.py (to_stop_order = from_stop_order),
    // KHÔNG lan cả tuyến như delay/road_block/vehicle_issue — tự đặt lại để
    // tránh dispatcher vô tình để tick sẵn làm severity tính sai (leo thang
    // nhầm theo downstream_stops_affected khi thực ra không có).
    setAffectsWholeRoute(newGroup !== "customer_reject" && newGroup !== "customer_change");
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
        // `late_departure` luôn tự đồng bộ số phút từ câu hỏi trên nên KHÔNG
        // có ô tick này — chặn luôn ở đây phòng khi dispatcher tick ở loại
        // khác rồi mới đổi sang "xuất phát trễ" (ô tick ẩn đi nhưng state còn).
        delay_minutes: delayUnknownEffective ? 0 : Number(delayMinutes) || 0,
        delay_unknown: delayUnknownEffective,
        area: area || null,
        description: description || null,
      };
      // Field suy ra từ answer_key (vd departure_status) + mọi câu trả lời phụ.
      Object.assign(payload, DERIVED_FIELDS[answerKey] ?? {}, followUps);
      if (showCustomerDelayTolerance && customerAcceptedDelayAnswer === "yes" && customerAcceptedDelayMinInput !== "") {
        payload.customer_accepted_delay_min = Number(customerAcceptedDelayMinInput) || 0;
      }

      const res = await apiClient.post("/api/exceptions", payload);
      navigate(`/exceptions/${res.data.exception_id}`);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (noScheduleToday) {
    return (
      <div className="page">
        <h1>Nhập ngoại lệ mới</h1>
        <div className="card">
          <div className="error-banner">
            Chưa có kế hoạch giao hàng cho hôm nay — vui lòng nhập kế hoạch trước khi khai báo ngoại lệ.
          </div>
          <Link to="/schedules/new" className="primary" style={{ display: "inline-block", marginTop: 12, textDecoration: "none", textAlign: "center" }}>
            Sang trang Xe & Kế hoạch
          </Link>
        </div>
      </div>
    );
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
                {s.vehicle_id} — {s.shift_date} (chuyến {s.trip_sequence})
              </option>
            ))}
          </select>
        </div>

        {schedule && schedule.stops.length > 0 && (
          <div className="form-field">
            <label>Các điểm giao/nhận trong chuyến</label>
            <table className="stops-mini-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Địa chỉ</th>
                  <th>Đơn hàng</th>
                  <th>Giờ đến dự kiến (ETA)</th>
                  <th>Hạn chót (SLA)</th>
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
                      setFollowUps({});
                    }}
                  />
                  {opt.label}
                </label>
              ))}
            </div>
          </div>
        )}

        {answerKey && (
          <FollowUpFields
            answerKey={answerKey}
            answers={followUps}
            onChange={(key, value) => {
              setFollowUps((prev) => ({ ...prev, [key]: value }));
              // Trễ xuất phát N phút nghĩa là MỌI điểm phía sau cũng trễ đúng N
              // phút đó (mục 15, kịch bản 1) — cùng 1 con số, không phải 2 input
              // độc lập; tự đồng bộ để dispatcher khỏi quên ô "delay_minutes".
              if (DEPARTURE_DELAY_KEYS.includes(key)) setDelayMinutes(value === undefined ? "0" : String(value));
            }}
          />
        )}

        {schedule && answerKey && (
          <>
            <div className="form-field">
              <label>4. Điểm giao/nhận bị ảnh hưởng từ</label>
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
                disabled={subType === "late_departure" || delayUnknown}
                onFocus={(e) => e.target.select()}
                onChange={(e) => setDelayMinutes(e.target.value)}
              />
              {subType === "late_departure" && (
                <span className="hint">Tự động lấy theo số phút trễ xuất phát ở trên.</span>
              )}
              {subType !== "late_departure" && (
                <label style={{ display: "block", marginTop: 6, fontWeight: "normal" }}>
                  <input
                    type="checkbox"
                    checked={delayUnknown}
                    onChange={(e) => setDelayUnknown(e.target.checked)}
                  />{" "}
                  Không ước tính được (vd mất liên lạc tài xế, chưa biết bao giờ xong) — nên ghi rõ tình huống ở
                  "Ghi chú thêm" bên dưới
                </label>
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
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            placeholder="VD: Khách đang đi công tác, hẹn 15h mai giao lại"
          />
        </div>

        <button
          type="submit"
          className="primary"
          disabled={
            submitting ||
            !scheduleId ||
            !group ||
            !answerKey ||
            fromStopOrder === "" ||
            missingRequiredFollowUp(answerKey, followUps)
          }
        >
          {submitting ? "Đang gửi..." : "Tạo ngoại lệ"}
        </button>
      </form>
    </div>
  );
}
