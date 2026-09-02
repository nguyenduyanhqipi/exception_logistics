"""Parse các sheet Excel theo mục 6 TECHNICAL_SPEC.md.

Hàng 1 của mỗi sheet trong `schedule_template.xlsx` là tên cột "máy đọc"
(khớp đúng tên field DB), hàng 2 là nhãn tiếng Việt để người dùng dễ hiểu khi
mở file — phải bỏ qua khi parse dữ liệu thật.
"""
import io
from datetime import date, time
from typing import Any

import pandas as pd

VEHICLE_COLUMNS = [
    "vehicle_id",
    "driver_name",
    "driver_phone",
    "max_payload_kg",
    "cost_per_km",
    "status",
    "vehicle_type",
    "notes",
]

VEHICLE_REQUIRED = ["vehicle_id", "driver_name", "driver_phone", "max_payload_kg"]

STOP_COLUMNS = [
    "vehicle_id",
    "shift_date",
    "shift_label",
    "trip_sequence",
    "depot_arrival_time",
    "depot_loading_duration_min",
    "stop_order",
    "stop_type",
    "stop_address",
    "stop_area",
    "order_id",
    "customer_name",
    "customer_phone",
    "eta",
    "loading_duration_min",
    "sla_deadline",
    "priority_tier",
    "sla_penalty",
    "volume_kg",
    "cargo_type",
    "notes",
]

STOP_REQUIRED = [
    "vehicle_id",
    "shift_date",
    "shift_label",
    "stop_order",
    "stop_type",
    "stop_address",
    "stop_area",
    "order_id",
    "customer_name",
    "customer_phone",
    "eta",
    "sla_deadline",
    "priority_tier",
]


class ExcelValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


# Cột chứa chuỗi số (SĐT, mã đơn...) PHẢI ép kiểu string khi đọc — nếu không,
# pandas tự suy luận thành số và làm mất số 0 đứng đầu (vd '0912000001' -> 912000001).
_TEXT_LIKE_NUMERIC_COLUMNS = {
    "vehicle_id": str,
    "driver_phone": str,
    "customer_phone": str,
    "order_id": str,
    "stop_area": str,
    "shift_label": str,
}


def _read_sheet(file_bytes: bytes, sheet_name: str) -> pd.DataFrame:
    try:
        df = pd.read_excel(
            io.BytesIO(file_bytes),
            sheet_name=sheet_name,
            header=0,
            skiprows=[1],
            engine="openpyxl",
            dtype=_TEXT_LIKE_NUMERIC_COLUMNS,
        )
    except ValueError as exc:
        raise ExcelValidationError([f"Không tìm thấy sheet '{sheet_name}' trong file Excel"]) from exc
    df = df.dropna(how="all")
    return df


def _parse_time_cell(value: Any, row_num: int, col: str, errors: list[str]) -> "time | None":
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, time):
        return value
    if isinstance(value, pd.Timestamp):
        return value.time()
    if isinstance(value, str):
        try:
            parts = value.strip().split(":")
            return time(int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            pass
    errors.append(f"Sheet Ke_hoach_giao_hang, hàng {row_num}, cột {col}: định dạng sai. Cần HH:MM")
    return None


def _parse_date_cell(value: Any, row_num: int, errors: list[str]) -> "date | None":
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, str):
        try:
            d, m, y = value.strip().split("/")
            return date(int(y), int(m), int(d))
        except (ValueError, IndexError):
            pass
    errors.append(f"Sheet Ke_hoach_giao_hang, hàng {row_num}, cột shift_date: định dạng sai. Cần DD/MM/YYYY")
    return None


def parse_vehicle_sheet(file_bytes: bytes) -> tuple[list[dict], list[str]]:
    df = _read_sheet(file_bytes, "Danh_muc_xe")
    errors: list[str] = []
    rows = []
    seen_ids = set()

    for idx, row in df.iterrows():
        row_num = idx + 3  # +1 header hàng 1, +1 label hàng 2, +1 1-indexed
        record = {col: row.get(col) for col in VEHICLE_COLUMNS if col in df.columns}

        for field in VEHICLE_REQUIRED:
            val = record.get(field)
            if val is None or (isinstance(val, float) and pd.isna(val)) or (isinstance(val, str) and not val.strip()):
                errors.append(f"Sheet Danh_muc_xe, hàng {row_num}, cột {field}: không được để trống")

        vehicle_id = record.get("vehicle_id")
        if isinstance(vehicle_id, str):
            vehicle_id = vehicle_id.strip()
            record["vehicle_id"] = vehicle_id
        if vehicle_id in seen_ids:
            errors.append(f"Sheet Danh_muc_xe, hàng {row_num}: vehicle_id '{vehicle_id}' bị trùng trong file")
        elif vehicle_id:
            seen_ids.add(vehicle_id)

        status_val = record.get("status")
        if status_val is None or (isinstance(status_val, float) and pd.isna(status_val)) or not str(status_val).strip():
            record["status"] = "active"
        elif str(status_val).strip() not in ("active", "inactive"):
            errors.append(f"Sheet Danh_muc_xe, hàng {row_num}, cột status: chỉ nhận 'active' hoặc 'inactive'")

        cost_per_km = record.get("cost_per_km")
        if cost_per_km is not None and isinstance(cost_per_km, float) and pd.isna(cost_per_km):
            record["cost_per_km"] = None

        vehicle_type = record.get("vehicle_type")
        if vehicle_type is not None and isinstance(vehicle_type, float) and pd.isna(vehicle_type):
            record["vehicle_type"] = None

        rows.append(record)

    if errors:
        raise ExcelValidationError(errors)
    return rows, errors


