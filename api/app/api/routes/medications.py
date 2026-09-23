from datetime import UTC, date, datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, ProfileMemberAccess
from app.models.care_event import CareEvent
from app.models.enums import (
    AuditAction,
    CareEventSource,
    CareEventType,
    CareRole,
    ConfirmationStatus,
    MedicationDoseStatus,
    MedicationScheduleType,
)
from app.models.medication import (
    Medication,
    MedicationDoseRecord,
    MedicationSchedule,
    MedicationScheduleDay,
)
from app.schemas.medication import (
    MedicationCreate,
    MedicationDoseCreate,
    MedicationDoseOccurrence,
    MedicationDoseRead,
    MedicationDoseUpdate,
    MedicationRead,
    MedicationScheduleCreate,
    MedicationScheduleRead,
    MedicationScheduleUpdate,
    MedicationUpdate,
)
from app.services.audit import add_audit_entry
from app.services.medications import (
    expected_doses,
    list_medications_query,
    local_schedule_instant,
    schedule_applies,
)
from app.services.wellbeing_summary import as_utc

router = APIRouter()
PLAN_MANAGERS = {CareRole.ADMIN, CareRole.FAMILY, CareRole.CARER}


def require_plan_manager(access: ProfileMemberAccess) -> None:
    if access.membership.role not in PLAN_MANAGERS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This membership role cannot manage medication plans",
        )


def require_dose_recorder(access: ProfileMemberAccess) -> None:
    is_subject = access.profile.subject_user_id == access.membership.user_id
    if access.membership.role not in PLAN_MANAGERS and not is_subject:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This member cannot record medication doses",
        )


def event_source(access: ProfileMemberAccess) -> CareEventSource:
    mapping = {
        CareRole.ADMIN: CareEventSource.ADMIN,
        CareRole.FAMILY: CareEventSource.FAMILY,
        CareRole.CARER: CareEventSource.CARER,
    }
    return mapping.get(access.membership.role, CareEventSource.SUBJECT)


def get_medication_or_404(db: DbSession, profile_id: UUID, medication_id: UUID) -> Medication:
    medication = db.scalar(list_medications_query(profile_id).where(Medication.id == medication_id))
    if medication is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medication not found")
    return medication


def get_schedule_or_404(
    db: DbSession, profile_id: UUID, medication_id: UUID, schedule_id: UUID
) -> MedicationSchedule:
    schedule = db.scalar(
        select(MedicationSchedule)
        .join(Medication, Medication.id == MedicationSchedule.medication_id)
        .options(selectinload(MedicationSchedule.days))
        .where(
            MedicationSchedule.id == schedule_id,
            MedicationSchedule.medication_id == medication_id,
            Medication.care_profile_id == profile_id,
        )
    )
    if schedule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    return schedule


def get_dose_or_404(db: DbSession, profile_id: UUID, dose_id: UUID) -> MedicationDoseRecord:
    dose = db.scalar(
        select(MedicationDoseRecord)
        .join(Medication, Medication.id == MedicationDoseRecord.medication_id)
        .options(
            selectinload(MedicationDoseRecord.medication),
            selectinload(MedicationDoseRecord.recorded_by),
            selectinload(MedicationDoseRecord.schedule).selectinload(MedicationSchedule.days),
        )
        .where(
            MedicationDoseRecord.id == dose_id,
            Medication.care_profile_id == profile_id,
        )
    )
    if dose is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dose record not found")
    return dose


def schedule_read(schedule: MedicationSchedule) -> MedicationScheduleRead:
    return MedicationScheduleRead(
        id=schedule.id,
        medication_id=schedule.medication_id,
        local_time=schedule.local_time,
        days_of_week=sorted(day.day_of_week for day in schedule.days),
        active=schedule.active,
        start_date=schedule.start_date,
        end_date=schedule.end_date,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
    )


def medication_read(medication: Medication) -> MedicationRead:
    return MedicationRead(
        id=medication.id,
        care_profile_id=medication.care_profile_id,
        name=medication.name,
        strength_text=medication.strength_text,
        form=medication.form,
        instructions_text=medication.instructions_text,
        notes=medication.notes,
        schedule_type=medication.schedule_type,
        active=medication.active,
        start_date=medication.start_date,
        end_date=medication.end_date,
        created_by_user_id=medication.created_by_user_id,
        schedules=[schedule_read(item) for item in medication.schedules],
        created_at=medication.created_at,
        updated_at=medication.updated_at,
    )


