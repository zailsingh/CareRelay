import json
import re
import textwrap
from collections import Counter, defaultdict
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.care_event import CareEvent
from app.models.care_profile import CareProfile
from app.models.enums import CareEventType, ConfirmationStatus, SymptomKind
from app.models.wellbeing import WellbeingCheckin
from app.schemas.ask import EvidenceReference
from app.schemas.report import (
    CareReport,
    ReportAppointment,
    ReportCareProfile,
    ReportEvent,
    ReportEventSummary,
    ReportFalls,
    ReportMedicationDose,
    ReportMedications,
    ReportPeriod,
    ReportRequest,
    ReportSymptom,
    ReportWellbeing,
)
from app.services.ai_provider import AIContext, AIProvider, AIProviderError
from app.services.medications import expected_doses, medication_status_counts
from app.services.wellbeing_summary import as_utc, calculate_wellbeing_summary

REPORT_DISCLAIMER = (
    "CareRelay summarises information recorded by the person and their care network. "
    "It does not provide a diagnosis or replace professional medical advice."
)


def resolve_report_period(request: ReportRequest, timezone_name: str) -> ReportPeriod:
    today = datetime.now(ZoneInfo(timezone_name)).date()
    if request.period == "custom":
        assert request.start_date is not None and request.end_date is not None
        return ReportPeriod(
            start_date=request.start_date,
            end_date=request.end_date,
            timezone=timezone_name,
            description=f"{request.start_date.isoformat()} to {request.end_date.isoformat()}",
        )
    days = int(request.period.removesuffix("d"))
    return ReportPeriod(
        start_date=today - timedelta(days=days - 1),
        end_date=today,
        timezone=timezone_name,
        description=f"Last {days} days",
    )


def _utc_bounds(period: ReportPeriod) -> tuple[datetime, datetime]:
    timezone = ZoneInfo(period.timezone)
    return (
        datetime.combine(period.start_date, time.min, timezone).astimezone(UTC),
        datetime.combine(period.end_date + timedelta(days=1), time.min, timezone).astimezone(UTC),
    )


def _checkin_evidence(item: WellbeingCheckin) -> EvidenceReference:
    return EvidenceReference(
        record_type="wellbeing_checkin",
        record_id=item.id,
        occurred_at=as_utc(item.occurred_at),
        label=f"Self report: {item.score} / 100",
    )


def _event_evidence(item: CareEvent) -> EvidenceReference:
    return EvidenceReference(
        record_type="care_event",
        record_id=item.id,
        occurred_at=as_utc(item.occurred_at),
        label=f"{item.event_type.value.replace('_', ' ').title()}: {item.summary}",
    )


def _report_event(item: CareEvent) -> ReportEvent:
    evidence = _event_evidence(item)
    return ReportEvent(
        event_type=item.event_type,
        occurred_at=as_utc(item.occurred_at),
        summary=item.summary,
        entered_by=item.entered_by.display_name,
        source_chat_confirmed=item.source_chat_message_id is not None,
        evidence=[evidence],
    )


def _trend(checkins: list[WellbeingCheckin]) -> tuple[str, str]:
    if len(checkins) < 2:
        return "insufficient_data", "Not enough self reports were recorded to calculate a trend."
    change = checkins[-1].score - checkins[0].score
    if change > 0:
        return "higher", f"The latest self report was {change} points higher than the first."
    if change < 0:
        return "lower", f"The latest self report was {abs(change)} points lower than the first."
    return "stable", "The first and latest self-reported wellbeing scores were the same."


def _deduplicate(items: list[EvidenceReference]) -> list[EvidenceReference]:
    unique = {(item.record_type, item.record_id): item for item in items}
    return sorted(unique.values(), key=lambda item: item.occurred_at, reverse=True)


