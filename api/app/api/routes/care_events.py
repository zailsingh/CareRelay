from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, ProfileMemberAccess
from app.models.care_event import CareEvent
from app.models.chat import ChatMessage, ChatRoom
from app.models.enums import (
    AuditAction,
    CareEventSource,
    CareEventType,
    CareRole,
    ConfirmationStatus,
)
from app.schemas.care_event import (
    CareEventCreate,
    CareEventRead,
    CareEventUpdate,
    EventEnteredBy,
    EventOrdering,
    validate_metadata,
)
from app.services.audit import add_audit_entry

router = APIRouter()

SOURCE_BY_ROLE = {
    CareRole.ADMIN: CareEventSource.ADMIN,
    CareRole.FAMILY: CareEventSource.FAMILY,
    CareRole.CARER: CareEventSource.CARER,
}


def require_event_contributor(access: ProfileMemberAccess) -> CareEventSource:
    source = SOURCE_BY_ROLE.get(access.membership.role)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This membership role cannot create family or carer observations",
        )
    return source


def normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Date-time filters must include a timezone offset",
        )
    return value.astimezone(UTC)


def event_read(event: CareEvent) -> CareEventRead:
    return CareEventRead(
        id=event.id,
        care_profile_id=event.care_profile_id,
        event_type=event.event_type,
        occurred_at=event.occurred_at,
        entered_by_user_id=event.entered_by_user_id,
        entered_by=EventEnteredBy.model_validate(event.entered_by),
        source=event.source,
        summary=event.summary,
        metadata=event.structured_data,
        confirmation_status=event.confirmation_status,
        source_chat_message_id=event.source_chat_message_id,
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


def event_snapshot(event: CareEvent) -> dict:
    return {
        "event_type": event.event_type.value,
        "occurred_at": event.occurred_at.isoformat(),
        "entered_by_user_id": str(event.entered_by_user_id),
        "source": event.source.value,
        "summary": event.summary,
        "metadata": event.structured_data,
        "confirmation_status": event.confirmation_status.value,
        "source_chat_message_id": (
            str(event.source_chat_message_id) if event.source_chat_message_id else None
        ),
    }


def get_event_or_404(db: DbSession, profile_id: UUID, event_id: UUID) -> CareEvent:
    event = db.scalar(
        select(CareEvent)
        .options(selectinload(CareEvent.entered_by))
        .where(CareEvent.id == event_id, CareEvent.care_profile_id == profile_id)
    )
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Care event not found")
    return event


def require_event_editor(event: CareEvent, access: ProfileMemberAccess) -> None:
    if (
        event.entered_by_user_id != access.membership.user_id
        and access.membership.role != CareRole.ADMIN
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the event author or a profile administrator can change this event",
        )


@router.post(
    "/{care_profile_id}/care-events",
    response_model=CareEventRead,
    status_code=status.HTTP_201_CREATED,
)
def create_care_event(
    care_profile_id: UUID,
    payload: CareEventCreate,
    db: DbSession,
    access: ProfileMemberAccess,
) -> CareEventRead:
    source = require_event_contributor(access)
    if payload.source_chat_message_id is not None:
        source_message = db.scalar(
            select(ChatMessage)
            .join(ChatRoom, ChatRoom.id == ChatMessage.chat_room_id)
            .where(
                ChatMessage.id == payload.source_chat_message_id,
                ChatRoom.care_profile_id == access.profile.id,
            )
        )
        if source_message is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Source chat message not found",
            )
        if payload.confirmation_status != ConfirmationStatus.CONFIRMED:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="A chat-derived care event must be explicitly confirmed",
            )
    event = CareEvent(
        care_profile_id=access.profile.id,
        event_type=payload.event_type,
        occurred_at=payload.occurred_at.astimezone(UTC),
        entered_by_user_id=access.membership.user_id,
        entered_by=access.membership.user,
        source=source,
        summary=payload.summary,
        structured_data=payload.metadata,
        confirmation_status=payload.confirmation_status,
        source_chat_message_id=payload.source_chat_message_id,
    )
    db.add(event)
    db.flush()
    add_audit_entry(
        db,
        care_profile_id=access.profile.id,
        actor_user_id=access.membership.user_id,
        action=AuditAction.CARE_EVENT_CREATED,
        target_type="care_event",
        target_id=event.id,
        after_state=event_snapshot(event),
    )
    db.commit()
    db.refresh(event)
    return event_read(event)


