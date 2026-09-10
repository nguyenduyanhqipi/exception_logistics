import { localToday } from "../exceptionForm";

// Bộ chọn kỳ báo cáo dùng CHUNG cho cả trang (đợt code 5, Pha 5).
//
// Mọi kỳ đều quy về đúng 1 giá trị `anchor` (một ngày bất kỳ NẰM TRONG kỳ) —
// backend tự suy ra đầu/cuối kỳ (api/reports.py::resolve_period). Nhờ vậy 5
// loại kỳ dùng chung một tham số, và "tuần" không phải hỏi "tuần số mấy" (đếm
// tuần ISO là thứ gần như không ai nhẩm được).

export type PeriodType = "day" | "week" | "month" | "quarter" | "year";

export const PERIOD_TABS: { key: PeriodType; label: string }[] = [
  { key: "day", label: "Ngày" },
  { key: "week", label: "Tuần" },
  { key: "month", label: "Tháng" },
  { key: "quarter", label: "Quý" },
  { key: "year", label: "Năm" },
];

/** Nhãn của kỳ CON khi bấm "Xem chi tiết theo ..." — tuần/tháng chia theo ngày,
 *  quý/năm chia theo tháng (xem api/reports.py::sub_buckets). */
export function subPeriodLabel(type: PeriodType): string | null {
  if (type === "week" || type === "month") return "ngày";
  if (type === "quarter" || type === "year") return "tháng";
  return null;
}

function ymd(anchor: string) {
  const [y, m, d] = anchor.split("-").map(Number);
  return { y, m, d };
}

function build(y: number, m: number, d: number) {
  const last = new Date(y, m, 0).getDate();
  const day = Math.min(d, last);
  return `${y}-${String(m).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

/** Thứ 2 → CN của tuần chứa `anchor`, hiện ngay dưới ô chọn để người dùng xác
 *  nhận trước khi bấm xem — chọn 1 ngày rồi đoán xem hệ thống hiểu tuần nào là
 *  chỗ dễ hiểu nhầm nhất của cả bộ lọc. */
function weekRangeText(anchor: string): string {
  const d = new Date(anchor + "T00:00:00");
  if (Number.isNaN(d.getTime())) return "";
  const monday = new Date(d);
  monday.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);
  const f = (x: Date) => `${String(x.getDate()).padStart(2, "0")}/${String(x.getMonth() + 1).padStart(2, "0")}`;
  return `→ Tuần từ Thứ 2 ${f(monday)} đến CN ${f(sunday)}/${sunday.getFullYear()}`;
}

interface Props {
  type: PeriodType;
  anchor: string;
  onAnchorChange: (anchor: string) => void;
  /** Kỳ so sánh dùng lại đúng component này, chỉ khác nhãn. */
  title?: string;
}

export function PeriodPicker({ type, anchor, onAnchorChange, title }: Props) {
  const { y, m, d } = ymd(anchor || localToday());
  const years = Array.from({ length: 6 }, (_, i) => new Date().getFullYear() - i);

  return (
    <div className="form-field" style={{ minWidth: 260 }}>
      {title && <label>{title}</label>}

      {(type === "day" || type === "week") && (
        <>
          <input type="date" value={anchor} onChange={(e) => onAnchorChange(e.target.value)} />
          {type === "week" && <span className="hint">{weekRangeText(anchor)}</span>}
          {type === "week" && <span className="hint">Chọn 1 ngày bất kỳ trong tuần muốn xem.</span>}
        </>
      )}

      {type === "month" && (
        <div style={{ display: "flex", gap: 8 }}>
          <select value={m} onChange={(e) => onAnchorChange(build(y, Number(e.target.value), 1))}>
            {Array.from({ length: 12 }, (_, i) => i + 1).map((mm) => (
              <option key={mm} value={mm}>
                Tháng {mm}
              </option>
            ))}
          </select>
          <select value={y} onChange={(e) => onAnchorChange(build(Number(e.target.value), m, 1))}>
            {years.map((yy) => (
              <option key={yy} value={yy}>
                {yy}
              </option>
            ))}
          </select>
        </div>
      )}

      {type === "quarter" && (
        <div style={{ display: "flex", gap: 8 }}>
          {/* Gửi lên backend vẫn là 1 ngày trong quý (tháng đầu quý) — backend
              không cần biết khái niệm "quý số mấy" từ phía client. */}
          <select
            value={Math.floor((m - 1) / 3) + 1}
            onChange={(e) => onAnchorChange(build(y, (Number(e.target.value) - 1) * 3 + 1, 1))}
          >
            {[1, 2, 3, 4].map((q) => (
              <option key={q} value={q}>
                Quý {q}
              </option>
            ))}
          </select>
          <select value={y} onChange={(e) => onAnchorChange(build(Number(e.target.value), m, 1))}>
            {years.map((yy) => (
              <option key={yy} value={yy}>
                {yy}
              </option>
            ))}
          </select>
        </div>
      )}

      {type === "year" && (
        <select value={y} onChange={(e) => onAnchorChange(build(Number(e.target.value), 1, 1))}>
          {years.map((yy) => (
            <option key={yy} value={yy}>
              Năm {yy}
            </option>
          ))}
        </select>
      )}

      <input type="hidden" value={d} readOnly />
    </div>
  );
}
