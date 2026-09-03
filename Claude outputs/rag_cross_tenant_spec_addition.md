## 20. RAG — Kho case dùng chung (cross-tenant), ẩn danh hoá theo pseudonymization

> **Quyết định (2026-09-03, trao đổi với founder ngoài phiên code):** đổi RAG từ mô hình mặc định
> ngầm định trong mục 1/4 (mỗi công ty tự tích luỹ case của riêng mình, cô lập tuyệt đối theo
> `company_id` như mọi bảng khác) sang **kho case dùng chung giữa mọi công ty khách hàng**, đã ẩn
> danh hoá — để RAG có giá trị ngay từ những tháng đầu thay vì mỗi công ty phải tự chờ tích luỹ
> ~200 case riêng. Đánh đổi: phải xây thêm 1 tầng ẩn danh hoá + kiểm soát truy vết, tăng độ phức tạp
> so với thiết kế per-tenant thuần tuý. Mục này ghi lại đầy đủ thiết kế, thay thế mô tả ngắn gọn cũ
> ở mục 1 ("RAG — schema sẵn, kích hoạt sau ~200 trường hợp") và bổ sung cho bảng `exception_embeddings`
> ở mục 4.

### 20.0 Vì sao cross-tenant thay vì per-tenant

Per-tenant (mặc định ngầm định trước đây, đi theo đúng nguyên tắc "mọi bảng đều company_id" ở mục 4):
an toàn tuyệt đối, dễ giải thích với khách hàng B2B ("dữ liệu công ty bạn không đi đâu cả"), nhưng
RAG chỉ có giá trị sau khi MỘT công ty tự tích luỹ đủ ~200 case — với công ty quy mô 30-70 xe
(~150 ngoại lệ/tháng theo ước tính ở tài liệu thương mại hoá), mất khoảng 1-2 tháng mới có RAG hữu ích,
và công ty quy mô nhỏ hơn có thể mất cả năm.

Cross-tenant: kho case cộng dồn từ MỌI công ty đã đồng ý chia sẻ → ngưỡng ~200 case đạt được ở
**cấp độ toàn nền tảng**, nhanh hơn nhiều (chỉ cần vài công ty pilot hoạt động vài tuần là đủ) — đồng
thời RAG càng nhiều khách hàng dùng càng khôn hơn cho TẤT CẢ khách hàng (network effect thật, không
chỉ là lời quảng cáo suông trong tài liệu thương mại hoá).

Đổi lại: bắt buộc phải ẩn danh hoá tới mức không công ty nào — kể cả đội vận hành nội bộ — đọc được
case đó thuộc công ty nào/khách hàng nào/ngày nào khi dùng ở luồng RAG bình thường, chỉ có thể tra
ngược qua 1 kênh riêng có kiểm soát chặt (mục 20.3).

### 20.1 Schema

