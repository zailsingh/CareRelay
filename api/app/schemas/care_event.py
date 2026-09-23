from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import (
    CareEventSource,
    CareEventType,
    ConfirmationStatus,
    MedicationDoseStatus,
    SymptomKind,
)


class MetadataBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FamilyObservationMetadata(MetadataBase):
    context: str | None = Field(default=None, max_length=200)


class SymptomObservationMetadata(MetadataBase):
    symptoms: list[SymptomKind] = Field(default_factory=list, max_length=len(SymptomKind))
    severity: str | None = Field(default=None, pattern="^(mild|moderate|severe)$")

    @field_validator("symptoms")
    @classmethod
    def unique_symptoms(cls, value: list[SymptomKind]) -> list[SymptomKind]:
        if len(value) != len(set(value)):
            raise ValueError("symptoms must not contain duplicates")
        return value


class MedicationMetadata(MetadataBase):
    medication_name: str | None = Field(default=None, max_length=200)
    dose: str | None = Field(default=None, max_length=100)
    medication_id: UUID | None = None
    medication_dose_id: UUID | None = None
    scheduled_local_date: date | None = None
    scheduled_local_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    dose_status: MedicationDoseStatus | None = None


class FallMetadata(MetadataBase):
    injury_observed: bool | None = None
    assistance_required: bool | None = None


class ActivityMetadata(MetadataBase):
    activity: str | None = Field(default=None, max_length=200)
    duration_minutes: int | None = Field(default=None, ge=0, le=1440)


class SleepObservationMetadata(MetadataBase):
    duration_hours: float | None = Field(default=None, ge=0, le=24)
    quality: str | None = Field(default=None, pattern="^(poor|fair|good)$")


class AppointmentMetadata(MetadataBase):
    provider: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=300)


class GeneralNoteMetadata(MetadataBase):
    category: str | None = Field(default=None, max_length=100)


METADATA_MODELS: dict[CareEventType, type[MetadataBase]] = {
    CareEventType.FAMILY_OBSERVATION: FamilyObservationMetadata,
    CareEventType.SYMPTOM_OBSERVATION: SymptomObservationMetadata,
    CareEventType.MEDICATION_TAKEN: MedicationMetadata,
    CareEventType.MEDICATION_MISSED: MedicationMetadata,
    CareEventType.MEDICATION_SKIPPED: MedicationMetadata,
    CareEventType.FALL: FallMetadata,
    CareEventType.ACTIVITY: ActivityMetadata,
    CareEventType.SLEEP_OBSERVATION: SleepObservationMetadata,
    CareEventType.APPOINTMENT: AppointmentMetadata,
    CareEventType.GENERAL_NOTE: GeneralNoteMetadata,
}


def validate_metadata(event_type: CareEventType, value: dict[str, Any] | None) -> dict[str, Any]:
    validated = METADATA_MODELS[event_type].model_validate(value or {})
    return validated.model_dump(mode="json", exclude_none=True)


class CareEventCreate(BaseModel):
    event_type: CareEventType
    occurred_at: datetime
    summary: str = Field(min_length=1, max_length=2000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    confirmation_status: ConfirmationStatus = ConfirmationStatus.CONFIRMED
    source_chat_message_id: UUID | None = None

    model_config = ConfigDict(str_strip_whitespace=True)

    @model_validator(mode="after")
    def validate_payload(self) -> "CareEventCreate":
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone offset")
        self.metadata = validate_metadata(self.event_type, self.metadata)
        return self


class CareEventUpdate(BaseModel):
    event_type: CareEventType | None = None
    occurred_at: datetime | None = None
    summary: str | None = Field(default=None, min_length=1, max_length=2000)
    metadata: dict[str, Any] | None = None
    confirmation_status: ConfirmationStatus | None = None

    model_config = ConfigDict(str_strip_whitespace=True)

    @model_validator(mode="after")
    def validate_payload(self) -> "CareEventUpdate":
        for required in ("event_type", "occurred_at", "summary", "confirmation_status"):
            if required in self.model_fields_set and getattr(self, required) is None:
                raise ValueError(f"{required} cannot be null")
        if self.occurred_at is not None and (
            self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None
        ):
            raise ValueError("occurred_at must include a timezone offset")
        return self


class EventEnteredBy(BaseModel):
    id: UUID
    display_name: str

    model_config = ConfigDict(from_attributes=True)


class CareEventRead(BaseModel):
    id: UUID
    care_profile_id: UUID
    event_type: CareEventType
    occurred_at: datetime
    entered_by_user_id: UUID
    entered_by: EventEnteredBy
    source: CareEventSource
    summary: str
    metadata: dict[str, Any]
    confirmation_status: ConfirmationStatus
    source_chat_message_id: UUID | None
    created_at: datetime
    updated_at: datetime


class EventOrdering(StrEnum):
    NEWEST = "newest"
    OLDEST = "oldest"
