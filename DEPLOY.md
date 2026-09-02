# Deploy — Giai đoạn 11

Chuẩn bị sẵn (Dockerfile, Procfile, render.yaml). Phần còn lại cần tài khoản
Railway/Render thật của bạn — không tự làm được, ghi rõ từng bước dưới đây.

## Lưu ý quan trọng: pgvector

Bảng `exception_embeddings` dùng cột kiểu `VECTOR` (pgvector). Cả Railway và
Render đều hỗ trợ pgvector trên Postgres managed, nhưng cách bật khác nhau
theo thời điểm/gói dịch vụ — **kiểm tra lại tài liệu chính thức của nhà cung
cấp tại thời điểm bạn deploy** trước khi chọn, vì thông tin này có thể đã đổi.
Alembic migration `a1b2c3d4e5f6` đã có sẵn `CREATE EXTENSION IF NOT EXISTS
vector` — nếu Postgres managed đó cho phép superuser tạo extension, mọi việc
tự động; nếu không, cần bật qua dashboard/CLI của nhà cung cấp trước khi chạy
migration.

## Cách A — Render (dùng `render.yaml` có sẵn)

1. Đăng nhập Render, "New +" → "Blueprint" → chọn repo GitHub của project này.
2. Render tự đọc `render.yaml` ở gốc repo → tạo sẵn: 1 Postgres DB, 1 web
   service (API), 1 worker service (background jobs) — đúng theo mục 16
   "worker chạy riêng, không chung tiến trình với API".
3. Điền 3 biến môi trường còn thiếu (đánh dấu `sync: false` trong
   `render.yaml`, Render sẽ hỏi khi tạo) cho CẢ web lẫn worker:
   `GEMINI_API_KEY`, `GOOGLE_MAPS_API_KEY`, `SENTRY_DSN` (Sentry để trống nếu
   chưa dùng). `DATABASE_URL`/`JWT_SECRET` đã tự sinh.
4. Deploy. Kiểm tra: `curl https://<tên-service>.onrender.com/health` trả
   `{"status":"ok"}`.

## Cách B — Railway

Railway không dùng file blueprint kiểu `render.yaml` — làm qua dashboard/CLI:

1. `railway login` (cần trình duyệt để xác thực tài khoản Railway của bạn).
2. Tạo project mới, "Add" → "Database" → "PostgreSQL" (Railway tự cấp
   `DATABASE_URL`).
3. Bật extension pgvector: mở "Query" trong Railway Postgres dashboard, chạy
   `CREATE EXTENSION IF NOT EXISTS vector;` (hoặc để migration tự làm nếu
   quyền cho phép).
4. "Add" → "GitHub Repo" → chọn repo, set "Root Directory" = `backend`.
   Railway tự nhận `Dockerfile` trong đó.
5. Thêm biến môi trường cho service: `GEMINI_API_KEY`, `GOOGLE_MAPS_API_KEY`,
   `JWT_SECRET` (tự sinh 1 chuỗi ngẫu nhiên dài), `SENTRY_DSN` (tuỳ chọn).
   `DATABASE_URL` dùng biến tham chiếu `${{Postgres.DATABASE_URL}}` Railway
   cung cấp sẵn khi link 2 service cùng project.
6. Thêm 1 service THỨ HAI cùng repo/thư mục nhưng đổi Start Command thành
   `python worker/job_processor.py` (worker riêng, cùng biến môi trường).
7. Deploy. Kiểm tra: gọi `GET /health` qua domain Railway cấp.

## Sau khi backend chạy — bước 11.2, 11.3

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