def dose_read(dose: MedicationDoseRecord) -> MedicationDoseRead:
    return MedicationDoseRead(
        id=dose.id,
        medication_id=dose.medication_id,
        medication_name=dose.medication.name,
        medication_strength=dose.medication.strength_text,
        schedule_id=dose.schedule_id,
        scheduled_for=as_utc(dose.scheduled_for),
        scheduled_local_date=dose.scheduled_local_date,
        scheduled_local_time=dose.scheduled_local_time,
        scheduled_timezone=dose.scheduled_timezone,
        status=dose.status,
        recorded_by=dose.recorded_by,
        recorded_at=as_utc(dose.recorded_at),
        note=dose.note,
        care_event_id=dose.care_event_id,
    )


def medication_snapshot(medication: Medication) -> dict:
    return {
        "schedule_type": medication.schedule_type.value,
        "active": medication.active,
        "start_date": medication.start_date.isoformat() if medication.start_date else None,
        "end_date": medication.end_date.isoformat() if medication.end_date else None,
    }


def schedule_snapshot(schedule: MedicationSchedule) -> dict:
    return {
        "local_time": schedule.local_time.isoformat(timespec="minutes"),
        "days_of_week": sorted(item.day_of_week for item in schedule.days),
        "active": schedule.active,
        "start_date": schedule.start_date.isoformat() if schedule.start_date else None,
        "end_date": schedule.end_date.isoformat() if schedule.end_date else None,
    }


def dose_snapshot(dose: MedicationDoseRecord) -> dict:
    return {
        "medication_id": str(dose.medication_id),
        "schedule_id": str(dose.schedule_id) if dose.schedule_id else None,
        "scheduled_for": as_utc(dose.scheduled_for).isoformat(),
        "status": dose.status.value,
        "care_event_id": str(dose.care_event_id),
    }


