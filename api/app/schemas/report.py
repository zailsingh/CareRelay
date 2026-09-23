from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import CareEventType, MedicationDoseStatus, SymptomKind
from app.schemas.ask import EvidenceReference
from app.schemas.wellbeing import DailyWellbeingAverage


class ReportRequest(BaseModel):
    period: Literal["7d", "30d", "90d", "custom"] = "30d"
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_period(self) -> "ReportRequest":
        if self.period == "custom":
            if self.start_date is None or self.end_date is None:
                raise ValueError("custom reports require start_date and end_date")
            if self.end_date < self.start_date:
                raise ValueError("end_date must be on or after start_date")
            if (self.end_date - self.start_date).days > 366:
                raise ValueError("custom report range cannot exceed 367 days")
        elif self.start_date is not None or self.end_date is not None:
            raise ValueError("start_date and end_date are only valid for a custom report")
        return self


class ReportPeriod(BaseModel):
    start_date: date
    end_date: date
    timezone: str
    description: str


class ReportCareProfile(BaseModel):
    id: UUID
    name: str
    subject_display_name: str


class ReportWellbeing(BaseModel):
    average: float | None
    minimum: int | None
    maximum: int | None
    checkin_count: int
    daily_averages: list[DailyWellbeingAverage]
    trend: Literal["higher", "lower", "stable", "insufficient_data"]
    trend_statement: str
    evidence: list[EvidenceReference]


class ReportSymptom(BaseModel):
    kind: SymptomKind
    label: str
    recorded_count: int
    evidence: list[EvidenceReference]


class ReportEvent(BaseModel):
    event_type: CareEventType
    occurred_at: datetime
    summary: str
    entered_by: str
    source_chat_confirmed: bool
    evidence: list[EvidenceReference]


class ReportEventSummary(BaseModel):
    total_count: int
    activity_count: int
    sleep_count: int
    general_observation_count: int
    items: list[ReportEvent]


class ReportFalls(BaseModel):
    count: int
    items: list[ReportEvent]
    evidence: list[EvidenceReference]


class ReportMedicationDose(BaseModel):
    medication_name: str
    scheduled_local_date: date
    scheduled_local_time: str
    status: MedicationDoseStatus | Literal["not_recorded"]
    evidence: list[EvidenceReference]


class ReportMedications(BaseModel):
    taken: int
    missed: int
    skipped: int
    not_recorded: int
    expected_scheduled_doses: int
    doses: list[ReportMedicationDose]
    evidence: list[EvidenceReference]


class ReportAppointment(BaseModel):
    occurred_at: datetime
    summary: str
    provider: str | None = None
    location: str | None = None
    evidence: list[EvidenceReference]


class CareReport(BaseModel):
    care_profile: ReportCareProfile
    period: ReportPeriod
    generated_at: datetime
    wellbeing: ReportWellbeing
    symptoms: list[ReportSymptom]
    falls: ReportFalls
    medications: ReportMedications
    care_events: ReportEventSummary
    appointments: list[ReportAppointment]
    narrative_summary: str
    narrative_source: Literal["ai", "deterministic"]
    points_to_discuss: list[str]
    evidence: list[EvidenceReference]
    disclaimer: str

    model_config = ConfigDict(from_attributes=True)


class PdfExportMetadata(BaseModel):
    filename: str = Field(min_length=1)