@router.get("/{care_profile_id}/care-events", response_model=list[CareEventRead])
def list_care_events(
    care_profile_id: UUID,
    db: DbSession,
    access: ProfileMemberAccess,
    event_type: Annotated[CareEventType | None, Query()] = None,
    start_at: Annotated[datetime | None, Query()] = None,
    end_at: Annotated[datetime | None, Query()] = None,
    entered_by: Annotated[UUID | None, Query()] = None,
    order: Annotated[EventOrdering, Query()] = EventOrdering.NEWEST,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[CareEventRead]:
    if start_at is not None and end_at is not None:
        if normalize_datetime(end_at) <= normalize_datetime(start_at):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="end_at must be after start_at",
            )
    query = (
        select(CareEvent)
        .options(selectinload(CareEvent.entered_by))
        .where(CareEvent.care_profile_id == access.profile.id)
    )
    if event_type is not None:
        query = query.where(CareEvent.event_type == event_type)
    if start_at is not None:
        query = query.where(CareEvent.occurred_at >= normalize_datetime(start_at))
    if end_at is not None:
        query = query.where(CareEvent.occurred_at < normalize_datetime(end_at))
    if entered_by is not None:
        query = query.where(CareEvent.entered_by_user_id == entered_by)
    ordering = (
        CareEvent.occurred_at.desc() if order == EventOrdering.NEWEST else CareEvent.occurred_at
    )
    events = db.scalars(
        query.order_by(ordering, CareEvent.created_at.desc()).offset(offset).limit(limit)
    ).all()
    return [event_read(event) for event in events]


@router.get("/{care_profile_id}/care-events/{event_id}", response_model=CareEventRead)
def retrieve_care_event(
    care_profile_id: UUID,
    event_id: UUID,
    db: DbSession,
    access: ProfileMemberAccess,
) -> CareEventRead:
    return event_read(get_event_or_404(db, access.profile.id, event_id))


@router.patch("/{care_profile_id}/care-events/{event_id}", response_model=CareEventRead)
def update_care_event(
    care_profile_id: UUID,
    event_id: UUID,
    payload: CareEventUpdate,
    db: DbSession,
    access: ProfileMemberAccess,
) -> CareEventRead:
    event = get_event_or_404(db, access.profile.id, event_id)
    require_event_editor(event, access)
    before = event_snapshot(event)
    fields = payload.model_fields_set
    final_type = payload.event_type or event.event_type
    if "event_type" in fields:
        event.event_type = final_type
    if "occurred_at" in fields:
        event.occurred_at = payload.occurred_at.astimezone(UTC)  # type: ignore[union-attr]
    if "summary" in fields:
        event.summary = payload.summary  # type: ignore[assignment]
    if "metadata" in fields:
        event.structured_data = validate_metadata(final_type, payload.metadata)
    elif "event_type" in fields:
        event.structured_data = validate_metadata(final_type, {})
    if "confirmation_status" in fields:
        event.confirmation_status = payload.confirmation_status  # type: ignore[assignment]
    add_audit_entry(
        db,
        care_profile_id=access.profile.id,
        actor_user_id=access.membership.user_id,
        action=AuditAction.CARE_EVENT_UPDATED,
        target_type="care_event",
        target_id=event.id,
        before_state=before,
        after_state=event_snapshot(event),
    )
    db.commit()
    db.refresh(event)
    return event_read(event)


@router.delete("/{care_profile_id}/care-events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_care_event(
    care_profile_id: UUID,
    event_id: UUID,
    db: DbSession,
    access: ProfileMemberAccess,
) -> Response:
    event = get_event_or_404(db, access.profile.id, event_id)
    require_event_editor(event, access)
    before = event_snapshot(event)
    add_audit_entry(
        db,
        care_profile_id=access.profile.id,
        actor_user_id=access.membership.user_id,
        action=AuditAction.CARE_EVENT_DELETED,
        target_type="care_event",
        target_id=event.id,
        before_state=before,
    )
    db.delete(event)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
