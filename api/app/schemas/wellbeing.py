from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import SymptomKind


class WellbeingCheckinCreate(BaseModel):
    score: int = Field(ge=0, le=100)
    occurred_at: datetime
    symptoms: list[SymptomKind] = Field(default_factory=list, max_length=len(SymptomKind))
    note: str | None = Field(default=None, max_length=2000)
    voice_transcript: str | None = Field(default=None, max_length=10000)

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("occurred_at")
    @classmethod
    def occurred_at_must_include_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone offset")
        return value

    @field_validator("symptoms")
    @classmethod
    def symptoms_must_be_unique(cls, value: list[SymptomKind]) -> list[SymptomKind]:
        if len(value) != len(set(value)):
            raise ValueError("symptoms must not contain duplicates")
        return value


class WellbeingCheckinUpdate(BaseModel):
    score: int | None = Field(default=None, ge=0, le=100)
    occurred_at: datetime | None = None
    symptoms: list[SymptomKind] | None = Field(default=None, max_length=len(SymptomKind))
    note: str | None = Field(default=None, max_length=2000)
    voice_transcript: str | None = Field(default=None, max_length=10000)

    model_config = ConfigDict(str_strip_whitespace=True)

    @model_validator(mode="after")
    def validate_patch(self) -> "WellbeingCheckinUpdate":
        if "score" in self.model_fields_set and self.score is None:
            raise ValueError("score cannot be null")
        if "occurred_at" in self.model_fields_set:
            if self.occurred_at is None:
                raise ValueError("occurred_at cannot be null")
            if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
                raise ValueError("occurred_at must include a timezone offset")
        if self.symptoms is not None and len(self.symptoms) != len(set(self.symptoms)):
            raise ValueError("symptoms must not contain duplicates")
        return self


class CheckinReporter(BaseModel):
    id: UUID
    display_name: str

    model_config = ConfigDict(from_attributes=True)


class WellbeingCheckinRead(BaseModel):
    id: UUID
    care_profile_id: UUID
    reported_by_user_id: UUID
    reported_by: CheckinReporter
    score: int
    occurred_at: datetime
    symptoms: list[SymptomKind]
    note: str | None
    voice_transcript: str | None
    created_at: datetime
    updated_at: datetime


class DailyWellbeingAverage(BaseModel):
    date: date
    checkin_count: int
    average_score: float | None


class WellbeingSummary(BaseModel):
    start_date: date
    end_date: date
    timezone: str
    checkin_count: int
    latest_score: int | None
    average_score: float | None
    minimum_score: int | None
    maximum_score: int | None
    daily_averages: list[DailyWellbeingAverage]
    symptom_frequency: dict[SymptomKind, int]
