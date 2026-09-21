from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChatSender(BaseModel):
    id: UUID
    display_name: str

    model_config = ConfigDict(from_attributes=True)


class ChatAttachmentRead(BaseModel):
    id: UUID
    file_name: str
    content_type: str
    byte_size: int

    model_config = ConfigDict(from_attributes=True)


class ChatMessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)

    model_config = ConfigDict(str_strip_whitespace=True)


class ChatMessageRead(BaseModel):
    id: UUID
    chat_room_id: UUID
    sender_user_id: UUID
    sender: ChatSender
    body: str | None
    sent_at: datetime
    edited_at: datetime | None
    deleted_at: datetime | None
    is_deleted: bool
    attachments: list[ChatAttachmentRead]


class ChatMessagePage(BaseModel):
    items: list[ChatMessageRead]
    next_cursor: str | None


class ChatUnreadCount(BaseModel):
    unread_count: int


class ChatWebSocketTicket(BaseModel):
    ticket: str
    expires_at: datetime


class ChatMarkRead(BaseModel):
    through_message_id: UUID | None = None


class ChatCareEventDraft(BaseModel):
    source_chat_message_id: UUID
    occurred_at: datetime
    summary: str
    event_type: None = None
    metadata: dict = Field(default_factory=dict)