```sql
-- Thay thế bảng exception_embeddings ở mục 4 (giữ tên bảng cũ nếu muốn, nhưng đổi hẳn nội dung/nguyên
-- tắc: KHÔNG còn là "1 dòng = 1 exception_id trực tiếp", mà là kho case đã qua lọc + ẩn danh hoá)
rag_case_bank (
  case_id UUID PK,                        -- id mới, KHÔNG suy ra được từ exception_id gốc
  exception_group TEXT,
  sub_type TEXT,
  severity TEXT,
  area_bucket TEXT,                       -- LẤY TỪ stops.area / exceptions.area (quận/huyện) —
                                           -- TUYỆT ĐỐI không lấy từ address (số nhà, tên đường)
  shift_label TEXT,                       -- ca_sang/ca_chieu/ca_dem — KHÔNG lấy shift_date thật
  time_to_deadline_bucket TEXT,           -- '<30p' / '30-90p' / '>90p' — KHÔNG lấy eta/sla_deadline
                                           -- thật (giờ:phút chính xác + ngày tháng dễ giúp suy ngược)
  downstream_stops_affected INT,
  has_priority_order BOOLEAN,
  cargo_type TEXT,
  volume_kg_bucket TEXT,                  -- vd 'nhẹ(<50kg)'/'vừa(50-200kg)'/'nặng(>200kg)' — không
                                           -- lưu số kg chính xác (số lẻ dễ khớp ngược 1 đơn cụ thể)
  notes_redacted TEXT,                    -- description/notes sau khi chạy qua bộ lọc redact (mục 20.2)
  option_cost_estimate DECIMAL,
  option_time_estimate_minutes INT,
  option_sla_risk_remaining DECIMAL,
  outcome_delivered_on_time BOOLEAN,
  outcome_cost_variance_pct DECIMAL,      -- (actual_cost - cost_estimate)/cost_estimate — TỶ LỆ,
                                           -- không lưu actual_cost tuyệt đối (số tiền tuyệt đối dễ
                                           -- gợi ý quy mô/đơn hàng cụ thể hơn tỷ lệ %)
  embedding VECTOR(768),
  admitted_at TIMESTAMPTZ                 -- thời điểm case được NẠP vào kho chung — cố ý lệch so với
                                           -- reported_at thật (xem mục 20.2, trễ nạp có chủ đích)
)

-- Bảng ánh xạ truy vết — TÁCH RIÊNG HOÀN TOÀN khỏi mọi query của option_generator/ranker/RAG retrieval.
-- Không JOIN bảng này ở bất kỳ đường code nào ngoài luồng tra vết 2 người mục 20.3.
-- company_id/exception_id lưu Ở DẠNG MÃ HOÁ (application-level, AES-256-GCM) — không phải plaintext
-- như bản thảo trước, vì bây giờ không ai (kể cả 1 mình founder) được đọc trực tiếp nữa.
rag_case_source_map (
  case_id UUID PK FK→rag_case_bank,
  company_id_encrypted BYTEA,       -- mã hoá bằng khoá K = K1 XOR K2 (mục 20.3) — vô nghĩa nếu
                                     -- không kết hợp đủ 2 nửa khoá
  exception_id_encrypted BYTEA,
  mapped_at TIMESTAMPTZ
)

-- Yêu cầu tra vết — bắt buộc 2 người khác nhau: 1 người khởi tạo, 1 người khác phê duyệt
-- (four-eyes principle) TRƯỚC khi khoá K1/K2 được ghép lại để giải mã.
rag_trace_requests (
  request_id UUID PK,
  case_id UUID FK→rag_case_bank,
  requested_by UUID FK→users,
  reason TEXT,                      -- bắt buộc — vd "khách hàng X khiếu nại rò dữ liệu, case liên
                                     -- quan tới report demo ngày Y"
  approved_by UUID FK→users NULLABLE,  -- CHECK (approved_by IS NULL OR approved_by != requested_by)
  status TEXT DEFAULT 'pending',    -- 'pending','approved','rejected','completed'
  requested_at TIMESTAMPTZ,
  approved_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ          -- lúc kết quả giải mã đã được xem — nên tự xoá kết quả hiển thị
                                     -- sau 1 lần xem/hết phiên, không lưu lại bản giải mã ở đâu khác
)

-- companies cần thêm cờ đồng ý chia sẻ dữ liệu — mặc định FALSE (opt-in, không phải opt-out)
ALTER TABLE companies ADD COLUMN rag_data_sharing_consent BOOLEAN DEFAULT false;
-- Quy tắc đơn giản nhất để tránh "ăn ké": company chưa bật consent thì option_generator KHÔNG
-- truy vấn rag_case_bank cho company đó (không được hưởng gợi ý từ case người khác nếu bản thân
-- không đóng góp case của mình) — quyết định kinh doanh cụ thể (có nên cho dùng miễn phí để dụ bật
-- consent hay không) để leader/Thắm quyết ở phần thương mại hoá, đây chỉ là chỗ cần 1 cột boolean.
```

### 20.2 Pipeline ẩn danh hoá (chạy trong background job, KHÔNG đồng bộ lúc dispatcher xác nhận quyết định)

1. Trigger: sau khi `outcomes` được ghi nhận cho 1 `decision` (tức đã có đủ input + quyết định +
   kết quả thật — case "trọn vẹn" mới đáng đưa vào kho, case dở dang không nạp).
