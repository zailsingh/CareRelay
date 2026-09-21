from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, ProfileMemberAccess, ProfileSubjectAccess
from app.models.wellbeing import WellbeingCheckin, WellbeingSymptom
from app.schemas.wellbeing import (
    CheckinReporter,
    WellbeingCheckinCreate,
    WellbeingCheckinRead,
    WellbeingCheckinUpdate,
    WellbeingSummary,
)
from app.services.wellbeing_summary import calculate_wellbeing_summary

router = APIRouter()


def normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Date-time filters must include a timezone offset",
        )
    return value.astimezone(UTC)


def checkin_read(checkin: WellbeingCheckin) -> WellbeingCheckinRead:
    return WellbeingCheckinRead(
        id=checkin.id,
        care_profile_id=checkin.care_profile_id,
        reported_by_user_id=checkin.reported_by_user_id,
        reported_by=CheckinReporter.model_validate(checkin.reported_by),
        score=checkin.score,
        occurred_at=checkin.occurred_at,
        symptoms=[symptom.kind for symptom in checkin.symptoms],
        note=checkin.note,
        voice_transcript=checkin.voice_transcript,
        created_at=checkin.created_at,
        updated_at=checkin.updated_at,
    )


def get_checkin_or_404(
    db: DbSession,
    care_profile_id: UUID,
    checkin_id: UUID,
) -> WellbeingCheckin:
    checkin = db.scalar(
        select(WellbeingCheckin)
        .options(
            selectinload(WellbeingCheckin.reported_by),
            selectinload(WellbeingCheckin.symptoms),
        )
        .where(
            WellbeingCheckin.id == checkin_id,
            WellbeingCheckin.care_profile_id == care_profile_id,
        )
    )
    if checkin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Check-in not found")
    return checkin


@router.post(
    "/{care_profile_id}/wellbeing-checkins",
    response_model=WellbeingCheckinRead,
    status_code=status.HTTP_201_CREATED,
)
def create_checkin(
    care_profile_id: UUID,
    payload: WellbeingCheckinCreate,
    db: DbSession,
    access: ProfileSubjectAccess,
) -> WellbeingCheckinRead:
    checkin = WellbeingCheckin(
        care_profile_id=access.profile.id,
        reported_by_user_id=access.membership.user_id,
        reported_by=access.membership.user,
        score=payload.score,
        occurred_at=payload.occurred_at.astimezone(UTC),
        note=payload.note or None,
        voice_transcript=payload.voice_transcript or None,
        symptoms=[WellbeingSymptom(kind=kind) for kind in payload.symptoms],
    )
    db.add(checkin)
    db.commit()
    db.refresh(checkin)
    return checkin_read(checkin)


@router.get(
    "/{care_profile_id}/wellbeing-checkins",
    response_model=list[WellbeingCheckinRead],
)
def list_checkins(
    care_profile_id: UUID,
    db: DbSession,
    access: ProfileMemberAccess,
    start_at: Annotated[datetime | None, Query()] = None,
    end_at: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[WellbeingCheckinRead]:
    query = (
        select(WellbeingCheckin)
        .options(
            selectinload(WellbeingCheckin.reported_by),
            selectinload(WellbeingCheckin.symptoms),
        )
        .where(WellbeingCheckin.care_profile_id == access.profile.id)
    )
    if start_at is not None:
        query = query.where(WellbeingCheckin.occurred_at >= normalize_datetime(start_at))
    if end_at is not None:
        query = query.where(WellbeingCheckin.occurred_at < normalize_datetime(end_at))
    checkins = db.scalars(
        query.order_by(WellbeingCheckin.occurred_at.desc(), WellbeingCheckin.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return [checkin_read(checkin) for checkin in checkins]


@router.get(
    "/{care_profile_id}/wellbeing-checkins/summary",
    response_model=WellbeingSummary,
)
def wellbeing_summary(
    care_profile_id: UUID,
    db: DbSession,
    access: ProfileMemberAccess,
    start_date: Annotated[date, Query()],
    end_date: Annotated[date, Query()],
) -> WellbeingSummary:
    return calculate_wellbeing_summary(
        db=db,
        care_profile_id=access.profile.id,
        start_date=start_date,
        end_date=end_date,
        timezone_name=access.profile.timezone,
    )


@router.get(
    "/{care_profile_id}/wellbeing-checkins/{checkin_id}",
    response_model=WellbeingCheckinRead,
)
def retrieve_checkin(
    care_profile_id: UUID,
    checkin_id: UUID,
    db: DbSession,
    access: ProfileMemberAccess,
) -> WellbeingCheckinRead:
    return checkin_read(get_checkin_or_404(db, access.profile.id, checkin_id))


@router.patch(
    "/{care_profile_id}/wellbeing-checkins/{checkin_id}",
    response_model=WellbeingCheckinRead,
)
def update_checkin(
    care_profile_id: UUID,
    checkin_id: UUID,
    payload: WellbeingCheckinUpdate,
    db: DbSession,
    access: ProfileSubjectAccess,
) -> WellbeingCheckinRead:
    checkin = get_checkin_or_404(db, access.profile.id, checkin_id)
    if checkin.reported_by_user_id != access.membership.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own self report",
        )

    fields = payload.model_fields_set
    if "score" in fields:
        checkin.score = payload.score  # type: ignore[assignment]
    if "occurred_at" in fields:
        checkin.occurred_at = payload.occurred_at.astimezone(UTC)  # type: ignore[union-attr]
    if "note" in fields:
        checkin.note = payload.note or None
    if "voice_transcript" in fields:
        checkin.voice_transcript = payload.voice_transcript or None
    if "symptoms" in fields:
        checkin.symptoms = [WellbeingSymptom(kind=kind) for kind in (payload.symptoms or [])]
    db.commit()
    db.refresh(checkin)
    return checkin_read(checkin)


@router.delete(
    "/{care_profile_id}/wellbeing-checkins/{checkin_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_checkin(
    care_profile_id: UUID,
    checkin_id: UUID,
    db: DbSession,
    access: ProfileSubjectAccess,
) -> Response:
    checkin = get_checkin_or_404(db, access.profile.id, checkin_id)
    if checkin.reported_by_user_id != access.membership.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own self report",
        )
    db.delete(checkin)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
