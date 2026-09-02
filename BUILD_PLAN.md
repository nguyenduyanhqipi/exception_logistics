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
- [~] **1.4** Tạo database PostgreSQL `exception_logistics`, bật extension `pgvector`.
  Kiểm tra: `psql -d exception_logistics -c "\dx"` thấy extension `vector`.
  Đã làm: database `exception_logistics` đã tạo (xác nhận qua `psql -U postgres`, auth scram-sha-256, cần PGPASSWORD). Còn thiếu: extension `vector` — bản cài PostgreSQL 17 trên máy KHÔNG có sẵn pgvector, cần build từ source (yêu cầu Visual Studio Build Tools + MSVC). Phiên Claude Code hiện tại chạy KHÔNG có quyền admin, không ghi được vào `C:\Program Files\PostgreSQL\17` → không thể tự cài. Đã gửi hướng dẫn 3 bước cho user tự chạy trong PowerShell admin (cài VS Build Tools → clone+build pgvector từ github.com/pgvector/pgvector → `CREATE EXTENSION vector`). Chờ user xác nhận xong trước khi tick `[x]`. KHÔNG chặn các bước 1.5-1.7 hay Giai đoạn 2 (chỉ chặn bảng `exception_embeddings`/cột VECTOR — dùng cho RAG giai đoạn 2, kích hoạt sau ~200 case theo mục 15).
- [x] **1.5** Khởi tạo Alembic, trỏ đúng `DATABASE_URL`.
  Kiểm tra: `alembic current` chạy không lỗi (chưa có migration nào cũng được). ĐÃ KIỂM TRA — `alembic init alembic` xong trong `backend/`; sửa `alembic/env.py` để `load_dotenv` từ `.env` ở gốc project và override `sqlalchemy.url` bằng `DATABASE_URL` (không hardcode credential vào `alembic.ini`, đúng nguyên tắc mục 13). `alembic current` chạy sạch, không lỗi, không có migration (đúng kỳ vọng).
- [x] **1.6** Tạo `.env` từ `.env.example`, điền `DATABASE_URL`, `JWT_SECRET`. (`GEMINI_API_KEY`, `GOOGLE_MAPS_API_KEY` điền ở Giai đoạn 5-6 khi cần dùng thật.)
  Kiểm tra: backend đọc được `.env` (test bằng 1 script in ra `DATABASE_URL`). ĐÃ KIỂM TRA — tạo `.env.example` (rỗng, mẫu) và `.env` (điền `DATABASE_URL=postgresql://postgres:***@localhost:5432/exception_logistics`, `JWT_SECRET` random 48-byte qua `secrets.token_urlsafe`) ở gốc project. Script Python test `load_dotenv` in đúng `DATABASE_URL` và xác nhận `JWT_SECRET` đã set. Đã thêm `.gitignore` loại trừ `.env` trước khi git init (mục 13: secrets không commit).
- [ ] **1.7** `git init`, commit khung sườn ban đầu (chưa có logic).
  Kiểm tra: `git log` có ít nhất 1 commit.

---

## Giai đoạn 2 — Nền dữ liệu: Database schema + Auth

*(Tham chiếu: mục 4, 13)*

- [ ] **2.1** Viết SQLAlchemy model cho TẤT CẢ bảng ở mục 4 (companies, vehicles, users, schedules, exceptions, exception_groups, resource_locks, impact_analysis, options, decisions, outcomes, exception_embeddings, prompt_versions, rule_versions, llm_usage_logs, audit_logs, geocode_cache, background_jobs).
  Kiểm tra: `alembic revision --autogenerate` sinh ra migration có đủ các bảng, không báo lỗi.
- [ ] **2.2** Chạy migration đầu tiên, xác nhận toàn bộ bảng + cột + kiểu dữ liệu đúng như mục 4 (đặc biệt: `vehicles.max_payload_kg`/`cost_per_km` nullable đúng, `schedules.depot_arrival_time`/`depot_loading_duration_min`/`planned_departure_time`, UNIQUE constraint của `schedules`).
  Kiểm tra: `psql -d exception_logistics -c "\d vehicles"` (và các bảng khác) khớp mục 4.
- [ ] **2.3** Middleware JWT validation (mục 13, bước 3).
  Kiểm tra: gọi 1 endpoint bất kỳ không kèm token → trả lỗi 401 rõ ràng.
- [ ] **2.4** Middleware tenant injection — tự động filter `company_id` mọi query (mục 13, bước 4).
  Kiểm tra: tạo 2 company demo, xác nhận query của company A không bao giờ trả dữ liệu company B.
- [ ] **2.5** Middleware RBAC — check role `dispatcher`/`manager` (mục 13, bước 5).
  Kiểm tra: gọi 1 endpoint `manager only` (vd `/api/reports/kpi`) bằng tài khoản dispatcher → trả lỗi 403.
