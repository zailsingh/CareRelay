from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.core.timezones import validate_timezone_name
from app.models.enums import CareRole


class CareProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    timezone: str = Field(default="UTC", min_length=1, max_length=100)
    for_self: bool = False

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("timezone")
    @classmethod
    def timezone_is_valid(cls, value: str) -> str:
        return validate_timezone_name(value)


class CareProfileUpdate(BaseModel):
    subject_user_id: UUID | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=100)

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("timezone")
    @classmethod
    def timezone_is_valid(cls, value: str | None) -> str | None:
        return validate_timezone_name(value) if value is not None else None

    @model_validator(mode="after")
    def timezone_cannot_be_null(self) -> "CareProfileUpdate":
        if "timezone" in self.model_fields_set and self.timezone is None:
            raise ValueError("timezone cannot be null")
        return self


class CareProfileRead(BaseModel):
    id: UUID
    name: str
    role: CareRole
    subject_user_id: UUID | None
    timezone: str
    created_at: datetime


class MembershipCreate(BaseModel):
    email: EmailStr
    role: CareRole

    model_config = ConfigDict(str_strip_whitespace=True)


class MembershipRead(BaseModel):
    id: UUID
    user_id: UUID
    display_name: str
    email: EmailStr | None
    role: CareRole
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MembershipRoleUpdate(BaseModel):
    role: CareRole

    @model_validator(mode="after")
    def disallow_new_cared_person_role(self) -> "MembershipRoleUpdate":
        if self.role == CareRole.CARED_PERSON:
            raise ValueError("cared_person is retained for legacy compatibility only")
        return self
