# TECHNICAL_SPEC.md — Exception Logistics
> Tài liệu này là nguồn sự thật duy nhất cho toàn bộ project — mô tả THIẾT KẾ (build gì, như thế nào).
> Claude Code đọc file này trước khi làm bất cứ thứ gì.
> Khi có quyết định mới, cập nhật file này trước khi code.
> Khi bắt đầu/tiếp tục CODE, đọc thêm `BUILD_PLAN.md` (cùng thư mục) — đó là checklist THỨ TỰ làm
> việc + theo dõi tiến độ (đang làm đến bước nào, bước nào xong). Luôn bắt đầu phiên code mới bằng
> cách đọc `BUILD_PLAN.md` để biết tiếp tục từ đâu, không đọc lại toàn bộ spec để đoán tiến độ.

---

## 1. PRODUCT OVERVIEW

**Tên sản phẩm:** Exception Logistics
**Loại:** Web application — Decision Support System
**Mục đích:** Hỗ trợ điều phối viên logistics xử lý ngoại lệ vận hành: từ phát hiện → phân tích tác động → đề xuất phương án → xác nhận quyết định.

**Chuỗi giá trị:** KẾ HOẠCH → NGOẠI LỆ → TÁC ĐỘNG → PHƯƠNG ÁN → QUYẾT ĐỊNH → HỌC TẬP

**Người dùng:**
- `dispatcher` — điều phối viên: nhập kế hoạch, nhập ngoại lệ, xem phương án, xác nhận
- `manager` — quản lý: xem báo cáo KPI, cài đặt hệ thống

**Không làm:**
- App tài xế (tài xế nhận thông tin qua điện thoại)
- GPS tracking realtime (vị trí xe do dispatcher nhập tay)
- TMS/WMS integration (đầu connector thiết kế sẵn, chưa implement)
- RAG (schema sẵn, kích hoạt sau ~200 trường hợp)
- Machine learning (giai đoạn 3)
- Tự động thực thi không có người xác nhận

---

## 2. TECH STACK

```
Frontend:   React + TypeScript
Backend:    Python + FastAPI
Database:   PostgreSQL + pgvector
LLM:        Gemini 2.5 Flash (Google AI API)
Embedding:  Gemini Embedding API (cho RAG giai đoạn 2)
Maps:       Google Geocoding API + Distance Matrix API
Migration:  Alembic
Error log:  Sentry (free tier)
File parse: pandas
Hosting:    Railway hoặc Render
```

**LLM Adapter:** Toàn bộ code gọi LLM qua một lớp trung gian duy nhất (`/backend/core/llm_adapter.py`). Đổi LLM chỉ sửa file này.

**Background jobs:** Queue đơn giản trong PostgreSQL (bảng `background_jobs`). Không dùng Redis hay Celery giai đoạn đầu.

---

## 3. PROJECT STRUCTURE

```
exception-logistics/
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx          # Trang chính dispatcher
│   │   │   ├── ExceptionDetail.tsx    # Xử lý một ngoại lệ
│   │   │   ├── ExceptionGroup.tsx     # Xử lý nhóm ngoại lệ
│   │   │   ├── ScheduleInput.tsx      # Nhập kế hoạch
│   │   │   └── ManagerDashboard.tsx   # Dashboard quản lý
│   │   ├── components/
│   │   ├── hooks/
│   │   │   └── usePolling.ts          # Polling background job status
│   │   └── api/
├── backend/
│   ├── main.py
│   ├── core/
│   │   ├── llm_adapter.py             # LLM Adapter — gọi Gemini
│   │   ├── rule_engine.py             # Rule-based classification
│   │   ├── impact_analyzer.py         # Phân tích tác động
│   │   ├── option_generator.py        # Sinh phương án (gọi LLM)
│   │   ├── ranker.py                  # Xếp hạng phương án
│   │   ├── geocoder.py                # Google Maps wrapper
│   │   └── conflict_detector.py       # Phát hiện xung đột nhiều ngoại lệ
│   ├── api/
│   │   ├── auth.py
│   │   ├── schedules.py
│   │   ├── exceptions.py
│   │   ├── decisions.py
│   │   └── reports.py
│   ├── models/                        # SQLAlchemy models
│   ├── schemas/                       # Pydantic schemas
│   ├── middleware/
│   │   ├── tenant.py                  # Auto-inject company_id
│   │   ├── auth.py                    # JWT validation
│   │   └── rbac.py                    # Role check
│   ├── worker/
│   │   └── job_processor.py           # Background job worker
│   └── alembic/                       # Migration scripts
├── TECHNICAL_SPEC.md                  # File này
├── .env.example
└── docker-compose.yml
```

---

## 4. DATABASE SCHEMA

### Nguyên tắc bắt buộc
- Mọi bảng đều có `company_id` — middleware tự động filter
- Mọi bảng dữ liệu người dùng đều có `deleted_at` — soft delete
- Tất cả timestamp lưu UTC
- Mọi thay đổi schema đều qua Alembic migration

### Các bảng

```sql
-- Multi-tenant root
companies (
  company_id UUID PK,
  name TEXT,
  timezone TEXT DEFAULT 'Asia/Ho_Chi_Minh',
  ranking_weights JSONB DEFAULT '{"cost":0.4,"time":0.3,"sla_risk":0.3}',
  default_depot_address TEXT,     -- điểm tập kết/kho mặc định — cấu hình trong Settings
  default_depot_area TEXT,
  default_cost_per_km DECIMAL DEFAULT 8000,  -- VNĐ/km DỰ PHÒNG — chỉ dùng khi 1 xe cụ thể
                                  -- chưa có vehicles.cost_per_km riêng (xem bảng vehicles)
  created_at TIMESTAMPTZ
)

-- Danh mục xe (fleet master data) — đổi theo tuần/tháng (đổi tài xế, thêm/bớt xe), KHÔNG
-- lặp lại mỗi chuyến/ngày. Quản lý qua sheet `Danh_muc_xe` (mục 6.1) — hiện rõ để dễ sửa
-- khi đổi tài xế, không giấu trong màn cấu hình khó tìm.
vehicles (
  vehicle_id TEXT PK,          -- biển số xe, vd 'B01'
  company_id UUID FK→companies,
  driver_name TEXT,
  driver_phone TEXT,
  vehicle_type TEXT NULLABLE,  -- mô tả tự do, KHÔNG bắt buộc (vd 'xe máy', 'xe tải thùng kín') — không
                                  -- còn dùng để phân loại nhỏ/trung/lớn, xem max_payload_kg
  max_payload_kg DECIMAL,      -- tải trọng tối đa (kg), company nhập đúng số theo giấy đăng ký xe — dùng
                                  -- khi chọn xe thay thế (mục 5.4) VÀ làm căn cứ đối chiếu biển cấm tải
                                  -- trọng trên đường khi cân nhắc đổi tuyến (vd đường cấm xe tải trên
                                  -- 1.500kg = 1,5 tấn) — luật giao thông tác động theo trọng tải cụ thể
                                  -- của xe, không theo bậc nhỏ/trung/lớn chung chung
  cost_per_km DECIMAL NULLABLE,   -- VNĐ/km CỦA RIÊNG XE NÀY (nhiên liệu + khấu hao) — mỗi loại
                                  -- xe tiêu hao khác nhau. NULL = dùng companies.default_cost_per_km
  status TEXT DEFAULT 'active',   -- 'active','inactive' — xe inactive không được đề xuất làm xe thay thế
  created_at TIMESTAMPTZ,
  deleted_at TIMESTAMPTZ
)

-- Users
users (
  user_id UUID PK,
  company_id UUID FK→companies,
  email TEXT UNIQUE,
  password_hash TEXT,
  role TEXT CHECK (role IN ('dispatcher','manager')),
  full_name TEXT,
  created_at TIMESTAMPTZ,
  deleted_at TIMESTAMPTZ
)

-- Kế hoạch vận chuyển (1 record = 1 CHUYẾN, KHÔNG phải 1 ca — 1 xe có thể có nhiều chuyến
-- trong cùng 1 ca (đi-về-đi lại lấy hàng đợt 2...), phân biệt bằng trip_sequence.
-- driver_name/phone lấy qua FK vehicles, không lưu trùng)
schedules (
  schedule_id UUID PK,
  company_id UUID FK→companies,
  vehicle_id TEXT FK→vehicles,
  shift_date DATE,
  shift_label TEXT,          -- 'ca_sang', 'ca_chieu', 'ca_dem'
  trip_sequence INT DEFAULT 1,  -- thứ tự chuyến trong ca (1 = chuyến đầu/duy nhất; 2 = chuyến 2 cùng ca...)
  depot_arrival_time TIME NULLABLE,  -- giờ dự kiến xe/tài xế CÓ MẶT tại kho để bắt đầu bốc hàng CHO
                                  -- CHUYẾN NÀY — nhập tay, neo vào ĐẦU chuyến, không lặp theo từng đơn
  depot_loading_duration_min INT NULLABLE,  -- phút bốc hàng dự kiến tại kho CHO CHUYẾN NÀY — nhập tay,
                                  -- cùng cấp với depot_arrival_time (không phải loading_duration_min
                                  -- trong stops[], cái đó là bốc/dỡ TẠI TỪNG ĐIỂM giữa/cuối tuyến)
  planned_departure_time TIME,   -- KHÔNG nhập tay — backend tự tính = depot_arrival_time +
                                  -- depot_loading_duration_min khi lưu chuyến. Giữ làm cột riêng để
                                  -- rule engine (mục 5.1, 'late_departure'/'slow_loading') và các nơi
                                  -- khác truy vấn trực tiếp mà không phải tính lại mỗi lần. Nếu thiếu
                                  -- 1 trong 2 giá trị đầu vào thì NULL — dispatcher nhập tay bù khi cần
  depot_address TEXT,        -- NULL = dùng companies.default_depot_address; chỉ set khi chuyến này xuất phát nơi khác
  stops JSONB,               -- [{stop_id, stop_order, stop_type('lay_hang'|'giao_hang'), address, area,
                              --   lat, lng, order_id, customer_name, customer_phone, eta, loading_duration_min,
                              --   sla_deadline, priority_tier('thuong'|'vip'|'hop_dong_phat'), sla_penalty,
                              --   volume_kg, cargo_type('normal'|'bulky'), notes}]  — khớp đúng tên cột/giá
                              --   trị enum của sheet `Ke_hoach_giao_hang` (mục 6.2), không tự đặt tên khác
  status TEXT DEFAULT 'active',
  created_by UUID FK→users,
  created_at TIMESTAMPTZ,
  deleted_at TIMESTAMPTZ
)
-- UNIQUE (company_id, vehicle_id, shift_date, shift_label, trip_sequence) WHERE deleted_at IS NULL

-- Ngoại lệ
exceptions (
  exception_id UUID PK,
  company_id UUID FK→companies,
  schedule_id UUID FK→schedules,
  group_id UUID FK→exception_groups NULLABLE,
  exception_group TEXT,      -- 'delay','road_block','customer_reject','customer_change','vehicle_issue'
  sub_type TEXT,             -- xem mục 5
  severity TEXT,             -- 'warning','serious','critical'
  vehicle_id TEXT,
  area TEXT,                 -- khu vực xe đang ở (nhập tay)
  description TEXT,
  status TEXT DEFAULT 'pending',  -- 'pending','analyzing','awaiting_decision','resolved'
  reported_by UUID FK→users,
  reported_at TIMESTAMPTZ,
  deleted_at TIMESTAMPTZ
)

-- Nhóm ngoại lệ (khi 2+ ngoại lệ liên quan nhau)
exception_groups (
  group_id UUID PK,
  company_id UUID FK→companies,
  exception_ids UUID[],
  mode TEXT CHECK (mode IN ('independent','combined')),
  status TEXT DEFAULT 'pending',
  created_at TIMESTAMPTZ
)

-- Khóa tài nguyên tạm thời
resource_locks (
  lock_id UUID PK,
  exception_id UUID,
  resource_type TEXT,        -- 'vehicle','driver'
  resource_id TEXT,
  locked_by UUID FK→users,
  locked_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ     -- tự hết hạn sau 10 phút
)

-- Phân tích tác động
impact_analysis (
  impact_id UUID PK,
  exception_id UUID FK→exceptions,
  affected_stops JSONB,      -- [{stop_id, order_id, delay_minutes, sla_breach, cost_estimate}]
  total_cost_estimate DECIMAL,
  created_at TIMESTAMPTZ
)

-- Phương án xử lý
options (
  option_id UUID PK,
  exception_id UUID NULLABLE,
  group_id UUID NULLABLE,
  description TEXT,
  score DECIMAL,
  cost_estimate DECIMAL,
  time_estimate_minutes INT,
  sla_risk_remaining DECIMAL,
  llm_explanation TEXT,      -- tiếng Việt
  prompt_version_id UUID FK→prompt_versions,
  rank INT,
  created_at TIMESTAMPTZ
)

-- Quyết định
decisions (
  decision_id UUID PK,
  company_id UUID FK→companies,
  exception_id UUID NULLABLE,
  group_id UUID NULLABLE,
  selected_option_id UUID FK→options,
  confirmed_by UUID FK→users,
  override_note TEXT,        -- nếu ghi đè đề xuất
  confirmed_at TIMESTAMPTZ
)

-- Kết quả thực tế
outcomes (
  outcome_id UUID PK,
  decision_id UUID FK→decisions,
  delivered_on_time BOOLEAN,
  actual_cost DECIMAL,
  notes TEXT,
  recorded_by UUID FK→users,
  recorded_at TIMESTAMPTZ
)

-- Vector store cho RAG (giai đoạn 2)
exception_embeddings (
  exception_id UUID FK→exceptions,
  embedding VECTOR(768),     -- pgvector
  created_at TIMESTAMPTZ
)

-- Prompt versioning
prompt_versions (
  version_id UUID PK,
  sub_type TEXT,             -- hoặc 'group' cho prompt nhóm
  content TEXT,              -- tiếng Anh
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ
)

-- Rule versioning
rule_versions (
  version_id UUID PK,
  rule_key TEXT,
  conditions JSONB,
  result JSONB,
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ
)

-- LLM usage log
llm_usage_logs (
  log_id UUID PK,
  company_id UUID,
  exception_id UUID NULLABLE,
  model TEXT,
  tokens_in INT,
  tokens_out INT,
  cost_usd DECIMAL,
  latency_ms INT,
  prompt_version_id UUID,
  success BOOLEAN,
  created_at TIMESTAMPTZ
)

-- Audit log
audit_logs (
  log_id UUID PK,
  company_id UUID,
  user_id UUID,
  action TEXT,               -- 'confirm_decision','override','update_settings',...
  entity_type TEXT,
  entity_id UUID,
  detail JSONB,
  created_at TIMESTAMPTZ
)

-- Cache Google Maps
geocode_cache (
  cache_id UUID PK,
  address_hash TEXT UNIQUE,  -- MD5 của địa chỉ
  address_raw TEXT,
  coordinates JSONB,         -- {lat, lng}
  distance_matrix JSONB,     -- cache kết quả distance matrix
  cached_at TIMESTAMPTZ
)

-- Background job queue
background_jobs (
  job_id UUID PK,
  company_id UUID,
  exception_id UUID NULLABLE,
  job_type TEXT,             -- 'analyze_exception','analyze_group'
  status TEXT DEFAULT 'pending',  -- 'pending','running','done','failed'
  result JSONB,
  error TEXT,
  created_at TIMESTAMPTZ,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ
)
```

