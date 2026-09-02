# Deploy — Giai đoạn 11

Chuẩn bị sẵn (Dockerfile backend/frontend, `docker-compose.yml`, `render.yaml`).
Phần còn lại cần tài khoản/VM thật của bạn — không tự làm được, ghi rõ từng
bước dưới đây.

**Đang dùng: Cách C (Google Compute Engine VM qua `docker-compose.yml`)** —
Cách A/B (Render/Railway) giữ lại bên dưới làm phương án dự phòng đã chuẩn bị
sẵn, không phải hướng đang triển khai.

## Cách C — Google Compute Engine VM (đang dùng, `docker-compose.yml`)

VM Ubuntu, IP tĩnh `34.142.218.150`, đã cài Docker. Chạy toàn bộ 4 service
(`db`, `api`, `worker`, `frontend`) qua `docker-compose.yml` ở gốc repo.

1. SSH vào VM, `git clone`/`git pull` repo này.
2. Tạo `.env` ở gốc repo (dùng `.env.example` làm mẫu) — điền `GEMINI_API_KEY`
   (`_2`/`_3` nếu có), `GOONG_API_KEY`, `JWT_SECRET` (chuỗi ngẫu nhiên dài),
   `SENTRY_DSN` (tuỳ chọn). `DATABASE_URL` KHÔNG cần điền — `docker-compose.yml`
   đã tự trỏ `api`/`worker` vào service `db` nội bộ.
3. `docker compose up -d --build`. Service `frontend` build với build arg
   `VITE_API_URL=http://34.142.218.150:8000` cố định sẵn trong
   `docker-compose.yml` — nếu đổi IP/domain, sửa giá trị này trước khi build
   lại (Vite bake `VITE_API_URL` vào bundle NGAY LÚC BUILD, không đọc được lúc
   chạy — đổi IP mà không build lại frontend sẽ vẫn gọi API ở IP cũ).
4. Chạy migration + seed (exec vào container `api`):
   ```bash
   docker compose exec api alembic upgrade head
   docker compose exec api python scripts/seed_demo_users.py
   docker compose exec api python scripts/seed_prompts.py
   docker compose exec api python scripts/seed_demo_data.py
   docker compose exec api python scripts/seed_historical_exceptions.py
   ```
   Nhắc lại ghi chú ở `scripts/seed_demo_data.py`: chạy lại **ngay trước buổi
   trình bày thật** vì giờ các điểm giao tính tương đối theo lúc chạy script.
5. Kiểm tra: `curl http://34.142.218.150:8000/health` trả `{"status":"ok"}`;
   mở `http://34.142.218.150` (port 80, service `frontend`) thấy trang đăng
   nhập, đăng nhập/dùng thử được bình thường (đặc biệt thử F5 ở 1 route con
   như `/exceptions/new` — `nginx.conf` đã cấu hình fallback SPA cho
   `BrowserRouter`, nếu quên bước này F5 sẽ ra 404).
6. Firewall VM: mở port 80 (frontend) và 8000 (API) cho traffic bên ngoài nếu
   Compute Engine chưa mở sẵn (mục "Firewall rules" trong GCP Console, hoặc
   `gcloud compute firewall-rules create`).

## Lưu ý quan trọng: pgvector

Bảng `exception_embeddings` dùng cột kiểu `VECTOR` (pgvector). Cả Railway và
Render đều hỗ trợ pgvector trên Postgres managed, nhưng cách bật khác nhau
theo thời điểm/gói dịch vụ — **kiểm tra lại tài liệu chính thức của nhà cung
cấp tại thời điểm bạn deploy** trước khi chọn, vì thông tin này có thể đã đổi.
Alembic migration `a1b2c3d4e5f6` đã có sẵn `CREATE EXTENSION IF NOT EXISTS
vector` — nếu Postgres managed đó cho phép superuser tạo extension, mọi việc
tự động; nếu không, cần bật qua dashboard/CLI của nhà cung cấp trước khi chạy
migration.