- [ ] **2.6** API `POST /api/auth/login`, `/refresh`, `/logout` (mục 12).
  Kiểm tra: tạo 1 user demo qua script/seed thủ công, đăng nhập lấy token thành công, refresh token hoạt động, logout vô hiệu hóa token.
- [ ] **2.7** Seed 1 company + 1 user `manager` + 1 user `dispatcher` demo để dùng test xuyên suốt các giai đoạn sau.
  Kiểm tra: đăng nhập được cả 2 tài khoản.

---

## Giai đoạn 3 — Dữ liệu nền: Vehicles + Schedules + Excel upload

*(Tham chiếu: mục 6, 12)*

- [ ] **3.1** API CRUD Vehicles: `GET/POST/PUT/DELETE /api/vehicles`.
  Kiểm tra: thêm/sửa/xóa (soft delete) 1 xe qua API, xác nhận đúng dữ liệu trong DB.
- [ ] **3.2** API `POST /api/vehicles/upload` — đọc sheet `Danh_muc_xe`, UPSERT theo `vehicle_id` (mục 6.1).
  Kiểm tra: upload thử `schedule_template.xlsx` (sheet `Danh_muc_xe`, sau khi xóa hàng ví dụ và điền 1-2 xe thật/demo) → đúng số xe được thêm, upload lại lần 2 với 1 xe sửa thông tin → xác nhận UPSERT (không tạo trùng, không xóa xe vắng mặt).
- [ ] **3.3** API CRUD Schedules cơ bản: `GET/POST /api/schedules`, `POST /api/schedules/{id}/stops` (mục 12).
  Kiểm tra: tạo 1 chuyến + thêm 1 điểm giao lẻ qua API, dữ liệu vào đúng bảng `schedules` (kể cả JSONB `stops`).
- [ ] **3.4** API `POST /api/schedules/upload` — đọc sheet `Ke_hoach_giao_hang`: forward-fill 4 cột khóa, validate `depot_arrival_time`/`depot_loading_duration_min` chỉ ở hàng đầu chuyến, tính `planned_departure_time` (mục 6.2).
  Kiểm tra: upload thử sheet `Ke_hoach_giao_hang` của 1 kịch bản demo (mục 15) → đúng số chuyến/điểm giao được tạo, `planned_departure_time` tính đúng, thử cố tình điền sai (vd `depot_arrival_time` ở hàng giữa chuyến) → hệ thống báo lỗi đúng như mô tả trong mục 6.2.
- [ ] **3.5** API Settings: `GET /api/settings`, `PUT /api/settings/weights`, `PUT /api/settings/depot` (mục 12).
  Kiểm tra: đổi `default_cost_per_km`/`ranking_weights` qua API, xác nhận lưu đúng vào `companies`.

---

## Giai đoạn 4 — Rule Engine (bộ não phân loại)

*(Tham chiếu: mục 5)*

- [ ] **4.1** `rule_engine.py` — logic nhận câu trả lời câu hỏi trắc nghiệm (mục 5.1), chốt `sub_type`.
  Kiểm tra: viết script test độc lập (không cần UI/DB), truyền câu trả lời mẫu cho cả 5 nhóm, ra đúng `sub_type` như bảng mục 5.1 (kể cả câu hỏi phụ của `delay`/`vehicle_issue`).
- [ ] **4.2** `impact_analyzer.py` — tính `time_to_deadline_min`, `downstream_stops_affected`, `has_priority_order` (mục 5.2).
  Kiểm tra: chạy trên dữ liệu 1 chuyến mẫu, số liệu tính ra đúng thủ công tính tay.
- [ ] **4.3** `rule_engine.py` — severity nền theo `sub_type` + leo thang theo bảng mục 5.2 (14 sub-type).
  Kiểm tra: chạy đủ 14 sub-type với input mẫu ở cả 2 phía ngưỡng (vừa dưới/vừa trên) → severity ra đúng.
- [ ] **4.4** `rule_engine.py` — 4 quy tắc ghi đè toàn cục (mục 5.2).
  Kiểm tra: input cố tình kích hoạt từng quy tắc 1-4 riêng lẻ → severity bị đẩy đúng như mô tả, không hạ xuống bao giờ.
- [ ] **4.5** `impact_analyzer.py` — xử lý tải trọng/hàng cồng kềnh khi tìm xe thay thế (mục 5.4).
  Kiểm tra: input `cargo_type=bulky` → nhân hệ số 1.7 đúng; input `volume_kg` trống → không loại xe nào vì tải trọng.
- [ ] **4.6** `conflict_detector.py` — `detect_conflict()` đủ 4 tín hiệu cứng + 1 tín hiệu tham khảo (mục 5.3).
  Kiểm tra: tạo 2 ngoại lệ test cùng `vehicle_id` → ra `combined`; 2 ngoại lệ không liên quan gì → ra `independent`.
- [ ] **4.7** `resource_locks` — ghi lock khi đề xuất tài nguyên, dọn lock hết hạn (mục 5.3).
  Kiểm tra: tạo 1 lock test với `expires_at` trong quá khứ, chạy job dọn dẹp → lock bị xóa.