---

## 5. EXCEPTION TYPES & SUBTYPES

```
exception_group: delay
  sub_types:
    - late_departure      # Xuất phát muộn — còn thể bù, tính lại ETA
    - slow_loading        # Bốc dỡ chậm — ảnh hưởng dây chuyền toàn tuyến
    - unknown_delay       # Trễ không rõ nguyên nhân — hỏi tài xế trước

exception_group: road_block
  sub_types:
    - traffic_jam         # Tắc đường — chờ hoặc đổi tuyến tùy thời gian ước tính
    - road_closed         # Đường bị chặn/cấm — bắt buộc đổi tuyến ngay

exception_group: customer_reject
  sub_types:
    - customer_absent     # Không có mặt — chờ, giao lại sau, hoặc hoàn hàng
    - customer_dispute    # Từ chối nhận (tranh chấp) — leo thang quản lý
    - wrong_address       # Sai địa chỉ — xác nhận lại rồi tiếp tục

exception_group: customer_change
  sub_types:
    - change_time         # Đổi giờ nhận — kiểm tra xung đột điểm khác
    - change_location     # Đổi địa điểm — tính lại tuyến
    - cancel_order        # Hủy đơn muộn — tính chi phí hủy, tái phân bổ xe

exception_group: vehicle_issue
  sub_types:
    - minor_breakdown     # Hỏng nhẹ — ước tính thời gian sửa, giữ hoặc điều chỉnh tuyến
    - major_breakdown     # Hỏng nặng — điều xe thay thế, xử lý hàng trên xe
    - accident            # Tai nạn — an toàn người trước, leo thang khẩn cấp
```

### 5.1 Câu hỏi nhanh xác định sub-type (dispatcher trả lời — KHÔNG dùng LLM để phân loại)

Khi dispatcher chọn `exception_group`, form hiển thị 1 câu hỏi trắc nghiệm (không phải text tự do) để rule engine chốt `sub_type` ngay lập tức. Free-text `description` vẫn có nhưng chỉ để lưu ngữ cảnh, không dùng để phân loại.

**Nhóm `delay` — "Xe đã xuất phát chưa?"**
| Trả lời | sub_type |
|---|---|
| Chưa xuất phát / xuất phát muộn hơn giờ kế hoạch | `late_departure` |
| Đã xuất phát, đang chậm tại điểm bốc/dỡ hàng | `slow_loading` |
| Đã xuất phát, đang di chuyển nhưng chậm không rõ lý do / mất liên lạc tài xế | `unknown_delay` |

Riêng khi chọn **"Chưa xuất phát / xuất phát muộn"**, nếu chuyến có khai báo `depot_arrival_time` (mục 4, 6.2), form hỏi thêm 1 câu để định vị đúng nguyên nhân (ghi vào `description`, không đổi `sub_type` nhưng giúp dispatcher/LLM hiểu đúng gốc rễ khi đề xuất phương án): *"Xe/tài xế có mặt tại kho đúng giờ không?"* — **Có** (đến kho đúng giờ nhưng xuất phát trễ) → nguyên nhân thực chất là bốc hàng chậm tại kho, gợi ý cân nhắc lại `sub_type = slow_loading`; **Không** (bản thân đến kho đã trễ) → giữ `late_departure`, nguyên nhân là xe/tài xế đến trễ chứ không phải quy trình bốc dỡ.

**Nhóm `road_block` — "Tình trạng đường hiện tại?"**
| Trả lời | sub_type |
|---|---|
| Ùn tắc nhưng xe vẫn nhích được | `traffic_jam` |
| Đường chặn hoàn toàn / cấm đường / ngập / tai nạn chắn ngang | `road_closed` |

**Nhóm `customer_reject` — "Vấn đề tại điểm giao là gì?"**
| Trả lời | sub_type |
|---|---|
| Không có ai nhận hàng | `customer_absent` |
| Khách có mặt nhưng từ chối nhận (tranh chấp hàng/giá/chất lượng) | `customer_dispute` |
| Địa chỉ sai / không tìm thấy / không tồn tại | `wrong_address` |

**Nhóm `customer_change` — "Khách yêu cầu thay đổi gì?"**
| Trả lời | sub_type |
|---|---|
| Đổi giờ nhận hàng | `change_time` |
| Đổi địa điểm giao | `change_location` |
| Hủy đơn | `cancel_order` |

**Nhóm `vehicle_issue` — "Mức độ hư hỏng xe?"** (kèm câu hỏi bắt buộc thứ 2 nếu chọn tai nạn: *"Có ai bị thương không?"* — câu trả lời này ghi vào `description`, không đổi sub_type nhưng kích hoạt cảnh báo an toàn ưu tiên cao nhất trong UI)
| Trả lời | sub_type |
|---|---|
| Xe vẫn chạy được, sự cố nhỏ (non hơi, đèn báo lỗi...) | `minor_breakdown` |
| Xe không chạy được, phải dừng hẳn, cần xe thay thế | `major_breakdown` |
| Có va chạm / tai nạn giao thông | `accident` |

### 5.2 Ngưỡng phân loại severity (chi tiết)

Rule engine dùng **2 lớp**: (a) severity nền theo `sub_type`, (b) quy tắc leo thang (escalation) dựa trên biến số thời gian/tác động thực tế của tình huống. Escalation chỉ đẩy severity lên, không bao giờ hạ xuống.

**Biến số dùng để leo thang** (tính trong `impact_analyzer.py`, đưa vào rule engine):
- `time_to_deadline_min` — số phút còn lại đến `sla_deadline` gần nhất trong các điểm bị ảnh hưởng
- `downstream_stops_affected` — số điểm giao phía sau bị trễ dây chuyền
- `has_priority_order` — TRUE nếu bất kỳ điểm bị ảnh hưởng nào có `priority_tier ∈ {vip, contract}` HOẶC `sla_penalty` > 500.000đ (mục 6 — `priority_tier` là cách dispatcher đánh dấu đơn quan trọng mà không cần biết số tiền phạt chính xác; `sla_penalty` chỉ dùng khi đơn thực sự có điều khoản phạt trong hợp đồng)

**Bảng severity nền theo sub_type:**

