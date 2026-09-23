from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import CareRole


class InvitationCreate(BaseModel):
    invited_email: EmailStr
    intended_role: Literal["family", "carer"] = "family"
    is_subject_invite: bool = False

    model_config = ConfigDict(str_strip_whitespace=True)


class InvitationRead(BaseModel):
    id: UUID
    care_profile_id: UUID
    invited_email: EmailStr
    intended_role: CareRole
    is_subject_invite: bool
    status: Literal["pending", "accepted", "expired", "revoked"]
    expires_at: datetime
    accepted_at: datetime | None
    email_sent_at: datetime | None
    delivery_status: Literal["sent", "failed", "pending"]
    accept_url: str | None = None
    created_at: datetime


class InvitationAccept(BaseModel):
    token: str = Field(min_length=20, max_length=500)


class InvitationAcceptResult(BaseModel):
    care_profile_id: UUID
    membership_id: UUID
    role: CareRole
    subject_linked: bool
