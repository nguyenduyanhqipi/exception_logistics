from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from middleware.auth import get_current_user
from middleware.tenant import get_db
from models import BackgroundJob

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{job_id}/status")
def get_job_status(
    job_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.get(BackgroundJob, job_id)
    if job is None or str(job.company_id) != current_user["company_id"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Không tìm thấy job {job_id}")

    return {
        "job_id": str(job.job_id),
        "job_type": job.job_type,
        "status": job.status,
        "result": job.result,
        "error": job.error,
    }