| exception_group | sub_type | Severity nền | Leo thang lên SERIOUS nếu (khi nền = warning) |
|---|---|---|---|
| delay | `late_departure` | warning | delay > 30 phút HOẶC `downstream_stops_affected` ≥ 3 |
| delay | `slow_loading` | warning | `downstream_stops_affected` ≥ 3 |
| delay | `unknown_delay` | warning | mất liên lạc tài xế > 15 phút |
| road_block | `traffic_jam` | warning | thời gian tắc ước tính > 60 phút |
| road_block | `road_closed` | **serious** (cố định) | — |
| customer_reject | `customer_absent` | warning | `has_priority_order` HOẶC đây là lần giao lại thứ 2+ |
| customer_reject | `customer_dispute` | **serious** (cố định) | — |
| customer_reject | `wrong_address` | warning | địa chỉ mới cách địa chỉ cũ > 5km |
| customer_change | `change_time` | warning | giờ mới xung đột lịch với điểm giao khác cùng chuyến |
| customer_change | `change_location` | warning | địa điểm mới cách tuyến hiện tại > 5km |
| customer_change | `cancel_order` | warning | `has_priority_order` |
| vehicle_issue | `minor_breakdown` | warning | thời gian sửa ước tính > 30 phút |
| vehicle_issue | `major_breakdown` | **serious** (cố định) | — |
| vehicle_issue | `accident` | **critical** (cố định, luôn) | — |

**Quy tắc ghi đè toàn cục (áp dụng sau bảng trên, ưu tiên cao nhất — chạy cuối cùng trong `rule_engine.py`):**
1. Có rủi ro an toàn con người (tai nạn có người bị thương) → **critical**, bất kể sub_type.
2. `time_to_deadline_min` < 30 (ít nhất 1 điểm ảnh hưởng) → tối thiểu **critical**.
3. `time_to_deadline_min` trong khoảng 30–90 → tối thiểu **serious**.
4. `downstream_stops_affected` ≥ 3 → nâng tối thiểu 1 bậc (warning→serious; serious/critical giữ nguyên).

Ngưỡng số (500.000đ, 5km, 30 phút, 60 phút, 30/90 phút...) lưu trong bảng `rule_versions.conditions` (JSONB) — không hardcode trong code, để company có thể tùy chỉnh qua Settings sau này.

### 5.4 Xử lý tải trọng và hàng cồng kềnh khi chọn xe thay thế

Dispatcher hiếm khi biết chính xác thể tích (m³) của lô hàng, nên hệ thống **không** yêu cầu nhập thể tích. Thay vào đó dùng 2 tín hiệu đơn giản, dễ đánh giá cảm quan:

- `volume_kg` (optional, per điểm giao) — cộng dồn theo xe để so với `vehicles.max_payload_kg` khi `option_generator.py` tìm xe thay thế (`nearest_available_vehicles`, mục 5.3). Xe có tổng `volume_kg` của các đơn cần chuyển vượt `max_payload_kg` bị loại khỏi candidate.
- `cargo_type` (optional, dropdown `normal` / `bulky`, per điểm giao) — nếu `bulky`, hệ thống nhân `volume_kg` với hệ số **1.7** (config trong `rule_versions`) trước khi so với `max_payload_kg`, để bù cho phần thể tích chiếm chỗ mà cân nặng không phản ánh được, mà không bắt dispatcher đo đạc chính xác. Đây là ước lượng thận trọng (conservative), không phải phép tính m³ thật.
- Nếu `volume_kg` bị bỏ trống hoàn toàn (dispatcher không rõ) → hệ thống không loại xe nào theo tải trọng, để LLM/dispatcher tự đánh giá bằng `description`/`notes` — tránh việc thiếu dữ liệu làm hệ thống loại nhầm phương án khả thi.

### 5.3 Logic phát hiện xung đột — chi tiết `conflict_detector.py`

Mở rộng mục 10 (Multi-Exception Handling). Khi ngoại lệ mới được tạo, hàm `detect_conflict(new_exception)` so sánh với mọi ngoại lệ đang active (`status IN ('pending','analyzing','awaiting_decision')`) của cùng company:

```python
def detect_conflict(new_exc, active_exceptions):
    for existing in active_exceptions:
        signals = []

        # 1. Cùng tài nguyên trực tiếp
        if new_exc.vehicle_id == existing.vehicle_id:
            signals.append("same_vehicle")
        if new_exc.schedule.driver_name == existing.schedule.driver_name:
            signals.append("same_driver")

        # 2. Cùng điểm giao trong cùng chuyến
        if new_exc.schedule_id == existing.schedule_id:
            if overlap(new_exc.affected_stop_ids, existing.affected_stop_ids):
                signals.append("same_stop")

        # 3. Tranh chấp tài nguyên dự phòng (resource contention)
        #    Áp dụng cho sub_type cần "xe thay thế": major_breakdown, road_closed, accident
        if needs_replacement_vehicle(new_exc) and needs_replacement_vehicle(existing):
            new_candidates = nearest_available_vehicles(new_exc, top_n=2)
            existing_candidates = nearest_available_vehicles(existing, top_n=2)
            if overlap(new_candidates, existing_candidates):
                signals.append("resource_contention")

        # 4. Cùng khu vực + cùng khung giờ — chỉ là tín hiệu tham khảo, KHÔNG tự kích hoạt combined
        if new_exc.area == existing.area and time_overlap(new_exc, existing, window_min=30):
            signals.append("same_area_same_time")  # log để dispatcher tham khảo, không đổi mode

        hard_signals = {"same_vehicle", "same_driver", "same_stop", "resource_contention"}
        if set(signals) & hard_signals:
            return "combined", existing, signals

    return "independent", None, []
```

**Kết quả:**
- **`independent`** — không có tín hiệu cứng nào → 2 ngoại lệ tạo 2 job riêng, dispatcher xử lý trên 2 màn hình `ExceptionDetail` song song, mỗi cái ra options độc lập.
- **`combined`** — có ít nhất 1 tín hiệu cứng → tạo `exception_groups` record với `mode='combined'`, cả 2 exception's `group_id` trỏ vào đó, job chuyển thành `analyze_group`, LLM nhận context của cả hai ngoại lệ cùng lúc (prompt loại `group`, xem mục 19), dispatcher xác nhận **một lần duy nhất** trên màn `ExceptionGroup.tsx`.

**Resource lock khi đang chờ xác nhận:** ngay khi option_generator đề xuất dùng một tài nguyên cụ thể (ví dụ "điều xe C03 đến hỗ trợ"), hệ thống ghi vào `resource_locks` (`resource_type='vehicle'`, `expires_at = now() + 10 phút`). Khi tính `resource_contention` ở bước 3, chỉ xét các lock có `expires_at > now()`. Worker chạy job dọn dẹp lock hết hạn mỗi 5 phút.

**Xử lý 3+ ngoại lệ đồng thời:** đưa vào hàng đợi ưu tiên `critical > serious > warning`; cùng severity thì theo `reported_at` (nhập trước xử lý trước). Sau mỗi lần dispatcher xác nhận quyết định (`POST /api/decisions`), hệ thống re-chạy `detect_conflict` và tính lại tài nguyên khả dụng cho ngoại lệ tiếp theo trong hàng đợi trước khi generate options — nếu tài nguyên vừa bị dùng bởi quyết định trước, nó bị loại khỏi danh sách candidate cho ngoại lệ sau.

---

## 6. EXCEL TEMPLATE FIELDS

File template: `schedule_template.xlsx` (đã tạo, nằm cùng thư mục với file spec này).

### 6.0 Nguyên tắc thiết kế — chia sheet theo TẦN SUẤT THAY ĐỔI thực tế

Hệ thống này là **công cụ dự phòng xử lý ngoại lệ**, không phải hệ điều hành chính — dispatcher chỉ nên tốn thời gian ít nhất có thể để nhập dữ liệu nền. Trục chia sheet là **tần suất thay đổi thật của từng loại dữ liệu trong vận tải**, không phải theo quan hệ CSDL:

| Loại dữ liệu | Tần suất thay đổi thực tế | Sheet |
|---|---|---|
| Biển số xe, tài xế, SĐT, tải trọng, chi phí/km | Vài tuần đến vài tháng (đổi tài xế, thêm/bớt xe) | `Danh_muc_xe` |
| Điểm tập kết/kho mặc định | Gần như không đổi | `companies` — Settings, không nằm trong Excel |
| Ca, giờ đến kho, giờ bốc hàng, giờ giao, đơn hàng | **Mỗi ngày, có thể mỗi ca** — KHÔNG giả định lặp lại | `Ke_hoach_giao_hang` |

Lưu ý rút kinh nghiệm: bản trước tôi từng tách riêng 1 sheet "Chuyến" và giả định ca/giờ chạy lặp lại giữa các ngày để tự động sao chép — **sai với thực tế vận tải**, vì lịch chạy đổi theo tải hàng từng ngày, không nên tự suy đoán. Nên `schedule_template.xlsx` giờ chỉ còn **2 sheet dữ liệu** (`Danh_muc_xe`, `Ke_hoach_giao_hang`) + 1 sheet hướng dẫn — không còn sheet "Chuyến" riêng, không còn cơ chế tự sao chép.

**Hai đường nhập liệu song song, không loại trừ nhau:** (1) **Form tương tác** (`ScheduleInput.tsx`, mục 3) — tạo/sửa từng chuyến hoặc thêm/sửa từng điểm giao lẻ qua `POST /api/schedules` và `POST /api/schedules/{id}/stops` (mục 12), phù hợp khi chỉ có vài thay đổi; (2) **Upload Excel** — phù hợp khi cần nạp nhiều đơn cùng lúc hoặc cập nhật hàng loạt thông tin xe (copy-paste từ hệ thống khác).

### 6.1 Sheet `Danh_muc_xe` — đổi theo tuần/tháng, hiện rõ để dễ sửa khi đổi tài xế (1 hàng = 1 xe)

Không phải "nhập 1 lần rồi quên" — xe đổi tài xế theo chu kỳ vài tuần/tháng là chuyện bình thường trong vận tải, nên sheet này vẫn cần dễ mở ra sửa, không giấu trong màn cấu hình khó tìm. Upload lại sheet này bất cứ khi nào có xe mới hoặc đổi tài xế; **không cần upload lại mỗi ngày**.

| Tên cột | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| vehicle_id | text | ✅ | Biển số xe — khóa để nối sang sheet `Ke_hoach_giao_hang` |
| driver_name | text | ✅ | Tên tài xế hiện tại của xe này |
| driver_phone | text | ✅ | SĐT tài xế |
| vehicle_type | text | ❌ | Mô tả tự do, không bắt buộc (vd `xe máy`, `xe tải thùng kín`) — chỉ để tham khảo, KHÔNG dùng để phân loại nhỏ/trung/lớn nữa |
| max_payload_kg | number | ✅ | Tải trọng tối đa (kg) theo giấy đăng ký xe — dùng khi cần điều xe thay thế (mục 5.4) VÀ để đối chiếu biển cấm tải trọng trên đường (vd đường cấm xe tải trên 1.500kg) khi cân nhắc đổi tuyến — nhập đúng số kg thực tế, không quy tròn theo bậc |
| cost_per_km | number | ❌ | Chi phí vận hành/km của RIÊNG xe này (nhiên liệu + khấu hao, VNĐ). Bỏ trống = dùng mức mặc định chung của công ty (Settings) |
| status | text | ✅ | `active` / `inactive` — xe `inactive` không được đề xuất làm xe thay thế. Mặc định `active` |
| notes | text | ❌ | Ghi chú thêm |

