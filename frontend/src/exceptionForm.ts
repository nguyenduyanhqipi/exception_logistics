// Hằng số dùng chung cho form TẠO (NewException.tsx) và form SỬA
// (EditException.tsx) ngoại lệ. Tách ra khỏi NewException.tsx để 2 form không
// trôi lệch nhau — answer_key PHẢI khớp đúng
// backend/core/rule_engine.py::ANSWER_TO_SUBTYPE, còn tên field trong
// FOLLOW_UPS phải khớp đúng backend/schemas/exception.py::ExceptionCreate +
// backend/api/exceptions.py::_SIGNAL_FIELDS (đây là hợp đồng API cố định).
//
// REDESIGN 2026-09-08 (Claude outputs/dot_code_5/exception_intake_review.md):
// còn 11 sub_type; `slow_loading`/`wrong_address`/`cancel_order` đã retire.
// Câu hỏi phụ trước đây viết tay thẳng trong JSX của từng form (depot_on_time,
// has_injury) — nay khai báo hết ở FOLLOW_UPS bên dưới để 2 form render CÙNG
// một danh sách, thêm câu hỏi mới chỉ phải sửa đúng file này.

export const GROUP_QUESTIONS: Record<
  string,
  { label: string; question: string; options: { key: string; label: string }[] }
