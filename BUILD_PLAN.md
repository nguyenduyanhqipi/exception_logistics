# BUILD_PLAN.md — Exception Logistics — Checklist thi công

> File này là **thứ tự làm việc + theo dõi tiến độ**, đi kèm `TECHNICAL_SPEC.md` (mô tả THIẾT KẾ — build gì, như thế nào). File này trả lời câu hỏi **làm cái gì TRƯỚC, cái gì SAU, và đang làm đến đâu**.

## Cách dùng file này (đọc trước khi code bất cứ gì)

1. **Luôn đọc `TECHNICAL_SPEC.md` trước**, rồi đọc file này để biết đang ở bước nào.
2. Tìm **bước đầu tiên chưa tick `[ ]`** trong danh sách dưới — bắt đầu từ đó. Không nhảy cóc sang bước sau nếu bước trước chưa xong, trừ khi bước sau không phụ thuộc (hiếm).
3. Mỗi bước đều có mục **"Kiểm tra"** — đây là cách xác nhận bước đó THỰC SỰ chạy được, không chỉ là "đã viết code". Chỉ tick `[x]` sau khi kiểm tra qua đúng như mô tả.
4. Nếu một phiên code kết thúc giữa chừng 1 bước (hết token, mất kết nối, dừng theo yêu cầu người dùng...): đánh dấu bước đó bằng `[~]` (đang làm dở) kèm 1 dòng ghi chú ngắn "đã làm gì / còn thiếu gì" ngay dưới bước đó, trước khi dừng. Phiên sau đọc ghi chú này để tiếp tục đúng chỗ, không phải đọc lại toàn bộ code đã viết để đoán.
5. Sau khi tick `[x]` một bước, **cập nhật luôn file này** (đây là file sống, sửa trực tiếp — không phải chỉ báo cáo bằng lời rồi quên ghi).
6. Không tự ý đổi thứ tự các Giai đoạn/bước trừ khi có lý do kỹ thuật bắt buộc (ví dụ 1 bước cần cái chưa tồn tại) — nếu đổi, ghi 1 dòng giải thích ngắn ngay tại bước đó.
7. Mỗi bước có API endpoint đều phải qua đủ tiêu chí ở **mục 18 TECHNICAL_SPEC.md** (Definition of Done: tenant isolation, validation, error handling, soft delete, audit log, trạng thái loading/error/success ở frontend) trước khi tick xong — không nhắc lại tiêu chí này ở từng bước cho đỡ dài.
8. Ký hiệu: `[ ]` chưa làm · `[~]` đang làm dở · `[x]` xong và đã kiểm tra.

---

## Giai đoạn 1 — Chuẩn bị môi trường

*(Tham chiếu: TECHNICAL_SPEC.md mục 3, 16)*

- [x] **1.1** Tạo cấu trúc thư mục project đúng theo mục 3 (frontend/, backend/, các thư mục con).
  Kiểm tra: cây thư mục khớp với sơ đồ mục 3. ĐÃ KIỂM TRA — `find frontend backend -maxdepth 3 -type d` khớp đủ các thư mục con.
- [x] **1.2** Tạo virtualenv Python, cài các thư viện backend (mục 16).
  Kiểm tra: `pip list` hiện đủ fastapi, sqlalchemy, alembic, google-generativeai... ĐÃ KIỂM TRA — `pip list` xác nhận đủ fastapi 0.141.1, sqlalchemy 2.0.52, alembic 1.19.1, google-generativeai 0.8.6, psycopg2-binary, python-jose, passlib, pandas, sentry-sdk, httpx, python-multipart, python-dotenv (thêm openpyxl để đọc .xlsx, bcrypt cho passlib).
- [x] **1.3** Khởi tạo frontend bằng Vite + React + TypeScript (mục 16), cài axios/react-router-dom/@tanstack/react-query.
  Kiểm tra: `npm run dev` chạy được, mở trình duyệt thấy trang mặc định của Vite. ĐÃ KIỂM TRA — `npm run dev` chạy ở port 5173, mở trình duyệt thấy trang mặc định Vite+React ("Get started", "Count is 0"). Đã thêm lại `src/pages`, `src/components`, `src/hooks`, `src/api` theo mục 3.
- [x] **1.4** Tạo database PostgreSQL `exception_logistics`, bật extension `pgvector`.
  Kiểm tra: `psql -d exception_logistics -c "\dx"` thấy extension `vector`. ĐÃ KIỂM TRA — database `exception_logistics` đã tạo. Bản cài PostgreSQL 17 trên máy ban đầu KHÔNG có sẵn pgvector; Claude Code (không có quyền admin, không ghi được vào `C:\Program Files\PostgreSQL\17`) không tự cài được, đã gửi hướng dẫn 3 bước cho user tự cài qua PowerShell admin (VS Build Tools → build pgvector từ source chính thức github.com/pgvector/pgvector → `CREATE EXTENSION vector`). User đã hoàn tất — `\dx` xác nhận `vector 0.8.0` (schema public, ivfflat + hnsw access methods).
- [x] **1.5** Khởi tạo Alembic, trỏ đúng `DATABASE_URL`.
  Kiểm tra: `alembic current` chạy không lỗi (chưa có migration nào cũng được). ĐÃ KIỂM TRA — `alembic init alembic` xong trong `backend/`; sửa `alembic/env.py` để `load_dotenv` từ `.env` ở gốc project và override `sqlalchemy.url` bằng `DATABASE_URL` (không hardcode credential vào `alembic.ini`, đúng nguyên tắc mục 13). `alembic current` chạy sạch, không lỗi, không có migration (đúng kỳ vọng).
- [x] **1.6** Tạo `.env` từ `.env.example`, điền `DATABASE_URL`, `JWT_SECRET`. (`GEMINI_API_KEY`, `GOOGLE_MAPS_API_KEY` điền ở Giai đoạn 5-6 khi cần dùng thật.)
  Kiểm tra: backend đọc được `.env` (test bằng 1 script in ra `DATABASE_URL`). ĐÃ KIỂM TRA — tạo `.env.example` (rỗng, mẫu) và `.env` (điền `DATABASE_URL=postgresql://postgres:***@localhost:5432/exception_logistics`, `JWT_SECRET` random 48-byte qua `secrets.token_urlsafe`) ở gốc project. Script Python test `load_dotenv` in đúng `DATABASE_URL` và xác nhận `JWT_SECRET` đã set. Đã thêm `.gitignore` loại trừ `.env` trước khi git init (mục 13: secrets không commit).
- [x] **1.7** `git init`, commit khung sườn ban đầu (chưa có logic).
  Kiểm tra: `git log` có ít nhất 1 commit. ĐÃ KIỂM TRA — `git init`, thêm `.gitignore` (loại `.env`, `venv/`, `node_modules/`...) trước khi add, xác nhận `git status` không dính file nhạy cảm/thư viện nặng, set git identity local cho repo (không --global, theo yêu cầu user), commit `f29b146`. `git log --oneline` hiện đúng 1 commit.

---

## Giai đoạn 2 — Nền dữ liệu: Database schema + Auth

*(Tham chiếu: mục 4, 13)*