2. Trễ nạp có chủ đích (`admitted_at` lệch `reported_at`): nạp vào `rag_case_bank` sau một khoảng
   trễ ngẫu nhiên (vài ngày đến vài tuần, cấu hình được) thay vì ngay lập tức — giảm khả năng ai đó
   đối chiếu "hôm nay công ty X báo bận rộn ở khu Y, đúng lúc kho chung xuất hiện case mới ở khu Y"
   để suy ngược.
3. Redact `description`/`notes` tự do (`notes_redacted`): chạy qua bước lọc loại bỏ số điện thoại
   (regex số VN), tên riêng (so khớp với `customer_name`/`driver_name` của chính case đó — loại bỏ
   nếu xuất hiện y nguyên trong text tự do), địa chỉ cụ thể (so khớp với `address` của case đó).
   Không dùng LLM để "diễn giải lại" toàn bộ ghi chú (rủi ro bịa thêm chi tiết) — chỉ xoá/thay thế
   token trùng khớp.
4. **Ngưỡng k-anonymity trước khi nhận case vào kho:** với tổ hợp
   `(exception_group, sub_type, area_bucket, shift_label)`, nếu kho hiện có ít hơn N case khác cùng
   tổ hợp này (N mặc định = 5, cấu hình qua `rule_versions` như các ngưỡng khác trong hệ thống) →
   generalize `area_bucket` thêm 1 bậc (quận/huyện → toàn thành phố) trước khi nạp, thay vì nạp thẳng
   một case "hiếm" dễ bị soi ra. Đây là bước bắt buộc, không phải tuỳ chọn — chỉ ẩn tên/địa chỉ mà
   không kiểm soát độ hiếm của tổ hợp còn lại vẫn có thể bị suy ngược qua tương quan.

### 20.3 Truy vết — khoá tách 2 người (dual control), không ai một mình tra được

**Nguyên tắc:** vẫn là pseudonymization (dữ liệu về nguyên tắc có thể định danh ngược, khác
anonymization tuyệt đối — xem đánh đổi ở cuối mục này), nhưng **không một cá nhân đơn lẻ nào —
kể cả founder — có đủ khả năng tự giải mã một mình**. Cần cả 2 điều kiện độc lập cùng xảy ra:

1. **Tách khoá mã hoá (kỹ thuật):** khoá đối xứng `K` dùng để mã hoá `company_id`/`exception_id` trong
   `rag_case_source_map` KHÔNG được lưu nguyên vẹn ở bất kỳ đâu trong hệ thống đang chạy. `K` sinh 1
   lần lúc thiết lập bằng `K = K1 XOR K2` (secret sharing 2-của-2 đơn giản, không cần thư viện Shamir
   phức tạp vì chỉ cần đúng 2 người): `K1` do founder giữ (vd trong password manager cá nhân, không
   đưa vào `.env`/server), `K2` do 1 người thứ hai được chỉ định trước giữ (vd kỹ thuật trưởng) —
   không ai giữ cả 2 nửa, và không nửa nào tự nó tiết lộ được gì về `K`.
2. **Phê duyệt chéo (quy trình, bảng `rag_trace_requests`):** người khởi tạo yêu cầu (`requested_by`)
   PHẢI khác người phê duyệt (`approved_by`, ràng buộc CHECK ở schema) — chỉ khi cả 2 người cùng nhập
   đúng nửa khoá của mình vào 1 công cụ giải mã riêng (tách khỏi ứng dụng chính, không phải 1 API công
   khai) thì `K` mới được ghép tạm thời trong bộ nhớ để giải mã ĐÚNG 1 case đang yêu cầu, không giải mã
   hàng loạt. Giải mã xong không lưu lại bản rõ ở đâu (không ghi vào DB, không log ra file) — chỉ hiển
   thị 1 lần cho 2 người cùng xem tại thời điểm đó.

