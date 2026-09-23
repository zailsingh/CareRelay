from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import MedicationDoseStatus, MedicationScheduleType


class MedicationScheduleBase(BaseModel):
    local_time: time
    days_of_week: list[int] = Field(min_length=1, max_length=7)
    active: bool = True
    start_date: date | None = None
    end_date: date | None = None

    @field_validator("local_time")
    @classmethod
    def require_local_clock_time(cls, value: time) -> time:
        if value.tzinfo is not None:
            raise ValueError("local_time must not include a timezone")
        return value.replace(second=0, microsecond=0)

    @field_validator("days_of_week")
    @classmethod
    def validate_days(cls, value: list[int]) -> list[int]:
        if any(day < 0 or day > 6 for day in value):
            raise ValueError("days_of_week values must be between 0 (Monday) and 6 (Sunday)")
        if len(value) != len(set(value)):
            raise ValueError("days_of_week must not contain duplicates")
        return sorted(value)

    @model_validator(mode="after")
    def validate_dates(self) -> "MedicationScheduleBase":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self


class MedicationScheduleCreate(MedicationScheduleBase):
    pass


class MedicationScheduleUpdate(BaseModel):
    local_time: time | None = None
    days_of_week: list[int] | None = Field(default=None, min_length=1, max_length=7)
    active: bool | None = None
    start_date: date | None = None
    end_date: date | None = None

    @field_validator("local_time")
    @classmethod
    def require_local_clock_time(cls, value: time | None) -> time | None:
        if value is not None and value.tzinfo is not None:
            raise ValueError("local_time must not include a timezone")
        return value.replace(second=0, microsecond=0) if value else value

    @field_validator("days_of_week")
    @classmethod
    def validate_days(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return value
        if any(day < 0 or day > 6 for day in value) or len(value) != len(set(value)):
            raise ValueError("days_of_week must contain unique values from 0 to 6")
        return sorted(value)

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> "MedicationScheduleUpdate":
        for field in ("local_time", "days_of_week", "active"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class MedicationScheduleRead(MedicationScheduleBase):
    id: UUID
    medication_id: UUID
    created_at: datetime
    updated_at: datetime


class MedicationBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    strength_text: str | None = Field(default=None, max_length=200)
    form: str | None = Field(default=None, max_length=100)
    instructions_text: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=2000)
    schedule_type: MedicationScheduleType
    start_date: date | None = None
    end_date: date | None = None

    model_config = ConfigDict(str_strip_whitespace=True)

    @model_validator(mode="after")
    def validate_dates(self) -> "MedicationBase":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self


class MedicationCreate(MedicationBase):
    schedules: list[MedicationScheduleCreate] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_schedule_kind(self) -> "MedicationCreate":
        if self.schedule_type == MedicationScheduleType.AS_NEEDED and self.schedules:
            raise ValueError("as-needed medications cannot have recurring schedules")
        return self


class MedicationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    strength_text: str | None = Field(default=None, max_length=200)
    form: str | None = Field(default=None, max_length=100)
    instructions_text: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=2000)
    schedule_type: MedicationScheduleType | None = None
    active: bool | None = None
    start_date: date | None = None
    end_date: date | None = None

    model_config = ConfigDict(str_strip_whitespace=True)

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> "MedicationUpdate":
        for field in ("name", "schedule_type", "active"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class MedicationRead(MedicationBase):
    id: UUID
    care_profile_id: UUID
    active: bool
    created_by_user_id: UUID
    schedules: list[MedicationScheduleRead]
    created_at: datetime
    updated_at: datetime


class DoseRecorder(BaseModel):
    id: UUID
    display_name: str

    model_config = ConfigDict(from_attributes=True)


class MedicationDoseCreate(BaseModel):
    medication_id: UUID
    schedule_id: UUID | None = None
    scheduled_for: datetime | None = None
    status: MedicationDoseStatus
    note: str | None = Field(default=None, max_length=2000)

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("scheduled_for")
    @classmethod
    def require_offset(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("scheduled_for must include a timezone offset")
        return value


class MedicationDoseUpdate(BaseModel):
    status: MedicationDoseStatus | None = None
    note: str | None = Field(default=None, max_length=2000)

    model_config = ConfigDict(str_strip_whitespace=True)


class MedicationDoseRead(BaseModel):
    id: UUID
    medication_id: UUID
    medication_name: str
    medication_strength: str | None
    schedule_id: UUID | None
    scheduled_for: datetime
    scheduled_local_date: date
    scheduled_local_time: time
    scheduled_timezone: str
    status: MedicationDoseStatus
    recorded_by: DoseRecorder
    recorded_at: datetime
    note: str | None
    care_event_id: UUID


class MedicationDoseOccurrence(BaseModel):
    occurrence_key: str
    medication_id: UUID
    medication_name: str
    medication_strength: str | None
    schedule_id: UUID | None
    scheduled_for: datetime
    scheduled_local_date: date
    scheduled_local_time: time
    scheduled_timezone: str
    status: Literal["taken", "missed", "skipped", "not_recorded"]
    dose_record: MedicationDoseRead | None = None
    due_state: Literal["recorded", "elapsed", "upcoming", "as_needed"]
