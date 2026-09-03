export type Severity = "warning" | "serious" | "critical";
export type ExceptionStatus = "pending" | "analyzing" | "awaiting_decision" | "resolved";

export interface Stop {
  stop_id: string;
  stop_order: number;
  stop_type: "lay_hang" | "giao_hang";
  address: string;
  area: string;
  order_id: string;
  customer_name: string;
  customer_phone: string;
  eta: string;
  sla_deadline: string;
  priority_tier: "thuong" | "vip" | "hop_dong_phat";
  volume_kg?: number | null;
  cargo_type?: string | null;
  notes?: string | null;
  // Các field còn lại của stop trong JSONB — form sửa đơn hàng phải gửi lại
  // ĐỦ mọi field vì backend (api/schedules.py::add_or_update_stop) dựng lại
  // stop từ payload, field nào không gửi coi như bị xoá.
  loading_duration_min?: number | null;
  sla_penalty?: number | null;
  lat?: number | null;
  lng?: number | null;
}

export interface Vehicle {
  vehicle_id: string;
  driver_name: string;
  driver_phone: string;
  max_payload_kg: number;
  vehicle_type: string | null;
  cost_per_km: number | null;
  status: string;
}

export interface Schedule {
  schedule_id: string;
  vehicle_id: string;
  shift_date: string;
  shift_label: string;
  trip_sequence: number;
  planned_departure_time: string | null;
  stops: Stop[];
  status: string;
}

export interface ExceptionSummary {
  exception_id: string;
  schedule_id: string;
  group_id: string | null;
  exception_group: string;
  sub_type: string;
  severity: Severity | null;
  vehicle_id: string | null;
  area: string | null;
  description: string | null;
  status: ExceptionStatus;
  customer_accepted_delay_min?: number | null;
  // Tín hiệu định lượng đã nhập lúc tạo/sửa — form sửa nạp lại từ đây.
  // null với ngoại lệ tạo trước migration f5a6b7c8d9e0.
  input_context?: Record<string, unknown> | null;
}

export interface AffectedStop {
  stop_id: string;
  order_id: string;
  new_eta: string;
  sla_deadline: string;
  sla_breach: boolean;
  delay_minutes: number;
  priority_tier: string;
  sla_penalty: number | null;
}

export interface OptionItem {
  option_id: string;
  description: string;
  cost_estimate: number | null;
  time_estimate_minutes: number | null;
  sla_risk_remaining: number | null;
  llm_explanation: string | null;
  score: number | null;
  rank: number | null;
}

export interface JobInfo {
  job_id: string;
  status: "pending" | "running" | "done" | "failed";
  error?: string | null;
}

export interface ExceptionDetail extends ExceptionSummary {
  impact_analysis: {
    affected_stops: AffectedStop[];
    total_cost_estimate: number | null;
  } | null;
  job: JobInfo | null;
  options: OptionItem[];
}

export interface ExceptionGroupDetail {
  group_id: string;
  mode: string;
  status: string;
  exceptions: ExceptionSummary[];
  options: OptionItem[];
  job: JobInfo | null;
}

// --- Dashboard "hoạt động hôm nay" (GET /api/dashboard/today) ---

export interface DashboardOpenException {
  exception_id: string;
  schedule_id: string;
  group_id: string | null;
  exception_group: string;
  sub_type: string;
  severity: Severity | null;
  status: ExceptionStatus;
  area: string | null;
  description: string | null;
  reported_at: string | null;
  // Rỗng = ngoại lệ ảnh hưởng cả chuyến, không khoanh vùng được đơn cụ thể.
  affected_stop_ids: string[];
  affected_order_ids: string[];
}

export interface DashboardTrip {
  schedule_id: string;
  trip_sequence: number;
  depot_address: string | null;
  depot_arrival_time: string | null;
  planned_departure_time: string | null;
  status: string;
  order_count: number;
  stops: Stop[];
}

export interface DashboardShift {
  shift_label: string;
  trip_count: number;
  order_count: number;
  trips: DashboardTrip[];
}

export interface DashboardVehicle {
  vehicle_id: string;
  driver_name: string | null;
  driver_phone: string | null;
  vehicle_type: string | null;
  vehicle_status: string | null;
  current_shift_order_count: number;
  today_order_count: number;
  shifts: DashboardShift[];
  open_exceptions: DashboardOpenException[];
}

export interface DashboardToday {
  shift_date: string;
  current_shift_label: string;
  server_time: string;
  vehicles: DashboardVehicle[];
}
