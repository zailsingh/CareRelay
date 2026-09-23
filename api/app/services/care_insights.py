from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.care_event import CareEvent
from app.models.enums import CareEventType, ConfirmationStatus, SymptomKind
from app.models.wellbeing import WellbeingCheckin
from app.schemas.ask import EvidenceReference
from app.services.medications import expected_doses, medication_status_counts
from app.services.wellbeing_summary import as_utc, calculate_wellbeing_summary


class ToolCallLimitExceeded(RuntimeError):
    pass


@dataclass
class ToolResult:
    name: str
    metrics: dict[str, Any]
    evidence: list[EvidenceReference]


class CareDataTools:
    """Permission-scoped, deterministic tools. No raw SQL capability is exposed to an LLM."""

    def __init__(
        self,
        db: Session,
        care_profile_id: UUID,
        timezone_name: str,
        max_calls: int = 4,
    ) -> None:
        self.db = db
        self.care_profile_id = care_profile_id
        self.timezone_name = timezone_name
        self.max_calls = max_calls
        self.calls: list[str] = []

    def _count(self, name: str) -> None:
        if len(self.calls) >= self.max_calls:
            raise ToolCallLimitExceeded("Ask CareRelay tool-call limit exceeded")
        self.calls.append(name)

    def _utc_bounds(self, start_date: date, end_date: date) -> tuple[datetime, datetime]:
        timezone = ZoneInfo(self.timezone_name)
        return (
            datetime.combine(start_date, time.min, timezone).astimezone(UTC),
            datetime.combine(end_date + timedelta(days=1), time.min, timezone).astimezone(UTC),
        )

    def _checkins(self, start_date: date, end_date: date) -> list[WellbeingCheckin]:
        start, end = self._utc_bounds(start_date, end_date)
        return list(
            self.db.scalars(
                select(WellbeingCheckin)
                .options(selectinload(WellbeingCheckin.symptoms))
                .where(
                    WellbeingCheckin.care_profile_id == self.care_profile_id,
                    WellbeingCheckin.occurred_at >= start,
                    WellbeingCheckin.occurred_at < end,
                )
                .order_by(WellbeingCheckin.occurred_at)
            ).all()
        )

    def _events(
        self,
        start_date: date,
        end_date: date,
        event_types: set[CareEventType] | None = None,
    ) -> list[CareEvent]:
        start, end = self._utc_bounds(start_date, end_date)
        query = select(CareEvent).where(
            CareEvent.care_profile_id == self.care_profile_id,
            CareEvent.confirmation_status == ConfirmationStatus.CONFIRMED,
            CareEvent.occurred_at >= start,
            CareEvent.occurred_at < end,
        )
        if event_types:
            query = query.where(CareEvent.event_type.in_(event_types))
        return list(self.db.scalars(query.order_by(CareEvent.occurred_at)).all())

    @staticmethod
    def _checkin_evidence(checkins: list[WellbeingCheckin]) -> list[EvidenceReference]:
        return [
            EvidenceReference(
                record_type="wellbeing_checkin",
                record_id=item.id,
                occurred_at=as_utc(item.occurred_at),
                label=f"Self report: {item.score} / 100",
            )
            for item in checkins
        ]

    @staticmethod
    def _event_evidence(events: list[CareEvent]) -> list[EvidenceReference]:
        return [
            EvidenceReference(
                record_type="care_event",
                record_id=item.id,
                occurred_at=as_utc(item.occurred_at),
                label=f"{item.event_type.value.replace('_', ' ').title()}: {item.summary}",
            )
            for item in events
        ]

    def get_wellbeing_summary(self, start_date: date, end_date: date) -> ToolResult:
        self._count("get_wellbeing_summary")
        summary = calculate_wellbeing_summary(
            self.db, self.care_profile_id, start_date, end_date, self.timezone_name
        )
        checkins = self._checkins(start_date, end_date)
        return ToolResult(
            "get_wellbeing_summary",
            summary.model_dump(mode="json"),
            self._checkin_evidence(checkins),
        )

    def compare_wellbeing_periods(
        self, current_start: date, current_end: date, previous_start: date, previous_end: date
    ) -> ToolResult:
        self._count("compare_wellbeing_periods")
        current = calculate_wellbeing_summary(
            self.db, self.care_profile_id, current_start, current_end, self.timezone_name
        )
        previous = calculate_wellbeing_summary(
            self.db, self.care_profile_id, previous_start, previous_end, self.timezone_name
        )
        difference = None
        if current.average_score is not None and previous.average_score is not None:
            difference = round(current.average_score - previous.average_score, 1)
        checkins = self._checkins(previous_start, current_end)
        return ToolResult(
            "compare_wellbeing_periods",
            {
                "current_average": current.average_score,
                "current_checkin_count": current.checkin_count,
                "previous_average": previous.average_score,
                "previous_checkin_count": previous.checkin_count,
                "difference": difference,
            },
            self._checkin_evidence(checkins),
        )

    def get_symptom_frequency(
        self, start_date: date, end_date: date, symptom: SymptomKind | None = None
    ) -> ToolResult:
        self._count("get_symptom_frequency")
        checkins = self._checkins(start_date, end_date)
        counts: Counter[str] = Counter(
            item.kind.value for checkin in checkins for item in checkin.symptoms
        )
        relevant = [
            checkin
            for checkin in checkins
            if symptom is None or any(item.kind == symptom for item in checkin.symptoms)
        ]
        frequencies = (
            {symptom.value: counts[symptom.value]}
            if symptom
            else {kind.value: counts[kind.value] for kind in SymptomKind}
        )
        return ToolResult(
            "get_symptom_frequency",
            {"symptom_frequency": frequencies, "checkin_count": len(checkins)},
            self._checkin_evidence(relevant),
        )

    def get_care_events(self, start_date: date, end_date: date) -> ToolResult:
        self._count("get_care_events")
        events = self._events(start_date, end_date)
        return ToolResult(
            "get_care_events",
            {
                "event_count": len(events),
                "events": [
                    {"event_type": event.event_type.value, "summary": event.summary}
                    for event in events
                ],
            },
            self._event_evidence(events),
        )

    def get_event_frequency(
        self, start_date: date, end_date: date, event_type: CareEventType | None = None
    ) -> ToolResult:
        self._count("get_event_frequency")
        events = self._events(start_date, end_date, {event_type} if event_type else None)
        counts = Counter(event.event_type.value for event in events)
        return ToolResult(
            "get_event_frequency",
            {
                "event_frequency": (
                    {event_type.value: counts[event_type.value]} if event_type else dict(counts)
                )
            },
            self._event_evidence(events),
        )

    def get_activity_summary(self, start_date: date, end_date: date) -> ToolResult:
        self._count("get_activity_summary")
        events = self._events(start_date, end_date, {CareEventType.ACTIVITY})
        minutes = sum(int(event.structured_data.get("duration_minutes", 0)) for event in events)
        return ToolResult(
            "get_activity_summary",
            {"activity_count": len(events), "recorded_duration_minutes": minutes},
            self._event_evidence(events),
        )

    def get_medication_event_summary(self, start_date: date, end_date: date) -> ToolResult:
        """Summarize authoritative doses plus unlinked legacy medication events."""
        self._count("get_medication_summary")
        occurrences = expected_doses(
            self.db,
            self.care_profile_id,
            self.timezone_name,
            start_date,
            end_date,
        )
        linked_event_ids = {
            item.record.care_event_id for item in occurrences if item.record is not None
        }
        legacy_events = [
            event
            for event in self._events(
                start_date,
                end_date,
                {
                    CareEventType.MEDICATION_TAKEN,
                    CareEventType.MEDICATION_MISSED,
                    CareEventType.MEDICATION_SKIPPED,
                },
            )
            if event.id not in linked_event_ids
        ]
        statuses = medication_status_counts(occurrences)
        legacy_counts = Counter(event.event_type for event in legacy_events)
        statuses["taken"] += legacy_counts[CareEventType.MEDICATION_TAKEN]
        statuses["missed"] += legacy_counts[CareEventType.MEDICATION_MISSED]
        statuses["skipped"] += legacy_counts[CareEventType.MEDICATION_SKIPPED]
        dose_evidence = [
            EvidenceReference(
                record_type="medication_dose",
                record_id=item.record.id,
                occurred_at=as_utc(item.record.recorded_at),
                label=(
                    f"{item.medication.name}: {item.record.status.value.replace('_', ' ')} "
                    f"for {item.scheduled_local_date.isoformat()} "
                    f"{item.scheduled_local_time.isoformat(timespec='minutes')}"
                ),
            )
            for item in occurrences
            if item.record is not None
        ]
        medication_evidence: dict[UUID, EvidenceReference] = {}
        for item in occurrences:
            if item.record is None:
                medication_evidence[item.medication.id] = EvidenceReference(
                    record_type="medication",
                    record_id=item.medication.id,
                    occurred_at=item.scheduled_for,
                    label=f"{item.medication.name}: scheduled dose with no recorded outcome",
                )
        rows = [
            {
                "medication_id": str(item.medication.id),
                "medication_name": item.medication.name,
                "strength_text": item.medication.strength_text,
                "schedule_id": str(item.schedule.id) if item.schedule else None,
                "scheduled_local_date": item.scheduled_local_date.isoformat(),
                "scheduled_local_time": item.scheduled_local_time.isoformat(timespec="minutes"),
                "status": item.record.status.value if item.record else "not_recorded",
                "recorded_by": (
                    item.record.recorded_by.display_name if item.record is not None else None
                ),
                "recorded_at": (
                    as_utc(item.record.recorded_at).isoformat() if item.record is not None else None
                ),
            }
            for item in occurrences
        ]
        return ToolResult(
            "get_medication_summary",
            {
                "taken": statuses["taken"],
                "missed": statuses["missed"],
                "skipped": statuses["skipped"],
                "not_recorded": statuses["not_recorded"],
                "expected_dose_count": len(
                    [item for item in occurrences if item.schedule is not None]
                ),
                "dose_statuses": rows,
                "legacy_medication_event_count": len(legacy_events),
            },
            dose_evidence
            + list(medication_evidence.values())
            + self._event_evidence(legacy_events),
        )

    def get_legacy_medication_event_summary(self, start_date: date, end_date: date) -> ToolResult:
        """Compatibility helper retained for callers that need CareEvent-only history."""
        self._count("get_legacy_medication_event_summary")
        events = self._events(
            start_date,
            end_date,
            {
                CareEventType.MEDICATION_TAKEN,
                CareEventType.MEDICATION_MISSED,
                CareEventType.MEDICATION_SKIPPED,
            },
        )
        counts = Counter(event.event_type.value for event in events)
        return ToolResult(
            "get_legacy_medication_event_summary",
            {
                "medication_taken": counts[CareEventType.MEDICATION_TAKEN.value],
                "medication_missed": counts[CareEventType.MEDICATION_MISSED.value],
                "medication_skipped": counts[CareEventType.MEDICATION_SKIPPED.value],
            },
            self._event_evidence(events),
        )

    def get_recent_changes(self, start_date: date, end_date: date) -> ToolResult:
        self._count("get_recent_changes")
        checkins = self._checkins(start_date, end_date)
        events = self._events(start_date, end_date)
        first = checkins[0].score if checkins else None
        latest = checkins[-1].score if checkins else None
        return ToolResult(
            "get_recent_changes",
            {
                "first_score": first,
                "latest_score": latest,
                "score_change": latest - first
                if first is not None and latest is not None
                else None,
                "checkin_count": len(checkins),
                "event_count": len(events),
            },
            self._checkin_evidence(checkins) + self._event_evidence(events),
        )
