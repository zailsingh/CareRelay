from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, ProfileMemberAccess
from app.models import CareMembership
from app.models.chat import ChatMessage, ChatReadState
from app.schemas.chat import (
    ChatCareEventDraft,
    ChatMarkRead,
    ChatMessageCreate,
    ChatMessagePage,
    ChatMessageRead,
    ChatUnreadCount,
    ChatWebSocketTicket,
)
from app.services.chat import (
    as_utc,
    decode_message_cursor,
    encode_message_cursor,
    get_or_create_default_room,
)
from app.services.chat_realtime import chat_connections
from app.services.websocket_tickets import websocket_tickets

router = APIRouter()


def message_read(message: ChatMessage) -> ChatMessageRead:
    return ChatMessageRead(
        id=message.id,
        chat_room_id=message.chat_room_id,
        sender_user_id=message.sender_user_id,
        sender=message.sender,
        body=message.body,
        sent_at=as_utc(message.sent_at),
        edited_at=as_utc(message.edited_at) if message.edited_at else None,
        deleted_at=as_utc(message.deleted_at) if message.deleted_at else None,
        is_deleted=message.deleted_at is not None,
        attachments=message.attachments,
    )


def get_message_or_404(db: DbSession, room_id: UUID, message_id: UUID) -> ChatMessage:
    message = db.scalar(
        select(ChatMessage)
        .options(selectinload(ChatMessage.sender), selectinload(ChatMessage.attachments))
        .where(ChatMessage.id == message_id, ChatMessage.chat_room_id == room_id)
    )
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat message not found")
    return message


def unread_count(db: DbSession, room_id: UUID, user_id: UUID) -> int:
    read_state = db.scalar(
        select(ChatReadState).where(
            ChatReadState.chat_room_id == room_id,
            ChatReadState.user_id == user_id,
        )
    )
    filters = [
        ChatMessage.chat_room_id == room_id,
        ChatMessage.sender_user_id != user_id,
        ChatMessage.deleted_at.is_(None),
    ]
    if read_state is not None and read_state.last_read_message_id is not None:
        marker = db.get(ChatMessage, read_state.last_read_message_id)
        if marker is not None:
            filters.append(
                or_(
                    ChatMessage.sent_at > marker.sent_at,
                    and_(ChatMessage.sent_at == marker.sent_at, ChatMessage.id > marker.id),
                )
            )
    return int(db.scalar(select(func.count(ChatMessage.id)).where(*filters)) or 0)