def add_schedule_model(
    medication: Medication, payload: MedicationScheduleCreate
) -> MedicationSchedule:
    schedule = MedicationSchedule(
        medication=medication,
        local_time=payload.local_time,
        active=payload.active,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    schedule.days = [MedicationScheduleDay(day_of_week=day) for day in payload.days_of_week]
    return schedule


@router.get("/{care_profile_id}/medications", response_model=list[MedicationRead])
def list_medications(
    care_profile_id: UUID, db: DbSession, access: ProfileMemberAccess
) -> list[MedicationRead]:
    return [
        medication_read(item)
        for item in db.scalars(list_medications_query(access.profile.id)).all()
    ]


@router.post(
    "/{care_profile_id}/medications",
    response_model=MedicationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_medication(
    care_profile_id: UUID,
    payload: MedicationCreate,
    db: DbSession,
    access: ProfileMemberAccess,
) -> MedicationRead:
    require_plan_manager(access)
    medication = Medication(
        care_profile_id=access.profile.id,
        name=payload.name,
        strength_text=payload.strength_text,
        form=payload.form,
        instructions_text=payload.instructions_text,
        notes=payload.notes,
        schedule_type=payload.schedule_type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        created_by_user_id=access.membership.user_id,
    )
    db.add(medication)
    schedules = []
    for schedule_payload in payload.schedules:
        schedule = add_schedule_model(medication, schedule_payload)
        schedules.append(schedule)
        db.add(schedule)
    db.flush()
    add_audit_entry(
        db,
        care_profile_id=access.profile.id,
        actor_user_id=access.membership.user_id,
        action=AuditAction.MEDICATION_CREATED,
        target_type="medication",
        target_id=medication.id,
        after_state=medication_snapshot(medication),
    )
    for schedule in schedules:
        add_audit_entry(
            db,
            care_profile_id=access.profile.id,
            actor_user_id=access.membership.user_id,
            action=AuditAction.MEDICATION_SCHEDULE_CREATED,
            target_type="medication_schedule",
            target_id=schedule.id,
            after_state=schedule_snapshot(schedule),
        )
    db.commit()
    return medication_read(get_medication_or_404(db, access.profile.id, medication.id))


@router.get("/{care_profile_id}/medications/{medication_id}", response_model=MedicationRead)
def retrieve_medication(
    care_profile_id: UUID,
    medication_id: UUID,
    db: DbSession,
    access: ProfileMemberAccess,
) -> MedicationRead:
    return medication_read(get_medication_or_404(db, access.profile.id, medication_id))


@router.patch("/{care_profile_id}/medications/{medication_id}", response_model=MedicationRead)
def update_medication(
    care_profile_id: UUID,
    medication_id: UUID,
    payload: MedicationUpdate,
    db: DbSession,
    access: ProfileMemberAccess,
) -> MedicationRead:
    require_plan_manager(access)
    medication = get_medication_or_404(db, access.profile.id, medication_id)
    before = medication_snapshot(medication)
    fields = payload.model_fields_set
    for field in (
        "name",
        "strength_text",
        "form",
        "instructions_text",
        "notes",
        "schedule_type",
        "active",
        "start_date",
        "end_date",
    ):
        if field in fields:
            setattr(medication, field, getattr(payload, field))
    if (
        medication.start_date
        and medication.end_date
        and medication.end_date < medication.start_date
    ):
        raise HTTPException(status_code=422, detail="end_date must not be before start_date")
    if medication.schedule_type == MedicationScheduleType.AS_NEEDED and any(
        schedule.active for schedule in medication.schedules
    ):
        raise HTTPException(
            status_code=409,
            detail="Deactivate recurring schedules before changing to as-needed",
        )
    action = (
        AuditAction.MEDICATION_DEACTIVATED
        if before["active"] and not medication.active
        else AuditAction.MEDICATION_UPDATED
    )
    add_audit_entry(
        db,
        care_profile_id=access.profile.id,
        actor_user_id=access.membership.user_id,
        action=action,
        target_type="medication",
        target_id=medication.id,
        before_state=before,
        after_state=medication_snapshot(medication),
    )
    db.commit()
    return medication_read(get_medication_or_404(db, access.profile.id, medication.id))


@router.delete(
    "/{care_profile_id}/medications/{medication_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def deactivate_medication(
    care_profile_id: UUID,
    medication_id: UUID,
    db: DbSession,
    access: ProfileMemberAccess,
) -> Response:
    require_plan_manager(access)
    medication = get_medication_or_404(db, access.profile.id, medication_id)
    if medication.active:
        before = medication_snapshot(medication)
        medication.active = False
        add_audit_entry(
            db,
            care_profile_id=access.profile.id,
            actor_user_id=access.membership.user_id,
            action=AuditAction.MEDICATION_DEACTIVATED,
            target_type="medication",
            target_id=medication.id,
            before_state=before,
            after_state=medication_snapshot(medication),
        )
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{care_profile_id}/medications/{medication_id}/schedules",
    response_model=MedicationScheduleRead,
    status_code=status.HTTP_201_CREATED,
)
def create_schedule(
    care_profile_id: UUID,
    medication_id: UUID,
    payload: MedicationScheduleCreate,
    db: DbSession,
    access: ProfileMemberAccess,
) -> MedicationScheduleRead:
    require_plan_manager(access)
    medication = get_medication_or_404(db, access.profile.id, medication_id)
    if medication.schedule_type != MedicationScheduleType.SCHEDULED:
        raise HTTPException(status_code=409, detail="As-needed medications cannot have schedules")
    schedule = add_schedule_model(medication, payload)
    db.add(schedule)
    db.flush()
    add_audit_entry(
        db,
        care_profile_id=access.profile.id,
        actor_user_id=access.membership.user_id,
        action=AuditAction.MEDICATION_SCHEDULE_CREATED,
        target_type="medication_schedule",
        target_id=schedule.id,
        after_state=schedule_snapshot(schedule),
    )
    db.commit()
    db.refresh(schedule)
    return schedule_read(get_schedule_or_404(db, access.profile.id, medication.id, schedule.id))


@router.patch(
    "/{care_profile_id}/medications/{medication_id}/schedules/{schedule_id}",
    response_model=MedicationScheduleRead,
)
def update_schedule(
    care_profile_id: UUID,
    medication_id: UUID,
    schedule_id: UUID,
    payload: MedicationScheduleUpdate,
    db: DbSession,
    access: ProfileMemberAccess,
) -> MedicationScheduleRead:
    require_plan_manager(access)
    schedule = get_schedule_or_404(db, access.profile.id, medication_id, schedule_id)
    before = schedule_snapshot(schedule)
    fields = payload.model_fields_set
    for field in ("local_time", "active", "start_date", "end_date"):
        if field in fields:
            setattr(schedule, field, getattr(payload, field))
    if "days_of_week" in fields:
        schedule.days = [
            MedicationScheduleDay(day_of_week=day) for day in payload.days_of_week or []
        ]
    if schedule.start_date and schedule.end_date and schedule.end_date < schedule.start_date:
        raise HTTPException(status_code=422, detail="end_date must not be before start_date")
    add_audit_entry(
        db,
        care_profile_id=access.profile.id,
        actor_user_id=access.membership.user_id,
        action=AuditAction.MEDICATION_SCHEDULE_UPDATED,
        target_type="medication_schedule",
        target_id=schedule.id,
        before_state=before,
        after_state=schedule_snapshot(schedule),
    )
    db.commit()
    return schedule_read(get_schedule_or_404(db, access.profile.id, medication_id, schedule_id))


@router.delete(
    "/{care_profile_id}/medications/{medication_id}/schedules/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_schedule(
    care_profile_id: UUID,
    medication_id: UUID,
    schedule_id: UUID,
    db: DbSession,
    access: ProfileMemberAccess,
) -> Response:
    require_plan_manager(access)
    schedule = get_schedule_or_404(db, access.profile.id, medication_id, schedule_id)
    if schedule.active:
        before = schedule_snapshot(schedule)
        schedule.active = False
        add_audit_entry(
            db,
            care_profile_id=access.profile.id,
            actor_user_id=access.membership.user_id,
            action=AuditAction.MEDICATION_SCHEDULE_REMOVED,
            target_type="medication_schedule",
            target_id=schedule.id,
            before_state=before,
            after_state=schedule_snapshot(schedule),
        )
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def occurrence_read(item) -> MedicationDoseOccurrence:
    return MedicationDoseOccurrence(
        occurrence_key=item.occurrence_key,
        medication_id=item.medication.id,
        medication_name=item.medication.name,
        medication_strength=item.medication.strength_text,
        schedule_id=item.schedule.id if item.schedule else None,
        scheduled_for=item.scheduled_for,
        scheduled_local_date=item.scheduled_local_date,
        scheduled_local_time=item.scheduled_local_time,
        scheduled_timezone=item.scheduled_timezone,
        status=item.record.status.value if item.record else "not_recorded",
        dose_record=dose_read(item.record) if item.record else None,
        due_state=item.due_state,
    )


@router.get("/{care_profile_id}/medication-doses", response_model=list[MedicationDoseOccurrence])
def list_doses(
    care_profile_id: UUID,
    start: date,
    end: date,
    db: DbSession,
    access: ProfileMemberAccess,
) -> list[MedicationDoseOccurrence]:
    if end < start or (end - start).days > 90:
        raise HTTPException(status_code=422, detail="Dose date range must be 1 to 91 days")
    return [
        occurrence_read(item)
        for item in expected_doses(db, access.profile.id, access.profile.timezone, start, end)
    ]


@router.get("/{care_profile_id}/medication-doses/{dose_id}", response_model=MedicationDoseRead)
def retrieve_dose(
    care_profile_id: UUID,
    dose_id: UUID,
    db: DbSession,
    access: ProfileMemberAccess,
) -> MedicationDoseRead:
    return dose_read(get_dose_or_404(db, access.profile.id, dose_id))


def event_type_for_status(dose_status: MedicationDoseStatus) -> CareEventType:
    return {
        MedicationDoseStatus.TAKEN: CareEventType.MEDICATION_TAKEN,
        MedicationDoseStatus.MISSED: CareEventType.MEDICATION_MISSED,
        MedicationDoseStatus.SKIPPED: CareEventType.MEDICATION_SKIPPED,
    }[dose_status]


def event_details(
    medication: Medication,
    dose_id: UUID,
    dose_status: MedicationDoseStatus,
    local_date: date,
    local_time,
) -> tuple[str, dict]:
    label = " ".join(filter(None, [medication.name, medication.strength_text]))
    local_clock = local_time.isoformat(timespec="minutes")
    return (
        label,
        {
            "medication_name": medication.name,
            "dose": medication.strength_text,
            "medication_id": str(medication.id),
            "medication_dose_id": str(dose_id),
            "scheduled_local_date": local_date.isoformat(),
            "scheduled_local_time": local_clock,
            "dose_status": dose_status.value,
        },
    )


@router.post(
    "/{care_profile_id}/medication-doses",
    response_model=MedicationDoseRead,
    status_code=status.HTTP_201_CREATED,
)
def record_dose(
    care_profile_id: UUID,
    payload: MedicationDoseCreate,
    db: DbSession,
    access: ProfileMemberAccess,
) -> MedicationDoseRead:
    require_dose_recorder(access)
    medication = get_medication_or_404(db, access.profile.id, payload.medication_id)
    recorded_at = datetime.now(UTC)
    timezone = ZoneInfo(access.profile.timezone)
    schedule = None
    if medication.schedule_type == MedicationScheduleType.SCHEDULED:
        if payload.schedule_id is None or payload.scheduled_for is None:
            raise HTTPException(
                status_code=422,
                detail="Scheduled medication outcomes require schedule_id and scheduled_for",
            )
        schedule = get_schedule_or_404(db, access.profile.id, medication.id, payload.schedule_id)
        local_day = payload.scheduled_for.astimezone(timezone).date()
        expected = local_schedule_instant(local_day, schedule.local_time, access.profile.timezone)
        if (
            not schedule_applies(medication, schedule, local_day)
            or as_utc(payload.scheduled_for) != expected
        ):
            raise HTTPException(status_code=422, detail="scheduled_for is not an expected dose")
        if payload.status == MedicationDoseStatus.MISSED and expected > recorded_at:
            raise HTTPException(
                status_code=422,
                detail="A future scheduled dose cannot be recorded as missed",
            )
        scheduled_for = expected
        local_time = schedule.local_time
    else:
        if payload.schedule_id is not None:
            raise HTTPException(
                status_code=422, detail="As-needed doses cannot reference a schedule"
            )
        if payload.status != MedicationDoseStatus.TAKEN:
            raise HTTPException(
                status_code=422,
                detail="As-needed medications only support recorded taken doses",
            )
        scheduled_for = as_utc(payload.scheduled_for or recorded_at)
        local_value = scheduled_for.astimezone(timezone)
        local_day = local_value.date()
        local_time = local_value.time().replace(tzinfo=None, second=0, microsecond=0)

    dose_id = uuid4()
    summary, metadata = event_details(medication, dose_id, payload.status, local_day, local_time)
    care_event = CareEvent(
        care_profile_id=access.profile.id,
        event_type=event_type_for_status(payload.status),
        occurred_at=recorded_at,
        entered_by_user_id=access.membership.user_id,
        source=event_source(access),
        summary=summary,
        structured_data=metadata,
        confirmation_status=ConfirmationStatus.CONFIRMED,
    )
    db.add(care_event)
    db.flush()
    dose = MedicationDoseRecord(
        id=dose_id,
        medication=medication,
        schedule=schedule,
        scheduled_for=scheduled_for,
        scheduled_local_date=local_day,
        scheduled_local_time=local_time,
        scheduled_timezone=access.profile.timezone,
        status=payload.status,
        recorded_by_user_id=access.membership.user_id,
        recorded_at=recorded_at,
        note=payload.note,
        care_event=care_event,
    )
    db.add(dose)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A dose outcome is already recorded for this scheduled dose",
        ) from exc
    add_audit_entry(
        db,
        care_profile_id=access.profile.id,
        actor_user_id=access.membership.user_id,
        action=AuditAction.MEDICATION_DOSE_RECORDED,
        target_type="medication_dose",
        target_id=dose.id,
        after_state=dose_snapshot(dose),
    )
    db.commit()
    return dose_read(get_dose_or_404(db, access.profile.id, dose.id))