def _deterministic_narrative(
    wellbeing: ReportWellbeing,
    symptoms: list[ReportSymptom],
    falls: ReportFalls,
    medications: ReportMedications,
    events: ReportEventSummary,
    appointments: list[ReportAppointment],
) -> str:
    parts = []
    if wellbeing.checkin_count:
        parts.append(
            f"{wellbeing.checkin_count} self-reported wellbeing check-ins were recorded, "
            f"with an average of {wellbeing.average} out of 100."
        )
    else:
        parts.append("No self-reported wellbeing check-ins were recorded during this period.")
    recorded_symptoms = [item for item in symptoms if item.recorded_count]
    if recorded_symptoms:
        summary = ", ".join(
            f"{item.label.lower()} {item.recorded_count}"
            for item in sorted(recorded_symptoms, key=lambda item: -item.recorded_count)[:3]
        )
        parts.append(f"The most frequently recorded symptoms were {summary}.")
    else:
        parts.append("No symptoms were recorded during this period.")
    parts.append(
        f"{falls.count} recorded fall{'s' if falls.count != 1 else ''}, "
        f"{events.total_count} confirmed care event{'s' if events.total_count != 1 else ''}, "
        f"and {len(appointments)} appointment record{'s' if len(appointments) != 1 else ''} "
        "were included."
    )
    parts.append(
        "Medication records show "
        f"{medications.taken} taken, {medications.missed} explicitly missed, "
        f"{medications.skipped} skipped, and {medications.not_recorded} with no recorded outcome."
    )
    return " ".join(parts)


def _points_to_discuss(
    symptoms: list[ReportSymptom],
    falls: ReportFalls,
    medications: ReportMedications,
    appointments: list[ReportAppointment],
) -> list[str]:
    points: list[str] = []
    if falls.count:
        points.append(f"Review the {falls.count} recorded fall{'s' if falls.count != 1 else ''}.")
    frequent = [item for item in symptoms if item.recorded_count]
    if frequent:
        top = max(frequent, key=lambda item: item.recorded_count)
        points.append(f"{top.label} was recorded {top.recorded_count} times.")
    if medications.missed or medications.skipped or medications.not_recorded:
        points.append(
            "Medication records include "
            f"{medications.missed} explicitly missed, {medications.skipped} skipped, and "
            f"{medications.not_recorded} with no recorded outcome."
        )
    if appointments:
        plural = "s" if len(appointments) != 1 else ""
        points.append(f"{len(appointments)} appointment record{plural} are included.")
    return points


def _provider_facts(report: CareReport) -> dict[str, Any]:
    return {
        "period": report.period.model_dump(mode="json"),
        "wellbeing": report.wellbeing.model_dump(mode="json", exclude={"evidence"}),
        "symptoms": [
            item.model_dump(mode="json", exclude={"evidence"}) for item in report.symptoms
        ],
        "falls": {"count": report.falls.count},
        "medications": report.medications.model_dump(
            mode="json", exclude={"evidence", "doses"}
        ),
        "care_events": {
            "total_count": report.care_events.total_count,
            "activity_count": report.care_events.activity_count,
            "sleep_count": report.care_events.sleep_count,
            "general_observation_count": report.care_events.general_observation_count,
        },
        "appointment_count": len(report.appointments),
    }


def _validate_narrative_numbers(answer: str, facts: dict[str, Any]) -> None:
    allowed = set(re.findall(r"\d+(?:\.\d+)?", json.dumps(facts))) | {"0", "100"}
    used = set(re.findall(r"\d+(?:\.\d+)?", answer))
    if not used.issubset(allowed):
        raise AIProviderError("AI report narrative contained a number absent from verified facts")


def _validate_narrative_safety(answer: str) -> None:
    lowered = answer.lower()
    unsafe = (
        "diagnos",
        "prescrib",
        "recommend taking",
        "recommend stopping",
        "should take",
        "should stop",
        "should start",
        "should change",
        "caused by",
    )
    if any(term in lowered for term in unsafe):
        raise AIProviderError("AI report narrative crossed the factual safety boundary")