@router.get("/{care_profile_id}/chat/messages", response_model=ChatMessagePage)
def list_messages(
    care_profile_id: UUID,
    db: DbSession,
    access: ProfileMemberAccess,
    before: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> ChatMessagePage:
    room = get_or_create_default_room(db, access.profile.id)
    query = (
        select(ChatMessage)
        .options(selectinload(ChatMessage.sender), selectinload(ChatMessage.attachments))
        .where(ChatMessage.chat_room_id == room.id)
    )
    if before is not None:
        cursor_time, cursor_id = decode_message_cursor(before)
        query = query.where(
            or_(
                ChatMessage.sent_at < cursor_time,
                and_(ChatMessage.sent_at == cursor_time, ChatMessage.id < cursor_id),
            )
        )
    messages = db.scalars(
        query.order_by(ChatMessage.sent_at.desc(), ChatMessage.id.desc()).limit(limit + 1)
    ).all()
    page = messages[:limit]
    next_cursor = None
    if len(messages) > limit and page:
        next_cursor = encode_message_cursor(page[-1].sent_at, page[-1].id)
    return ChatMessagePage(items=[message_read(item) for item in page], next_cursor=next_cursor)


@router.post(
    "/{care_profile_id}/chat/messages",
    response_model=ChatMessageRead,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    care_profile_id: UUID,
    payload: ChatMessageCreate,
    db: DbSession,
    access: ProfileMemberAccess,
) -> ChatMessageRead:
    room = get_or_create_default_room(db, access.profile.id)
    message = ChatMessage(
        chat_room_id=room.id,
        sender_user_id=access.membership.user_id,
        sender=access.membership.user,
        body=payload.body,
        sent_at=datetime.now(UTC),
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    result = message_read(message)
    await chat_connections.broadcast(
        access.profile.id,
        {"type": "message_created", "message": result.model_dump(mode="json")},
    )
    return result


@router.get("/{care_profile_id}/chat/unread", response_model=ChatUnreadCount)
def get_unread_count(
    care_profile_id: UUID,
    db: DbSession,
    access: ProfileMemberAccess,
) -> ChatUnreadCount:
    room = get_or_create_default_room(db, access.profile.id)
    return ChatUnreadCount(unread_count=unread_count(db, room.id, access.membership.user_id))


@router.post("/{care_profile_id}/chat/ws-ticket", response_model=ChatWebSocketTicket)
def create_websocket_ticket(
    care_profile_id: UUID,
    access: ProfileMemberAccess,
) -> ChatWebSocketTicket:
    ticket = websocket_tickets.issue(access.membership.user_id, access.profile.id)
    return ChatWebSocketTicket(ticket=ticket.value, expires_at=ticket.expires_at)


@router.post("/{care_profile_id}/chat/read", response_model=ChatUnreadCount)
def mark_chat_read(
    care_profile_id: UUID,
    payload: ChatMarkRead,
    db: DbSession,
    access: ProfileMemberAccess,
) -> ChatUnreadCount:
    room = get_or_create_default_room(db, access.profile.id)
    if payload.through_message_id is not None:
        marker = get_message_or_404(db, room.id, payload.through_message_id)
    else:
        marker = db.scalar(
            select(ChatMessage)
            .where(ChatMessage.chat_room_id == room.id)
            .order_by(ChatMessage.sent_at.desc(), ChatMessage.id.desc())
        )
    state = db.scalar(
        select(ChatReadState).where(
            ChatReadState.chat_room_id == room.id,
            ChatReadState.user_id == access.membership.user_id,
        )
    )
    if state is None:
        state = ChatReadState(chat_room_id=room.id, user_id=access.membership.user_id)
        db.add(state)
    should_advance = marker is not None
    if marker is not None and state.last_read_message_id is not None:
        previous = db.get(ChatMessage, state.last_read_message_id)
        if previous is not None:
            should_advance = (as_utc(marker.sent_at), marker.id) > (
                as_utc(previous.sent_at),
                previous.id,
            )
    if marker is not None and should_advance:
        state.last_read_message_id = marker.id
        state.last_read_at = datetime.now(UTC)
    db.commit()
    return ChatUnreadCount(unread_count=unread_count(db, room.id, access.membership.user_id))


@router.delete(
    "/{care_profile_id}/chat/messages/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_message(
    care_profile_id: UUID,
    message_id: UUID,
    db: DbSession,
    access: ProfileMemberAccess,
) -> Response:
    room = get_or_create_default_room(db, access.profile.id)
    message = get_message_or_404(db, room.id, message_id)
    if message.sender_user_id != access.membership.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the sender can delete this message",
        )
    if message.deleted_at is None:
        message.body = None
        message.deleted_at = datetime.now(UTC)
        db.commit()
        await chat_connections.broadcast(
            access.profile.id,
            {
                "type": "message_deleted",
                "message_id": str(message.id),
                "deleted_at": as_utc(message.deleted_at).isoformat(),
            },
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{care_profile_id}/chat/messages/{message_id}/care-event-draft",
    response_model=ChatCareEventDraft,
)
def care_event_draft_from_message(
    care_profile_id: UUID,
    message_id: UUID,
    db: DbSession,
    access: ProfileMemberAccess,
) -> ChatCareEventDraft:
    room = get_or_create_default_room(db, access.profile.id)
    message = get_message_or_404(db, room.id, message_id)
    if message.deleted_at is not None or message.body is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Message was deleted")
    return ChatCareEventDraft(
        source_chat_message_id=message.id,
        occurred_at=as_utc(message.sent_at),
        summary=message.body,
    )


@router.websocket("/{care_profile_id}/chat/ws")
async def chat_websocket(
    websocket: WebSocket,
    care_profile_id: UUID,
    ticket: Annotated[str, Query(min_length=1)],
    db: DbSession,
) -> None:
    issued = websocket_tickets.consume(ticket, care_profile_id)
    if issued is None:
        await websocket.accept()
        await websocket.close(code=4401, reason="Not authenticated")
        return
    membership = db.scalar(
        select(CareMembership).where(
            CareMembership.care_profile_id == care_profile_id,
            CareMembership.user_id == issued.user_id,
        )
    )
    if membership is None:
        await websocket.accept()
        await websocket.close(code=4404, reason="Care profile not found")
        return
    await chat_connections.connect(care_profile_id, websocket)
    await websocket.send_json({"type": "ready", "care_profile_id": str(care_profile_id)})
    try:
        while True:
            payload = await websocket.receive_json()
            if payload.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except (ValueError, WebSocketDisconnect):
        pass
    finally:
        await chat_connections.disconnect(care_profile_id, websocket)
