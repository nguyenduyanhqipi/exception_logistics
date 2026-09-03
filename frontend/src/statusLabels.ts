// Nhãn tiếng Việt cho status/severity của ngoại lệ — nguồn duy nhất dùng
// chung ở Dashboard, Lịch sử và trang chi tiết, để thêm 1 status mới không
// phải đi sửa 3 chỗ rồi sót 1 chỗ.
//
// "awaiting_outcome" là status thêm ngày 2026-09-04: đã chốt phương án nhưng
// CHƯA nhập kết quả thực tế (xem backend/api/decisions.py).

export const EXCEPTION_STATUS_LABEL: Record<string, string> = {
  pending: "Chờ xử lý",
  analyzing: "Đang phân tích",
  awaiting_decision: "Chờ xác nhận",
  awaiting_outcome: "Chưa có kết quả",
  resolved: "Đã xử lý",
};

export const SEVERITY_LABEL: Record<string, string> = {
  warning: "Cảnh báo",
  serious: "Nghiêm trọng",
  critical: "Khẩn cấp",
};