> = {
  delay: {
    label: "Trễ giờ",
    question: "Xe đã xuất phát khỏi kho chưa?",
    options: [
      { key: "chua_xuat_phat", label: "Chưa xuất phát" },
      { key: "da_xuat_phat_nhung_tre", label: "Đã xuất phát nhưng trễ hơn kế hoạch" },
      { key: "mat_lien_lac_tai_xe", label: "Mất liên lạc hoàn toàn với tài xế" },
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
    ],
  },
  customer_change: {
    label: "Khách đổi yêu cầu",
    question: "Khách yêu cầu thay đổi gì?",
    options: [
      { key: "doi_gio_nhan", label: "Đổi giờ nhận hàng" },
      { key: "doi_dia_diem", label: "Đổi địa điểm giao" },
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
  // `chua_xuat_phat` và `da_xuat_phat_nhung_tre` CÙNG ra `late_departure`: cùng
  // bản chất "xuất phát trễ", chỉ khác con số là ước tính hay thực tế — phân
  // biệt bằng `departure_status` (xem DERIVED_FIELDS), không tách sub_type.
  delay: {
    chua_xuat_phat: "late_departure",
    da_xuat_phat_nhung_tre: "late_departure",
    mat_lien_lac_tai_xe: "unknown_delay",
  },
  road_block: { un_tac_van_di_duoc: "traffic_jam", chan_hoan_toan: "road_closed" },
  customer_reject: { khong_co_nguoi_nhan: "customer_absent", tu_choi_nhan_tranh_chap: "customer_dispute" },
  customer_change: { doi_gio_nhan: "change_time", doi_dia_diem: "change_location" },
  vehicle_issue: {
    hong_nhe_van_chay_duoc: "minor_breakdown",
    hong_nang_phai_dung: "major_breakdown",
    tai_nan: "accident",
  },
};

// Field SUY RA từ answer_key, KHÔNG hỏi dispatcher: hỏi lại "xe đã xuất phát
// chưa" lần nữa thì thừa, mà rule engine/AI vẫn cần giá trị này ở dạng field
// riêng (backend/core/rule_engine.py::_base_and_escalation đọc nó để biết lấy
// con số ước tính hay thực tế).
export const DERIVED_FIELDS: Record<string, Record<string, string>> = {
  chua_xuat_phat: { departure_status: "chua_xuat_phat" },
  da_xuat_phat_nhung_tre: { departure_status: "da_xuat_phat" },
};

// Ánh xạ ngược sub_type -> {group, answer_key}. `exceptions` chỉ lưu sub_type
// chứ không lưu answer_key, nên form SỬA suy ngược lại từ đây khi
// `input_context.answer_key` không có (ngoại lệ tạo trước khi có cột đó).
//
// KHÔNG còn là song ánh từ 2026-09-08: `late_departure` có 2 answer_key. Chọn
// `chua_xuat_phat` làm mặc định vì đó là trường hợp phổ biến hơn khi khai báo,
// dispatcher đổi lại 1 cú bấm nếu sai — chấp nhận được, vì nhánh này CHỈ chạy
// với ngoại lệ cũ thiếu input_context.
export const SUBTYPE_TO_ANSWER: Record<string, { group: string; answerKey: string }> = Object.fromEntries(
  Object.entries(ANSWER_TO_SUBTYPE).flatMap(([group, answers]) =>
    Object.entries(answers).map(([answerKey, subType]) => [subType, { group, answerKey }]),
  ),
);

// Khách nói muốn gì -> sub_type NÊN dùng thay vì `customer_absent`. Bản sao
// của backend/core/rule_engine.py::CUSTOMER_REQUEST_TO_SUBTYPE — cùng loại
// "hợp đồng API chép 2 phía" với ANSWER_TO_SUBTYPE ở trên, sửa bên nào phải
// soi lại bên kia.
//
// CHỈ để GỢI Ý (spec mục 5.1: "không đổi sub_type"): dispatcher tự bấm chọn
// lại, hệ thống không âm thầm đổi hộ — người nhập mới biết câu chuyện thật,
// còn khách nói "hẹn giao lại" không phải lúc nào cũng đúng nghĩa đổi giờ.
export const CUSTOMER_REQUEST_SUGGESTION: Record<string, string | null> = {
  hen_giao_lai: "change_time",
  doi_dia_diem: "change_location",
  huy: null,
};

export type FollowUpType = "number" | "boolean" | "choice" | "location";

export type FollowUpField = {
  /** Tên field gửi lên backend — cũng là key trong `exceptions.input_context`. */
  key: string;
  label: string;
  type: FollowUpType;
  /** Chỉ dùng cho type "choice". */
  options?: { key: string; label: string }[];
  /** Bỏ trống = bắt buộc. Đặt true cho câu hỏi "nếu biết". */
  optional?: boolean;
  /** Câu hỏi lồng: chỉ hiện khi câu trước trả lời đúng giá trị này. */
  showWhen?: { key: string; equals: unknown };
  hint?: string;
};

// Câu hỏi phụ theo ANSWER_KEY (không theo sub_type): `late_departure` có 2
// answer_key với 2 bộ câu hỏi khác hẳn nhau, khoá theo sub_type là không đủ.
export const FOLLOW_UPS: Record<string, FollowUpField[]> = {
  // --- delay ---
  chua_xuat_phat: [
    {
      key: "late_departure_cause",
      label: "Nguyên nhân chậm xuất phát?",
      type: "choice",
      options: [
        { key: "thieu_nhan_luc", label: "Thiếu nhân lực bốc xếp" },
        { key: "thieu_hong_thiet_bi", label: "Thiếu / hỏng thiết bị (xe nâng, pallet...)" },
        { key: "cho_chung_tu", label: "Chờ chứng từ / thủ tục" },
        { key: "hang_chua_ve_kho", label: "Hàng chưa về kho kịp" },
        { key: "khac", label: "Khác" },
      ],
    },
    {
      key: "estimated_departure_delay_min",
      label: "Dự kiến trễ bao nhiêu phút?",
      type: "number",
      hint: "Ước tính — xe chưa xuất phát nên chưa có số thực tế.",
    },
  ],
  da_xuat_phat_nhung_tre: [
    { key: "departure_delay_min", label: "Trễ thực tế bao nhiêu phút?", type: "number" },
    {
      key: "departed_late_cause",
      label: "Nguyên nhân (nếu biết)?",
      type: "choice",
      optional: true,
      options: [
        { key: "cham_tai_kho", label: "Chậm tại kho" },
        { key: "phat_sinh_doc_duong", label: "Phát sinh dọc đường" },
        { key: "khong_ro", label: "Không rõ" },
      ],
    },
  ],
  mat_lien_lac_tai_xe: [
    { key: "driver_contact_lost_min", label: "Đã mất liên lạc bao nhiêu phút?", type: "number" },
  ],

  // --- road_block ---
  un_tac_van_di_duoc: [
    { key: "estimated_traffic_duration_min", label: "Thời gian tắc đường ước tính (phút)", type: "number" },
  ],
  chan_hoan_toan: [
    {
      key: "current_address",
      label: "Vị trí xe hiện tại",
      type: "location",
      hint: "Dùng để tìm tuyến thay thế né đoạn đang bị chặn. Chỉ cần điền MỘT trong hai: gõ địa chỉ hoặc ghim toạ độ trên bản đồ.",
    },
  ],

  // --- customer_reject ---
  khong_co_nguoi_nhan: [
    { key: "contacted_customer", label: "Có liên lạc được với khách không?", type: "boolean" },
    {
      key: "customer_request",
      label: "Khách muốn xử lý thế nào?",
      type: "choice",
      showWhen: { key: "contacted_customer", equals: true },
      options: [
        { key: "hen_giao_lai", label: "Hẹn giao lại giờ khác / ngày khác" },
        { key: "doi_dia_diem", label: "Đổi địa điểm nhận" },
        { key: "huy", label: "Huỷ đơn" },
      ],
    },
    {
      key: "is_repeat_delivery",
      label: "Đây có phải lần giao lại (lần 2 trở lên) không?",
      type: "boolean",
      showWhen: { key: "contacted_customer", equals: false },
    },
  ],
  tu_choi_nhan_tranh_chap: [
    {
      key: "dispute_type",
      label: "Loại tranh chấp?",
      type: "choice",
      options: [
        { key: "thieu_hang_sai_so_luong", label: "Thiếu hàng / sai số lượng" },
        { key: "hang_hong_vo", label: "Hàng hỏng / vỡ" },
        { key: "sai_gia_cod", label: "Sai giá / COD" },
        { key: "khac", label: "Khác" },
      ],
    },
  ],

  // --- customer_change ---
  doi_gio_nhan: [
    {
      key: "has_time_conflict",
      label: "Giờ mới có xung đột với điểm giao khác cùng chuyến không?",
      type: "boolean",
    },
  ],
  doi_dia_diem: [
    { key: "new_location_distance_km", label: "Địa điểm mới cách tuyến hiện tại bao xa (km)?", type: "number" },
  ],

  // --- vehicle_issue ---
  hong_nhe_van_chay_duoc: [
    { key: "estimated_repair_min", label: "Thời gian sửa ước tính (phút)", type: "number" },
  ],
  hong_nang_phai_dung: [
    {
      key: "current_address",
      label: "Vị trí xe hiện tại",
      type: "location",
      hint: "Dùng để tìm xe thay thế gần nhất. Chỉ cần điền MỘT trong hai: gõ địa chỉ hoặc ghim toạ độ trên bản đồ.",
    },
    {
      key: "can_transfer_cargo_safely",
      label: "Xe có thể dừng an toàn tại đây để chuyển hàng sang xe khác không?",
      type: "choice",
      options: [
        { key: "co", label: "Có" },
        { key: "khong", label: "Không" },
        { key: "chua_chac", label: "Chưa chắc" },
      ],
    },
  ],
  tai_nan: [
    { key: "has_injury", label: "Có ai bị thương không?", type: "boolean" },
    { key: "vehicle_movable", label: "Xe còn di chuyển được sau tai nạn không?", type: "boolean" },
  ],
};

/** Field số phút trễ xuất phát của `late_departure` — dùng để tự đồng bộ sang ô
 * "số phút trễ tại các điểm bị ảnh hưởng": trễ xuất phát N phút nghĩa là MỌI
 * điểm phía sau cũng trễ đúng N phút đó (mục 15, kịch bản 1), không phải 2 con
 * số độc lập. */
export const DEPARTURE_DELAY_KEYS = ["departure_delay_min", "estimated_departure_delay_min"];

/** Câu hỏi phụ nào đang thực sự hiện, sau khi lọc `showWhen`. */
export function visibleFollowUps(answerKey: string, answers: Record<string, unknown>): FollowUpField[] {
  return (FOLLOW_UPS[answerKey] ?? []).filter(
    (f) => !f.showWhen || answers[f.showWhen.key] === f.showWhen.equals,
  );
}

/** Còn câu hỏi phụ BẮT BUỘC nào chưa trả lời không (dùng để khoá nút submit). */
export function missingRequiredFollowUp(answerKey: string, answers: Record<string, unknown>): boolean {
  return visibleFollowUps(answerKey, answers).some((f) => {
    if (f.optional) return false;
    // Field "location" (LocationPicker.tsx) ghi 2 kiểu độc lập: gõ địa chỉ chữ
    // HOẶC ghim toạ độ trên bản đồ — coi là đã trả lời nếu có MỘT trong hai,
    // không bắt phải có cả 2. Thiếu điều kiện này thì ghim bản đồ xong nút
    // submit vẫn khoá, người dùng tưởng nhầm là bug (đã gặp thật, 2026-09-12).
    if (f.type === "location") {
      const hasAddress = typeof answers[f.key] === "string" && answers[f.key] !== "";
      const hasCoords = typeof answers.current_lat === "number" && typeof answers.current_lng === "number";
      return !hasAddress && !hasCoords;
    }
    return answers[f.key] === undefined || answers[f.key] === null || answers[f.key] === "";
  });
}

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
