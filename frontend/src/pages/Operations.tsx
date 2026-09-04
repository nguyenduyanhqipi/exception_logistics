import { useSearchParams } from "react-router-dom";
import { UploadPanel } from "../components/UploadPanel";
import { VehicleList } from "../components/VehicleList";
import { ScheduleForm } from "./ScheduleInput";

// Trang "Xe & Kế hoạch" — gộp 2 mục nav cũ "Nhập kế hoạch" (ScheduleInput) và
// "Upload Excel" (ExcelUpload) làm một (2026-09-04). Cả 2 đều là việc chuẩn bị
// dữ liệu đầu vào trước ca chạy, tách 2 mục nav chỉ làm thanh nav dài thêm.
//
// Tab lưu trong query string (`?tab=`) chứ không phải state cục bộ, để 2 route
// cũ /schedules/new và /excel-upload redirect thẳng vào đúng tab được (xem
// App.tsx) — trong code còn nhiều chỗ trỏ tới 2 đường dẫn đó.

type Tab = "vehicles" | "schedules";

const TABS: { key: Tab; label: string }[] = [
  { key: "vehicles", label: "Danh mục xe" },
  { key: "schedules", label: "Nhập kế hoạch" },
];

export function Operations() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab: Tab = searchParams.get("tab") === "schedules" ? "schedules" : "vehicles";

  function selectTab(next: Tab) {
    setSearchParams({ tab: next }, { replace: true });
  }

  return (
    <div className="page">
      <h1>Xe &amp; Kế hoạch</h1>
      <div className="filters">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            className={tab === t.key ? "primary" : "secondary"}
            onClick={() => selectTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* `key` ép UploadPanel dựng lại khi đổi tab — nếu không, file đã chọn và
          thông báo lỗi/thành công của tab trước còn dính sang tab sau. */}
      <UploadPanel key={tab} kind={tab} />

      {tab === "vehicles" && <VehicleList />}
      {tab === "schedules" && (
        <>
          <h2>Nhập kế hoạch thủ công</h2>
          <ScheduleForm />
        </>
      )}
    </div>
  );
}
