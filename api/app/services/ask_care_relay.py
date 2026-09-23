import json
import re
from datetime import date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.enums import CareEventType, SymptomKind
from app.schemas.ask import (
    AskDiagnostics,
    AskPeriod,
    AskResponse,
    AskVisualization,
    EvidenceReference,
    ProviderOutput,
)
from app.services.ai_provider import AIContext, AIProvider, AIProviderError
from app.services.care_insights import CareDataTools, ToolResult

SAFETY_NOTE = (
    "CareRelay summarizes recorded information only. It does not diagnose conditions, "
    "assess clinical significance, or recommend treatment or medication changes."
)


def _asks_for_medical_advice(question: str) -> bool:
    """Keep clinical interpretation and treatment decisions outside the AI provider."""
    lowered = question.lower()
    direct_terms = (
        "diagnos",
        "prescrib",
        "treatment",
        "clinical significance",
        "medical significance",
        "is it serious",
        "is this serious",
        "is it dangerous",
        "is this dangerous",
        "what caused",
        "what causes",
        "what do i do",
        "what should i do",
        "make up",
        "catch-up",
        "catch up",
        "double dose",
        "take two",
    )
    if any(term in lowered for term in direct_terms):
        return True

    subject = r"(?:i|we|mum|mom|dad|she|he|they)"
    if re.search(rf"\bshould\s+{subject}\b", lowered):
        return True
    if re.search(
        rf"\b(?:can|could)\s+{subject}\b.*\b(?:take|stop|start|change|adjust|increase|decrease)\b",
        lowered,
    ):
        return True
    return bool(
        re.search(
            r"\b(?:stop|start|change|adjust|increase|decrease)\b.*"
            r"\b(?:medication|medicine|dose|dosage)\b",
            lowered,
        )
    )


def _period(question: str, timezone_name: str) -> tuple[date, date, str]:
    today = datetime.now(ZoneInfo(timezone_name)).date()
    lowered = question.lower()
    if "yesterday" in lowered:
        yesterday = today - timedelta(days=1)
        return yesterday, yesterday, "Yesterday"
    if "today" in lowered:
        return today, today, "Today"
    if any(term in lowered for term in ("this morning", "morning medication", "morning dose")):
        return today, today, "Today"
    if "tonight" in lowered or "evening medication" in lowered or "evening dose" in lowered:
        return today, today, "Today"
    if "since monday" in lowered:
        start = today - timedelta(days=today.weekday())
        return start, today, "Since Monday"
    if "this week" in lowered and "last week" not in lowered:
        start = today - timedelta(days=today.weekday())
        return start, today, "This week"
    days = (
        30
        if any(term in lowered for term in ("30 day", "recent", "symptom", "dizz", "fall"))
        else 7
    )
    return today - timedelta(days=days - 1), today, f"Last {days} days"


def _deduplicate_evidence(results: list[ToolResult]) -> list[EvidenceReference]:
    evidence: dict[tuple[str, UUID], EvidenceReference] = {}
    for result in results:
        for item in result.evidence:
            evidence[(item.record_type, item.record_id)] = item
    return sorted(evidence.values(), key=lambda item: item.occurred_at, reverse=True)