## Cách A — Render (dự phòng đã chuẩn bị sẵn, không phải hướng đang dùng)

1. Đăng nhập Render, "New +" → "Blueprint" → chọn repo GitHub của project này.
2. Render tự đọc `render.yaml` ở gốc repo → tạo sẵn: 1 Postgres DB, 1 web
   service (API), 1 worker service (background jobs) — đúng theo mục 16
   "worker chạy riêng, không chung tiến trình với API".
3. Điền 3 biến môi trường còn thiếu (đánh dấu `sync: false` trong
   `render.yaml`, Render sẽ hỏi khi tạo) cho CẢ web lẫn worker:
   `GEMINI_API_KEY`, `GOONG_API_KEY`, `SENTRY_DSN` (Sentry để trống nếu
   chưa dùng). `DATABASE_URL`/`JWT_SECRET` đã tự sinh.
4. Deploy. Kiểm tra: `curl https://<tên-service>.onrender.com/health` trả
   `{"status":"ok"}`.

## Cách B — Railway (dự phòng đã chuẩn bị sẵn, không phải hướng đang dùng)

Railway không dùng file blueprint kiểu `render.yaml` — làm qua dashboard/CLI:

1. `railway login` (cần trình duyệt để xác thực tài khoản Railway của bạn).
2. Tạo project mới, "Add" → "Database" → "PostgreSQL" (Railway tự cấp
   `DATABASE_URL`).
3. Bật extension pgvector: mở "Query" trong Railway Postgres dashboard, chạy
   `CREATE EXTENSION IF NOT EXISTS vector;` (hoặc để migration tự làm nếu
   quyền cho phép).
4. "Add" → "GitHub Repo" → chọn repo, set "Root Directory" = `backend`.
   Railway tự nhận `Dockerfile` trong đó.
5. Thêm biến môi trường cho service: `GEMINI_API_KEY`, `GOONG_API_KEY`,
   `JWT_SECRET` (tự sinh 1 chuỗi ngẫu nhiên dài), `SENTRY_DSN` (tuỳ chọn).
   `DATABASE_URL` dùng biến tham chiếu `${{Postgres.DATABASE_URL}}` Railway
   cung cấp sẵn khi link 2 service cùng project.
6. Thêm 1 service THỨ HAI cùng repo/thư mục nhưng đổi Start Command thành
   `python -m worker.job_processor` (worker riêng, cùng biến môi trường).
7. Deploy. Kiểm tra: gọi `GET /health` qua domain Railway cấp.

## Sau khi backend chạy — bước 11.2, 11.3 (chỉ áp dụng cho Cách A/B — Cách C đã gộp sẵn ở bước 3-4 phía trên)

- **11.2** Deploy frontend (Vercel/Netlify/Render Static Site/Railway đều
  được — spec mục 2 chỉ định backend, không ép nền tảng frontend): set biến
  môi trường build `VITE_API_URL=<URL backend production>`, build command
  `npm run build` (thư mục `frontend/`), publish thư mục `dist/`.
- **11.3** Trên môi trường production, SSH/exec vào service backend (hoặc
  chạy 1 lần qua Railway/Render shell) rồi chạy đúng thứ tự:
  ```bash
  python scripts/seed_demo_users.py
  python scripts/seed_prompts.py
  python scripts/seed_demo_data.py
  python scripts/seed_historical_exceptions.py
  ```
  Nhắc lại ghi chú ở `scripts/seed_demo_data.py`: chạy lại **ngay trước buổi
  trình bày thật** (không chạy 1 lần rồi để đó) vì giờ các điểm giao tính
  tương đối theo lúc chạy script.

## 11.4, 11.5 — diễn tập + buffer

Việc của bạn lúc trình bày thật, không phải việc code — không có gì để chuẩn
bị thêm ngoài đảm bảo 11.1-11.3 đã xong và ổn định.