- [x] **2.1** Viết SQLAlchemy model cho TẤT CẢ bảng ở mục 4 (companies, vehicles, users, schedules, exceptions, exception_groups, resource_locks, impact_analysis, options, decisions, outcomes, exception_embeddings, prompt_versions, rule_versions, llm_usage_logs, audit_logs, geocode_cache, background_jobs).
  Kiểm tra: `alembic revision --autogenerate` sinh ra migration có đủ các bảng, không báo lỗi. ĐÃ KIỂM TRA — viết 18 model trong `backend/models/` (base, company, vehicle, user, schedule, exception [Exception_, ExceptionGroup, ResourceLock, ImpactAnalysis], option, decision [Decision, Outcome], embedding [ExceptionEmbedding dùng `pgvector.sqlalchemy.Vector(768)`], prompt [PromptVersion, RuleVersion], system [LLMUsageLog, AuditLog, GeocodeCache, BackgroundJob]). Nối `target_metadata` trong `alembic/env.py`. `alembic revision --autogenerate` sinh đủ 18 bảng, không lỗi (log xác nhận từng bảng). Sửa tay 2 chỗ autogenerate thiếu: (1) thiếu `import pgvector.sqlalchemy` trong file migration cho cột VECTOR — tự thêm; (2) thêm `CREATE EXTENSION IF NOT EXISTS vector` đầu `upgrade()` (và `DROP EXTENSION` cuối `downgrade()`) vì DB local chưa có pgvector — xem ghi chú bước 1.4/2.2, migration đã sẵn sàng để chạy ngay khi pgvector cài xong.
- [x] **2.2** Chạy migration đầu tiên, xác nhận toàn bộ bảng + cột + kiểu dữ liệu đúng như mục 4 (đặc biệt: `vehicles.max_payload_kg`/`cost_per_km` nullable đúng, `schedules.depot_arrival_time`/`depot_loading_duration_min`/`planned_departure_time`, UNIQUE constraint của `schedules`).
  Kiểm tra: `psql -d exception_logistics -c "\d vehicles"` (và các bảng khác) khớp mục 4. ĐÃ KIỂM TRA — TÁCH migration autogenerate ban đầu thành 2 file (lý do kỹ thuật bắt buộc — pgvector chưa sẵn sàng lúc đó): `c6cde1a087a1_initial_schema.py` (17 bảng) + `a1b2c3d4e5f6_add_pgvector_exception_embeddings.py` (`CREATE EXTENSION vector` + bảng `exception_embeddings`). Đã `alembic upgrade head` (chạy cả 2 migration) sau khi user cài xong pgvector — đủ 18/18 bảng. Đối chiếu tay `\d vehicles` (max_payload_kg NOT NULL, cost_per_km nullable đúng), `\d schedules` (depot_arrival_time/depot_loading_duration_min/planned_departure_time đều nullable, UNIQUE partial index đúng mục 4), `\d exception_embeddings` (cột `embedding vector(768)`, FK đúng exceptions). Khớp hoàn toàn mục 4.
- [x] **2.3** Middleware JWT validation (mục 13, bước 3).
  Kiểm tra: gọi 1 endpoint bất kỳ không kèm token → trả lỗi 401 rõ ràng. ĐÃ KIỂM TRA — `core/security.py` (JWT encode/decode bằng python-jose, hash mật khẩu bằng `bcrypt` trực tiếp — passlib 1.7.4 KHÔNG tương thích bcrypt 5.x cài từ pip, lỗi "password cannot be longer than 72 bytes"/"module bcrypt has no attribute __about__", đã bỏ passlib khỏi code dù vẫn có trong danh sách cài mục 16), `middleware/auth.py` (dependency `get_current_user` qua `OAuth2PasswordBearer`). Gọi `GET /api/auth/me` và `GET /api/settings` không kèm token → `401` với message rõ ràng.
- [x] **2.4** Middleware tenant injection — tự động filter `company_id` mọi query (mục 13, bước 4).
  Kiểm tra: tạo 2 company demo, xác nhận query của company A không bao giờ trả dữ liệu company B. ĐÃ KIỂM TRA — `database.py` đăng ký event `do_orm_execute` trên `Session`, dùng `with_loader_criteria` tự động thêm điều kiện `company_id` cho các model có tenant (Vehicle, User, Schedule, Exception_, ExceptionGroup, Decision) dựa vào contextvar `core/tenant_context.py::current_company_id` (set bởi `middleware/tenant.py::get_db` từ JWT của request).
  PHÁT HIỆN + SỬA 2 BUG THẬT (bug 2 nghiêm trọng hơn, chỉ lộ ra khi build Giai đoạn 3 và test qua HTTP thật với 2 company):
  (1) Dạng callable `lambda cls, cid=company_id: cls.company_id == cid` bị SQLAlchemy cache biểu thức theo (entity, statement shape) chứ không theo giá trị đóng trong closure → company B nhận nhầm dữ liệu company A ở lần gọi thứ 2. Sửa: truyền thẳng biểu thức `model.company_id == company_id` đã bind giá trị (đúng pattern chính thức SQLAlchemy docs).
  (2) `get_db` khai báo dạng `def` (sync generator) — FastAPI chạy sync generator dependency qua threadpool (`anyio.to_thread.run_sync`), mỗi lần dispatch chụp 1 BẢN SAO `contextvars.Context` riêng → `current_company_id.set()` trong `get_db` KHÔNG lan ra context thật của request, endpoint đọc lại thấy `None` (tenant filter tắt hoàn toàn) mà không báo lỗi gì — không lộ ra lúc test DB thuần vì chỉ có 1 company. Sửa: đổi `get_db` thành `async def` (chạy thẳng trên event loop, không qua threadpool). Xác minh lại bằng HTTP thật: company B tạo xe `BXX1`, company A gọi `GET /api/vehicles` KHÔNG thấy `BXX1`, PUT vào `BXX1` bằng token company A → 404 (không leak), company B chỉ thấy đúng xe của mình.
  `scripts/test_tenant_isolation.py` (test tầng DB thuần, không qua HTTP) xác nhận cơ chế `with_loader_criteria` đúng sau khi sửa bug (1) — bài học: test tầng DB không đủ để bắt bug (2), phải test qua HTTP thật mới lộ ra.
- [x] **2.5** Middleware RBAC — check role `dispatcher`/`manager` (mục 13, bước 5).
  Kiểm tra: gọi 1 endpoint `manager only` (vd `/api/reports/kpi`) bằng tài khoản dispatcher → trả lỗi 403.
  Đổi thứ tự nhỏ (lý do kỹ thuật bắt buộc, theo quy tắc 6): chưa có endpoint manager-only nào tồn tại ở Giai đoạn 2 (`/api/reports/kpi` thuộc Giai đoạn 9, `/api/settings` thuộc bước 3.5) — đã tạo TRƯỚC một phần nhỏ `GET /api/settings` (`backend/api/settings.py`, chỉ phần GET, chưa có PUT) chỉ để có endpoint thật kiểm RBAC; bước 3.5 sẽ hoàn thiện thêm PUT, không phải viết lại GET này.
  ĐÃ KIỂM TRA — `middleware/rbac.py::require_role(*roles)`. Đăng nhập tài khoản `dispatcher@demo.vn`, gọi `GET /api/settings` → `403` kèm message "Vai trò 'dispatcher' không có quyền truy cập chức năng này"; tài khoản `manager@demo.vn` gọi cùng endpoint → `200`.