**Validation:** `vehicle_id` không trùng; upload theo kiểu **UPSERT** (xe đã tồn tại → cập nhật tài xế/SĐT/tải trọng mới; xe chưa có → thêm mới) — không xóa xe vắng mặt trong file (tránh mất dữ liệu nếu chỉ upload danh sách 1 phần).

### 6.2 Sheet `Ke_hoach_giao_hang` — nhập/upload mỗi ngày, mỗi ca (1 hàng = 1 điểm giao)

Đây là sheet chính, thay đổi thật sự mỗi ngày. Các cột "đầu chuyến" (giờ đến kho, giờ bốc hàng) đặt **ngay cạnh nhau và cạnh các cột điểm giao** để dễ hiểu trình tự: xe đến kho → bốc hàng → (hệ thống tự tính giờ xuất phát) → lần lượt các điểm giao.

| Tên cột | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| vehicle_id | text | ✅* | Biển số xe — phải có sẵn trong `Danh_muc_xe`. *Để trống nếu cùng chuyến với hàng ngay phía trên (xem "Điền nhanh") |
| shift_date | date (DD/MM/YYYY) | ✅* | Ngày chạy |
| shift_label | text | ✅* | ca_sang / ca_chieu / ca_dem |
| trip_sequence | int | ❌* | Chuyến thứ mấy trong ca — **bỏ trống = 1**. 1 xe có thể chạy nhiều chuyến trong cùng 1 ca (đi giao, quay về kho lấy thêm, đi tiếp) — chỉ điền 2, 3... khi thực sự có chuyến thứ 2 trở đi |
| depot_arrival_time | time (HH:MM) | ❌** | Giờ xe/tài xế CÓ MẶT tại kho để bắt đầu bốc hàng — **chỉ điền ở hàng ĐẦU TIÊN của mỗi chuyến**, để trống ở các hàng điểm giao tiếp theo cùng chuyến đó |
| depot_loading_duration_min | number | ❌** | Phút bốc hàng dự kiến tại kho — cũng **chỉ điền ở hàng đầu tiên của chuyến**. Hệ thống tự tính giờ xuất phát = `depot_arrival_time + depot_loading_duration_min` (không có cột riêng để nhập giờ xuất phát) |
| stop_order | int | ✅ | Thứ tự điểm giao (1, 2, 3...) trong chuyến |
| stop_type | text | ✅ | `lay_hang` (pickup giữa tuyến) hoặc `giao_hang` (delivery) — mặc định `giao_hang` |
| stop_address | text | ✅ | Địa chỉ điểm giao/lấy hàng |
| stop_area | text | ✅ | Khu vực (quận/huyện) |
| order_id | text | ✅ | Mã đơn hàng — mã định danh riêng của từng đơn |
| customer_name | text | ✅ | Tên khách hàng |
| customer_phone | text | ✅ | SĐT khách |
| eta | time (HH:MM) | ✅ | Giờ dự kiến đến điểm này |
| loading_duration_min | number | ❌ | Phút bốc/dỡ ước tính TẠI ĐIỂM NÀY (áp dụng cho cả `giao_hang` lẫn `lay_hang` giữa tuyến — vd thời gian khách nhận hàng, hoặc bốc thêm hàng ở 1 điểm phụ). Hệ thống tự tính giờ rời điểm = eta + loading_duration_min, dùng để phát hiện `slow_loading` (mục 5.1) |
| sla_deadline | time (HH:MM) | ✅ | Hạn giao hàng tối đa |
| priority_tier | text | ✅ | `thuong` / `vip` / `hop_dong_phat` — mặc định `thuong`. Đơn `vip`/`hop_dong_phat` được rule engine ưu tiên xử lý cao hơn (mục 5.2) mà không cần biết số tiền phạt chính xác |
| sla_penalty | number | ❌ | Chỉ điền khi `priority_tier = hop_dong_phat` VÀ biết chính xác mức phạt trong hợp đồng (VNĐ) |
| volume_kg | number | ❌ | Khối lượng hàng (kg) — dùng khi cần điều xe thay thế (mục 5.4) |
| cargo_type | text | ❌ | `normal` / `bulky` (hàng cồng kềnh — chiếm nhiều diện tích so với cân nặng). Bỏ trống = `normal` |
| notes | text | ❌ | Ghi chú thêm |

*\*Điền nhanh (giảm lặp cột khóa):* khi nhiều hàng liên tiếp thuộc cùng 1 chuyến, chỉ điền `vehicle_id`/`shift_date`/`shift_label`/`trip_sequence` ở **hàng đầu tiên của chuyến đó**, các hàng tiếp theo để trống — parser forward-fill trước khi validate:
```python
df[["vehicle_id", "shift_date", "shift_label", "trip_sequence"]] = \
    df[["vehicle_id", "shift_date", "shift_label", "trip_sequence"]].ffill()
df["trip_sequence"] = df["trip_sequence"].fillna(1).astype(int)
```
(Không dùng merge cell — dễ vỡ khi sắp xếp lại hàng; forward-fill khi đọc file an toàn hơn.)

*\*\*`depot_arrival_time`/`depot_loading_duration_min`* — KHÔNG forward-fill (khác bản chất với cột khóa phía trên): 2 cột này chỉ có ý nghĩa ở đúng 1 thời điểm ĐẦU chuyến, nên chỉ đọc giá trị ở hàng đầu tiên của mỗi nhóm (`vehicle_id+shift_date+shift_label+trip_sequence` sau forward-fill); nếu 1 hàng giữa/cuối nhóm lại có giá trị khác 0/trống ở 2 cột này → báo lỗi rõ ràng thay vì âm thầm dùng nhầm: *"Hàng 12: depot_arrival_time chỉ được điền ở hàng đầu tiên của chuyến"*.

### Validation rules khi upload
- `shift_date` phải là ngày hợp lệ; `eta`, `sla_deadline`, `depot_arrival_time` phải đúng format HH:MM
- `stop_order` phải là số nguyên dương, không trùng trong cùng một chuyến
- `vehicle_id` (sau khi forward-fill), `order_id`, `stop_address` không được để trống
- `vehicle_id` phải tồn tại trong `vehicles` với `status='active'` (báo lỗi rõ nếu chưa khai báo xe: *"Xe B07 chưa có trong Danh_muc_xe — thêm xe trước khi nhập kế hoạch"*)
- `stop_type` chỉ nhận `lay_hang`/`giao_hang`; `priority_tier` chỉ nhận `thuong`/`vip`/`hop_dong_phat`; `cargo_type` chỉ nhận `normal`/`bulky`
- Nếu có `depot_loading_duration_min` mà thiếu `depot_arrival_time` (hoặc ngược lại) → cảnh báo (không chặn): `planned_departure_time` sẽ để trống vì thiếu 1 trong 2 giá trị đầu vào
- Báo lỗi cụ thể từng ô: "Sheet Ke_hoach_giao_hang, hàng 5, cột eta: định dạng sai. Cần HH:MM"

---

## 7. RANKING ALGORITHM

```python
def calculate_score(option, weights):
    # weights từ company settings, default:
    # {"cost": 0.4, "time": 0.3, "sla_risk": 0.3}

    cost_score   = normalize(option.cost_estimate)        # thấp hơn = điểm cao hơn
    time_score   = normalize(option.time_estimate_minutes) # thấp hơn = điểm cao hơn
    sla_score    = normalize(option.sla_risk_remaining)   # thấp hơn = điểm cao hơn

    return (
        weights["cost"]     * (1 - cost_score) +
        weights["time"]     * (1 - time_score) +
        weights["sla_risk"] * (1 - sla_score)
    )
    # Score cao hơn = phương án tốt hơn
```

LLM không tham gia tính điểm. LLM chỉ viết `llm_explanation` (tiếng Việt) giải thích tại sao phương án này được xếp hạng như vậy trong ngữ cảnh cụ thể.

**Mở rộng sau này (thêm tiêu chí/trọng số thứ 4+):** kiến trúc hiện tại cố ý tách rời để việc này KHÔNG phải viết lại hệ thống — `ranking_weights` là JSONB cấu hình (không hardcode), `calculate_score()` là hàm DUY NHẤT dùng nó, và prompt đã có versioning sẵn. Nếu sau này cần thêm 1 tiêu chí mới (vd rủi ro uy tín, mức phát thải...), các điểm cần sửa chỉ gồm: (1) thêm 1 cột mới vào bảng `options` (migration Alembic) để LLM ghi số ước tính cho tiêu chí đó; (2) thêm vài dòng chuẩn hóa + nhân trọng số cho tiêu chí đó trong `calculate_score()`; (3) thêm key mặc định vào `companies.ranking_weights` + cho phép chỉnh qua `PUT /api/settings/weights`; (4) thêm field đó vào JSON schema output của system prompt (mục 19.0) và tạo `prompt_versions` mới (không sửa đè bản cũ). Không cần đổi `rule_engine.py`, `conflict_detector.py`, hay schema `exceptions`/`schedules` — các phần đó độc lập với ranking. Tóm lại: ảnh hưởng cục bộ, không phải thiết kế lại.

---

## 8. LLM CONFIGURATION

**Model:** `gemini-3.6-flash` (Google AI API) — đổi từ `gemini-2.5-flash` lúc code Giai đoạn 6/10 (lý do kỹ thuật bắt buộc, xem docstring `backend/core/llm_adapter.py`): gọi thử `gemini-2.5-flash` bằng API key mới cấp trả lỗi thật `404 NOT_FOUND — "This model models/gemini-2.5-flash is no longer available to new users. Please update your code to use models/gemini-3.6-flash"` — Google đã sunset model này cho key/project mới. `gemini-3.6-flash` gọi được trên mọi key (kể cả key cũ), xác nhận chất lượng output tương đương/tốt hơn qua test thật.
**Xoay vòng nhiều API key:** free tier Gemini giới hạn 20 request/ngày/key, không đủ cho khối lượng test thật của dự án — `llm_adapter.py` giữ tối đa 3 key (`GEMINI_API_KEY`/`_2`/`_3` trong `.env`), tự động xoay sang key kế tiếp khi 1 key báo lỗi hạn mức (429 RESOURCE_EXHAUSTED), trong suốt với `option_generator.py`.
**Ngôn ngữ prompt:** Tiếng Anh
**Output format:** JSON bắt buộc — có trường tiếng Việt để hiển thị trực tiếp

**Output JSON schema:**
```json
{
  "options": [
    {
      "description": "string (tiếng Việt)",
      "rationale": "string (tiếng Việt) — lý do đề xuất",
      "cost_estimate": number,
      "time_estimate_minutes": number,
      "sla_risk_remaining": number,
      "explanation": "string (tiếng Việt) — giải thích xếp hạng"
    }
  ]
}
```

**Retry logic:**
1. Gọi LLM
2. Parse JSON → nếu fail: clean up text thừa → thử parse lại
3. Nếu vẫn fail: gọi lại LLM với prompt nhắc rõ "respond ONLY with valid JSON"
4. Nếu vẫn fail sau 3 lần: trả lỗi graceful, cho dispatcher nhập phương án thủ công