Với đúng 2 người trong đội (founder + 1 người), về bản chất đây là "cả 2 cùng có mặt và đồng ý mới
mở được", không khác gì 2 chìa khoá phải xoay cùng lúc — không ai một mình chủ động tra cứu tuỳ tiện
được nữa, kể cả chính founder.

- Quyền tạo/phê duyệt `rag_trace_requests` KHÔNG gắn với role `manager` hiện có (role này scope theo
  1 company, còn tra vết cần vượt company) — cần 1 khái niệm quyền mới ở cấp nền tảng, tạm gọi
  `platform_admin`, **cấp cho tối thiểu 2 người cụ thể** (không phải 1), tách biệt khỏi CHECK
  constraint `role IN ('dispatcher','manager')` của bảng `users` hiện tại.
- Mọi request (kể cả bị từ chối) ghi vào `audit_logs` (action mới: `'rag_trace_lookup'`, `detail` gồm
  `case_id`, `requested_by`, `approved_by`, `reason`, `status`) — đúng nguyên tắc audit log đã có sẵn
  trong `Definition of Done` (mục 18).
- **Vẫn cần nêu đúng thuật ngữ pseudonymization** (không phải ẩn danh tuyệt đối) trong hợp đồng
  mẫu/chính sách bảo mật (chi phí pháp lý đã có ở tài liệu thương mại hoá, mục 3.1/8) — cơ chế 2
  người làm giảm rủi ro 1 cá nhân lạm quyền, nhưng không đổi bản chất pháp lý: dữ liệu vẫn được xem
  là có thể định danh ngược (2 người cộng lại vẫn tra được), nên khách hàng vẫn cần được thông báo và
  đồng ý rõ ràng.
- **Đánh đổi cần biết:** nếu 1 trong 2 người giữ khoá rời đội/mất khoá vĩnh viễn (nghỉ việc không bàn
  giao, quên mật khẩu password manager...) thì KHÔNG AI khôi phục lại được khả năng tra vết — kể cả
  founder. Cần có quy trình bàn giao khoá rõ ràng khi đổi nhân sự giữ `K2`, không thể chỉ đổi mật khẩu
  tài khoản như thông thường.

### 20.4 Cập nhật ngưỡng kích hoạt (mục 1)

Mục 1 hiện ghi: *"RAG (schema sẵn, kích hoạt sau ~200 trường hợp)"* — cập nhật thành: *"RAG — kho
case dùng chung cross-tenant đã ẩn danh hoá (mục 20), kích hoạt khi `rag_case_bank` đạt ~200 case
CỘNG DỒN TOÀN NỀN TẢNG (không phải 200 case/công ty) — company chỉ được truy vấn kho chung nếu đã
bật `rag_data_sharing_consent`."*

---

*Ghi chú thêm vào changelog cuối file: "v5.5 — Bổ sung mục 20: RAG đổi từ per-tenant (ngầm định) sang
kho case dùng chung cross-tenant, ẩn danh hoá qua pseudonymization (redact PII/địa chỉ/thời gian
thật, bucket hoá các biến định lượng, ngưỡng k-anonymity tối thiểu 5 case/tổ hợp trước khi nạp kho,
trễ nạp có chủ đích) + bảng ánh xạ truy vết MÃ HOÁ với khoá tách 2 người (dual control — không ai
một mình giải mã được, kể cả founder, cần đúng 2 người phê duyệt chéo qua `rag_trace_requests`) +
quyền `platform_admin` mới ở cấp nền tảng (không phải cấp company), cấp cho tối thiểu 2 người + cờ
`companies.rag_data_sharing_consent`. Quyết định đổi hướng 2026-09-03 sau khi rà lại mâu thuẫn giữa
mục 1 (RAG kích hoạt sau ~200 case) và thực tế mỗi company tự tích luỹ riêng sẽ quá chậm để có giá
trị thương mại sớm; cơ chế khoá tách 2 người được chọn sau khi cân nhắc giữa pseudonymization 1
người giữ khoá (rủi ro lạm quyền) và ẩn danh tuyệt đối không ai tra được (mất khả năng xử lý khiếu
nại/yêu cầu xoá dữ liệu của khách hàng)."*
