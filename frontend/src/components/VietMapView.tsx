import { useEffect, useRef } from "react";

// VietMap GL JS được nạp bằng thẻ <script> trong index.html (KHÔNG import ở
// đây) — package `@vietmap/vietmap-gl-js@6.0.1` không khai `main`/`module`/
// `exports` mà lại đặt `"sideEffects": false`, nên Vite tree-shake sạch bundle
// UMD nếu import lấy side effect; đã kiểm chứng bằng cách grep bản build.
// Ở đây chỉ đọc lại global mà bundle đó gán vào.

// VietMap GL JS là bản fork của MapLibre GL JS v4.1.2 (đọc trong header file
// dist). Package chỉ ship `export as namespace vietmapgl` (kiểu UMD global) chứ
// không có module typing dùng được, nên khai báo TẠI ĐÂY đúng phần đang dùng —
// hẹp và rõ hơn là ép `any` khắp nơi.
type LngLat = [number, number];
type Bbox = [number, number, number, number];

interface GlMap {
  on(event: string, handler: (e: { lngLat: { lng: number; lat: number } }) => void): void;
  once(event: string, handler: () => void): void;
  remove(): void;
  addSource(id: string, source: unknown): void;
  addLayer(layer: unknown): void;
  getSource(id: string): unknown;
  removeLayer(id: string): void;
  removeSource(id: string): void;
  getLayer(id: string): unknown;
  fitBounds(bounds: [[number, number], [number, number]], opts?: unknown): void;
  isStyleLoaded(): boolean;
  addControl?(control: unknown, position?: string): void;
}

interface GlMarker {
  setLngLat(p: LngLat): GlMarker;
  addTo(map: GlMap): GlMarker;
  remove(): void;
}

interface VietMapGl {
  Map: new (opts: Record<string, unknown>) => GlMap;
  Marker: new (opts?: Record<string, unknown>) => GlMarker;
  NavigationControl: new () => unknown;
}

function gl(): VietMapGl | null {
  // Bundle UMD tự gán vào globalThis lúc import (xem chú thích ở đầu file), nên
  // phải đọc qua global chứ không phải qua giá trị import — TypeScript không
  // biết chuyện đó nên cần ép kiểu qua unknown.
  return (globalThis as unknown as { vietmapgl?: VietMapGl }).vietmapgl ?? null;
}

/** Style URL của Tilemap. Key tilemap BẮT BUỘC nằm ở phía trình duyệt (nó nằm
 *  ngay trong URL mà SDK tải), bảo vệ bằng giới hạn domain/IP trong Console
 *  VietMap — khác hẳn key API của Route v4/Static Map, cái đó giữ ở backend
 *  (xem backend/api/maps.py). */
const STYLE_URL = `https://maps.vietmap.vn/maps/styles/tm/style.json?apikey=${
  import.meta.env.VITE_VIETMAP_TILEMAP_KEY ?? ""
}`;

// 4 mức tắc đường Route v4 trả về (đã xác nhận bằng gọi thật, xem
// backend/core/vietmap.py::CONGESTION_LEVELS).
const CONGESTION_COLOR: Record<string, string> = {
  low: "#16a34a",
  moderate: "#eab308",
  heavy: "#f97316",
  severe: "#dc2626",
};
const CONGESTION_FALLBACK = "#2563eb";

export const CONGESTION_LABEL: Record<string, string> = {
  low: "Thông thoáng",
  moderate: "Hơi đông",
  heavy: "Ùn ứ",
  severe: "Tắc nặng",
};

export type RouteShape = {
  /** `[lng, lat]` — giữ NGUYÊN thứ tự VietMap trả về, cũng là thứ tự GeoJSON. */
  coordinates: LngLat[];
  congestion: { value: string; first: number; last: number }[];
  bbox?: Bbox | null;
};

export type MapMarker = { lngLat: LngLat; color?: string };

interface Props {
  center: LngLat;
  zoom?: number;
  markers?: MapMarker[];
  route?: RouteShape | null;
  /** Bấm vào bản đồ để ghim vị trí. Bỏ trống = bản đồ chỉ để xem. */
  onPick?: (lngLat: LngLat) => void;
  height?: number;
}

const SOURCE_ID = "route";
const LAYER_ID = "route-line";

