from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.excel_parser import ExcelValidationError, parse_vehicle_sheet
from middleware.auth import get_current_user
from middleware.tenant import get_db
from models import AuditLog, Vehicle
from schemas.vehicle import VehicleCreate, VehicleResponse, VehicleUpdate

router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])


def _write_audit_log(db: Session, current_user: dict, action: str, entity_id: str, detail: dict):
    db.add(
        AuditLog(
            company_id=current_user["company_id"],
            user_id=current_user["user_id"],
            action=action,
            entity_type="vehicle",
            entity_id=None,
            detail={"vehicle_id": entity_id, **detail},
        )
    )


@router.get("", response_model=list[VehicleResponse])
def list_vehicles(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.execute(select(Vehicle).order_by(Vehicle.vehicle_id)).scalars().all()
    return rows


@router.post("", response_model=VehicleResponse, status_code=status.HTTP_201_CREATED)
def create_vehicle(
    payload: VehicleCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # `vehicle_id` là PK TOÀN CỤC (không composite theo company_id, xem mục 4) —
    # 1 vehicle_id chỉ thuộc về đúng 1 công ty trong toàn hệ thống. `db.get()`
    # thường bị tenant filter (with_loader_criteria, database.py) ẩn mất các
    # dòng của công ty KHÁC — nếu dùng `db.get()` trần ở đây, xe công ty khác
    # sẽ coi như "chưa tồn tại", code chạy tiếp xuống INSERT rồi vỡ ràng buộc
    # PK ở tầng DB (IntegrityError 500 thay vì 400 sạch sẽ — bug thật đã tái
    # hiện và xác nhận bằng test HTTP). Phải chủ động `skip_tenant_filter` để
    # thấy được xe của MỌI công ty khi kiểm tra trùng PK toàn cục.
    existing = db.get(Vehicle, payload.vehicle_id, execution_options={"skip_tenant_filter": True})
    if existing is not None:
        # Dù xe thuộc công ty KHÁC vẫn phải chặn (insert cùng PK sẽ vỡ ràng
        # buộc) — chỉ khác ở NỘI DUNG thông báo lỗi, tránh nói sai là "công ty
        # bạn đã có xe này" khi thực ra là xe của công ty khác.
        if str(existing.company_id) == current_user["company_id"]:
            detail = f"Xe {payload.vehicle_id} đã tồn tại"
        else:
            detail = f"Mã xe {payload.vehicle_id} đã được công ty khác sử dụng, vui lòng chọn mã khác"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    vehicle = Vehicle(company_id=current_user["company_id"], **payload.model_dump())
    db.add(vehicle)
    db.flush()
    _write_audit_log(db, current_user, "create_vehicle", vehicle.vehicle_id, payload.model_dump(mode="json"))
    db.commit()
    db.refresh(vehicle)
    return vehicle


@router.put("/{vehicle_id}", response_model=VehicleResponse)
def update_vehicle(
    vehicle_id: str,
    payload: VehicleUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None or str(vehicle.company_id) != current_user["company_id"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Không tìm thấy xe {vehicle_id}")

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(vehicle, field, value)

    _write_audit_log(db, current_user, "update_vehicle", vehicle_id, {k: str(v) for k, v in changes.items()})
    db.commit()
    db.refresh(vehicle)
    return vehicle


@router.post("/upload")
async def upload_vehicles(
    file: UploadFile,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    content = await file.read()
    try:
        rows, _ = parse_vehicle_sheet(content)
    except ExcelValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"errors": exc.errors})

    created, updated = 0, 0
    for record in rows:
        vehicle_id = record["vehicle_id"]
        # Cùng lý do như create_vehicle ở trên: PHẢI skip_tenant_filter để
        # phát hiện đúng vehicle_id đã thuộc công ty khác, tránh INSERT trùng
        # PK toàn cục rồi vỡ ràng buộc DB (500) thay vì báo lỗi rõ ràng (400).
        vehicle = db.get(Vehicle, vehicle_id, execution_options={"skip_tenant_filter": True})
        if vehicle is None:
            vehicle = Vehicle(company_id=current_user["company_id"], vehicle_id=vehicle_id)
            db.add(vehicle)
            created += 1
        else:
            if str(vehicle.company_id) != current_user["company_id"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Xe {vehicle_id} thuộc công ty khác",
                )
            updated += 1

        vehicle.driver_name = record["driver_name"]
        vehicle.driver_phone = record["driver_phone"]
        vehicle.max_payload_kg = record["max_payload_kg"]
        vehicle.cost_per_km = record.get("cost_per_km")
        vehicle.status = record.get("status", "active")
        vehicle.vehicle_type = record.get("vehicle_type")

    _write_audit_log(db, current_user, "upload_vehicles", "-", {"created": created, "updated": updated})
    db.commit()
    return {"created": created, "updated": updated, "total": len(rows)}


@router.delete("/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle(
    vehicle_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None or str(vehicle.company_id) != current_user["company_id"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Không tìm thấy xe {vehicle_id}")

    vehicle.status = "inactive"
    _write_audit_log(db, current_user, "delete_vehicle", vehicle_id, {})
    db.commit()
    return None