async def build_care_report(
    *,
    db: Session,
    profile: CareProfile,
    request: ReportRequest,
    provider: AIProvider,
) -> CareReport:
    period = resolve_report_period(request, profile.timezone)
    start_utc, end_utc = _utc_bounds(period)
    checkins = list(
        db.scalars(
            select(WellbeingCheckin)
            .options(selectinload(WellbeingCheckin.symptoms))
            .where(
                WellbeingCheckin.care_profile_id == profile.id,
                WellbeingCheckin.occurred_at >= start_utc,
                WellbeingCheckin.occurred_at < end_utc,
            )
            .order_by(WellbeingCheckin.occurred_at)
        ).all()
    )
    events = list(
        db.scalars(
            select(CareEvent)
            .options(selectinload(CareEvent.entered_by))
            .where(
                CareEvent.care_profile_id == profile.id,
                CareEvent.confirmation_status == ConfirmationStatus.CONFIRMED,
                CareEvent.occurred_at >= start_utc,
                CareEvent.occurred_at < end_utc,
            )
            .order_by(CareEvent.occurred_at)
        ).all()
    )
    wellbeing_summary = calculate_wellbeing_summary(
        db, profile.id, period.start_date, period.end_date, profile.timezone
    )
    trend, trend_statement = _trend(checkins)
    wellbeing_evidence = [_checkin_evidence(item) for item in checkins]
    wellbeing = ReportWellbeing(
        average=wellbeing_summary.average_score,
        minimum=wellbeing_summary.minimum_score,
        maximum=wellbeing_summary.maximum_score,
        checkin_count=wellbeing_summary.checkin_count,
        daily_averages=wellbeing_summary.daily_averages,
        trend=trend,
        trend_statement=trend_statement,
        evidence=wellbeing_evidence,
    )

    symptom_evidence: dict[SymptomKind, list[EvidenceReference]] = defaultdict(list)
    symptom_counts: Counter[SymptomKind] = Counter()
    for checkin in checkins:
        for symptom in checkin.symptoms:
            symptom_counts[symptom.kind] += 1
            symptom_evidence[symptom.kind].append(_checkin_evidence(checkin))
    for event in events:
        if event.event_type != CareEventType.SYMPTOM_OBSERVATION:
            continue
        for value in event.structured_data.get("symptoms", []):
            try:
                kind = SymptomKind(value)
            except ValueError:
                continue
            symptom_counts[kind] += 1
            symptom_evidence[kind].append(_event_evidence(event))
    symptoms = [
        ReportSymptom(
            kind=kind,
            label=kind.value.replace("_", " ").title(),
            recorded_count=symptom_counts[kind],
            evidence=_deduplicate(symptom_evidence[kind]),
        )
        for kind in SymptomKind
        if symptom_counts[kind]
    ]

    medication_event_types = {
        CareEventType.MEDICATION_TAKEN,
        CareEventType.MEDICATION_MISSED,
        CareEventType.MEDICATION_SKIPPED,
    }
    report_events = [event for event in events if event.event_type not in medication_event_types]
    event_items = [_report_event(event) for event in report_events]
    care_events = ReportEventSummary(
        total_count=len(report_events),
        activity_count=sum(event.event_type == CareEventType.ACTIVITY for event in report_events),
        sleep_count=sum(
            event.event_type == CareEventType.SLEEP_OBSERVATION for event in report_events
        ),
        general_observation_count=sum(
            event.event_type
            in {CareEventType.FAMILY_OBSERVATION, CareEventType.GENERAL_NOTE}
            for event in report_events
        ),
        items=event_items,
    )
    fall_items = [
        _report_event(event) for event in report_events if event.event_type == CareEventType.FALL
    ]
    falls = ReportFalls(
        count=len(fall_items),
        items=fall_items,
        evidence=[item.evidence[0] for item in fall_items],
    )
    appointments = [
        ReportAppointment(
            occurred_at=as_utc(event.occurred_at),
            summary=event.summary,
            provider=event.structured_data.get("provider"),
            location=event.structured_data.get("location"),
            evidence=[_event_evidence(event)],
        )
        for event in report_events
        if event.event_type == CareEventType.APPOINTMENT
    ]

    occurrences = expected_doses(
        db, profile.id, profile.timezone, period.start_date, period.end_date
    )
    medication_counts = medication_status_counts(occurrences)
    medication_doses: list[ReportMedicationDose] = []
    medication_evidence: list[EvidenceReference] = []
    for occurrence in occurrences:
        if occurrence.record is not None:
            evidence = EvidenceReference(
                record_type="medication_dose",
                record_id=occurrence.record.id,
                occurred_at=as_utc(occurrence.record.recorded_at),
                label=(
                    f"{occurrence.medication.name}: {occurrence.record.status.value} "
                    f"for {occurrence.scheduled_local_date.isoformat()} "
                    f"{occurrence.scheduled_local_time.isoformat(timespec='minutes')}"
                ),
            )
            status = occurrence.record.status
        else:
            evidence = EvidenceReference(
                record_type="medication",
                record_id=occurrence.medication.id,
                occurred_at=occurrence.scheduled_for,
                label=f"{occurrence.medication.name}: scheduled dose with no recorded outcome",
            )
            status = "not_recorded"
        medication_evidence.append(evidence)
        medication_doses.append(
            ReportMedicationDose(
                medication_name=occurrence.medication.name,
                scheduled_local_date=occurrence.scheduled_local_date,
                scheduled_local_time=occurrence.scheduled_local_time.isoformat(timespec="minutes"),
                status=status,
                evidence=[evidence],
            )
        )
    medications = ReportMedications(
        taken=medication_counts["taken"],
        missed=medication_counts["missed"],
        skipped=medication_counts["skipped"],
        not_recorded=medication_counts["not_recorded"],
        expected_scheduled_doses=len(occurrences),
        doses=medication_doses,
        evidence=_deduplicate(medication_evidence),
    )

    deterministic = _deterministic_narrative(
        wellbeing, symptoms, falls, medications, care_events, appointments
    )
    report = CareReport(
        care_profile=ReportCareProfile(
            id=profile.id,
            name=profile.name,
            subject_display_name=(
                profile.subject_user.display_name if profile.subject_user else profile.name
            ),
        ),
        period=period,
        generated_at=datetime.now(UTC),
        wellbeing=wellbeing,
        symptoms=symptoms,
        falls=falls,
        medications=medications,
        care_events=care_events,
        appointments=appointments,
        narrative_summary=deterministic,
        narrative_source="deterministic",
        points_to_discuss=_points_to_discuss(symptoms, falls, medications, appointments),
        evidence=_deduplicate(
            wellbeing_evidence
            + [evidence for symptom in symptoms for evidence in symptom.evidence]
            + [evidence for item in event_items for evidence in item.evidence]
            + medication_evidence
        ),
        disclaimer=REPORT_DISCLAIMER,
    )
    facts = _provider_facts(report)
    try:
        output = await provider.generate(
            AIContext(
                question="Write a concise factual care report narrative from verified facts only.",
                deterministic_answer=deterministic,
                facts=facts,
                safety_note=REPORT_DISCLAIMER,
            )
        )
        answer = output.answer.strip()
        _validate_narrative_numbers(answer, facts)
        _validate_narrative_safety(answer)
        report.narrative_summary = answer
        report.narrative_source = "ai"
    except (AIProviderError, ValidationError, ValueError, KeyError, TypeError):
        pass
    return report