- [ ] **4.8** **Test tổng Giai đoạn 4:** chạy rule engine (chỉ phần backend thuần, chưa cần AI/UI) trên cả 6 kịch bản demo mục 15, đối chiếu từng kết quả với "Kết quả rule engine kỳ vọng" ghi trong spec — PHẢI khớp 100% trước khi qua Giai đoạn 5.

---

## Giai đoạn 5 — Background job + API ngoại lệ

*(Tham chiếu: mục 10, 11, 12)*

- [ ] **5.1** Bảng `background_jobs` + `job_processor.py` (worker poll `status='pending'`, xử lý, cập nhật `done`/`failed`).
  Kiểm tra: tạo 1 job test thủ công trong DB, khởi động worker, xác nhận job chuyển trạng thái đúng.
- [ ] **5.2** API `POST /api/exceptions` (tạo ngoại lệ → gọi `detect_conflict` → tạo job `analyze_exception` hoặc `analyze_group`).
  Kiểm tra: gọi API tạo ngoại lệ, xác nhận job đúng loại được tạo tùy có xung đột hay không.
- [ ] **5.3** API `GET /api/jobs/{job_id}/status` (polling).
  Kiểm tra: poll job vừa tạo, trạng thái chuyển từ `pending` → `done` (option_generator/ranker có thể tạm stub trả kết quả giả ở bước này, làm thật ở Giai đoạn 6-7).
- [ ] **5.4** API `GET /api/exceptions`, `/api/exceptions/{id}`, `/api/exceptions/groups/{group_id}`.
  Kiểm tra: lấy danh sách + chi tiết đúng dữ liệu vừa tạo.
- [ ] **5.5** Xử lý hàng đợi 3+ ngoại lệ đồng thời theo severity (mục 5.3, 10).
  Kiểm tra: tạo 3 ngoại lệ test với severity khác nhau cùng lúc, xác nhận xử lý theo đúng thứ tự `critical > serious > warning`.

---

## Giai đoạn 6 — Tích hợp AI (Gemini)

*(Tham chiếu: mục 8, 9, 19)*

- [ ] **6.1** `llm_adapter.py` — kết nối Gemini 2.5 Flash (điền `GEMINI_API_KEY` thật vào `.env` ở bước này).
  Kiểm tra: gọi thử 1 prompt đơn giản, nhận được response từ Gemini.
- [ ] **6.2** Seed 15 prompt (1 system + 14 sub-type, mục 19.0-19.1) vào bảng `prompt_versions`, `is_active=true`.
  Kiểm tra: query DB thấy đủ 15 dòng, đúng nội dung tiếng Anh trong spec.
- [ ] **6.3** `option_generator.py` — build `CONTEXT` JSON tự động từ DB (mục 19 intro).
  Kiểm tra: chạy trên 1 ngoại lệ test, in ra CONTEXT, đối chiếu đủ trường như mô tả (exception info, vehicle/driver, trip, impact_analysis, ranking_weights).
- [ ] **6.4** `option_generator.py` — ghép system prompt + user prompt theo `sub_type` + CONTEXT, gọi LLM, parse JSON + retry logic 3 lần (mục 8).
  Kiểm tra: chạy trên 1-2 kịch bản demo, nhận được 2-3 options hợp lệ đúng JSON schema; test cố tình gây lỗi parse (mock response sai định dạng) → retry đúng logic.
- [ ] **6.5** Prompt loại `group` cho combined mode (mục 19.2) — tích hợp vào `option_generator.py` khi `exception_groups.mode='combined'`.
  Kiểm tra: chạy trên kịch bản bonus (mục 15), CONTEXT chứa đủ cả 2 ngoại lệ, output phân biệt rõ hành động cho từng exception_id/vehicle_id.
- [ ] **6.6** `llm_usage_logs` — ghi log mỗi lần gọi (tokens, cost, latency, prompt_version_id); hard limit 100 calls/company/day.
  Kiểm tra: gọi vài lần, xác nhận log đầy đủ; test chạm giới hạn (hạ tạm limit xuống 2-3 để test nhanh) → chặn đúng và báo lỗi rõ ràng.
- [ ] **6.7** LLM fallback khi Gemini lỗi/down — cho phép nhập phương án thủ công (mục 8).
  Kiểm tra: giả lập lỗi API (sai key tạm thời) → hệ thống báo lỗi rõ, không crash, vẫn cho tạo phương án thủ công.
- [ ] **6.8** **Test tổng Giai đoạn 6:** đọc kỹ output AI của toàn bộ 6 kịch bản demo — không chỉ đúng JSON, mà giọng văn/logic tiếng Việt có đúng như 1 giám sát điều phối thật viết không (mục 19.0). Đây là bước ĐỌC BẰNG MẮT, không tự động hóa được — người dùng (bạn) nên tham gia đọc thử ở bước này.

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

- _(chưa có)_
