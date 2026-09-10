import { useMemo, useState } from "react";
import { apiClient, apiErrorMessage } from "../api/client";
import { formatVnd } from "./OutcomeForm";
import { CONGESTION_LABEL, VietMapView, type RouteShape } from "./VietMapView";

// Khối "Vị trí & tuyến thay thế" trên trang chi tiết ngoại lệ (đợt code 5,
// Pha 4 — map_routing_feature.md).
//
// CHỈ hiện cho 2 sub_type thật sự cần: `road_closed` (phải né đoạn đang chặn)
// và `major_breakdown` (xe thay thế phải tới đúng chỗ xe hỏng). Các sub_type
// khác không hỏi vị trí xe lúc nhập nên cũng không có gì để vẽ.
export const MAP_SUB_TYPES = ["road_closed", "major_breakdown"];

type ApiPath = {
  distance_m: number | null;
  duration_min: number;
  toll_cost: number | null;
  coordinates: [number, number][];
  bbox: [number, number, number, number] | null;
  congestion: { value: string; first: number; last: number }[];
};

type RoutesResponse = {
  origin: { lat: number; lng: number; address: string | null };
  destination: { lat: number; lng: number; address: string | null; order_id: string | null };
  paths: ApiPath[];
};

/** Nhãn gợi ý cho từng tuyến, theo đúng tiêu chí đã chốt trong thiết kế:
 *  nhanh nhất = `time` thấp nhất; rẻ nhất = quãng đường ngắn nhất cộng phí trạm;
 *  còn lại = "cân bằng". Chỉ là GỢI Ý — dispatcher tự chọn, vì `avoid` của
 *  Route v4 không né được đúng đoạn đang bị chặn nên chỉ người nhìn bản đồ mới
 *  biết tuyến nào thực sự đi vòng qua được. */
function pathLabels(paths: ApiPath[]): string[] {
  if (paths.length === 0) return [];
  let fastest = 0;
  let cheapest = 0;
  paths.forEach((p, i) => {
    if (p.duration_min < paths[fastest].duration_min) fastest = i;
    const cost = (p.distance_m ?? 0) + (p.toll_cost ?? 0);
    const best = (paths[cheapest].distance_m ?? 0) + (paths[cheapest].toll_cost ?? 0);
    if (cost < best) cheapest = i;
  });
  return paths.map((_, i) => {
    const tags: string[] = [];
    if (i === fastest) tags.push("Nhanh nhất");
    if (i === cheapest) tags.push("Rẻ nhất");
    return tags.length ? tags.join(" · ") : "Cân bằng";
  });
}

export function RoutePanel({ exceptionId, subType }: { exceptionId: string; subType: string }) {
  const [data, setData] = useState<RoutesResponse | null>(null);
  const [selected, setSelected] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!MAP_SUB_TYPES.includes(subType)) return null;

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.get<RoutesResponse>(`/api/maps/exceptions/${exceptionId}/routes`);
      setData(res.data);
      setSelected(0);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  // Mảng marker phải ỔN ĐỊNH giữa các lần render: VietMapView so sánh nó bằng
  // tham chiếu, mảng literal mới mỗi lần render sẽ khiến marker bị xoá và vẽ
  // lại liên tục (nháy, và tốn công vô ích).
  const markers = useMemo(
    () =>
      data
        ? [
            { lngLat: [data.origin.lng, data.origin.lat] as [number, number], color: "#dc2626" },
            { lngLat: [data.destination.lng, data.destination.lat] as [number, number], color: "#16a34a" },
          ]
        : [],
    [data],
  );
  const labels = data ? pathLabels(data.paths) : [];
  const current = data?.paths[selected];
  const route: RouteShape | null = current
    ? { coordinates: current.coordinates, congestion: current.congestion, bbox: current.bbox }
    : null;

  return (
    <div className="card">
      <h2 style={{ marginTop: 0 }}>Vị trí &amp; tuyến thay thế</h2>

      {!data && (
        <>
          <p className="drill-muted" style={{ marginTop: 0 }}>
            Xem vị trí xe trên bản đồ và các tuyến đi tới điểm giao kế tiếp, có tô màu mức độ tắc đường theo từng
            đoạn.
          </p>
          <button type="button" className="primary" disabled={loading} onClick={load}>
            {loading ? "Đang tìm tuyến..." : "Xem bản đồ & tuyến đi"}
          </button>
        </>
      )}
      {error && <div className="error-banner">{error}</div>}

      {data && (
        <>
          <dl className="drill-dl">
            <div>
              <dt>Vị trí xe</dt>
              <dd>{data.origin.address || `${data.origin.lat.toFixed(5)}, ${data.origin.lng.toFixed(5)}`}</dd>
            </div>
            <div>
              <dt>Điểm giao kế tiếp</dt>
              <dd>
                {data.destination.address ?? "-"}
                {data.destination.order_id && <span className="drill-muted"> · {data.destination.order_id}</span>}
              </dd>
            </div>
          </dl>

          <div className="radio-group" style={{ marginBottom: 10 }}>
            {data.paths.map((p, i) => (
              <label key={i} className={`radio-option ${selected === i ? "selected" : ""}`}>
                <input type="radio" checked={selected === i} onChange={() => setSelected(i)} />
                <span>
                  <strong>{labels[i]}</strong>
                  <span className="drill-muted">
                    {" "}
                    · {((p.distance_m ?? 0) / 1000).toFixed(1)} km · {p.duration_min} phút
                    {p.toll_cost ? ` · phí trạm ${formatVnd(p.toll_cost)}` : " · không phí trạm"}
                  </span>
                </span>
              </label>
            ))}
          </div>

          {current && (
            <>
              <VietMapView
                center={[data.origin.lng, data.origin.lat]}
                zoom={13}
                markers={markers}
                route={route}
                height={380}
              />
              <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginTop: 8 }}>
                {Object.entries(CONGESTION_LABEL).map(([level, label]) => (
                  <span key={level} className="hint" style={{ display: "flex", alignItems: "center", gap: 5 }}>
                    <span
                      style={{
                        width: 14,
                        height: 4,
                        borderRadius: 2,
                        background: { low: "#16a34a", moderate: "#eab308", heavy: "#f97316", severe: "#dc2626" }[
                          level
                        ],
                      }}
                    />
                    {label}
                  </span>
                ))}
              </div>
              <p className="hint" style={{ marginTop: 8 }}>
                Tuyến trên chỉ là gợi ý của bản đồ — hệ thống KHÔNG né được đúng đoạn đang bị chặn, hãy tự xem lại
                tuyến trước khi báo cho tài xế.
              </p>
            </>
          )}
        </>
      )}
    </div>
  );
}