def parse_schedule_sheet(file_bytes: bytes) -> tuple[list[dict], list[str]]:
    df = _read_sheet(file_bytes, "Ke_hoach_giao_hang")
    errors: list[str] = []

    for col in ["vehicle_id", "shift_date", "shift_label", "trip_sequence"]:
        if col in df.columns:
            df[col] = df[col].ffill()
    if "trip_sequence" in df.columns:
        df["trip_sequence"] = df["trip_sequence"].apply(lambda v: 1 if pd.isna(v) else int(v))
    else:
        df["trip_sequence"] = 1

    depot_group_seen: set[tuple] = set()
    rows = []

    for idx, row in df.iterrows():
        row_num = idx + 3
        record = {col: row.get(col) for col in STOP_COLUMNS if col in df.columns}

        for field in STOP_REQUIRED:
            val = record.get(field)
            if val is None or (isinstance(val, float) and pd.isna(val)) or (isinstance(val, str) and not val.strip()):
                errors.append(f"Sheet Ke_hoach_giao_hang, hàng {row_num}, cột {field}: không được để trống")

        group_key = (record.get("vehicle_id"), record.get("shift_date"), record.get("shift_label"), record.get("trip_sequence"))
        is_first_of_group = group_key not in depot_group_seen
        if is_first_of_group:
            depot_group_seen.add(group_key)

        depot_arrival = record.get("depot_arrival_time")
        depot_loading = record.get("depot_loading_duration_min")
        has_depot_arrival = not (depot_arrival is None or (isinstance(depot_arrival, float) and pd.isna(depot_arrival)))
        has_depot_loading = not (depot_loading is None or (isinstance(depot_loading, float) and pd.isna(depot_loading)))

        if not is_first_of_group and (has_depot_arrival or has_depot_loading):
            errors.append(
                f"Hàng {row_num}: depot_arrival_time/depot_loading_duration_min chỉ được điền ở hàng đầu tiên của chuyến"
            )
            record["depot_arrival_time"] = None
            record["depot_loading_duration_min"] = None
        else:
            record["depot_arrival_time"] = _parse_time_cell(depot_arrival, row_num, "depot_arrival_time", errors) if has_depot_arrival else None
            record["depot_loading_duration_min"] = int(depot_loading) if has_depot_loading else None

        record["shift_date"] = _parse_date_cell(record.get("shift_date"), row_num, errors)
        record["eta"] = _parse_time_cell(record.get("eta"), row_num, "eta", errors)
        record["sla_deadline"] = _parse_time_cell(record.get("sla_deadline"), row_num, "sla_deadline", errors)

        stop_type = record.get("stop_type")
        if stop_type is None or (isinstance(stop_type, float) and pd.isna(stop_type)) or not str(stop_type).strip():
            record["stop_type"] = "giao_hang"
        elif str(stop_type).strip() not in ("lay_hang", "giao_hang"):
            errors.append(f"Sheet Ke_hoach_giao_hang, hàng {row_num}, cột stop_type: chỉ nhận 'lay_hang' hoặc 'giao_hang'")

        priority_tier = record.get("priority_tier")
        if priority_tier is None or (isinstance(priority_tier, float) and pd.isna(priority_tier)) or not str(priority_tier).strip():
            record["priority_tier"] = "thuong"
        elif str(priority_tier).strip() not in ("thuong", "vip", "hop_dong_phat"):
            errors.append(f"Sheet Ke_hoach_giao_hang, hàng {row_num}, cột priority_tier: chỉ nhận 'thuong'/'vip'/'hop_dong_phat'")

        cargo_type = record.get("cargo_type")
        if cargo_type is None or (isinstance(cargo_type, float) and pd.isna(cargo_type)) or not str(cargo_type).strip():
            record["cargo_type"] = "normal"
        elif str(cargo_type).strip() not in ("normal", "bulky"):
            errors.append(f"Sheet Ke_hoach_giao_hang, hàng {row_num}, cột cargo_type: chỉ nhận 'normal' hoặc 'bulky'")

        for optional_field in ["loading_duration_min", "sla_penalty", "volume_kg", "notes", "depot_address"]:
            val = record.get(optional_field)
            if val is not None and isinstance(val, float) and pd.isna(val):
                record[optional_field] = None

        record["row_num"] = row_num
        rows.append(record)

    seen_stop_orders: dict[tuple, set] = {}
    for r in rows:
        key = (r.get("vehicle_id"), r.get("shift_date"), r.get("shift_label"), r.get("trip_sequence"))
        seen = seen_stop_orders.setdefault(key, set())
        so = r.get("stop_order")
        if so in seen:
            errors.append(f"Hàng {r['row_num']}: stop_order {so} bị trùng trong cùng một chuyến ({r.get('vehicle_id')})")
        else:
            seen.add(so)

    if errors:
        raise ExcelValidationError(errors)
    return rows, errors
