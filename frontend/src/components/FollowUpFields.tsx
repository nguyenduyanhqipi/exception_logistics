import { CUSTOMER_REQUEST_SUGGESTION, visibleFollowUps, type FollowUpField } from "../exceptionForm";
import { LocationPicker } from "./LocationPicker";
import { subTypeLabel } from "../labels";

// Render các câu hỏi phụ của 1 answer_key. Dùng CHUNG cho form tạo
// (NewException.tsx) và form sửa (EditException.tsx) — trước đây mỗi form tự
// viết tay JSX cho từng câu hỏi (depot_on_time, has_injury, EXTRA_FIELD), thêm
// 1 câu hỏi là phải sửa đúng 2 chỗ và rất dễ quên 1 chỗ. Nay danh sách câu hỏi
// nằm hết ở exceptionForm.ts::FOLLOW_UPS, component này chỉ vẽ.
//
// `answers` giữ giá trị ĐÚNG KIỂU sẽ gửi lên backend (number/boolean/string),
// KHÔNG phải chuỗi của ô input — để form không phải ép kiểu lại lúc submit và
// để `showWhen` so sánh được bằng `===` với true/false thật.

type Props = {
  answerKey: string;
  answers: Record<string, unknown>;
  onChange: (key: string, value: unknown) => void;
};

export function FollowUpFields({ answerKey, answers, onChange }: Props) {
  const fields = visibleFollowUps(answerKey, answers);
  if (fields.length === 0) return null;
  return (
    <>
      {fields.map((f) => (
        <div className="form-field" key={f.key}>
          <label>
            {f.label}
            {f.optional && <span className="hint"> (không bắt buộc)</span>}
          </label>
          {/* "location" ghi 3 field một lúc (địa chỉ + lat + lng) nên không đi
              qua FollowUpInput — cái đó chỉ biết 1 key. Gọi onChange nhiều lần
              là an toàn: cả 2 form đều setState kiểu hàm nên các patch cộng dồn. */}
          {f.type === "location" ? (
            <LocationPicker
              address={typeof answers.current_address === "string" ? answers.current_address : ""}
              lat={typeof answers.current_lat === "number" ? answers.current_lat : null}
              lng={typeof answers.current_lng === "number" ? answers.current_lng : null}
              onChange={(patch) => {
                for (const [k, v] of Object.entries(patch)) onChange(k, v);
              }}
            />
          ) : (
            <FollowUpInput field={f} value={answers[f.key]} onChange={(v) => onChange(f.key, v)} />
          )}
          {f.hint && <span className="hint">{f.hint}</span>}
        </div>
      ))}
      <CustomerRequestHint request={answers.customer_request} />
    </>
  );
}

// Khách vắng mặt nhưng liên lạc được và nói rõ muốn gì -> ngoại lệ này thực chất
// là "đổi giờ"/"đổi địa điểm"/"huỷ đơn", không phải "khách vắng mặt". Backend
// tính sẵn `suggested_sub_type` (rule_engine.classify_sub_type) nhưng KHÔNG trả
// ra response, nên gợi ý sẽ không bao giờ tới được dispatcher nếu chỉ dựa vào
// đó — hiện ngay tại form lúc đang nhập còn đúng lúc hơn: chưa gửi đi đã sửa
// được, không phải tạo xong rồi vào sửa lại.
function CustomerRequestHint({ request }: { request: unknown }) {
  if (typeof request !== "string") return null;
  if (!(request in CUSTOMER_REQUEST_SUGGESTION)) return null;
  const suggested = CUSTOMER_REQUEST_SUGGESTION[request];
  return (
    <div className="form-field">
      <div className="hint" style={{ background: "#fffbeb", color: "#92400e", padding: "8px 10px", borderRadius: 6 }}>
        {suggested ? (
          <>
            Khách đã nói rõ yêu cầu — cân nhắc chọn lại loại ngoại lệ{" "}
            <strong>&ldquo;{subTypeLabel(suggested)}&rdquo;</strong> (nhóm &ldquo;Khách đổi yêu cầu&rdquo;) để hệ
            thống đề xuất đúng hướng xử lý. Vẫn giữ &ldquo;Khách vắng mặt&rdquo; cũng được nếu bạn thấy hợp lý hơn.
          </>
        ) : (
          <>
            Đơn đã chắc chắn huỷ thì không cần tạo ngoại lệ — vào trang{" "}
            <strong>Xe &amp; Kế hoạch</strong> xoá điểm giao đó khỏi chuyến là xong.
          </>
        )}
      </div>
    </div>
  );
}

function FollowUpInput({
  field,
  value,
  onChange,
}: {
  field: FollowUpField;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  if (field.type === "number") {
    return (
      <input
        type="number"
        min={0}
        // value === undefined -> ô rỗng. KHÔNG dùng `value ?? ""` với số 0 vì 0
        // là câu trả lời hợp lệ (trễ 0 phút) và `??` giữ đúng 0, nhưng viết rõ
        // ra đây để lần sau không ai đổi nhầm sang `||`.
        value={value === undefined || value === null ? "" : String(value)}
        onFocus={(e) => e.target.select()}
        onChange={(e) => onChange(e.target.value === "" ? undefined : Number(e.target.value))}
      />
    );
  }

  if (field.type === "boolean") {
    return (
      <div className="radio-group">
        <label className={`radio-option ${value === true ? "selected" : ""}`}>
          <input type="radio" checked={value === true} onChange={() => onChange(true)} />
          Có
        </label>
        <label className={`radio-option ${value === false ? "selected" : ""}`}>
          <input type="radio" checked={value === false} onChange={() => onChange(false)} />
          Không
        </label>
      </div>
    );
  }

  return (
    <div className="radio-group">
      {(field.options ?? []).map((opt) => (
        <label key={opt.key} className={`radio-option ${value === opt.key ? "selected" : ""}`}>
          <input type="radio" checked={value === opt.key} onChange={() => onChange(opt.key)} />
          {opt.label}
        </label>
      ))}
    </div>
  );
}
