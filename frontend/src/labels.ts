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