def _pdf_lines(report: CareReport) -> list[str]:
    lines = [
        "CARERELAY",
        "CARE RELAY SUMMARY",
        f"For: {report.care_profile.subject_display_name}",
        (
            f"Period: {report.period.start_date} to {report.period.end_date} "
            f"({report.period.timezone})"
        ),
        f"Generated: {report.generated_at.astimezone(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "NARRATIVE SUMMARY",
        report.narrative_summary,
        "",
        "SELF-REPORTED WELLBEING",
    ]
    if report.wellbeing.checkin_count:
        lines.extend(
            [
                f"Average self-reported wellbeing: {report.wellbeing.average} / 100",
                f"Check-ins: {report.wellbeing.checkin_count}",
                f"Recorded range: {report.wellbeing.minimum} to {report.wellbeing.maximum} / 100",
                report.wellbeing.trend_statement,
            ]
        )
    else:
        lines.append("No self-reported wellbeing check-ins were recorded during this period.")
    lines.extend(["", "RECORDED SYMPTOMS"])
    lines.extend(
        [f"{item.label}: recorded {item.recorded_count} times" for item in report.symptoms]
        or ["No symptoms were recorded during this period."]
    )
    lines.extend(
        [
            "",
            "CARE EVENTS",
            f"Falls recorded: {report.falls.count}",
            f"Activity records: {report.care_events.activity_count}",
            f"Sleep observations: {report.care_events.sleep_count}",
        ]
    )
    lines.extend(
        f"{item.occurred_at.date()}: {item.event_type.value.replace('_', ' ')} - {item.summary}"
        for item in report.care_events.items
    )
    lines.extend(
        [
            "",
            "MEDICATION RECORD",
            f"Taken: {report.medications.taken}",
            f"Explicitly missed: {report.medications.missed}",
            f"Skipped: {report.medications.skipped}",
            f"No recorded outcome: {report.medications.not_recorded}",
            "",
            "APPOINTMENTS / NOTES",
        ]
    )
    lines.extend(
        f"{item.occurred_at.date()}: {item.summary}"
        + (f" - {item.provider}" if item.provider else "")
        for item in report.appointments
    )
    if not report.appointments:
        lines.append("No appointments were recorded during this period.")
    lines.extend(["", "POINTS TO DISCUSS"])
    lines.extend(report.points_to_discuss or ["No additional recorded points were identified."])
    lines.extend(["", report.disclaimer])
    return lines


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def render_report_pdf(report: CareReport) -> bytes:
    wrapped = [part for line in _pdf_lines(report) for part in (textwrap.wrap(line, 90) or [""])]
    page_size = 48
    pages = [wrapped[index : index + page_size] for index in range(0, len(wrapped), page_size)]
    objects: list[bytes] = [b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>", b""]
    page_ids: list[int] = []
    for page_number, lines in enumerate(pages, 1):
        content_lines = ["BT", "/F1 10 Tf", "50 790 Td", "14 TL"]
        for line in lines:
            content_lines.append(f"({_pdf_escape(line)}) Tj")
            content_lines.append("T*")
        content_lines.extend(["", f"(Page {page_number} of {len(pages)}) Tj", "ET"])
        content = "\n".join(content_lines).encode("latin-1", errors="replace")
        content_id = len(objects) + 1
        objects.append(
            f"<< /Length {len(content)} >>\nstream\n".encode()
            + content
            + b"\nendstream"
        )
        page_id = len(objects) + 1
        page_ids.append(page_id)
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] "
                f"/Resources << /Font << /F1 1 0 R >> >> /Contents {content_id} 0 R >>"
            ).encode()
        )
    objects[1] = (
        f"<< /Type /Pages /Kids [{' '.join(f'{item} 0 R' for item in page_ids)}] "
        f"/Count {len(page_ids)} >>"
    ).encode()
    catalog_id = len(objects) + 1
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    result = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_id, value in enumerate(objects, 1):
        offsets.append(len(result))
        result.extend(f"{object_id} 0 obj\n".encode() + value + b"\nendobj\n")
    xref = len(result)
    result.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    result.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(result)
