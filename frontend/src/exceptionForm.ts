// Hằng số dùng chung cho form TẠO (NewException.tsx) và form SỬA
// (EditException.tsx) ngoại lệ. Tách ra khỏi NewException.tsx để 2 form không
// trôi lệch nhau — answer_key PHẢI khớp đúng
// backend/core/rule_engine.py::ANSWER_TO_SUBTYPE.

export const GROUP_QUESTIONS: Record<
  string,
  { label: string; question: string; options: { key: string; label: string }[] }
> = {
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
    question: "Vấn đề tại điểm giao/nhận là gì?",
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

export const ANSWER_TO_SUBTYPE: Record<string, Record<string, string>> = {
  delay: { chua_xuat_phat: "late_departure", dang_boc_do_cham: "slow_loading", dang_di_chuyen_cham_khong_ro_ly_do: "unknown_delay" },
  road_block: { un_tac_van_di_duoc: "traffic_jam", chan_hoan_toan: "road_closed" },
  customer_reject: { khong_co_nguoi_nhan: "customer_absent", tu_choi_nhan_tranh_chap: "customer_dispute", sai_dia_chi: "wrong_address" },
  customer_change: { doi_gio_nhan: "change_time", doi_dia_diem: "change_location", huy_don: "cancel_order" },
  vehicle_issue: { hong_nhe_van_chay_duoc: "minor_breakdown", hong_nang_phai_dung: "major_breakdown", tai_nan: "accident" },
};

// Ánh xạ ngược sub_type -> {group, answer_key}. `exceptions` chỉ lưu sub_type
// chứ không lưu answer_key, nên form SỬA suy ngược lại từ đây để chọn sẵn
// đúng câu trả lời trắc nghiệm (ánh xạ là song ánh nên suy ngược an toàn).
// Chỉ dùng khi `input_context.answer_key` không có (ngoại lệ tạo trước khi có
// cột input_context).
export const SUBTYPE_TO_ANSWER: Record<string, { group: string; answerKey: string }> = Object.fromEntries(
  Object.entries(ANSWER_TO_SUBTYPE).flatMap(([group, answers]) =>
    Object.entries(answers).map(([answerKey, subType]) => [subType, { group, answerKey }]),
  ),
);

// sub_type nào cần thêm 1 số liệu định lượng để rule engine tính severity (mục 5.2).
export const EXTRA_FIELD: Record<string, { key: string; label: string; type: "number" | "boolean" }> = {
  late_departure: { key: "departure_delay_min", label: "Số phút trễ xuất phát so với kế hoạch", type: "number" },
  unknown_delay: { key: "driver_contact_lost_min", label: "Số phút mất liên lạc với tài xế", type: "number" },
  traffic_jam: { key: "estimated_traffic_duration_min", label: "Thời gian tắc đường ước tính (phút)", type: "number" },
  customer_absent: { key: "is_repeat_delivery", label: "Đây có phải lần giao lại (lần 2 trở lên) không?", type: "boolean" },
  wrong_address: { key: "new_address_distance_km", label: "Địa chỉ mới cách địa chỉ cũ bao xa (km)?", type: "number" },
  change_time: { key: "has_time_conflict", label: "Giờ mới có xung đột với điểm giao khác cùng chuyến không?", type: "boolean" },
  change_location: { key: "new_location_distance_km", label: "Địa điểm mới cách tuyến hiện tại bao xa (km)?", type: "number" },
  minor_breakdown: { key: "estimated_repair_min", label: "Thời gian sửa ước tính (phút)", type: "number" },
};

// Chỉ nhóm ngoại lệ có khả năng gây TRỄ mới cần hỏi khách có chấp nhận trễ
// không — customer_reject/customer_change là vấn đề tại điểm giao/đổi yêu cầu,
// không phải trễ tiến độ.
export function showsCustomerDelayTolerance(group: string): boolean {
  return group === "delay" || group === "road_block" || group === "vehicle_issue";
}

/** Ngày hôm nay theo giờ ĐỊA PHƯƠNG của máy người dùng, dạng YYYY-MM-DD.
 *
 * KHÔNG dùng `new Date().toISOString().slice(0,10)`: `toISOString()` trả giờ
 * UTC, nên trong khoảng 00:00-07:00 giờ VN nó ra ngày HÔM QUA — lệch với
 * `shift_date` mà backend ghi (container api/worker chạy TZ=Asia/Ho_Chi_Minh,
 * xem docker-compose.yml). */
export function localToday(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Ca hiện tại theo giờ địa phương — khung giờ giữ ĐÚNG như
 *  backend/api/dashboard.py::SHIFT_WINDOWS. */
export function currentShiftLabel(): string {
  const h = new Date().getHours();
  if (h < 12) return "ca_sang";
  if (h < 18) return "ca_chieu";
  return "ca_dem";
}