- [x] **2.6** API `POST /api/auth/login`, `/refresh`, `/logout` (mục 12).
  Kiểm tra: tạo 1 user demo qua script/seed thủ công, đăng nhập lấy token thành công, refresh token hoạt động, logout vô hiệu hóa token. ĐÃ KIỂM TRA — `backend/api/auth.py`. Login đúng mật khẩu → 200 kèm access+refresh token; sai mật khẩu → 401. `/refresh` với refresh token hợp lệ → access token mới, 200. `/logout` revoke refresh token (thêm `jti` vào set in-memory `_revoked_refresh_jtis` trong `core/security.py` — chưa có bảng session trong schema mục 4 nên dùng in-memory cho giai đoạn 1 tiến trình; ghi chú rõ trong code). Gọi lại `/refresh` bằng đúng refresh token vừa logout → 401 "Refresh token đã bị thu hồi (đã logout)" — xác nhận token THỰC SỰ bị vô hiệu hóa chứ không chỉ là hình thức. Thêm `GET /api/auth/me` (không có trong mục 12, bổ sung nhỏ để có endpoint auth-only test JWT).
- [x] **2.7** Seed 1 company + 1 user `manager` + 1 user `dispatcher` demo để dùng test xuyên suốt các giai đoạn sau.
  Kiểm tra: đăng nhập được cả 2 tài khoản. ĐÃ KIỂM TRA — `backend/scripts/seed_demo_users.py` (idempotent, UPSERT-style bằng cách check tồn tại trước khi insert). Seed company `00000000-0000-0000-0000-000000000001` (Công ty Vận tải Thành Công) + `manager@demo.vn`/`manager123` (manager) + `dispatcher@demo.vn`/`dispatcher123` (dispatcher). Đăng nhập thành công cả 2 tài khoản qua `POST /api/auth/login`.

---

## Giai đoạn 3 — Dữ liệu nền: Vehicles + Schedules + Excel upload

*(Tham chiếu: mục 6, 12)*

- [x] **3.1** API CRUD Vehicles: `GET/POST/PUT/DELETE /api/vehicles`.
  Kiểm tra: thêm/sửa/xóa (soft delete) 1 xe qua API, xác nhận đúng dữ liệu trong DB. ĐÃ KIỂM TRA — `backend/api/vehicles.py` + `schemas/vehicle.py`. Test qua HTTP thật (2 company, xem bug (2) ghi ở bước 2.4): tạo/sửa/xóa mềm (status='inactive', đúng theo mục 12) đều đúng, tenant isolation đúng (company khác không thấy/không sửa được xe của company kia, trả 404 chứ không lộ dữ liệu). PHÁT HIỆN + SỬA thêm 1 bug: so sánh `vehicle.company_id != current_user["company_id"]` trong Python — `vehicle.company_id` là `uuid.UUID` (từ DB) còn `current_user["company_id"]` là `str` (từ JWT decode) → luôn `!=` do khác kiểu, khiến MỌI request PUT/DELETE (kể cả đúng chủ sở hữu) đều trả 404. Sửa bằng `str(vehicle.company_id) != ...`. Audit log ghi action `create_vehicle`/`update_vehicle`/`delete_vehicle` vào `audit_logs.detail` (JSONB, không dùng `entity_id` vì PK xe là TEXT biển số, không phải UUID).
- [x] **3.2** API `POST /api/vehicles/upload` — đọc sheet `Danh_muc_xe`, UPSERT theo `vehicle_id` (mục 6.1).
  Kiểm tra: upload thử `schedule_template.xlsx` (sheet `Danh_muc_xe`, sau khi xóa hàng ví dụ và điền 1-2 xe thật/demo) → đúng số xe được thêm, upload lại lần 2 với 1 xe sửa thông tin → xác nhận UPSERT (không tạo trùng, không xóa xe vắng mặt).
  ĐÃ KIỂM TRA — `backend/core/excel_parser.py::parse_vehicle_sheet` (bỏ qua hàng nhãn tiếng Việt thứ 2, validate required fields/status enum/trùng vehicle_id). Dữ liệu mẫu trong `schedule_template.xlsx` (3 xe B01/B02/C01) chính là dữ liệu demo thật theo mục 15 nên dùng thẳng, không cần sửa. Upload lần 1 → `{created:3, updated:0}`. Sửa `cost_per_km` của B01 (7000→7500) trong bản copy rồi upload lại → `{created:0, updated:3}`, B01 đúng giá trị mới, B02/C01 không đổi, không xe nào bị xóa — đúng UPSERT.
  PHÁT HIỆN + SỬA 2 bug thật khi test: (1) `pandas.read_excel` không nhận trực tiếp `bytes` (`UploadFile.read()` trả về) — phải bọc `io.BytesIO()`. (2) pandas tự suy luận `driver_phone`/`vehicle_id`/`order_id`... thành số khi đọc Excel, làm mất số 0 đứng đầu SĐT (`0912000001` → `912000001`) dù cell gốc trong file là text — sửa bằng cách ép `dtype=str` cho các cột dạng chuỗi số khi đọc (`_TEXT_LIKE_NUMERIC_COLUMNS`).