def _fallback_answer(
    results: list[ToolResult],
    period: str,
    medical: bool,
    question: str,
) -> str:
    by_name = {result.name: result for result in results}
    answer: str
    if "compare_wellbeing_periods" in by_name:
        data = by_name["compare_wellbeing_periods"].metrics
        if data["current_average"] is None or data["previous_average"] is None:
            answer = "There is not enough self-reported wellbeing data to compare both weeks."
        else:
            direction = (
                "higher"
                if data["difference"] > 0
                else "lower"
                if data["difference"] < 0
                else "the same"
            )
            answer = (
                f"This week's average self-reported wellbeing was {data['current_average']} / 100, "
                f"compared with {data['previous_average']} / 100 last week. It was {direction} "
                f"by {abs(data['difference'])} points."
            )
    elif "get_symptom_frequency" in by_name:
        data = by_name["get_symptom_frequency"].metrics["symptom_frequency"]
        nonzero = [(name, count) for name, count in data.items() if count]
        if not nonzero:
            answer = f"No matching symptoms were recorded during {period.lower()}."
        else:
            ordered = sorted(nonzero, key=lambda item: (-item[1], item[0]))
            answer = (
                "Recorded symptom frequency: "
                + ", ".join(f"{name.replace('_', ' ')} {count}" for name, count in ordered)
                + "."
            )
    elif "get_event_frequency" in by_name:
        frequencies = by_name["get_event_frequency"].metrics["event_frequency"]
        count = sum(frequencies.values())
        verb = "events were" if count != 1 else "event was"
        answer = f"{count} matching confirmed care {verb} recorded during {period.lower()}."
    elif "get_medication_summary" in by_name:
        data = by_name["get_medication_summary"].metrics
        dose_rows = data["dose_statuses"]
        lowered = question.lower()
        if "morning" in lowered:
            dose_rows = [row for row in dose_rows if int(row["scheduled_local_time"][:2]) < 12]
        elif "evening" in lowered or "tonight" in lowered:
            dose_rows = [row for row in dose_rows if int(row["scheduled_local_time"][:2]) >= 17]
        if len(dose_rows) == 1:
            row = dose_rows[0]
            clock = row["scheduled_local_time"]
            if row["status"] == "not_recorded":
                answer = (
                    f"There is no dose record for {row['medication_name']} scheduled at "
                    f"{clock} on {row['scheduled_local_date']}."
                )
            else:
                answer = (
                    f"{row['medication_name']} scheduled at {clock} on "
                    f"{row['scheduled_local_date']} was recorded as {row['status']}"
                    + (f" by {row['recorded_by']}." if row["recorded_by"] else ".")
                )
        elif not dose_rows and not data["legacy_medication_event_count"]:
            answer = f"There are no scheduled or recorded medication doses for {period.lower()}."
        else:
            answer = (
                f"Medication records for {period.lower()}: {data['taken']} taken, "
                f"{data['missed']} missed, and {data['skipped']} skipped. "
                f"{data['not_recorded']} expected doses have no recorded outcome."
            )
    elif "get_recent_changes" in by_name:
        data = by_name["get_recent_changes"].metrics
        if data["checkin_count"] == 0 and data["event_count"] == 0:
            answer = (
                f"There is not enough recorded information to identify changes {period.lower()}."
            )
        else:
            score_text = (
                f" Self-reported wellbeing changed by {data['score_change']} points "
                "from the first to latest report."
                if data["score_change"] is not None
                else ""
            )
            answer = (
                f"There were {data['checkin_count']} self reports and "
                f"{data['event_count']} confirmed care events.{score_text}"
            )
    else:
        wellbeing = by_name.get("get_wellbeing_summary")
        events = by_name.get("get_care_events")
        if wellbeing and wellbeing.metrics["checkin_count"]:
            data = wellbeing.metrics
            answer = (
                f"Average self-reported wellbeing was {data['average_score']} / 100 across "
                f"{data['checkin_count']} check-ins during {period.lower()}. "
                "The recorded range was "
                f"{data['minimum_score']} to {data['maximum_score']} / 100."
            )
            if events:
                answer += f" There were also {events.metrics['event_count']} confirmed care events."
        elif events and events.metrics["event_count"]:
            answer = (
                f"No self reports were recorded, but {events.metrics['event_count']} "
                f"confirmed care events were recorded during {period.lower()}."
            )
        else:
            answer = f"There is not enough recorded information to answer for {period.lower()}."
    if medical:
        if "get_medication_summary" in by_name:
            answer += (
                " I cannot diagnose or recommend treatment. I cannot advise starting, "
                "stopping, changing, or making up a dose. "
                "Please ask a qualified clinician or pharmacist, or follow the medication's "
                "approved instructions."
            )
        else:
            answer += (
                " I cannot diagnose or recommend treatment; consider discussing these recorded "
                "facts with a qualified clinician."
            )
    return answer