**LLM fallback:** Khi Gemini down hoàn toàn → thông báo rõ cho user → cho phép nhập phương án thủ công.

**Cost control:** Hard limit 100 LLM calls/company/day (configurable). Log mọi call vào `llm_usage_logs`.

---

## 9. PROMPT VERSIONING

Prompt lưu trong bảng `prompt_versions`, không hardcode.
Mỗi sub_type có prompt riêng. Có thêm prompt loại `group` cho xử lý nhiều ngoại lệ cùng lúc.

Khi sửa prompt: tạo version mới với `is_active=true`, set version cũ `is_active=false`. Không xóa version cũ — giữ lịch sử.

Mỗi lần gọi LLM: log `prompt_version_id` vào `llm_usage_logs`.

---

## 10. MULTI-EXCEPTION HANDLING

Khi ngoại lệ thứ 2 được nhập, `conflict_detector.py` kiểm tra:
- Cùng `vehicle_id`?
- Cùng `driver_name`?
- Cùng stop trong schedule?
- Phương án dự kiến của ngoại lệ 1 dùng tài nguyên mà ngoại lệ 2 cần?

**Nếu không có xung đột:** mode = `independent` — xử lý song song, hai màn hình riêng.

**Nếu có xung đột:** mode = `combined` — LLM nhận context cả hai, dùng prompt loại `group`, sinh gói phương án giải quyết đồng thời, dispatcher xác nhận một lần.

**Resource locking:** Khi dispatcher đang xem phương án (chưa xác nhận), tài nguyên liên quan được lock vào `resource_locks` với `expires_at = now() + 10 minutes`. Worker dọn lock hết hạn định kỳ.

**3+ ngoại lệ:** Xử lý tuần tự theo severity (critical → serious → warning). Sau mỗi lần xác nhận, cập nhật tài nguyên khả dụng trước khi xử lý ngoại lệ tiếp theo.

---

## 11. BACKGROUND JOB FLOW

```
1. dispatcher nhập ngoại lệ → POST /api/exceptions
2. API validate input → lưu exception vào DB → tạo job trong background_jobs → trả về {exception_id, job_id, status: "analyzing"}
3. Worker (chạy riêng) poll background_jobs WHERE status='pending'
4. Worker xử lý: rule_engine → impact_analyzer → geocoder (nếu cần) → option_generator → ranker
5. Worker update job status='done', lưu kết quả vào impact_analysis + options
6. Frontend polling GET /api/jobs/{job_id}/status mỗi 2 giây
7. Khi status='done' → frontend fetch kết quả và hiển thị
```

---

## 12. API ENDPOINTS (chính)

```
Auth:
  POST   /api/auth/login
  POST   /api/auth/refresh
  POST   /api/auth/logout

Vehicles (fleet master data — đổi theo tuần/tháng, KHÔNG lặp lại trong Excel kế hoạch hàng ngày):
  GET    /api/vehicles                     # Danh mục xe (manager + dispatcher)
  POST   /api/vehicles                     # Thêm xe mới
  PUT    /api/vehicles/{vehicle_id}       # Sửa thông tin xe (đổi tài xế, tải trọng, cost_per_km...)
  POST   /api/vehicles/upload              # Upload sheet Danh_muc_xe (mục 6.1) — UPSERT theo vehicle_id
  DELETE /api/vehicles/{vehicle_id}       # Soft delete (status='inactive')

Schedules:
  GET    /api/schedules                    # Danh sách ca hiện tại
  POST   /api/schedules                    # Tạo chuyến (nhận 1 hoặc mảng nhiều chuyến — form "khai báo nhanh")
  POST   /api/schedules/{id}/stops         # Thêm/sửa 1 điểm giao lẻ vào chuyến đã có (không cần upload lại cả file)
  POST   /api/schedules/upload             # Upload sheet Ke_hoach_giao_hang (mục 6.2) — mỗi ngày/ca
  DELETE /api/schedules/{id}              # Soft delete

Exceptions:
  GET    /api/exceptions                   # Danh sách, filter theo status/severity
  POST   /api/exceptions                   # Tạo ngoại lệ mới → trigger job
  GET    /api/exceptions/{id}             # Chi tiết + impact + options
  GET    /api/exceptions/groups/{group_id} # Chi tiết nhóm ngoại lệ

Jobs:
  GET    /api/jobs/{job_id}/status         # Polling status

Decisions:
  POST   /api/decisions                    # Xác nhận phương án
  POST   /api/outcomes                     # Nhập kết quả thực tế

Reports (manager only):
  GET    /api/reports/kpi                  # KPI tổng hợp
  GET    /api/reports/trends               # Xu hướng ngoại lệ
  GET    /api/reports/cost-accuracy        # So sánh ước tính vs thực tế
  GET    /api/reports/llm-usage            # Chi phí LLM theo thời gian

System:
  GET    /health                           # Health check
  GET    /api/settings                     # Cài đặt company (manager only) — depot, cost_per_km, ranking_weights
  PUT    /api/settings/weights             # Điều chỉnh trọng số xếp hạng
  PUT    /api/settings/depot               # Cài đặt depot mặc định + default_cost_per_km dự phòng (mục 4, 6)
```

---

## 13. SECURITY & MIDDLEWARE

```python
# Thứ tự middleware (FastAPI)
1. CORS
2. Rate limiting (100 req/min per user)
3. JWT validation → extract user_id, company_id, role
4. Tenant injection → mọi query tự động filter theo company_id
5. RBAC → check role phù hợp với endpoint
```

**Secrets:** Tất cả API key trong `.env`, không commit vào git.
```
GEMINI_API_KEY=
GOOGLE_MAPS_API_KEY=
DATABASE_URL=
JWT_SECRET=
SENTRY_DSN=
```

**Input sanitization:** Mọi text input được strip và validate trước khi đưa vào prompt LLM.

---

## 14. GOOGLE MAPS INTEGRATION

**Geocoding:** Chuyển `area` (khu vực dispatcher nhập) thành tọa độ `{lat, lng}`.

**Distance Matrix:** Tính khoảng cách và thời gian di chuyển giữa vị trí xe và các điểm cần thiết (điểm giao còn lại, điểm sửa xe gần nhất).

**Caching:** Kết quả lưu vào `geocode_cache` theo hash của địa chỉ. Không gọi API lại với cùng địa chỉ.

**Graceful degradation:** Nếu Maps API lỗi → tiếp tục xử lý ngoại lệ mà không có thông tin khoảng cách → thông báo rõ cho user "Không thể tính khoảng cách do lỗi bản đồ".

---

## 15. FAKE DATA FOR DEMO

### Công ty demo
```
company_id: demo-company-001
name: Công ty Vận tải Thành Công
timezone: Asia/Ho_Chi_Minh
default_depot_address: 18 Phạm Hùng, Nam Từ Liêm (kho trung chuyển chính)
default_depot_area: Nam Từ Liêm
default_cost_per_km: 8000 (VNĐ/km — dự phòng, dùng khi xe chưa có cost_per_km riêng)
```

### Xe và tài xế (10 xe — seed vào bảng `vehicles`, mục 4 — khớp sheet `Danh_muc_xe`, mục 6.1)
```
vehicle_id | driver_name      | driver_phone  | max_payload_kg | cost_per_km
B01        | Nguyễn Văn An    | 0912000001    | 1000           | 7000
B02        | Trần Thị Bình    | 0912000002    | 1000           | 7000
B03        | Lê Văn Cường     | 0912000003    | 1000           | 7000
B04        | Phạm Thị Dung    | 0912000004    | 1000           | 7000
B05        | Hoàng Văn Em     | 0912000005    | 1000           | 7000
C01        | Vũ Thị Phương    | 0912000006    | 1500           | 9500
C02        | Đặng Văn Giang   | 0912000007    | 1500           | 9500
C03        | Bùi Thị Hoa      | 0912000008    | 1500           | 9500
C04        | Đinh Văn Inh     | 0912000009    | 1500           | 9500
C05        | Ngô Thị Kim      | 0912000010    | 1500           | 9500
```
(Dòng B* = xe tải 1.000kg (1 tấn), C* = xe tải 1.500kg (1,5 tấn) — không còn phân theo bậc nhỏ/trung/lớn, dùng đúng số kg thực tế trong `max_payload_kg` (mục 4, 6.1), vì luật giao thông cấm/hạn chế theo trọng tải cụ thể chứ không theo cỡ chung chung — ví dụ có tuyến cấm xe tải trên 1.500kg thì C* sẽ không được đề xuất đi qua tuyến đó. Chủ đích để kịch bản bonus mục 15 có ý nghĩa thật: xe C03 tải 1.500kg đủ sức nhận thêm hàng từ cả B01 lẫn C02 khi được điều đi hỗ trợ. `cost_per_km` xe tải nặng hơn cao hơn — minh họa lý do field này nên theo từng xe thay vì 1 số chung cho cả công ty.)

### Khu vực giao hàng (Hà Nội nội thành)
```
Cầu Giấy, Đống Đa, Hai Bà Trưng, Hoàn Kiếm,
Hoàng Mai, Long Biên, Nam Từ Liêm, Tây Hồ,
Thanh Xuân, Ba Đình
```

### Kịch bản demo chi tiết (5 chính + 1 bonus)

Mỗi kịch bản là 1 `schedule` riêng, ngày `01/09/2026`, seed sẵn trong DB demo (`demo-company-001`) để chạy độc lập lúc trình bày — không phụ thuộc thứ tự chạy trước đó. Số liệu dưới đây dùng trực tiếp để viết seed script (mục 15, phần seed) và để test rule engine/prompt.

---

**Kịch bản 1 — `delay` / `late_departure` (minh họa leo thang do downstream_stops_affected ≥ 3)**

- Xe **B01** — tài xế **Nguyễn Văn An** (0912000001) — ca sáng
- `depot_arrival_time`: `06:30` (giờ dự kiến có mặt tại kho), `depot_loading_duration_min`: `30` (bốc hàng dự kiến mất 30 phút) → `planned_departure_time` hệ thống tự tính = `06:30 + 30' = 07:00`. Thực tế: tài xế kẹt xe cá nhân, có mặt tại kho lúc `07:20` (trễ 50 phút so với kế hoạch) rồi bốc hàng bình thường (~25 phút) → xuất phát lúc `07:45` → **trễ 45 phút so với kế hoạch xuất phát**
- Khi nhập ngoại lệ, dispatcher trả lời câu hỏi phụ (mục 5.1) *"Xe/tài xế có mặt tại kho đúng giờ không?"* → **Không** → xác nhận nguyên nhân là tài xế đến trễ (không phải bốc hàng chậm), giữ `sub_type = late_departure`
- Ngoại lệ được nhập lúc: `07:45`
- Route (3 điểm, đúng thứ tự):