@router.patch("/{care_profile_id}/medication-doses/{dose_id}", response_model=MedicationDoseRead)
def correct_dose(
    care_profile_id: UUID,
    dose_id: UUID,
    payload: MedicationDoseUpdate,
    db: DbSession,
    access: ProfileMemberAccess,
) -> MedicationDoseRead:
    require_dose_recorder(access)
    dose = get_dose_or_404(db, access.profile.id, dose_id)
    before = dose_snapshot(dose)
    if payload.status is not None:
        if dose.schedule_id is None and payload.status != MedicationDoseStatus.TAKEN:
            raise HTTPException(
                status_code=422,
                detail="As-needed medications only support recorded taken doses",
            )
        dose.status = payload.status
    if "note" in payload.model_fields_set:
        dose.note = payload.note
    summary, metadata = event_details(
        dose.medication,
        dose.id,
        dose.status,
        dose.scheduled_local_date,
        dose.scheduled_local_time,
    )
    dose.care_event.event_type = event_type_for_status(dose.status)
    dose.care_event.summary = summary
    dose.care_event.structured_data = metadata
    dose.care_event.updated_at = datetime.now(UTC)
    add_audit_entry(
        db,
        care_profile_id=access.profile.id,
        actor_user_id=access.membership.user_id,
        action=AuditAction.MEDICATION_DOSE_CORRECTED,
        target_type="medication_dose",
        target_id=dose.id,
        before_state=before,
        after_state=dose_snapshot(dose),
    )
    db.commit()
    return dose_read(get_dose_or_404(db, access.profile.id, dose.id))