export function VietMapView({ center, zoom = 14, markers = [], route = null, onPick, height = 360 }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<GlMap | null>(null);
  const markerRefs = useRef<GlMarker[]>([]);
  // Giữ callback trong ref: `map.on("click")` chỉ gắn 1 lần lúc khởi tạo, nếu
  // đóng gói thẳng prop vào listener thì nó dính mãi giá trị của lần render đầu.
  const onPickRef = useRef(onPick);
  onPickRef.current = onPick;

  // Khởi tạo bản đồ ĐÚNG 1 LẦN. Mỗi lần tạo lại là một loạt tile-request mới,
  // mà hạn mức Tilemap chỉ 10 lệnh/phút (thấp hơn hẳn mọi API khác của VietMap).
  useEffect(() => {
    const vm = gl();
    if (!vm || !containerRef.current || mapRef.current) return;
    const map = new vm.Map({
      container: containerRef.current,
      style: STYLE_URL,
      center,
      zoom,
    });
    map.addControl?.(new vm.NavigationControl(), "top-right");
    mapRef.current = map;

    if (onPickRef.current) {
      map.on("click", (e) => onPickRef.current?.([e.lngLat.lng, e.lngLat.lat]));
    }

    // Chống bắn tile liên tục khi kéo/phóng nhanh: gộp các sự kiện dồn dập
    // trong 400ms thành 1 lần "camera đã ổn định". Không khoá camera (user chốt
    // giữ zoom/pan tự do), nhưng đây là lớp an toàn rẻ tiền cho trần 10/phút.
    let settleTimer: number | undefined;
    const onSettle = () => {
      window.clearTimeout(settleTimer);
      settleTimer = window.setTimeout(() => {
        /* camera đã ổn định — chưa cần làm gì thêm, tile do SDK tự quản. */
      }, 400);
    };
    map.on("moveend", onSettle);
    map.on("zoomend", onSettle);

    return () => {
      window.clearTimeout(settleTimer);
      map.remove();
      mapRef.current = null;
    };
    // Cố ý KHÔNG phụ thuộc center/zoom: đó là vị trí BAN ĐẦU, đổi chúng không
    // được phép dựng lại cả bản đồ.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Marker: xoá hết rồi vẽ lại — số marker ở đây luôn rất nhỏ (xe + điểm đến),
  // so khớp từng cái để cập nhật tại chỗ chỉ làm code khó đọc hơn mà không
  // nhanh hơn đáng kể.
  useEffect(() => {
    const vm = gl();
    const map = mapRef.current;
    if (!vm || !map) return;
    markerRefs.current.forEach((m) => m.remove());
    markerRefs.current = markers.map((m) =>
      new vm.Marker({ color: m.color ?? "#2563eb" }).setLngLat(m.lngLat).addTo(map),
    );
  }, [markers]);

  // Vẽ tuyến, tô màu THEO TỪNG ĐOẠN của `congestion[]`.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const draw = () => {
      if (map.getLayer(LAYER_ID)) map.removeLayer(LAYER_ID);
      if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID);
      if (!route || route.coordinates.length < 2) return;

      map.addSource(SOURCE_ID, { type: "geojson", data: toCongestionGeoJson(route) });
      map.addLayer({
        id: LAYER_ID,
        type: "line",
        source: SOURCE_ID,
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-width": 6, "line-color": ["get", "color"] },
      });
      if (route.bbox) {
        const [minLng, minLat, maxLng, maxLat] = route.bbox;
        map.fitBounds(
          [
            [minLng, minLat],
            [maxLng, maxLat],
          ],
          { padding: 48, duration: 600 },
        );
      }
    };

    // Không thêm source/layer trước khi style tải xong, SDK sẽ ném lỗi.
    //
    // `once` chứ không phải `on`: effect này chạy lại mỗi lần đổi tuyến, dùng
    // `on` là mỗi lần lại gắn thêm 1 listener "load" nữa và không bao giờ gỡ —
    // sau vài lần bấm đổi tuyến là mỗi sự kiện load kéo theo cả chồng lần vẽ.
    if (map.isStyleLoaded()) draw();
    else map.once("load", draw);
  }, [route]);

  if (!gl()) {
    return <div className="error-banner">Không tải được thư viện bản đồ VietMap.</div>;
  }
  return (
    <div>
      <div ref={containerRef} style={{ height, borderRadius: 8, overflow: "hidden" }} />
      {onPick && <span className="hint">Bấm vào bản đồ để ghim vị trí xe.</span>}
    </div>
  );
}

/** Cắt tuyến thành nhiều LineString theo mức tắc để tô được nhiều màu trên
 *  cùng 1 layer.
 *
 *  `first`/`last` của `congestion[]` là CHỈ SỐ vào mảng `coordinates` (không
 *  phải mét/giây) — `last + 1` để 2 đoạn liền nhau dùng chung 1 điểm, nếu
 *  không tuyến vẽ ra sẽ đứt quãng ngay tại mỗi ranh giới đổi màu. */
function toCongestionGeoJson(route: RouteShape) {
  const segments = route.congestion.length
    ? route.congestion
    : [{ value: "", first: 0, last: route.coordinates.length - 1 }];
  return {
    type: "FeatureCollection",
    features: segments
      .map((seg) => ({
        type: "Feature",
        properties: {
          color: CONGESTION_COLOR[seg.value] ?? CONGESTION_FALLBACK,
          level: seg.value,
        },
        geometry: {
          type: "LineString",
          coordinates: route.coordinates.slice(seg.first, seg.last + 1),
        },
      }))
      .filter((f) => f.geometry.coordinates.length >= 2),
  };
}
