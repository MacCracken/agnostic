"""Report generation, download, and scheduling endpoints."""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from shared.audit import AuditAction, audit_log
from webgui.auth import Permission
from webgui.routes.dependencies import get_current_user, require_permission

logger = logging.getLogger(__name__)

router = APIRouter()

_REPORTS_DIR = Path("/app/reports").resolve()


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------


class ReportGenerateRequest(BaseModel):
    session_id: str
    report_type: str = "executive_summary"
    format: str = "json"


class ScheduleReportRequest(BaseModel):
    report_type: str
    format: str
    schedule: dict


class ScheduleReportResponse(BaseModel):
    job_id: str
    name: str
    next_run: str | None


# ---------------------------------------------------------------------------
# Report endpoints
# ---------------------------------------------------------------------------


@router.get("/reports")
async def list_reports(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    from config.environment import config

    redis_client = config.get_redis_client()
    user_id = user.get("user_id", "")
    # Use SCAN instead of KEYS to avoid blocking Redis
    pattern = f"report:*:{user_id}:*"
    matched_keys: list[str] = []
    cursor = 0
    while True:
        cursor, batch = redis_client.scan(cursor=cursor, match=pattern, count=200)
        matched_keys.extend(batch)
        if cursor == 0:
            break
    # Fetch all values in one round-trip with MGET
    reports = []
    if matched_keys:
        values = redis_client.mget(matched_keys)
        for data in values:
            if data:
                reports.append(json.loads(data))
    total = len(reports)
    return {
        "items": reports[offset : offset + limit],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/reports/generate")
async def generate_report(
    req: ReportGenerateRequest,
    user: dict = Depends(require_permission(Permission.REPORTS_GENERATE)),
):
    from webgui.exports import ReportFormat, ReportRequest, ReportType, report_generator

    try:
        report_type = ReportType(req.report_type)
        report_format = ReportFormat(req.format)
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid report type or format: {e}"
        ) from e

    report_req = ReportRequest(
        session_id=req.session_id,
        report_type=report_type,
        format=report_format,
    )
    metadata = await report_generator.generate_report(report_req, user["user_id"])
    audit_log(
        AuditAction.REPORT_GENERATED,
        actor=user.get("user_id"),
        resource_type="report",
        resource_id=metadata.report_id,
    )
    return {
        "report_id": metadata.report_id,
        "generated_at": metadata.generated_at.isoformat(),
        "session_id": metadata.session_id,
        "report_type": metadata.report_type.value,
        "format": metadata.format.value,
        "file_size": metadata.file_size,
    }


@router.get("/reports/{report_id}/download")
async def download_report(
    report_id: str,
    user: dict = Depends(get_current_user),
):
    from config.environment import config

    redis_client = config.get_redis_client()
    meta_data = redis_client.get(f"report:{report_id}:meta")
    if not meta_data:
        raise HTTPException(status_code=404, detail="Report not found")

    meta = json.loads(meta_data)
    file_path = meta.get("file_path")
    if not file_path:
        raise HTTPException(status_code=404, detail="Report file not found")

    # Prevent path traversal: ensure file is inside the reports directory
    resolved = Path(file_path).resolve()
    if not resolved.is_relative_to(_REPORTS_DIR):
        logger.warning(
            "Path traversal attempt blocked for report %s: %s", report_id, file_path
        )
        raise HTTPException(status_code=403, detail="Access denied")

    if not resolved.exists():
        raise HTTPException(status_code=404, detail="Report file not found on disk")

    audit_log(
        AuditAction.REPORT_DOWNLOADED,
        actor=user.get("user_id"),
        resource_type="report",
        resource_id=report_id,
    )

    return FileResponse(
        path=str(resolved),
        filename=resolved.name,
        media_type="application/octet-stream",
    )


# ---------------------------------------------------------------------------
# Scheduled report endpoints
# ---------------------------------------------------------------------------


@router.get("/reports/scheduled")
async def get_scheduled_reports(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    from webgui.scheduled_reports import scheduled_report_manager

    jobs = scheduled_report_manager.get_jobs()
    total = len(jobs)
    return {
        "items": jobs[offset : offset + limit],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/reports/scheduled")
async def schedule_report(
    req: ScheduleReportRequest,
    user: dict = Depends(require_permission(Permission.REPORTS_GENERATE)),
):
    from webgui.scheduled_reports import scheduled_report_manager

    try:
        job_id = await scheduled_report_manager.schedule_custom_report(
            report_type=req.report_type,
            format=req.format,
            schedule=req.schedule,
            report_name=f"{req.report_type} by {user['user_id']}",
            tenant_id=user.get("tenant_id"),
        )

        audit_log(
            AuditAction.REPORT_SCHEDULED,
            actor=user.get("user_id"),
            resource_type="report",
            resource_id=job_id,
        )

        jobs = scheduled_report_manager.get_jobs()
        job = next((j for j in jobs if j["id"] == job_id), None)

        return {
            "job_id": job_id,
            "name": job["name"] if job else req.report_type,
            "next_run": job["next_run"] if job else None,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Failed to schedule report: {e}")
        raise HTTPException(status_code=500, detail="Failed to schedule report") from e


@router.delete("/reports/scheduled/{job_id}")
async def delete_scheduled_report(
    job_id: str,
    user: dict = Depends(require_permission(Permission.REPORTS_GENERATE)),
):
    from webgui.scheduled_reports import scheduled_report_manager

    if scheduled_report_manager.remove_job(job_id):
        audit_log(
            AuditAction.REPORT_SCHEDULE_REMOVED,
            actor=user.get("user_id"),
            resource_type="report",
            resource_id=job_id,
        )
        return {"status": "deleted", "job_id": job_id}
    raise HTTPException(status_code=404, detail="Job not found")
