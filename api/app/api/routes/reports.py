import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from app.api.deps import DbSession, ProfileMemberAccess
from app.models.enums import AuditAction
from app.schemas.report import CareReport, ReportRequest
from app.services.ai_provider import AIProvider, get_ai_provider
from app.services.audit import add_audit_entry
from app.services.reports import build_care_report, render_report_pdf

router = APIRouter()
AIProviderDep = Annotated[AIProvider, Depends(get_ai_provider)]


def _audit_state(report: CareReport) -> dict:
    return {
        "period": {
            "start_date": report.period.start_date.isoformat(),
            "end_date": report.period.end_date.isoformat(),
            "timezone": report.period.timezone,
        }
    }


@router.post("/{care_profile_id}/reports/preview", response_model=CareReport)
async def preview_report(
    care_profile_id: UUID,
    payload: ReportRequest,
    db: DbSession,
    access: ProfileMemberAccess,
    provider: AIProviderDep,
) -> CareReport:
    report = await build_care_report(
        db=db,
        profile=access.profile,
        request=payload,
        provider=provider,
    )
    add_audit_entry(
        db,
        care_profile_id=access.profile.id,
        actor_user_id=access.membership.user_id,
        action=AuditAction.REPORT_PREVIEW_GENERATED,
        target_type="care_report",
        target_id=None,
        after_state=_audit_state(report),
    )
    db.commit()
    return report


@router.post("/{care_profile_id}/reports/pdf")
async def export_report_pdf(
    care_profile_id: UUID,
    payload: ReportRequest,
    db: DbSession,
    access: ProfileMemberAccess,
    provider: AIProviderDep,
) -> Response:
    report = await build_care_report(
        db=db,
        profile=access.profile,
        request=payload,
        provider=provider,
    )
    pdf = render_report_pdf(report)
    add_audit_entry(
        db,
        care_profile_id=access.profile.id,
        actor_user_id=access.membership.user_id,
        action=AuditAction.REPORT_PDF_GENERATED,
        target_type="care_report",
        target_id=None,
        after_state=_audit_state(report),
    )
    db.commit()
    safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", report.care_profile.name).strip("-")
    filename = f"CareRelay-{safe_name or 'care-report'}-{report.period.end_date}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
        },
    )