def _validate_provider_numbers(answer: str, facts: dict, period: AskPeriod) -> None:
    supplied = json.dumps({"facts": facts, "period": period.model_dump(mode="json")})
    allowed = set(re.findall(r"\d+(?:\.\d+)?", supplied))
    allowed.update({"0", "100"})
    used = set(re.findall(r"\d+(?:\.\d+)?", answer))
    if not used.issubset(allowed):
        raise AIProviderError("AI response contained a number not present in verified facts")


async def answer_question(
    *,
    db: Session,
    care_profile_id: UUID,
    timezone_name: str,
    question: str,
    provider: AIProvider,
    max_tool_calls: int,
) -> AskResponse:
    lowered = question.lower()
    start, end, description = _period(question, timezone_name)
    tools = CareDataTools(db, care_profile_id, timezone_name, max_tool_calls)
    results: list[ToolResult]

    if "this week" in lowered and "last week" in lowered:
        today = end
        current_start = today - timedelta(days=today.weekday())
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=6)
        results = [
            tools.compare_wellbeing_periods(current_start, today, previous_start, previous_end)
        ]
        start, description = previous_start, "This week compared with last week"
    elif "symptom" in lowered or "dizz" in lowered:
        symptom = next(
            (kind for kind in SymptomKind if kind.value.replace("_", " ") in lowered), None
        )
        results = [tools.get_symptom_frequency(start, end, symptom)]
    elif "fall" in lowered:
        results = [tools.get_event_frequency(start, end, CareEventType.FALL)]
    elif "activity" in lowered or "walk" in lowered:
        results = [tools.get_activity_summary(start, end)]
    elif any(term in lowered for term in ("medication", "medicine", "dose", "tablet")):
        results = [tools.get_medication_event_summary(start, end)]
    elif "changed" in lowered or "change" in lowered:
        results = [tools.get_recent_changes(start, end)]
    else:
        results = [tools.get_wellbeing_summary(start, end), tools.get_care_events(start, end)]

    metrics = {result.name: result.metrics for result in results}
    evidence = _deduplicate_evidence(results)
    period = AskPeriod(
        start_date=start,
        end_date=end,
        timezone=timezone_name,
        description=description,
    )
    medical = _asks_for_medical_advice(question)
    deterministic = _fallback_answer(results, description, medical, question)
    insufficient = not evidence
    medication_question = any(result.name == "get_medication_summary" for result in results)
    if insufficient or medical or medication_question:
        # Medical-advice prompts never reach a generative provider. The user still receives
        # useful, deterministic record context plus the clinical boundary from the fallback.
        answer = deterministic
    else:
        try:
            raw_output = await provider.generate(
                AIContext(
                    question=question,
                    deterministic_answer=deterministic,
                    facts=metrics,
                    safety_note=SAFETY_NOTE,
                )
            )
            output = ProviderOutput.model_validate(raw_output)
        except ValidationError as exc:
            raise AIProviderError("AI response did not match the required schema") from exc
        _validate_provider_numbers(output.answer, metrics, period)
        answer = output.answer
        if medical and "cannot diagnose" not in answer.lower():
            answer += (
                " I cannot diagnose or recommend treatment; consider discussing these recorded "
                "facts with a qualified clinician."
            )

    wellbeing = next((result for result in results if result.name == "get_wellbeing_summary"), None)
    visualization = None
    if wellbeing and wellbeing.metrics["average_score"] is not None:
        visualization = AskVisualization(
            type="wellbeing_summary",
            average=wellbeing.metrics["average_score"],
            checkin_count=wellbeing.metrics["checkin_count"],
            daily_averages=wellbeing.metrics["daily_averages"],
        )
    return AskResponse(
        answer=answer,
        metrics=metrics,
        evidence=evidence,
        period=period,
        visualization=visualization,
        diagnostics=AskDiagnostics(
            provider=provider.name,
            model=provider.model,
            tools_used=tools.calls,
            tool_call_count=len(tools.calls),
        ),
    )
