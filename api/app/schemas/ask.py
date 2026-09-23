from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)

    model_config = ConfigDict(str_strip_whitespace=True)


class EvidenceReference(BaseModel):
    record_type: Literal["wellbeing_checkin", "care_event", "medication", "medication_dose"]
    record_id: UUID
    occurred_at: datetime
    label: str


class AskPeriod(BaseModel):
    start_date: date
    end_date: date
    timezone: str
    description: str


class AskVisualization(BaseModel):
    type: Literal["wellbeing_summary"]
    average: float
    checkin_count: int
    daily_averages: list[dict[str, Any]]


class AskDiagnostics(BaseModel):
    provider: str
    model: str
    tools_used: list[str]
    tool_call_count: int


class AskResponse(BaseModel):
    answer: str
    metrics: dict[str, Any]
    evidence: list[EvidenceReference]
    period: AskPeriod
    visualization: AskVisualization | None = None
    diagnostics: AskDiagnostics


class ProviderOutput(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)

    model_config = ConfigDict(extra="forbid")