| # | Địa chỉ | Order ID | Khách hàng | SĐT | ETA gốc | ETA mới (sau trễ 45') | SLA deadline | priority_tier | Khối lượng |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 144 Xuân Thủy, Cầu Giấy | DH-20260901-101 | Nguyễn Thị Lan | 0987001101 | 07:30 | 08:15 | 09:00 | thuong | 25kg |
| 2 | 72 Hồ Tùng Mậu, Nam Từ Liêm | DH-20260901-102 | Trần Văn Hùng | 0987001102 | 08:10 | 08:55 | 09:30 | thuong | 40kg |
| 3 | 15 Âu Cơ, Tây Hồ | DH-20260901-103 | Lê Thị Mai | 0987001103 | 08:50 | 09:35 | 10:00 | thuong | 18kg |

- **Kết quả rule engine kỳ vọng:** không điểm nào breach SLA (buffer dương ở cả 3), nhưng có tới 3 lý do cùng đẩy severity lên **serious**: (1) trễ xuất phát 45 phút > ngưỡng 30 phút của `late_departure` (mục 5.2); (2) `downstream_stops_affected = 3`; (3) `time_to_deadline_min` của điểm gần nhất (stop 1, 75 phút) rơi vào khoảng 30–90 → quy tắc toàn cục #3 cũng tự áp sàn serious. Ba đường leo thang trùng kết quả — tốt để giải thích logic khi demo (dù thực tế chỉ cần 1 trong 3 lý do là đủ). Cả 3 điểm `priority_tier = thuong` nên `has_priority_order = FALSE` — chứng minh escalation ở kịch bản này đến từ độ trễ + rủi ro dây chuyền, không phải vì đơn quan trọng.
- **Điểm demo:** cho thấy rule engine leo thang severity dù không SLA nào bị breach thật sự — vì rủi ro dây chuyền.

---

**Kịch bản 2 — `road_block` / `road_closed` (minh họa leo thang lên critical)**

- Xe **B03** — tài xế **Lê Văn Cường** (0912000003) — ca chiều
- Ngoại lệ: cầu Vĩnh Tuy / đường Minh Khai đoạn qua Hai Bà Trưng **bị chặn hoàn toàn do tai nạn giao thông nghiêm trọng**, xe không thể qua
- Ngoại lệ được nhập lúc: `14:35`
- Route còn lại (2 điểm):

| # | Địa chỉ | Order ID | Khách hàng | SĐT | ETA gốc | SLA deadline | priority_tier | Khối lượng |
|---|---|---|---|---|---|---|---|---|
| 1 | 200 Minh Khai, Hai Bà Trưng | DH-20260901-201 | Phạm Văn Đức | 0987002101 | 14:30 | 15:00 | thuong | 60kg |
| 2 | 45 Tam Trinh, Hoàng Mai | DH-20260901-202 | Ngô Thị Hằng | 0987002102 | 15:10 | 16:00 | thuong | 30kg |

- **Kết quả rule engine kỳ vọng:** `road_closed` có severity nền cố định **serious**. `time_to_deadline_min` cho stop 1 = 15:00 − 14:35 = **25 phút < 30** → quy tắc toàn cục #2 đẩy tiếp lên **critical**.
- **Điểm demo:** cho thấy ngay cả sub-type "serious cố định" vẫn có thể bị đẩy lên critical khi deadline sát nút — severity không tĩnh, luôn tính lại theo thời gian thực.

---

**Kịch bản 3 — `customer_reject` / `customer_absent` (kịch bản mức warning, đối lập 1 & 2)**

- Xe **B02** — tài xế **Trần Thị Bình** (0912000002) — ca sáng
- Route: điểm 1 (88 Tây Sơn, Đống Đa) đã giao thành công lúc 09:10. Ngoại lệ xảy ra ở **điểm 2**.
- Ngoại lệ được nhập lúc: `09:45`

| # | Địa chỉ | Order ID | Khách hàng | SĐT | ETA gốc | SLA deadline | priority_tier | Khối lượng | Ghi chú |
|---|---|---|---|---|---|---|---|---|---|
| 2 | 25 Nguyễn Trãi, Thanh Xuân | DH-20260901-301 | Vũ Văn Long | 0912345678 | 09:40 | 12:00 | thuong | 12kg | Không có ai ở nhà, lần giao đầu tiên |
| 3 | 50 Lê Trọng Tấn, Thanh Xuân | DH-20260901-302 | Đỗ Văn Nam | 0987003103 | 10:20 | 13:00 | thuong | 15kg | Chưa bị ảnh hưởng |

- **Kết quả rule engine kỳ vọng:** `customer_absent` nền = warning. `priority_tier = thuong` → `has_priority_order = FALSE`, đây là lần giao lại đầu tiên → **không leo thang, giữ warning**. `time_to_deadline_min` = 135 phút → không kích hoạt quy tắc toàn cục nào.
- **Điểm demo:** đối trọng với kịch bản 1 & 2 — cho thấy hệ thống không "báo động giả", giữ đúng mức warning khi rủi ro thực sự thấp.

---

**Kịch bản 4 — `customer_change` / `cancel_order` (minh họa leo thang do giá trị đơn hàng cao)**

- Xe **B04** — tài xế **Phạm Thị Dung** (0912000004) — ca chiều
- Xe đã xuất phát, còn cách điểm giao ~15 phút thì khách gọi báo hủy đơn (đổi ý, không cần hàng nữa)
- Ngoại lệ được nhập lúc: `13:55`

| Địa chỉ | Order ID | Khách hàng | SĐT | ETA gốc | SLA deadline | priority_tier | sla_penalty (hợp đồng) | Khối lượng | Giá trị hàng |
|---|---|---|---|---|---|---|---|---|---|
| 10 Hàng Bài, Hoàn Kiếm | DH-20260901-401 | Đỗ Thị Nga | 0909112233 | 13:50 | 15:30 | hop_dong_phat | 600.000đ | 8kg | 2.500.000đ (hàng thời trang, khách có hợp đồng phân phối với công ty) |

- **Kết quả rule engine kỳ vọng:** `cancel_order` nền = warning. `priority_tier = hop_dong_phat` → `has_priority_order = TRUE` (số tiền phạt hợp đồng 600.000đ > ngưỡng 500.000đ cũng cùng chiều, dùng làm số liệu tham khảo khi tính chi phí hủy trong `impact_analysis`) → leo thang **warning → serious**.
- **Điểm demo:** minh họa đường leo thang thứ 3 — dispatcher chỉ cần chọn tier `hop_dong_phat` (không cần tự tính/đoán số tiền phạt), khác cơ chế với kịch bản 1 (số điểm bị ảnh hưởng) và kịch bản 2 (deadline sát).

---

**Kịch bản 5 — `vehicle_issue` / `major_breakdown`**

- Xe **C02** — tài xế **Đặng Văn Giang** (0912000007) — ca sáng
- Xe chết máy hoàn toàn trên đường Nguyễn Văn Cừ, Long Biên, không thể chạy tiếp. Trên xe còn hàng của 2 điểm giao.
- Ngoại lệ được nhập lúc: `09:50`

| # | Địa chỉ | Order ID | Khách hàng | SĐT | ETA gốc | SLA deadline | priority_tier | Khối lượng | cargo_type |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 30 Ngô Gia Tự, Long Biên | DH-20260901-501 | Bùi Văn Tùng | 0987005101 | 10:15 | 11:00 | thuong | 55kg | normal |
| 2 | 12 Nguyễn Sơn, Long Biên | DH-20260901-502 | Trịnh Thị Yến | 0987005102 | 10:45 | 12:30 | thuong | 20kg | normal |

- **Kết quả rule engine kỳ vọng:** `major_breakdown` nền = **serious cố định**. `time_to_deadline_min` cho stop 1 = 11:00 − 09:50 = 70 phút → rơi vào 30–90 → sàn serious (trùng khớp, không đẩy thêm lên critical). Tổng `volume_kg` cần chuyển = 75kg, nhỏ hơn nhiều `max_payload_kg` của bất kỳ xe nào trong danh mục (mục 15) → không xe nào bị loại vì tải trọng khi tìm xe thay thế (mục 5.4).
- **Điểm demo:** minh họa luồng "cần xe thay thế" — option generator phải đề xuất điều xe gần nhất tới trung chuyển hàng, không chỉ đơn thuần chờ sửa xe.

---

**Kịch bản bonus — 2 ngoại lệ cùng lúc, kích hoạt `combined` mode qua `resource_contention`**

- **Ngoại lệ A:** Xe **B01** — tài xế **Nguyễn Văn An** — `vehicle_issue` / `minor_breakdown` tại **Cầu Giấy** (thủng lốp trước, ga-ra ước tính sửa **50 phút**). Còn 2 điểm giao gần deadline nên dispatcher cân nhắc điều xe thay thế thay vì chờ sửa.
  - Route còn lại: 40 Cầu Giấy (DH-20260901-601, khách Nguyễn Văn Kiên, deadline 11:00, priority_tier thuong, 22kg, cargo_type normal) và 88 Trần Đăng Ninh, Cầu Giấy (DH-20260901-602, khách Hồ Thị Vân, deadline 11:45, priority_tier thuong, 15kg, cargo_type normal)
  - Ngoại lệ nhập lúc `10:05`. Theo mục 5.2: `minor_breakdown` leo thang serious nếu sửa > 30 phút → 50 phút → **serious**.
- **Ngoại lệ B:** Xe **C02** — tài xế **Đặng Văn Giang** — `vehicle_issue` / `major_breakdown` tại **Nam Từ Liêm** (cách Cầu Giấy ~4km), xe chết máy hoàn toàn, cần xe thay thế ngay.
  - Route còn lại: 15 Trần Hữu Dực, Nam Từ Liêm (DH-20260901-603, khách Lương Văn Phúc, deadline 11:15, priority_tier vip — khách hàng lâu năm, 45kg, cargo_type normal)
  - Ngoại lệ nhập lúc `10:08` — **serious cố định** (major_breakdown). `priority_tier = vip` không đổi severity (đã serious sẵn) nhưng được đưa vào `CONTEXT` (mục 19) để LLM ưu tiên đề xuất phân bổ C03 cho B trước khi cân nhắc phương án cho A.
- **Tín hiệu xung đột:** cả hai đều thuộc nhóm "cần xe thay thế" (`needs_replacement_vehicle`). Xe rảnh gần nhất cho cả hai đều là **C03** (tài xế Bùi Thị Hoa, xe tải trung `max_payload_kg=1500`, đang đỗ tại kho trung chuyển Nam Từ Liêm — nằm giữa 2 vị trí) → `nearest_available_vehicles` của A và B trùng nhau ở candidate C03 → `resource_contention = true` → `mode = combined` (mục 5.3). Tổng khối lượng nếu C03 nhận cả 2 bên (22+15+45 = 82kg) vẫn nằm sâu dưới `max_payload_kg`, nên tải trọng không phải yếu tố loại phương án ở đây — điểm nghẽn thực sự là **thời gian** (C03 chỉ đến được 1 nơi trước).
- **Kết quả kỳ vọng:** hệ thống tạo 1 `exception_groups` record gộp A + B, dùng prompt `group` (mục 19.2), sinh phương án phân bổ C03 ưu tiên theo severity/deadline/priority_tier (ngoại lệ B có deadline sát hơn — 11:15 so với 11:00/11:45 của A — và `priority_tier=vip`), phương án còn lại cho A dùng xe hỗ trợ khác hoặc chờ sửa tại chỗ.
- **Điểm demo:** đây là kịch bản thể hiện rõ nhất giá trị cốt lõi của hệ thống — không xử lý 2 ngoại lệ độc lập rồi giẫm chân nhau lên cùng 1 xe thay thế, mà dispatcher xác nhận **một quyết định duy nhất** đã cân nhắc cả hai.

