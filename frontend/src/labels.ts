// Nhãn tiếng Việt cho sub_type — nguồn duy nhất dùng chung mọi nơi hiển thị
// sub_type (Dashboard, ExceptionDetail, ExceptionGroup...), tránh in thẳng mã
// tiếng Anh raw ra UI. Rút gọn từ câu hỏi/đáp án trong NewException.tsx
// (GROUP_QUESTIONS/ANSWER_TO_SUBTYPE) — sub_type nào thêm ở đó thì thêm nhãn
// tương ứng ở đây.
export const SUB_TYPE_LABEL: Record<string, string> = {
  late_departure: "Xuất phát trễ",
  slow_loading: "Chậm bốc/dỡ hàng",
  unknown_delay: "Trễ không rõ lý do",
  traffic_jam: "Ùn tắc giao thông",
  road_closed: "Đường bị chặn/cấm",
  customer_absent: "Khách vắng mặt",
  customer_dispute: "Khách từ chối nhận",
  wrong_address: "Sai địa chỉ",
  change_time: "Đổi giờ nhận hàng",
  change_location: "Đổi địa điểm giao",
  cancel_order: "Hủy đơn",
  minor_breakdown: "Sự cố xe nhẹ",
  major_breakdown: "Sự cố xe nặng",
  accident: "Tai nạn giao thông",
};

export function subTypeLabel(subType: string): string {
  return SUB_TYPE_LABEL[subType] ?? subType;
}


// Nhãn tiếng Việt cho `exception_group` (nhóm ngoại lệ, tầng trên sub_type) —
// lấy đúng chữ đang dùng ở form nhập ngoại lệ (exceptionForm.ts::GROUP_QUESTIONS)
// để bảng "Xu hướng ngoại lệ" ở trang Báo cáo không hiện mã tiếng Anh thô.
export const EXCEPTION_GROUP_LABEL: Record<string, string> = {
  delay: "Trễ giờ",
  road_block: "Chặn đường",
  customer_reject: "Khách từ chối nhận hàng",
  customer_change: "Khách đổi yêu cầu",
  vehicle_issue: "Sự cố xe",
};

export function exceptionGroupLabel(group: string): string {
  return EXCEPTION_GROUP_LABEL[group] ?? group;
}
