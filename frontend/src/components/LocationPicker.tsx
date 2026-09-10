import { useMemo, useState } from "react";
import { VietMapView } from "./VietMapView";

// Ô nhập "Vị trí xe hiện tại" của `road_closed` và `major_breakdown`
// (exceptionForm.ts::FOLLOW_UPS, type "location").
//
// Ghi 3 field cùng lúc: `current_address` (chữ, để đọc) + `current_lat`/
// `current_lng` (toạ độ, để tìm đường và tìm xe thay thế gần nhất). Địa chỉ
// chữ KHÔNG thay được toạ độ: "Km12 QL1A" tra ra cả chục điểm khác nhau, mà
// Route v4 thì chỉ nhận toạ độ.

// Trung tâm Hà Nội — chỉ dùng làm điểm mở bản đồ khi CHƯA ghim gì. Không phải
// giá trị mặc định của field: chưa bấm thì `current_lat/lng` vẫn để trống, vì
// một toạ độ bịa còn tệ hơn không có toạ độ (backend sẽ vẽ tuyến từ chỗ xe
// không hề đứng).
const DEFAULT_CENTER: [number, number] = [105.8542, 21.0285];

interface Props {
  address: string;
  lat: number | null;
  lng: number | null;
  onChange: (patch: { current_address?: string; current_lat?: number; current_lng?: number }) => void;
}

export function LocationPicker({ address, lat, lng, onChange }: Props) {
  // Bản đồ tương tác chỉ mở khi người dùng bấm: hạn mức Tilemap của VietMap là
  // 10 lệnh/phút, thấp hơn hẳn mọi API khác — tự mở sẵn cho mọi ngoại lệ là
  // cách nhanh nhất để chạm trần rồi tile trắng giữa lúc đang nhập liệu.
  const [showMap, setShowMap] = useState(false);
  const pinned = lat !== null && lng !== null;
  // Xem chú thích cùng loại ở RoutePanel: mảng marker phải ổn định theo giá trị,
  // không phải mảng literal mới mỗi lần render.
  const markers = useMemo(
    () => (pinned ? [{ lngLat: [lng!, lat!] as [number, number], color: "#dc2626" }] : []),
    [pinned, lat, lng],
  );

  return (
    <div>
      <input
        type="text"
        value={address}
        placeholder="VD: Km12 QL1A, đoạn qua Thường Tín"
        onChange={(e) => onChange({ current_address: e.target.value })}
      />
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 6 }}>
        <button type="button" className="secondary" onClick={() => setShowMap((v) => !v)}>
          {showMap ? "Đóng bản đồ" : pinned ? "Chỉnh vị trí trên bản đồ" : "Chọn trên bản đồ"}
        </button>
        {pinned ? (
          <span className="hint">
            Đã ghim: {lat!.toFixed(5)}, {lng!.toFixed(5)}
          </span>
        ) : (
          <span className="hint">Chưa ghim toạ độ — thiếu toạ độ thì không gợi ý được tuyến thay thế.</span>
        )}
      </div>

      {showMap && (
        <div style={{ marginTop: 8 }}>
          <VietMapView
            center={pinned ? [lng!, lat!] : DEFAULT_CENTER}
            zoom={pinned ? 15 : 12}
            markers={markers}
            height={320}
            // VietMap GL JS dùng [lng, lat]; input_context lưu lat/lng riêng —
            // đổi thứ tự ĐÚNG TẠI ĐÂY, một chỗ duy nhất.
            onPick={([pickedLng, pickedLat]) =>
              onChange({ current_lat: pickedLat, current_lng: pickedLng })
            }
          />
        </div>
      )}
    </div>
  );
}