---

## 16. ENVIRONMENT SETUP (ngày đầu)

**Đã cài sẵn trên máy (xác nhận trước khi bắt đầu Giai đoạn 1 của `BUILD_PLAN.md`):** PostgreSQL 17.11, Python 3.13.15, Node.js LTS 24.20, Git + Git Bash. Không cần cài lại — các bước dưới chỉ còn là khởi tạo project trên nền sẵn có.

```bash
# 1. Clone/init project
mkdir exception-logistics && cd exception-logistics
git init

# 2. Backend
python -m venv venv
source venv/bin/activate  # Windows (Git Bash): source venv/Scripts/activate
pip install fastapi uvicorn sqlalchemy alembic psycopg2-binary
pip install python-jose passlib pandas google-generativeai
pip install sentry-sdk httpx python-multipart python-dotenv

# 3. Frontend — dùng Vite (không dùng create-react-app, đã ngừng bảo trì)
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install axios react-router-dom @tanstack/react-query

# 4. Database (PostgreSQL 17.11 đã cài)
# Tạo database: exception_logistics
createdb exception_logistics   # hoặc dùng psql / pgAdmin

# 5. pgvector extension
# Chạy trong psql: CREATE EXTENSION IF NOT EXISTS vector;
# (Nếu pgvector chưa có sẵn theo bản cài PostgreSQL 17.11, cần cài thêm extension này riêng)

# 6. Alembic init
alembic init alembic
# Cấu hình alembic.ini với DATABASE_URL

# 7. .env
cp .env.example .env
# Điền các API key vào .env (GEMINI_API_KEY, GOOGLE_MAPS_API_KEY, DATABASE_URL, JWT_SECRET, SENTRY_DSN)
```

Chi tiết từng bước nhỏ hơn (kèm theo dõi tiến độ) nằm trong `BUILD_PLAN.md` — Giai đoạn 1.

---

## 17. BUILD ORDER (tổng quan)

> Đây là tổng quan cấp cao. Checklist chi tiết từng bước nhỏ, có thể tick từng bước và tiếp tục qua nhiều phiên code khác nhau, nằm trong `BUILD_PLAN.md` (cùng thư mục) — đó là file Claude Code nên theo trong lúc code, không phải bảng dưới đây.

```
Ngày 1-2:   Setup project + database schema + Alembic migrations
            + Auth (JWT, RBAC, tenant middleware)
            + Excel template file + validation logic

Ngày 3-4:   Rule engine (classification + conflict detection)
            + Impact analyzer
            + Background job queue + worker

Ngày 5-6:   LLM Adapter + Gemini integration
            + Prompt versioning
            + Option generator + LLM output parser

Ngày 7:     Ranker (scoring algorithm)
            + Google Maps integration + cache
            + Resource locking

Ngày 8-9:   Frontend — Dashboard dispatcher
            + Form nhập ngoại lệ
            + Màn hình xử lý đơn + nhóm
            + Polling mechanism

Ngày 10:    Frontend — Dashboard manager (KPI cơ bản)
            + Form nhập kế hoạch + Excel upload UI
            + Settings page

Ngày 11:    Fake data seeding (10 xe, kịch bản demo)
            + End-to-end testing toàn bộ chuỗi
            + Bug fixes

Ngày 12:    Deploy lên Railway/Render
            + Demo rehearsal
            + Buffer cho sự cố cuối
```

---

## 18. DEFINITION OF DONE (mỗi feature)

Một feature được coi là xong khi:
- [ ] API endpoint hoạt động đúng
- [ ] Tenant isolation đúng (không leak data cross-company)
- [ ] Input validation đúng (trả lỗi rõ ràng tiếng Việt)
- [ ] Error handling đúng (không crash, thông báo user-friendly)
- [ ] Soft delete đúng (deleted_at, không hard delete)
- [ ] Audit log đúng (action quan trọng được ghi lại)
- [ ] Frontend hiển thị đúng trạng thái loading/error/success

---

## 19. PROMPT TEMPLATES

Prompt viết bằng **tiếng Anh** (theo mục 8), lưu trong bảng `prompt_versions`. Mỗi lần gọi LLM, `llm_adapter.py` ghép: **[System prompt chung]** + **[User prompt theo `sub_type` (hoặc `group`)]** + **[CONTEXT — JSON dữ liệu thực tế của ngoại lệ]**.

`CONTEXT` là JSON được `option_generator.py` build tự động từ DB trước khi gọi LLM, gồm: thông tin ngoại lệ (`exception_group`, `sub_type`, `severity`, `description`, `vehicle_id`, `area`), thông tin xe/tài xế (tra từ `vehicles`: `driver_name`, `max_payload_kg` — đồng thời là hạng tải trọng của xe theo kg, dùng để chọn xe thay thế đủ sức chở VÀ để AI nhận biết giới hạn tải trọng khi cân nhắc đổi tuyến, `cost_per_km` — hoặc `companies.default_cost_per_km` nếu xe chưa có giá riêng, `vehicle_type` mô tả tự do nếu công ty có khai báo), thông tin chuyến (`planned_departure_time`, các `stops` còn lại với `eta`/`sla_deadline`/`priority_tier`/`sla_penalty`/`volume_kg`/`cargo_type`), kết quả `impact_analysis` (điểm bị ảnh hưởng, phút trễ, `sla_breach`), khoảng cách/tuyến từ Google Maps nếu có, và `ranking_weights` của company (để LLM viết `explanation` bám đúng ưu tiên cost/time/sla mà không cần biết rank cuối — rank do `ranker.py` tính riêng, không phải LLM).

### 19.0 System prompt (dùng chung cho MỌI lần gọi — `sub_type = 'system'`)

```
You are the decision-support engine inside "Exception Logistics", a system used by
Vietnamese logistics dispatch teams to resolve real-time delivery exceptions
(delays, road blocks, customer issues, vehicle breakdowns).

ROLE AND SCOPE
- You do NOT execute any action. You only propose options for a human dispatcher to
  review and confirm. Never use language implying the action has already happened.
- You do NOT calculate the final ranking score — a separate deterministic algorithm
  ranks options using cost, time, and SLA-risk weights (given to you in CONTEXT as
  ranking_weights). Your job is to generate realistic, distinct candidate options and
  explain them in plain Vietnamese.
- Always treat driver and public safety as the top priority in any option involving a
  vehicle incident or accident.
- Never invent facts not present in CONTEXT (exact prices, distances, company
  policies you were not told). Base cost_estimate and time_estimate_minutes on the
  numbers given in CONTEXT and reasonable Vietnamese domestic-logistics norms when a
  number isn't given — but do not present rough estimates as precise facts.

OUTPUT RULES
- Respond with ONLY valid JSON. No markdown, no code fences, no text before or after
  the JSON.
- Generate between 2 and 3 distinct options. Options must represent genuinely
  different courses of action, not minor variations of the same action.
- Every option must include realistic numeric estimates: cost_estimate (VND, integer),
  time_estimate_minutes (integer), sla_risk_remaining (float 0.0–1.0, where 0 = no
  risk of SLA breach remains, 1 = breach is now certain).
- "description", "rationale" and "explanation" MUST be written in natural, concise
  Vietnamese, as if written by an experienced dispatch supervisor speaking to a
  colleague — not a literal translation of English.
  - "description": what the dispatcher would actually do, in 1-2 sentences.
  - "rationale": why this is a reasonable response to THIS specific situation.
  - "explanation": how this option trades off against the company's ranking
    priorities (cost_weight, time_weight, sla_risk_weight from CONTEXT) — e.g. which
    priority it serves best and what it sacrifices. Do not state a specific rank or
    position; the system computes that separately after you respond.
- If a sub-type's guidance below asks for a mandatory safety-first option, that option
  must still follow the same JSON shape. Its cost_estimate and time_estimate_minutes
  should reflect only the immediate safety action's real cost and duration — often
  minimal, sometimes genuinely zero, but do NOT default cost_estimate to 0 as a rule;
  report the actual estimated cost when the immediate action has one (e.g. dispatching
  emergency assistance, a towing arrangement already set in motion). Zero-cost is the
  best case, not the assumption.
- Never return an empty "options" array. If the situation truly has no automatable
  option, return exactly one option whose description explains that manual dispatcher
  judgment is required and why.

OUTPUT JSON SCHEMA
{
  "options": [
    {
      "description": "string (Vietnamese)",
      "rationale": "string (Vietnamese)",
      "cost_estimate": number,
      "time_estimate_minutes": number,
      "sla_risk_remaining": number,
      "explanation": "string (Vietnamese)"
    }
  ]
}
```

### 19.1 User prompt theo sub_type

Mỗi prompt dưới đây là **toàn bộ nội dung** của 1 row trong `prompt_versions` (`sub_type = <tên>`), theo sau bởi `CONTEXT: {context_json}` do code tự nối vào (không phải phần cố định của prompt text lưu trong DB).

**`delay` / `late_departure`**
```
SITUATION: A delivery vehicle departed later than scheduled and has not yet reached
its first stop. Time may still be partially recoverable depending on remaining route
length, traffic, and how much SLA buffer each remaining stop has.

Consider when generating options:
- Whether the original stop order can still meet every SLA deadline as-is (no change
  needed beyond notifying the dispatcher of the new ETA).
- Whether reordering the remaining stops (serving the tightest SLA deadline first)
  recovers more stops than keeping the original order.
- Whether any specific stop is now mathematically unrecoverable and should be
  proactively flagged to the customer with a revised ETA or compensation, rather than
  attempted at the cost of delaying every other stop further.

Generate 2-3 options for the dispatcher.
```

**`delay` / `slow_loading`**
```
SITUATION: The vehicle is taking longer than planned to load or unload at a stop,
which pushes back the ETA of every subsequent stop on the route (cascading delay).

Consider when generating options:
- Whether remaining stops can be reordered to protect the ones closest to SLA breach
  first, accepting more delay on stops with larger SLA buffer.
- Whether splitting the remaining stops with another nearby vehicle currently
  available is cheaper than the SLA penalties this delay would otherwise cause.
- Whether the loading delay itself can be shortened (e.g. partial load now, remainder
  delivered on a later run) instead of changing the route.

Generate 2-3 options for the dispatcher.
```

**`delay` / `unknown_delay`**
```
SITUATION: The vehicle is running behind schedule for an unclear reason, and contact
with the driver may be limited or has been lost for some minutes.

Consider when generating options:
- Re-establishing driver contact (phone call, check last known area) is the first
  priority action and should appear as its own option or as step one of every option.
- A contingency assuming the delay is minor and self-resolving (continue route,
  monitor) versus a contingency assuming a more serious unreported problem (prepare a
  replacement vehicle on standby, notify affected customers of possible delay).
- An escalation path (notify manager, consider this vehicle_issue instead) if contact
  is not re-established within a reasonable window.

Generate 2-3 options for the dispatcher.
```

