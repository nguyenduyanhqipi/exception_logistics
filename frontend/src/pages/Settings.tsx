import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { apiClient, apiErrorMessage } from "../api/client";

interface CompanySettings {
  company_id: string;
  name: string;
  timezone: string;
  ranking_weights: { cost: number; time: number; sla_risk: number };
  default_depot_address: string | null;
  default_depot_area: string | null;
  default_cost_per_km: number;
}

export function Settings() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["settings"],
    queryFn: async () => (await apiClient.get<CompanySettings>("/api/settings")).data,
  });

  const [cost, setCost] = useState("");
  const [time, setTime] = useState("");
  const [slaRisk, setSlaRisk] = useState("");
  const [depotAddress, setDepotAddress] = useState("");
  const [depotArea, setDepotArea] = useState("");
  const [costPerKm, setCostPerKm] = useState("");
  const [weightsError, setWeightsError] = useState<string | null>(null);
  const [weightsSaved, setWeightsSaved] = useState(false);
  const [depotError, setDepotError] = useState<string | null>(null);
  const [depotSaved, setDepotSaved] = useState(false);

  useEffect(() => {
    if (!data) return;
    setCost(String(data.ranking_weights.cost));
    setTime(String(data.ranking_weights.time));
    setSlaRisk(String(data.ranking_weights.sla_risk));
    setDepotAddress(data.default_depot_address ?? "");
    setDepotArea(data.default_depot_area ?? "");
    setCostPerKm(String(data.default_cost_per_km));
  }, [data]);

  async function handleSaveWeights(e: FormEvent) {
    e.preventDefault();
    setWeightsError(null);
    setWeightsSaved(false);
    try {
      await apiClient.put("/api/settings/weights", { cost: Number(cost), time: Number(time), sla_risk: Number(slaRisk) });
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      setWeightsSaved(true);
    } catch (err) {
      setWeightsError(apiErrorMessage(err));
    }
  }

  async function handleSaveDepot(e: FormEvent) {
    e.preventDefault();
    setDepotError(null);
    setDepotSaved(false);
    try {
      await apiClient.put("/api/settings/depot", {
        default_depot_address: depotAddress || null,
        default_depot_area: depotArea || null,
        default_cost_per_km: costPerKm ? Number(costPerKm) : null,
      });
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      setDepotSaved(true);
    } catch (err) {
      setDepotError(apiErrorMessage(err));
    }
  }

  if (isLoading || !data) return <div className="loading-spinner">Đang tải...</div>;

  const weightsSum = (Number(cost) || 0) + (Number(time) || 0) + (Number(slaRisk) || 0);

  return (
    <div className="page">
      <h1>Cài đặt hệ thống</h1>

      <form onSubmit={handleSaveWeights} className="card">
        <h2>Trọng số xếp hạng phương án</h2>
        <p style={{ color: "#6b7280", fontSize: 13 }}>Tổng 3 trọng số phải bằng 1.0. Thay đổi ảnh hưởng đến lần phân tích ngoại lệ tiếp theo.</p>
        {weightsError && <div className="error-banner">{weightsError}</div>}
        {weightsSaved && <div className="success-banner">Đã lưu trọng số.</div>}
        <div style={{ display: "flex", gap: 16 }}>
          <div className="form-field" style={{ flex: 1 }}>
            <label>Chi phí (cost)</label>
            <input type="number" step="0.05" min={0} max={1} value={cost} onChange={(e) => { setCost(e.target.value); setWeightsSaved(false); }} />
          </div>
          <div className="form-field" style={{ flex: 1 }}>
            <label>Thời gian (time)</label>
            <input type="number" step="0.05" min={0} max={1} value={time} onChange={(e) => { setTime(e.target.value); setWeightsSaved(false); }} />
          </div>
          <div className="form-field" style={{ flex: 1 }}>
            <label>Rủi ro SLA (sla_risk)</label>
            <input type="number" step="0.05" min={0} max={1} value={slaRisk} onChange={(e) => { setSlaRisk(e.target.value); setWeightsSaved(false); }} />
          </div>
        </div>
        <p style={{ fontSize: 13, color: Math.abs(weightsSum - 1) > 0.01 ? "#991b1b" : "#6b7280" }}>Tổng hiện tại: {weightsSum.toFixed(2)}</p>
        <button type="submit" className="primary">Lưu trọng số</button>
      </form>

      <form onSubmit={handleSaveDepot} className="card">
        <h2>Kho trung chuyển mặc định</h2>
        {depotError && <div className="error-banner">{depotError}</div>}
        {depotSaved && <div className="success-banner">Đã lưu.</div>}
        <div className="form-field">
          <label>Địa chỉ kho mặc định</label>
          <input value={depotAddress} onChange={(e) => { setDepotAddress(e.target.value); setDepotSaved(false); }} />
        </div>
        <div className="form-field">
          <label>Khu vực kho mặc định</label>
          <input value={depotArea} onChange={(e) => { setDepotArea(e.target.value); setDepotSaved(false); }} />
        </div>
        <div className="form-field">
          <label>Chi phí/km dự phòng (VNĐ) — dùng khi xe chưa có giá riêng</label>
          <input type="number" min={0} value={costPerKm} onChange={(e) => { setCostPerKm(e.target.value); setDepotSaved(false); }} />
        </div>
        <button type="submit" className="primary">Lưu cài đặt kho</button>
      </form>
    </div>
  );
}
