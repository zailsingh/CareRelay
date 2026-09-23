from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.medication import Medication, MedicationDoseRecord, MedicationSchedule
from app.services.wellbeing_summary import as_utc


@dataclass(frozen=True)
class ExpectedDose:
    medication: Medication
    schedule: MedicationSchedule | None
    scheduled_for: datetime
    scheduled_local_date: date
    scheduled_local_time: time
    scheduled_timezone: str
    record: MedicationDoseRecord | None
    due_state: str

    @property
    def occurrence_key(self) -> str:
        if self.schedule is None:
            return f"dose:{self.record.id}"  # type: ignore[union-attr]
        return f"{self.schedule.id}:{self.scheduled_local_date.isoformat()}"


def local_schedule_instant(day: date, local_time: time, timezone_name: str) -> datetime:
    """Resolve a wall-clock schedule deterministically, including DST gaps/folds.

    Ambiguous times use the first occurrence. A nonexistent time maps through the timezone's
    post-transition wall time while the separately stored local fields retain user intent.
    """
    timezone = ZoneInfo(timezone_name)
    intended = datetime.combine(day, local_time.replace(tzinfo=None))
    return intended.replace(tzinfo=timezone, fold=0).astimezone(UTC)


def utc_date_bounds(start: date, end: date, timezone_name: str) -> tuple[datetime, datetime]:
    timezone = ZoneInfo(timezone_name)
    return (
        datetime.combine(start, time.min, timezone).astimezone(UTC),
        datetime.combine(end + timedelta(days=1), time.min, timezone).astimezone(UTC),
    )


def schedule_applies(medication: Medication, schedule: MedicationSchedule, day: date) -> bool:
    if not medication.active or not schedule.active:
        return False
    if medication.start_date and day < medication.start_date:
        return False
    if medication.end_date and day > medication.end_date:
        return False
    if schedule.start_date and day < schedule.start_date:
        return False
    if schedule.end_date and day > schedule.end_date:
        return False
    return day.weekday() in {item.day_of_week for item in schedule.days}


def list_medications_query(care_profile_id: UUID):
    return (
        select(Medication)
        .options(
            selectinload(Medication.created_by),
            selectinload(Medication.schedules).selectinload(MedicationSchedule.days),
        )
        .where(Medication.care_profile_id == care_profile_id)
        .order_by(Medication.active.desc(), Medication.name, Medication.created_at)
    )


def expected_doses(
    db: Session,
    care_profile_id: UUID,
    timezone_name: str,
    start: date,
    end: date,
    *,
    now: datetime | None = None,
) -> list[ExpectedDose]:
    if end < start:
        raise ValueError("end must not be before start")
    medications = list(db.scalars(list_medications_query(care_profile_id)).all())
    range_start, range_end = utc_date_bounds(start, end, timezone_name)
    records = list(
        db.scalars(
            select(MedicationDoseRecord)
            .join(Medication, Medication.id == MedicationDoseRecord.medication_id)
            .options(
                selectinload(MedicationDoseRecord.medication),
                selectinload(MedicationDoseRecord.schedule).selectinload(MedicationSchedule.days),
                selectinload(MedicationDoseRecord.recorded_by),
            )
            .where(
                Medication.care_profile_id == care_profile_id,
                MedicationDoseRecord.scheduled_for >= range_start,
                MedicationDoseRecord.scheduled_for < range_end,
            )
        ).all()
    )
    by_schedule_and_instant = {
        (record.schedule_id, as_utc(record.scheduled_for)): record
        for record in records
        if record.schedule_id is not None
    }
    used_record_ids: set[UUID] = set()
    current = as_utc(now or datetime.now(UTC))
    results: list[ExpectedDose] = []
    day = start
    while day <= end:
        for medication in medications:
            if medication.schedule_type.value != "scheduled":
                continue
            for schedule in medication.schedules:
                if not schedule_applies(medication, schedule, day):
                    continue
                scheduled_for = local_schedule_instant(day, schedule.local_time, timezone_name)
                record = by_schedule_and_instant.get((schedule.id, scheduled_for))
                if record:
                    used_record_ids.add(record.id)
                results.append(
                    ExpectedDose(
                        medication=medication,
                        schedule=schedule,
                        scheduled_for=scheduled_for,
                        scheduled_local_date=day,
                        scheduled_local_time=schedule.local_time,
                        scheduled_timezone=timezone_name,
                        record=record,
                        due_state=(
                            "recorded"
                            if record is not None
                            else "upcoming"
                            if scheduled_for > current
                            else "elapsed"
                        ),
                    )
                )
        day += timedelta(days=1)

    # Preserve corrections/history for inactive schedules and include as-needed administrations.
    for record in records:
        if record.id in used_record_ids:
            continue
        results.append(
            ExpectedDose(
                medication=record.medication,
                schedule=record.schedule,
                scheduled_for=as_utc(record.scheduled_for),
                scheduled_local_date=record.scheduled_local_date,
                scheduled_local_time=record.scheduled_local_time,
                scheduled_timezone=record.scheduled_timezone,
                record=record,
                due_state="as_needed" if record.schedule_id is None else "recorded",
            )
        )
    return sorted(results, key=lambda item: (item.scheduled_for, item.medication.name))


def medication_status_counts(occurrences: list[ExpectedDose]) -> Counter[str]:
    """Count authoritative dose outcomes without treating absent outcomes as missed."""
    return Counter(
        item.record.status.value if item.record is not None else "not_recorded"
        for item in occurrences
    )