**`road_block` / `traffic_jam`**
```
SITUATION: The vehicle is stuck in traffic congestion but can still move; the
congestion's expected clearance time is uncertain.

Consider when generating options:
- Comparing "wait it out" against "reroute now" using the estimated congestion
  duration versus the extra distance/time an alternate route would add.
- The impact on every downstream stop's SLA under each choice.
- Whether simply reordering the remaining stops (serving a still-reachable stop first
  while waiting) reduces risk more cheaply than a full detour.

Generate 2-3 options for the dispatcher.
```

**`road_block` / `road_closed`**
```
SITUATION: The road is fully closed or blocked (accident, flooding, official closure)
and the vehicle cannot continue on its current path — a route change is required, not
optional.

Consider when generating options:
- The most viable alternate route and its added distance, time, and fuel cost.
- Whether it is cheaper to reassign one or more remaining stops to a different nearby
  vehicle instead of detouring the whole route.
- Immediate ETA updates to every customer whose stop is affected by the detour.

Generate 2-3 options for the dispatcher.
```

**`customer_reject` / `customer_absent`**
```
SITUATION: No one was available to receive the delivery at the stop.

Consider when generating options:
- Attempting phone contact with the customer before deciding next steps.
- Waiting briefly at the location versus continuing the route and returning to this
  stop later the same shift versus rescheduling for the next business day.
- Returning the goods to the depot if this is a repeat failed attempt, including the
  cost of a repeat delivery run versus any return/restocking cost.

Generate 2-3 options for the dispatcher.
```

**`customer_reject` / `customer_dispute`**
```
SITUATION: The customer is present but is disputing or refusing to accept the
delivery (disagreement over goods condition, price, or quantity).

Consider when generating options:
- This is not a decision the driver should resolve alone. At least one option must
  escalate to a customer service or account manager rather than asking the driver to
  negotiate further.
- Whether to leave the goods in a held/pending state at the customer's location or
  return them with the vehicle while the dispute is resolved.
- Documenting the dispute (photos, notes, timestamp) so the escalation has evidence.
- Do NOT propose pressuring the customer to accept, or any option that keeps the
  driver in a prolonged conflict.

Generate 2-3 options for the dispatcher.
```

**`customer_reject` / `wrong_address`**
```
SITUATION: The delivery address provided does not match reality (doesn't exist, wrong
building, incomplete) and must be confirmed before the driver can proceed.

Consider when generating options:
- Contacting the customer immediately to confirm the correct address is the first
  step in every option.
- Whether the corrected address is still a reasonable detour from the current route
  (same-day delivery still possible) or requires rescheduling for a later run.
- The cost/time difference between a same-day correction and next-day rescheduling.

Generate 2-3 options for the dispatcher.
```

**`customer_change` / `change_time`**
```
SITUATION: The customer has requested a different delivery time than originally
scheduled.

Consider when generating options:
- Whether the newly requested time fits within the vehicle's remaining route without
  breaching any other stop's SLA.
- Whether it requires reordering the remaining stops rather than just shifting one.
- Whether CONTEXT shows another stop with a conflicting or overlapping time window —
  if so, options must address that conflict explicitly, not ignore it.

Generate 2-3 options for the dispatcher.
```

**`customer_change` / `change_location`**
```
SITUATION: The customer has requested delivery to a different location than
originally planned.

Consider when generating options:
- The added distance/time from the new location relative to the vehicle's current
  route.
- Whether it is more efficient to detour to the new location now versus treating it
  as a separate delivery on a later run.
- The cost of the extra distance versus the cost of rescheduling entirely.

Generate 2-3 options for the dispatcher.
```

**`customer_change` / `cancel_order`**
```
SITUATION: The customer has cancelled the order after the vehicle already departed
with the goods on board.

Consider when generating options:
- The cost of returning the goods to the depot now versus holding them on the vehicle
  for the remainder of the shift and returning them at end of day.
- Any cancellation fee that applies per company policy, if indicated in CONTEXT.
- Whether removing this stop lets the remaining route run faster/cheaper — factor
  that benefit into cost_estimate.
- Do NOT propose contacting the customer to try to reverse a cancellation they already
  made.

Generate 2-3 options for the dispatcher.
```

**`vehicle_issue` / `minor_breakdown`**
```
SITUATION: The vehicle has a minor mechanical issue (e.g. low tire pressure, warning
light) but can likely continue driving; a repair time estimate is available.

Consider when generating options:
- Continuing the route with a quick stop at a nearby repair point versus continuing
  cautiously without stopping if the issue does not affect safety.
- The time cost of the repair stop against how many remaining stops are close to SLA
  breach.
- Whether a single at-risk stop should be reassigned to another vehicle instead of
  delaying the entire remaining route for a repair.

Generate 2-3 options for the dispatcher.
```

**`vehicle_issue` / `major_breakdown`**
```
SITUATION: The vehicle cannot continue driving and still has undelivered goods on
board.

Consider when generating options:
- Dispatching the nearest available replacement vehicle to either (a) transfer the
  goods at the breakdown location and continue the route, or (b) pick up only the
  most SLA-critical remaining stops directly from the depot.
- The cost/time of transferring goods at the roadside versus returning all goods to
  the depot and redispatching later.
- Which remaining stops are most at SLA risk and should be prioritized if only a
  partial pickup by the replacement vehicle is feasible.
- Towing/recovery of the broken-down vehicle is informational context, not a decision
  the dispatcher needs an option for.

Generate 2-3 options for the dispatcher.
```

**`vehicle_issue` / `accident`**
```
SITUATION: The vehicle has been involved in a traffic accident. CONTEXT includes
whether anyone is reported injured. Driver and public safety take precedence over
every logistics consideration.

Consider when generating options:
- The first option must be the immediate safety/emergency response action (call
  emergency services 115/113, do not move injured parties, secure the scene). Its
  cost_estimate and time_estimate_minutes should reflect only that immediate action's
  real cost and duration — often at or near zero, but state the true estimate rather
  than defaulting to 0 when the action genuinely has a cost. This option has no
  trade-off, it is not optional.
- Only after the safety action, generate 1-2 further options for handling the goods
  and remaining route (dispatch replacement vehicle, return goods to depot) — clearly
  state in "description" that these follow only once the safety situation is
  resolved/confirmed stable.
- Never suggest continuing the delivery route before safety is addressed, even if
  CONTEXT reports no injuries.

Generate 2-3 options for the dispatcher (the first is always the safety option).
```

### 19.2 Prompt nhóm — `group` (2+ ngoại lệ combined)

Dùng khi `exception_groups.mode = 'combined'` (xem mục 5.3). `CONTEXT` trong trường hợp này chứa **mảng** cả hai (hoặc nhiều) ngoại lệ đầy đủ, cộng thêm trường `conflict_signals` (vd `["resource_contention"]`) giải thích vì sao chúng bị gộp.

```
SITUATION: Two or more operational exceptions were reported at nearly the same time
and share a critical resource (same vehicle, same driver, same delivery stop, or the
same candidate replacement vehicle/route) — see conflict_signals in CONTEXT. They
must be resolved together as one coordinated decision, not as independent plans that
might conflict with each other.

Consider when generating options:
- Every option must resolve ALL exceptions listed in CONTEXT simultaneously. Do not
  propose a plan for one exception that ignores the resource needs of the other(s).
- If multiple exceptions want the same resource (e.g. the same nearby replacement
  vehicle), propose how to allocate it — for example prioritizing the
  higher-severity exception and giving the other a different resource or a delayed
  resolution — rather than assuming both can have it.
- Be explicit inside "description": name which action applies to which
  exception_id/vehicle_id so the dispatcher can tell the plan apart per exception.
- If exceptions genuinely do not need to share anything once examined closely (a
  false-positive link), one option may propose reverting to independent handling —
  explain why in "rationale".

Generate 2-3 combined options for the dispatcher. Each option's cost_estimate and
time_estimate_minutes must reflect the TOTAL impact across all exceptions in this
group, not just one.
```

---

*Last updated: v5.2 — Bỏ "khách đe dọa tài xế" khỏi quy tắc ghi đè toàn cục #1 (mục 5.2): sản phẩm tập trung vào logistics hàng hóa, tình huống này hợp lý hơn ở logistics chở người và không có cơ chế nào trong luồng nhập liệu để dispatcher khai báo nó xảy ra — quyết định của người dùng là bỏ hẳn thay vì thêm câu hỏi capture mới. Quy tắc #1 giờ chỉ còn "tai nạn có người bị thương → critical".*

*Lịch sử rút gọn: v5.3 đổi model LLM (mục 8) từ `gemini-2.5-flash` sang `gemini-3.6-flash` (bị Google sunset cho key/project mới, phát hiện lúc test thật Giai đoạn 10) + thêm cơ chế xoay vòng tối đa 3 API key khi hết hạn mức free tier. v5.1 đổi `vehicles.vehicle_type` thành mô tả tự do không bắt buộc, `max_payload_kg` trở thành căn cứ DUY NHẤT vừa chọn xe thay thế (mục 5.4) vừa đối chiếu biển cấm tải trọng trên đường; hạ 4 ngưỡng leo thang severity (`late_departure` >30', `wrong_address`/`change_location` >5km, `minor_breakdown` >30'); bỏ ép `cost_estimate=0` mặc định trong system prompt/prompt accident; sửa 2 chỗ sót (enum cũ trong comment `schedules.stops`, ghi chú "10km" cũ) + thêm ghi chú "Mở rộng sau này" vào mục 7. v5.0 thiết kế lại toàn bộ Excel/schema theo trục tần suất thay đổi — 2 sheet `Danh_muc_xe`/`Ke_hoach_giao_hang` thay cho `Chuyen`/`Diem_giao` cũ, bỏ cơ chế tự sao chép ≤7 ngày (giả định sai), `planned_departure_time` đổi sang tự tính, thêm `vehicles.cost_per_km`. v4.3 sửa đơn vị "chuyến" ≠ "ca", thêm `trip_sequence` để 1 xe chạy nhiều chuyến/ca. v4.2 thêm trường giờ đến kho để tách nguyên nhân trễ + làm rõ vehicle_id là tra cứu DB thường, không phải tự động dò tìm. v4.1 sheet chuyến thành tùy chọn + tự sao chép chuyến lặp lại (bỏ ở v5.0) + làm rõ 2 đường nhập liệu (form/Excel). v4.0 redesign schema: bảng `vehicles`, cấu hình company (depot/cost_per_km), `priority_tier` thay `sla_penalty` bắt buộc, mục 5.4 tải trọng/hàng cồng kềnh. Phần 4 (fake seed data lịch sử) vẫn tạm hoãn tới cuối. Đây là nguồn sự thật duy nhất. Mọi quyết định mới cập nhật vào đây trước khi code.*