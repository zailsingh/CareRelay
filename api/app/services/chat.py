import base64
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.chat import ChatRoom


def get_or_create_default_room(db: Session, care_profile_id: UUID) -> ChatRoom:
    room = db.scalar(select(ChatRoom).where(ChatRoom.care_profile_id == care_profile_id))
    if room is not None:
        return room
    room = ChatRoom(care_profile_id=care_profile_id, name="Family chat")
    db.add(room)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        room = db.scalar(select(ChatRoom).where(ChatRoom.care_profile_id == care_profile_id))
        if room is None:
            raise
        return room
    db.refresh(room)
    return room


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def encode_message_cursor(sent_at: datetime, message_id: UUID) -> str:
    raw = f"{as_utc(sent_at).isoformat()}|{message_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_message_cursor(value: str) -> tuple[datetime, UUID]:
    try:
        padded = value + "=" * (-len(value) % 4)
        timestamp, message_id = base64.urlsafe_b64decode(padded).decode().rsplit("|", 1)
        parsed = datetime.fromisoformat(timestamp)
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(UTC), UUID(message_id)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid message cursor",
        ) from exc
