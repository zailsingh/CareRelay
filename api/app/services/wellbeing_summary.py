from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.timezones import validate_timezone_name
from app.models.enums import SymptomKind
from app.models.wellbeing import WellbeingCheckin
from app.schemas.wellbeing import DailyWellbeingAverage, WellbeingSummary


def parse_timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(validate_timezone_name(timezone_name))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="timezone must be a valid IANA timezone name",
        ) from exc


def as_utc(value: datetime) -> datetime:
    # SQLite test databases do not preserve the timezone marker. Values are normalized
    # to UTC before persistence, so a naive value read from SQLite represents UTC.
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def calculate_wellbeing_summary(
    db: Session,
    care_profile_id,
    start_date: date,
    end_date: date,
    timezone_name: str,
) -> WellbeingSummary:
    if end_date < start_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="end_date must be on or after start_date",
        )
    if (end_date - start_date).days > 366:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="summary range cannot exceed 367 days",
        )

    timezone = parse_timezone(timezone_name)
    start_utc = datetime.combine(start_date, time.min, timezone).astimezone(UTC)
    end_exclusive_utc = datetime.combine(
        end_date + timedelta(days=1), time.min, timezone
    ).astimezone(UTC)

    checkins = db.scalars(
        select(WellbeingCheckin)
        .options(selectinload(WellbeingCheckin.symptoms))
        .where(
            WellbeingCheckin.care_profile_id == care_profile_id,
            WellbeingCheckin.occurred_at >= start_utc,
            WellbeingCheckin.occurred_at < end_exclusive_utc,
        )
        .order_by(WellbeingCheckin.occurred_at)
    ).all()

    by_day: dict[date, list[int]] = defaultdict(list)
    symptom_counts: Counter[SymptomKind] = Counter()
    for checkin in checkins:
        local_day = as_utc(checkin.occurred_at).astimezone(timezone).date()
        by_day[local_day].append(checkin.score)
        symptom_counts.update(symptom.kind for symptom in checkin.symptoms)

    daily_averages: list[DailyWellbeingAverage] = []
    day = start_date
    while day <= end_date:
        scores = by_day.get(day, [])
        daily_averages.append(
            DailyWellbeingAverage(
                date=day,
                checkin_count=len(scores),
                average_score=round(sum(scores) / len(scores), 1) if scores else None,
            )
        )
        day += timedelta(days=1)

    scores = [checkin.score for checkin in checkins]
    latest = max(checkins, key=lambda checkin: as_utc(checkin.occurred_at), default=None)
    return WellbeingSummary(
        start_date=start_date,
        end_date=end_date,
        timezone=timezone_name,
        checkin_count=len(checkins),
        latest_score=latest.score if latest else None,
        average_score=round(sum(scores) / len(scores), 1) if scores else None,
        minimum_score=min(scores) if scores else None,
        maximum_score=max(scores) if scores else None,
        daily_averages=daily_averages,
        symptom_frequency={kind: symptom_counts[kind] for kind in SymptomKind},
    )