- [x] **3.3** API CRUD Schedules cơ bản: `GET/POST /api/schedules`, `POST /api/schedules/{id}/stops` (mục 12).
  Kiểm tra: tạo 1 chuyến + thêm 1 điểm giao lẻ qua API, dữ liệu vào đúng bảng `schedules` (kể cả JSONB `stops`). ĐÃ KIỂM TRA — `backend/api/schedules.py` + `schemas/schedule.py`. `POST /api/schedules` nhận 1 hoặc mảng nhiều chuyến (`Union[ScheduleCreate, list]`), tự tính `planned_departure_time = depot_arrival_time + depot_loading_duration_min` (test: 06:30+30' → 07:00 đúng), chặn tạo trùng chuyến (cùng vehicle_id/shift_date/shift_label/trip_sequence còn active) trả 400 rõ ràng. `POST /api/schedules/{id}/stops` thêm điểm giao lẻ vào chuyến có sẵn, giữ đúng thứ tự `stop_order`, tenant-scoped (404 nếu chuyến thuộc company khác). `DELETE` soft-delete qua `deleted_at`, xác nhận chuyến biến mất khỏi `GET /api/schedules` (đã filter `deleted_at IS NULL`). Đã tự rút kinh nghiệm từ bug loại UUID-vs-str ở bước 3.1: mọi so sánh `company_id` trong code Python đều dùng `str(...)`.
- [x] **3.4** API `POST /api/schedules/upload` — đọc sheet `Ke_hoach_giao_hang`: forward-fill 4 cột khóa, validate `depot_arrival_time`/`depot_loading_duration_min` chỉ ở hàng đầu chuyến, tính `planned_departure_time` (mục 6.2).
  Kiểm tra: upload thử sheet `Ke_hoach_giao_hang` của 1 kịch bản demo (mục 15) → đúng số chuyến/điểm giao được tạo, `planned_departure_time` tính đúng, thử cố tình điền sai (vd `depot_arrival_time` ở hàng giữa chuyến) → hệ thống báo lỗi đúng như mô tả trong mục 6.2.
  ĐÃ KIỂM TRA — `parse_schedule_sheet` (forward-fill 4 cột khóa + `trip_sequence` mặc định 1, validate không forward-fill `depot_arrival_time`/`depot_loading_duration_min`, validate `stop_order` không trùng trong chuyến). `api/schedules.py::upload_schedules` group theo (vehicle_id, shift_date, shift_label, trip_sequence), validate xe tồn tại + active trước khi tạo, UPSERT theo chuyến (khác vehicles — hợp lý vì lịch mỗi ngày thường cần sửa/nạp lại đúng ngày đó). Upload nguyên `schedule_template.xlsx` (kịch bản 1 mục 15, xe B01) → `{created:1, trips:1, total_stops:3}`, đối chiếu JSON trả về khớp 100% dữ liệu kịch bản 1 (planned_departure_time=07:00, đủ 3 điểm giao đúng thứ tự, stop 3 đúng priority_tier=vip/cargo_type=bulky/notes). Test lỗi: sửa file cố tình điền `depot_arrival_time` ở hàng giữa chuyến → đúng message spec; xóa `order_id` 1 hàng → báo đúng "Sheet Ke_hoach_giao_hang, hàng 5, cột order_id: không được để trống".
  PHÁT HIỆN + SỬA 1 bug thật: cột `notes`/các cột optional khác trống bị pandas trả `NaN` (float), khi dump JSON tạo token `NaN` không hợp lệ với JSONB Postgres (`invalid input syntax for type json`) — sửa bằng cách chuẩn hóa các cột optional (`notes`, `depot_address`, `loading_duration_min`, `sla_penalty`, `volume_kg`) về `None` khi phát hiện NaN trong `excel_parser.py`.
- [x] **3.5** API Settings: `GET /api/settings`, `PUT /api/settings/weights`, `PUT /api/settings/depot` (mục 12).
  Kiểm tra: đổi `default_cost_per_km`/`ranking_weights` qua API, xác nhận lưu đúng vào `companies`. ĐÃ KIỂM TRA — GET đã làm ở bước 2.5 (test RBAC); thêm PUT `/weights` (validate tổng 3 trọng số = 1.0 ± 0.01, sai → 422 rõ ràng) và PUT `/depot` (`default_depot_address`/`area`/`cost_per_km`, partial update qua `exclude_unset`). Cả 2 ghi `audit_logs` action `update_settings` kèm old/new value. Đổi thử weights + depot qua API, `GET /api/settings` xác nhận lưu đúng; test weights tổng ≠ 1.0 → 422. Đã khôi phục lại giá trị demo mặc định (mục 15: depot 18 Phạm Hùng/Nam Từ Liêm, cost_per_km 8000, weights 0.4/0.3/0.3) sau khi test xong.

---

## Giai đoạn 4 — Rule Engine (bộ não phân loại)

*(Tham chiếu: mục 5)*

- [x] **4.1** `rule_engine.py` — logic nhận câu trả lời câu hỏi trắc nghiệm (mục 5.1), chốt `sub_type`.
  Kiểm tra: viết script test độc lập (không cần UI/DB), truyền câu trả lời mẫu cho cả 5 nhóm, ra đúng `sub_type` như bảng mục 5.1 (kể cả câu hỏi phụ của `delay`/`vehicle_issue`). ĐÃ KIỂM TRA — `core/rule_engine.py::classify_sub_type` + `ANSWER_TO_SUBTYPE` (answer_key cố định làm hợp đồng API với form frontend sau này). `scripts/test_rule_engine.py` chạy đủ 14 sub_type + câu hỏi phụ `delay` (đến kho đúng giờ → `suggested_sub_type=slow_loading` nhưng KHÔNG đổi `sub_type`, đúng spec "không đổi sub_type") — 100% PASS.
- [x] **4.2** `impact_analyzer.py` — tính `time_to_deadline_min`, `downstream_stops_affected`, `has_priority_order` (mục 5.2).
  Kiểm tra: chạy trên dữ liệu 1 chuyến mẫu, số liệu tính ra đúng thủ công tính tay. ĐÃ KIỂM TRA — `core/impact_analyzer.py::analyze_impact` dùng đúng dữ liệu Kịch bản 1 mục 15 (B01, trễ 45 phút, nhập lúc 07:45): `downstream_stops_affected=3`, `time_to_deadline_min=75` (09:00-07:45), `has_priority_order=False`, cả 3 điểm không breach SLA — khớp 100% số liệu tính tay VÀ đúng "Kết quả rule engine kỳ vọng" ghi trong spec (severity cuối = serious). `scripts/test_impact_analyzer.py`.
- [ ] **4.3** `rule_engine.py` — severity nền theo `sub_type` + leo thang theo bảng mục 5.2 (14 sub-type).
  Kiểm tra: chạy đủ 14 sub-type với input mẫu ở cả 2 phía ngưỡng (vừa dưới/vừa trên) → severity ra đúng.
- [ ] **4.4** `rule_engine.py` — 4 quy tắc ghi đè toàn cục (mục 5.2).
  Kiểm tra: input cố tình kích hoạt từng quy tắc 1-4 riêng lẻ → severity bị đẩy đúng như mô tả, không hạ xuống bao giờ.
- [x] **4.5** `impact_analyzer.py` — xử lý tải trọng/hàng cồng kềnh khi tìm xe thay thế (mục 5.4).
  Kiểm tra: input `cargo_type=bulky` → nhân hệ số 1.7 đúng; input `volume_kg` trống → không loại xe nào vì tải trọng. ĐÃ KIỂM TRA — `filter_vehicles_by_payload()`: 700kg bulky × 1.7 = 1190kg → đúng loại xe 1000kg, giữ xe 1500kg; 500kg bulky × 1.7 = 850kg → cả 2 xe đủ; `volume_kg=None` (bỏ trống hoàn toàn) → không loại xe nào.
- [x] **4.6** `conflict_detector.py` — `detect_conflict()` đủ 4 tín hiệu cứng + 1 tín hiệu tham khảo (mục 5.3).
  Kiểm tra: tạo 2 ngoại lệ test cùng `vehicle_id` → ra `combined`; 2 ngoại lệ không liên quan gì → ra `independent`. ĐÃ KIỂM TRA — `core/conflict_detector.py::detect_conflict` (dict-based, `nearest_available_vehicles_fn` inject từ ngoài để test không cần Maps/DB). `scripts/test_conflict_detector.py` — đủ `same_vehicle`/`same_driver`/`same_stop`/`resource_contention` → `combined`; không liên quan → `independent`; `same_area_same_time` chỉ tham khảo, không tự kích hoạt `combined`.
  PHÁT HIỆN mâu thuẫn thật trong spec: mục 5.3 định nghĩa `needs_replacement_vehicle` cố định 3 sub_type (`major_breakdown`,`road_closed`,`accident`) — theo định nghĩa này, Kịch bản bonus mục 15 (ngoại lệ A = `minor_breakdown`) sẽ KHÔNG kích hoạt `resource_contention` với B, mâu thuẫn với chính mục 15 khẳng định "cả hai đều thuộc nhóm cần xe thay thế". Giải quyết: mở rộng `needs_replacement_vehicle` để `minor_breakdown` cũng tính là "cần xe thay thế" khi ĐÃ leo thang lên `serious` (đúng lý do kịch bản bonus chọn A sửa 50 phút — leo thang serious theo mục 5.2), giữ nguyên KHÔNG áp dụng khi còn `warning` (tránh gọi Maps API cho mọi hư hỏng vặt không cần thiết). Test riêng cả 2 nhánh (serious → combined, warning → independent).
- [x] **4.7** `resource_locks` — ghi lock khi đề xuất tài nguyên, dọn lock hết hạn (mục 5.3).
  Kiểm tra: tạo 1 lock test với `expires_at` trong quá khứ, chạy job dọn dẹp → lock bị xóa. ĐÃ KIỂM TRA — `core/resource_lock.py` (`create_lock`, `get_active_locks` chỉ lấy `expires_at > now()`, `cleanup_expired_locks`). `scripts/test_resource_lock.py`: tạo 1 lock hết hạn (quá khứ) + 1 lock còn hạn trên cùng exception test, `get_active_locks` đúng chỉ thấy lock còn hạn, `cleanup_expired_locks` xóa đúng 1 lock hết hạn, không đụng lock còn hạn. Dọn sạch dữ liệu test sau khi chạy.
- [x] **4.8** **Test tổng Giai đoạn 4:** chạy rule engine (chỉ phần backend thuần, chưa cần AI/UI) trên cả 6 kịch bản demo mục 15, đối chiếu từng kết quả với "Kết quả rule engine kỳ vọng" ghi trong spec — PHẢI khớp 100% trước khi qua Giai đoạn 5.
  ĐÃ KIỂM TRA — `scripts/test_stage4_scenarios.py`: cả 6 kịch bản (5 chính + bonus) khớp 100% — KB1 serious (3 lý do trùng), KB2 critical (deadline sát), KB3 warning (đối trọng, không báo động giả — phát hiện cần thêm `to_stop_order` vào `compute_affected_stops` vì điểm giao kế tiếp KHÔNG bị ảnh hưởng, khác các kịch bản dây chuyền khác), KB4 serious (giá trị đơn cao), KB5 serious (sàn 30-90, tổng volume_kg=75 không loại xe nào), Bonus: A và B đều serious, `resource_contention` đúng kích hoạt `combined` qua xe C03. 20/20 PASS.

---

## Giai đoạn 5 — Background job + API ngoại lệ

*(Tham chiếu: mục 10, 11, 12)*

- [x] **5.1** Bảng `background_jobs` + `job_processor.py` (worker poll `status='pending'`, xử lý, cập nhật `done`/`failed`).
  Kiểm tra: tạo 1 job test thủ công trong DB, khởi động worker, xác nhận job chuyển trạng thái đúng. ĐÃ KIỂM TRA — `worker/job_processor.py::process_pending_jobs` (ưu tiên severity, stub `option_generator`/`ranker` tạm — thật ở Giai đoạn 6-7). Quyết định kiến trúc: `rule_engine`/`impact_analyzer` chạy ĐỒNG BỘ ngay lúc tạo exception (api/exceptions.py), KHÔNG đợi worker — vì đó là tính toán thuần Python không I/O, và `detect_conflict` (mục 5.3) cần severity ngay lúc tạo để xét `resource_contention`. Worker chỉ còn lo phần thật sự chậm (geocoder/LLM/ranker, Giai đoạn 6-7) — diễn giải hợp lý cho chỗ mục 11 liệt kê rule_engine trong bước worker nhưng mục 5.3 lại yêu cầu detect_conflict chạy ngay lúc tạo (2 yêu cầu chỉ tương thích nếu rule_engine chạy trước, đồng bộ). Job chuyển đúng `pending`→`running`→`done`, exception chuyển `analyzing`→`awaiting_decision`.
- [x] **5.2** API `POST /api/exceptions` (tạo ngoại lệ → gọi `detect_conflict` → tạo job `analyze_exception` hoặc `analyze_group`).
  Kiểm tra: gọi API tạo ngoại lệ, xác nhận job đúng loại được tạo tùy có xung đột hay không. ĐÃ KIỂM TRA — `api/exceptions.py`. Test qua HTTP thật: ngoại lệ độc lập → `job_type=analyze_exception`; ngoại lệ thứ 2 cùng `vehicle_id` với ngoại lệ đang active → tự tạo `exception_groups` (`mode=combined`), gán đúng `group_id` cho cả 2 exception, job `analyze_group`. Đã dọn dữ liệu test sau khi xác nhận.
  PHÁT HIỆN + SỬA 2 bug thật: (1) trộn datetime timezone-aware (`datetime.now(timezone.utc)`) với thời gian `stops[].eta`/`sla_deadline` vốn là giờ địa phương naive — `TypeError: can't subtract offset-naive and offset-aware datetimes`; sửa bằng cách tách riêng `reported_at` (UTC, lưu DB) và `now_local` (naive, dùng tính impact); (2) `impact_analyzer.compute_affected_stops` trả `datetime.time` object thô trong `affected_stops`, không serialize được khi lưu JSONB (`TypeError: Object of type time is not JSON serializable`) — sửa bằng cách chuyển `time` sang chuỗi ISO trước khi trả về, giữ giá trị `time` gốc ở field nội bộ `_sla_deadline_time` (không lưu DB) để `compute_time_to_deadline_min` vẫn tính đúng.
- [x] **5.3** API `GET /api/jobs/{job_id}/status` (polling).
  Kiểm tra: poll job vừa tạo, trạng thái chuyển từ `pending` → `done` (option_generator/ranker có thể tạm stub trả kết quả giả ở bước này, làm thật ở Giai đoạn 6-7). ĐÃ KIỂM TRA — `api/jobs.py`. Poll job qua API trước/sau khi chạy `process_pending_jobs()` — đúng chuyển `pending`→`done`, `result` trả về message stub rõ ràng.
- [x] **5.4** API `GET /api/exceptions`, `/api/exceptions/{id}`, `/api/exceptions/groups/{group_id}`.
  Kiểm tra: lấy danh sách + chi tiết đúng dữ liệu vừa tạo. ĐÃ KIỂM TRA — cả 3 endpoint trả đúng dữ liệu (bao gồm `impact_analysis` + trạng thái `job` lồng trong chi tiết 1 exception; danh sách đủ 2 exception cho group detail).
- [x] **5.5** Xử lý hàng đợi 3+ ngoại lệ đồng thời theo severity (mục 5.3, 10).
  Kiểm tra: tạo 3 ngoại lệ test với severity khác nhau cùng lúc, xác nhận xử lý theo đúng thứ tự `critical > serious > warning`. ĐÃ KIỂM TRA — `scripts/test_job_queue_priority.py`: cố ý tạo job THEO THỨ TỰ NGƯỢC (warning trước, critical sau cùng) để chứng minh worker sắp xếp theo severity chứ không theo thứ tự tạo — `process_pending_jobs()` xử lý đúng critical → serious → warning (đối chiếu qua `started_at`), cả 3 job đều chuyển `done`.

---

## Giai đoạn 6 — Tích hợp AI (Gemini)

*(Tham chiếu: mục 8, 9, 19)*

- [x] **6.1** `llm_adapter.py` — kết nối Gemini 2.5 Flash (điền `GEMINI_API_KEY` thật vào `.env` ở bước này).
  Kiểm tra: gọi thử 1 prompt đơn giản, nhận được response từ Gemini. ĐÃ KIỂM TRA — user cung cấp `GEMINI_API_KEY` thật, điền vào `.env`. Gọi thử `generate("Say hello in exactly 3 words.")` → nhận response thành công.
  Đổi khác mục 16 (lý do kỹ thuật bắt buộc): dùng SDK `google-genai` thay vì `google-generativeai` — package `google-generativeai` liệt kê trong mục 16 đã bị Google DEPRECATED HOÀN TOÀN (cảnh báo FutureWarning "All support... has ended", ngừng nhận update/fix lỗi), rủi ro thật cho 1 dependency lõi. `google-genai` là SDK chính thức thay thế của cùng Google, cùng model `gemini-2.5-flash`, cùng interface đơn giản — nhờ `llm_adapter.py` cô lập đúng như thiết kế mục 2, chỉ đổi 1 file, không ảnh hưởng gì khác. Đã test lại với SDK mới — nhanh hơn (~1.3s so với ~3.1s), không còn cảnh báo deprecated.
- [x] **6.2** Seed 15 prompt (1 system + 14 sub-type, mục 19.0-19.1) vào bảng `prompt_versions`, `is_active=true`.
  Kiểm tra: query DB thấy đủ 15 dòng, đúng nội dung tiếng Anh trong spec. ĐÃ KIỂM TRA — `scripts/seed_prompts.py` (idempotent qua `_upsert`, copy nguyên văn tiếng Anh từ mục 19.0/19.1). Query DB xác nhận đủ 15 dòng (`system` + 14 sub_type) `is_active=true`, độ dài nội dung hợp lý theo từng prompt. Seed luôn cả prompt `group` (mục 19.2, tổng 16 dòng) ngay tại bước này thay vì tách riêng ở 6.5 — cùng 1 script, không có lý do trì hoãn.
- [x] **6.3** `option_generator.py` — build `CONTEXT` JSON tự động từ DB (mục 19 intro).
  Kiểm tra: chạy trên 1 ngoại lệ test, in ra CONTEXT, đối chiếu đủ trường như mô tả (exception info, vehicle/driver, trip, impact_analysis, ranking_weights). ĐÃ KIỂM TRA — `core/option_generator.py::build_context`. Test trên exception mô phỏng Kịch bản 1 (B01, 3 stops) — CONTEXT có đủ exception (group/sub_type/severity/description/vehicle_id/area), vehicle (driver_name/max_payload_kg/cost_per_km/vehicle_type), trip (planned_departure_time + stops), impact_analysis (affected_stops đủ 3, đúng sla_breach/new_eta), ranking_weights. `distance_info=None` (Giai đoạn 7 sẽ điền, graceful degradation đúng mục 14).
- [x] **6.4** `option_generator.py` — ghép system prompt + user prompt theo `sub_type` + CONTEXT, gọi LLM, parse JSON + retry logic 3 lần (mục 8).
  Kiểm tra: chạy trên 1-2 kịch bản demo, nhận được 2-3 options hợp lệ đúng JSON schema; test cố tình gây lỗi parse (mock response sai định dạng) → retry đúng logic. ĐÃ KIỂM TRA — `scripts/test_option_generator.py` gọi Gemini THẬT trên Kịch bản 1 → nhận đúng 3 option hợp lệ, đủ 6 field JSON schema, chất lượng tốt (đọc kỹ hơn ở 6.8). `scripts/test_llm_retry.py` (mock `generate`, không tốn quota thật): code fence markdown → dọn sạch parse ngay (1 lần gọi); 2 lần đầu hỏng + lần 3 đúng → retry đúng 3 lần rồi thành công; cả 3 lần đều hỏng → dừng đúng sau 3 lần, trả về thất bại graceful (`options=None`, không raise exception) để dispatcher nhập tay (mục 8 bước 4).
- [x] **6.5** Prompt loại `group` cho combined mode (mục 19.2) — tích hợp vào `option_generator.py` khi `exception_groups.mode='combined'`.
  Kiểm tra: chạy trên kịch bản bonus (mục 15), CONTEXT chứa đủ cả 2 ngoại lệ, output phân biệt rõ hành động cho từng exception_id/vehicle_id. ĐÃ KIỂM TRA — `build_group_context`/`generate_options_for_group`. Test với đúng kịch bản bonus (B01 minor_breakdown + C02 major_breakdown, đơn VIP DH-603) → CONTEXT đủ 2 exception; Gemini thật trả 2-3 option, MỖI option đều nêu rõ hành động riêng cho B01 VÀ C02 (nhắc đúng địa danh/mã đơn từng xe), đúng tinh thần "1 quyết định phối hợp" thay vì 2 kế hoạch độc lập giẫm chân nhau.
  PHÁT HIỆN + SỬA: `_infer_conflict_signals` bản đầu tự viết lại logic đơn giản (chỉ check same_vehicle/same_stop) → trả `[]` rỗng cho đúng kịch bản bonus (2 xe khác nhau, tín hiệu thật là `resource_contention` qua C03). Sửa bằng cách TÁI DÙNG `conflict_detector.detect_conflict()` thay vì viết lại logic riêng (tránh 2 nơi có thể lệch nhau). Còn hạn chế đã ghi rõ trong code: `resource_contention` cần `nearest_available_vehicles_fn` (geocoder, Giai đoạn 7) nên `conflict_signals` hiển thị cho LLM vẫn có thể rỗng ở trường hợp 2 xe khác nhau cho đến khi Giai đoạn 7 xong — không chặn chất lượng output vì LLM vẫn tự suy luận đúng từ nội dung CONTEXT.
- [x] **6.6** `llm_usage_logs` — ghi log mỗi lần gọi (tokens, cost, latency, prompt_version_id); hard limit 100 calls/company/day.
  Kiểm tra: gọi vài lần, xác nhận log đầy đủ; test chạm giới hạn (hạ tạm limit xuống 2-3 để test nhanh) → chặn đúng và báo lỗi rõ ràng. ĐÃ KIỂM TRA — `core/llm_usage.py` (`estimate_cost_usd` ước tính tham khảo, ghi rõ trong docstring KHÔNG phải giá chính xác; `has_quota_remaining`/`log_llm_call`), nối vào `_call_llm_with_retry` — kiểm tra hạn mức TRƯỚC mỗi lần gọi thật (kể cả các lần retry), ghi log SAU mỗi lần gọi kể cả khi fail. `scripts/test_llm_quota.py` hạ `daily_limit` tương đối (`before_count+2`) để test nhanh không cần chèn 100 dòng giả: 2 lần đầu thành công + ghi log đúng, lần 3 bị chặn bằng `QuotaExceededError` rõ ràng, KHÔNG ghi log cho lần bị chặn (chặn trước khi gọi LLM, không lãng phí).
- [x] **6.7** LLM fallback khi Gemini lỗi/down — cho phép nhập phương án thủ công (mục 8).
  Kiểm tra: giả lập lỗi API (sai key tạm thời) → hệ thống báo lỗi rõ, không crash, vẫn cho tạo phương án thủ công. ĐÃ KIỂM TRA — nối `option_generator.py` thật vào `job_processor.py` (thay stub Giai đoạn 5), fallback graceful: LLM lỗi/hết hạn mức → job vẫn `done` (không phải `failed` — đây là fallback có kiểm soát, không phải lỗi hệ thống), ghi rõ lý do vào `job.error`, tự tạo 1 option placeholder để dispatcher luôn có gì đó để xác nhận/ghi đè. Thêm `POST /api/exceptions/{id}/manual-option` (không có trong mục 12, bổ sung cần thiết để thực sự "cho phép nhập phương án thủ công" — quyết định/decisions luôn cần `selected_option_id`). `scripts/test_llm_fallback.py` (mock Gemini luôn fail) xác nhận không crash, đủ 5 tiêu chí; test endpoint qua HTTP thật cũng thành công (201).
- [~] **6.8** **Test tổng Giai đoạn 6:** đọc kỹ output AI của toàn bộ 6 kịch bản demo — không chỉ đúng JSON, mà giọng văn/logic tiếng Việt có đúng như 1 giám sát điều phối thật viết không (mục 19.0). Đây là bước ĐỌC BẰNG MẮT, không tự động hóa được — người dùng (bạn) nên tham gia đọc thử ở bước này.
  Đã làm: đã gọi Gemini THẬT (không phải mock) và tự đọc kỹ 2/6 kịch bản trong lúc test 6.4/6.5 — Kịch bản 1 (late_departure, xem log bước 6.4) và Kịch bản bonus (combined mode B01+C02, xem log bước 6.5). Cả 2 đều: JSON hợp lệ đúng schema, giọng văn tiếng Việt tự nhiên như giám sát điều phối thật (không dịch máy), logic bám sát đúng dữ liệu (nhận diện đúng điểm VIP buffer hẹp nhất ở KB1; phân biệt rõ hành động cho từng xe B01/C02 + đúng mã đơn ở kịch bản bonus), không có tuyên bố "đã thực hiện xong" (đúng ROLE AND SCOPE của system prompt). Còn thiếu: chưa chạy + đọc kỹ 4/6 kịch bản còn lại (2 road_closed, 3 customer_absent, 4 cancel_order, 5 major_breakdown) — cơ chế kỹ thuật (JSON schema, retry, quota, context) đã kiểm chứng đủ vững ở 6.3-6.7 nên rủi ro thấp, nhưng CHƯA đối chiếu bằng mắt như spec yêu cầu. Phiên sau nên chạy `scripts/test_option_generator.py`-style cho 4 kịch bản còn lại và tự đọc trước khi tick `[x]` hoàn toàn.

---

## Giai đoạn 7 — Xếp hạng + Google Maps

*(Tham chiếu: mục 7, 14)*

- [ ] **7.1** `ranker.py` — `calculate_score()` theo mục 7.
  Kiểm tra: chạy trên các options đã sinh ở Giai đoạn 6, điểm số tính đúng công thức, thay đổi `ranking_weights` → thứ hạng đổi theo đúng logic.
- [ ] **7.2** `geocoder.py` — wrapper Google Geocoding + Distance Matrix (điền `GOOGLE_MAPS_API_KEY` thật ở bước này).
  Kiểm tra: geocode thử 1 địa chỉ demo (mục 15) ra đúng tọa độ hợp lý.
- [ ] **7.3** `geocode_cache` — cache theo hash địa chỉ, không gọi API lại địa chỉ đã có.
  Kiểm tra: gọi geocode 2 lần cùng địa chỉ, lần 2 không tốn API call (kiểm tra qua log/số lần gọi thực tế).
- [ ] **7.4** Graceful degradation khi Maps API lỗi (mục 14).
  Kiểm tra: giả lập lỗi (sai key tạm) → hệ thống vẫn xử lý ngoại lệ, chỉ thiếu thông tin khoảng cách, báo rõ cho user.
- [ ] **7.5** Nối toàn bộ pipeline đúng thứ tự: `rule_engine → impact_analyzer → geocoder → option_generator → ranker` (mục 11) trong `job_processor.py`.
  Kiểm tra: **chạy end-to-end thuần backend** (không cần UI) cả 6 kịch bản demo mục 15 — từ tạo exception đến có options đã xếp hạng — kết quả hợp lý ở mọi bước, không lỗi giữa chừng. Đây là cột mốc quan trọng: nếu qua được bước này, toàn bộ "bộ não" hệ thống đã chạy đúng, phần còn lại chỉ là giao diện.

---

## Giai đoạn 8 — Frontend cho Dispatcher

*(Tham chiếu: mục 3)*

- [ ] **8.1** Setup routing + layout khung, trang đăng nhập gọi API auth.
  Kiểm tra: đăng nhập qua giao diện thật bằng tài khoản demo (Giai đoạn 2), vào được trang chính.
- [ ] **8.2** `Dashboard.tsx` — danh sách ngoại lệ + trạng thái, filter theo severity/status.
  Kiểm tra: thấy đúng danh sách ngoại lệ đã tạo ở các giai đoạn test trước.
- [ ] **8.3** Form nhập ngoại lệ mới — đúng luồng câu hỏi trắc nghiệm theo mục 5.1 (không phải text tự do).
  Kiểm tra: nhập thử 1 kịch bản demo qua giao diện, `sub_type` ra đúng.
- [ ] **8.4** `ExceptionDetail.tsx` — hiển thị impact + options, polling job status mỗi 2 giây (`usePolling.ts`).
  Kiểm tra: sau khi nhập ngoại lệ, thấy trạng thái "đang phân tích" rồi tự chuyển sang hiển thị options mà không cần bấm refresh tay.
- [ ] **8.5** `ExceptionGroup.tsx` — xử lý ngoại lệ nhóm (combined mode).
  Kiểm tra: nhập kịch bản bonus (2 ngoại lệ liên quan) qua giao diện, hệ thống tự gộp và hiển thị đúng màn hình nhóm.
- [ ] **8.6** Xác nhận quyết định (`POST /api/decisions`) + màn nhập outcome thực tế (`POST /api/outcomes`).
  Kiểm tra: chọn 1 option, xác nhận, sau đó nhập kết quả thực tế — dữ liệu lưu đúng, audit log ghi lại hành động `confirm_decision`.

---

## Giai đoạn 9 — Frontend cho Manager + Excel UI

*(Tham chiếu: mục 3, 6)*

- [ ] **9.1** `ManagerDashboard.tsx` — KPI cơ bản (`GET /api/reports/kpi`, `/trends`, `/cost-accuracy`, `/llm-usage`).
  Kiểm tra: đăng nhập tài khoản manager, thấy số liệu tổng hợp hợp lý từ dữ liệu test đã có.
- [ ] **9.2** Settings page — depot mặc định, `default_cost_per_km`, `ranking_weights`.
  Kiểm tra: đổi trọng số qua giao diện, xác nhận ảnh hưởng đúng đến thứ hạng phương án ở lần phân tích tiếp theo.
- [ ] **9.3** Form nhập kế hoạch nhanh qua giao diện (không qua Excel) — `ScheduleInput.tsx`.
  Kiểm tra: tạo 1 chuyến mới trực tiếp trên form, dữ liệu đúng như tạo qua API.
- [ ] **9.4** Excel upload UI (2 sheet `Danh_muc_xe`/`Ke_hoach_giao_hang`) — hiển thị lỗi validation rõ ràng theo từng ô (mục 6.2).
  Kiểm tra: upload 1 file cố tình có lỗi (vd thiếu `order_id`) → giao diện hiển thị đúng thông báo lỗi cụ thể hàng/cột như mô tả trong spec, không chỉ báo "upload thất bại" chung chung.

---

## Giai đoạn 10 — Dữ liệu demo + Kiểm thử toàn bộ

*(Tham chiếu: mục 15, Phần 4 đã hoãn)*

- [ ] **10.1** Viết seed script: 10 xe (mục 15) + 6 kịch bản demo (5 chính + bonus) — tạo sẵn trong DB `demo-company-001` để chạy độc lập lúc trình bày.
  Kiểm tra: chạy seed script từ đầu (DB rỗng) → đủ dữ liệu, không lỗi.
- [ ] **10.2** *(Phần đã hoãn trước đó)* Seed 20-30 ngoại lệ lịch sử giả cho Learning Database — làm ở bước này vì hệ thống đã chạy thật, biết rõ format/kết quả cần seed.
  Kiểm tra: dữ liệu lịch sử xuất hiện đúng trong các báo cáo/KPI liên quan (nếu tính năng đó đã dùng đến dữ liệu này).
- [ ] **10.3** Test toàn bộ 6 kịch bản demo qua giao diện thật (không phải script), từ đầu đến cuối (nhập ngoại lệ → xem phương án → xác nhận quyết định).
  Kiểm tra: cả 6 kịch bản chạy mượt, kết quả khớp phần "Điểm demo" mô tả trong mục 15.
- [ ] **10.4** Sửa lỗi phát sinh trong lúc test toàn bộ.
  Kiểm tra: chạy lại 6 kịch bản 1 lần nữa sau khi sửa, không còn lỗi.

---

## Giai đoạn 11 — Deploy + Diễn tập demo

*(Tham chiếu: mục 2)*

- [ ] **11.1** Deploy backend + database lên Railway hoặc Render.
  Kiểm tra: gọi thử 1 API endpoint qua URL production, nhận response đúng.
- [ ] **11.2** Deploy frontend, trỏ đúng API URL production.
  Kiểm tra: mở URL production, đăng nhập và dùng thử được như môi trường local.
- [ ] **11.3** Chạy lại toàn bộ seed dữ liệu demo trên môi trường production.
  Kiểm tra: 6 kịch bản demo sẵn sàng trên bản production, giống hệt local.
- [ ] **11.4** Diễn tập demo (rehearsal) — chạy thử toàn bộ kịch bản trình bày như lúc thi thật.
  Kiểm tra: không có bước nào bị lỗi/khựng giữa buổi diễn tập.
- [ ] **11.5** Buffer cho sự cố cuối — dự phòng thời gian xử lý phát sinh trước ngày thi.

---

## Nhật ký tiến độ (Claude Code ghi ngắn gọn mỗi khi hoàn thành 1 Giai đoạn)

*(Thêm 1 dòng mỗi lần xong trọn 1 Giai đoạn — không cần ghi từng bước nhỏ ở đây, chi tiết đã có ở checkbox phía trên)*

- **Giai đoạn 1** (2026-09-02): Xong. Điểm cần lưu ý: máy dev không có sẵn pgvector cho PG17 trên Windows, phải build từ source qua VS Build Tools (quyền admin, Claude Code không có quyền này) — mất thời gian chờ user tự cài.
- **Giai đoạn 2** (2026-09-02): Xong. 18/18 bảng, JWT + tenant injection (SQLAlchemy `with_loader_criteria`) + RBAC middleware, API auth (login/refresh/logout — logout dùng revoke list in-memory vì chưa có bảng session trong schema), seed demo. Phát hiện + sửa 1 bug thật: `with_loader_criteria` dạng callable bị SQLAlchemy cache sai company_id giữa các request — phải truyền thẳng biểu thức đã bind giá trị. Tạo trước 1 phần nhỏ `GET /api/settings` (thuộc 3.5) để có endpoint test RBAC.
- **Giai đoạn 3** (2026-09-02): Xong. CRUD Vehicles + Schedules, upload Excel cả 2 sheet (UPSERT cho xe, UPSERT theo chuyến cho lịch), Settings PUT. Phát hiện + sửa 3 bug thật quan trọng: (1) `get_db` phải là `async def` chứ không phải `def` — sync generator dependency chạy qua threadpool của FastAPI làm mất hoàn toàn giá trị contextvar tenant filter giữa dependency và endpoint (lộ ra khi test qua HTTP thật với 2 company, không lộ ra khi chỉ test tầng DB); (2) so sánh `company_id` kiểu `uuid.UUID` (từ DB) với `str` (từ JWT) bằng `!=` trong Python luôn `True` do khác kiểu — khiến MỌI request PUT/DELETE vehicles/schedules đều trả 404 dù đúng chủ sở hữu; (3) pandas đọc Excel tự suy luận cột SĐT/mã đơn thành số làm mất số 0 đầu, và ô trống thành `NaN` (không phải `None`) làm JSONB Postgres từ chối khi lưu. Bài học chung: test tầng DB/script độc lập không đủ để bắt bug ở tầng framework (threadpool, type coercion) — phải test qua HTTP thật.
- **Giai đoạn 4** (2026-09-02): Xong. `rule_engine.py` (classify_sub_type + calculate_severity đủ 14 sub-type + 4 quy tắc toàn cục), `impact_analyzer.py` (affected_stops/time_to_deadline_min/downstream_stops_affected/has_priority_order + xử lý tải trọng/bulky mục 5.4), `conflict_detector.py` (4 tín hiệu cứng + 1 tham khảo), `resource_lock.py`. Toàn bộ 6 kịch bản demo mục 15 khớp 100% kết quả kỳ vọng. Phát hiện + sửa 2 điểm cần làm rõ so với spec: (1) `compute_affected_stops` cần thêm tham số `to_stop_order` — không phải mọi ngoại lệ đều ảnh hưởng dây chuyền đến hết chuyến (customer_absent chỉ ảnh hưởng đúng 1 điểm, theo đúng ghi chú "chưa bị ảnh hưởng" ở Kịch bản 3); (2) mở rộng `needs_replacement_vehicle` để `minor_breakdown` cũng tính là cần xe thay thế khi đã leo thang `serious`, khớp Kịch bản bonus (mục 5.3 chỉ liệt kê 3 sub_type cố định, không đủ để kịch bản bonus hoạt động đúng như spec mô tả).
- **Giai đoạn 5** (2026-09-02): Xong. `background_jobs`/`job_processor.py`, API `POST /api/exceptions` (rule_engine+impact_analyzer chạy đồng bộ, `detect_conflict` tạo job đúng loại `analyze_exception`/`analyze_group`), `GET /api/jobs/{id}/status`, `GET /api/exceptions`/`{id}`/`groups/{group_id}`, hàng đợi ưu tiên severity. Test qua HTTP thật: luồng độc lập (pending→done, awaiting_decision) và luồng combined (2 exception cùng xe → tự gộp `exception_groups`) đều đúng. Phát hiện + sửa 2 bug thật (trộn datetime aware/naive khi tính time_to_deadline; `datetime.time` không serialize JSONB) — chi tiết ở ghi chú bước 5.2. Rút kinh nghiệm thao tác: dùng file JSON + `--data-binary @file` khi test payload tiếng Việt qua curl (Bash tool làm hỏng ký tự non-ASCII khi truyền trực tiếp trong `-d "..."`), và luôn xóa `options`/`impact_analysis` TRƯỚC `exceptions` khi dọn dữ liệu test (thứ tự FK).
- **Giai đoạn 6** (2026-09-02): Gần xong (6.1-6.7 xong, 6.8 mới đọc 2/6 kịch bản — xem ghi chú bước 6.8). `llm_adapter.py` dùng SDK `google-genai` (đổi khỏi `google-generativeai` đã bị Google deprecated hoàn toàn — xem ghi chú 6.1), seed 16 prompt (15 theo yêu cầu + `group`), `option_generator.py` (build_context + gọi LLM thật + retry 3 lần + parse JSON), `llm_usage.py` (log + hard limit 100 calls/ngày), fallback graceful khi LLM lỗi (job vẫn `done`, tạo option placeholder, thêm endpoint `POST /api/exceptions/{id}/manual-option`). Test qua Gemini THẬT (không mock) trên Kịch bản 1 và Kịch bản bonus — chất lượng output tiếng Việt tốt, đúng giọng văn giám sát điều phối, logic chính xác. Phát hiện + sửa 1 bug thật trong `_infer_conflict_signals` (viết lại logic riêng thay vì tái dùng `conflict_detector.detect_conflict`, khiến bỏ sót tín hiệu).
