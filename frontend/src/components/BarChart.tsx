// Biểu đồ cột SVG tối giản cho trang Báo cáo (đợt code 5, Pha 5).
//
// Tự vẽ thay vì thêm thư viện chart: cả trang chỉ cần đúng 1 dạng biểu đồ (cột,
// nhóm hoặc chồng) — kéo về recharts/chart.js là thêm ~150KB vào bundle cho
// đúng một hình. SVG thuần cũng in ra PDF/ảnh chụp báo cáo sắc nét hơn canvas.
//
// Một component dùng cho CẢ 3 nhu cầu trong thiết kế:
// - 1 series               -> cột đơn (số ngoại lệ theo ngày/tháng)
// - nhiều series, stacked  -> cột chồng ("tách theo loại", 5 nhóm ngoại lệ)
// - nhiều series, grouped  -> cột đôi (chế độ so sánh Kỳ A / Kỳ B)

export type ChartSeries = { label: string; color: string; values: number[] };

interface Props {
  categories: string[];
  series: ChartSeries[];
  /** true = cột chồng lên nhau; false = các cột đứng cạnh nhau. */
  stacked?: boolean;
  height?: number;
  /** Định dạng số khi hiện tooltip/nhãn trục (vd tiền tệ, %, phút). */
  format?: (value: number) => string;
}

const CHART_WIDTH = 720;
const PAD_LEFT = 52;
const PAD_BOTTOM = 34;
const PAD_TOP = 12;

export function BarChart({ categories, series, stacked = false, height = 220, format }: Props) {
  const fmt = format ?? ((v: number) => String(Math.round(v * 100) / 100));
  const plotH = height - PAD_BOTTOM - PAD_TOP;
  const plotW = CHART_WIDTH - PAD_LEFT - 8;

  // Trần trục Y: cột chồng thì so theo TỔNG của mỗi cột, cột nhóm thì so theo
  // giá trị lớn nhất của từng series — dùng nhầm là cột tràn ra ngoài khung.
  const columnTotals = categories.map((_, i) =>
    stacked ? series.reduce((s, ser) => s + (ser.values[i] ?? 0), 0) : Math.max(...series.map((ser) => ser.values[i] ?? 0)),
  );
  const rawMax = Math.max(0, ...columnTotals);
  // Dữ liệu toàn số 0 (kỳ chưa có ngoại lệ nào) vẫn phải vẽ ra khung trống chứ
  // không chia cho 0.
  const max = rawMax > 0 ? rawMax : 1;

  const slot = plotW / Math.max(categories.length, 1);
  const barWidth = stacked ? Math.min(38, slot * 0.6) : Math.min(30, (slot * 0.7) / series.length);

  if (categories.length === 0) return <p className="drill-muted">Chưa có dữ liệu để vẽ.</p>;

  return (
    <div style={{ overflowX: "auto" }}>
      <svg viewBox={`0 0 ${CHART_WIDTH} ${height}`} style={{ width: "100%", minWidth: 420 }} role="img">
        {/* 3 đường lưới ngang + nhãn giá trị */}
        {[0, 0.5, 1].map((t) => {
          const y = PAD_TOP + plotH * (1 - t);
          return (
            <g key={t}>
              <line x1={PAD_LEFT} y1={y} x2={CHART_WIDTH - 8} y2={y} stroke="#e5e7eb" strokeWidth={1} />
              <text x={PAD_LEFT - 6} y={y + 4} textAnchor="end" fontSize={10} fill="#6b7280">
                {fmt(max * t)}
              </text>
            </g>
          );
        })}

        {categories.map((cat, i) => {
          const slotX = PAD_LEFT + slot * i;
          let stackTop = PAD_TOP + plotH;
          return (
            <g key={cat + i}>
              {series.map((ser, s) => {
                const value = ser.values[i] ?? 0;
                const h = (value / max) * plotH;
                const x = stacked
                  ? slotX + (slot - barWidth) / 2
                  : slotX + (slot - barWidth * series.length) / 2 + barWidth * s;
                const y = stacked ? stackTop - h : PAD_TOP + plotH - h;
                if (stacked) stackTop -= h;
                return (
                  <rect key={ser.label} x={x} y={y} width={barWidth} height={Math.max(h, value > 0 ? 1 : 0)} fill={ser.color} rx={2}>
                    <title>{`${cat} · ${ser.label}: ${fmt(value)}`}</title>
                  </rect>
                );
              })}
              {/* Nhãn trục X: bỏ bớt khi quá dày (tháng 31 ngày) để không chồng chữ */}
              {(categories.length <= 16 || i % Math.ceil(categories.length / 16) === 0) && (
                <text x={slotX + slot / 2} y={height - 12} textAnchor="middle" fontSize={10} fill="#6b7280">
                  {cat}
                </text>
              )}
            </g>
          );
        })}
        <line x1={PAD_LEFT} y1={PAD_TOP + plotH} x2={CHART_WIDTH - 8} y2={PAD_TOP + plotH} stroke="#9ca3af" />
      </svg>

      {series.length > 1 && (
        <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginTop: 4 }}>
          {series.map((ser) => (
            <span key={ser.label} className="hint" style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <span style={{ width: 12, height: 12, borderRadius: 2, background: ser.color }} />
              {ser.label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
