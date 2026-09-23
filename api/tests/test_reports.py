from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.models.audit_log import AuditLog
from app.models.enums import AuditAction
from app.schemas.ask import ProviderOutput
from app.services.ai_provider import AIContext, AIProvider, AIProviderError, get_ai_provider
from tests.conftest import auth
from tests.test_medications import create_medication, setup_medication_profile


def report(
    client: TestClient,
    context: dict[str, Any],
    payload: dict | None = None,
    token_key: str = "owner",
):
    return client.post(
        f"/api/v1/care-profiles/{context['profile']['id']}/reports/preview",
        headers=auth(context[token_key]),
        json=payload or {"period": "30d"},
    )


def add_checkin(client: TestClient, context: dict[str, Any], when: datetime, score: int) -> None:
    response = client.post(
        f"/api/v1/care-profiles/{context['profile']['id']}/wellbeing-checkins",
        headers=auth(context["subject"]),
        json={
            "score": score,
            "occurred_at": when.isoformat(),
            "symptoms": ["dizziness"],
            "note": "Recorded self report",
        },
    )
    assert response.status_code == 201, response.text


def add_event(
    client: TestClient,
    context: dict[str, Any],
    event_type: str,
    summary: str,
    when: datetime,
    metadata: dict | None = None,
    source_chat_message_id: str | None = None,
) -> dict:
    response = client.post(
        f"/api/v1/care-profiles/{context['profile']['id']}/care-events",
        headers=auth(context["owner"]),
        json={
            "event_type": event_type,
            "occurred_at": when.isoformat(),
            "summary": summary,
            "metadata": metadata or {},
            "confirmation_status": "confirmed",
            "source_chat_message_id": source_chat_message_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize(("period", "days"), [("7d", 7), ("30d", 30), ("90d", 90)])
def test_standard_report_periods_are_profile_timezone_days(
    client: TestClient, period: str, days: int
) -> None:
    context = setup_medication_profile(client, f"-{period}")
    response = report(client, context, {"period": period})
    assert response.status_code == 200
    body = response.json()
    assert body["period"]["timezone"] == "Australia/Melbourne"
    start = date.fromisoformat(body["period"]["start_date"])
    end = date.fromisoformat(body["period"]["end_date"])
    assert (end - start).days == days - 1


def test_custom_report_metrics_evidence_events_chat_and_audit(
    client: TestClient, db: Session
) -> None:
    context = setup_medication_profile(client, "-full-report")
    timezone = ZoneInfo("Australia/Melbourne")
    today = datetime.now(timezone).date()
    first = datetime.combine(today - timedelta(days=2), time(9), timezone)
    last = datetime.combine(today - timedelta(days=1), time(10), timezone)
    add_checkin(client, context, first, 40)
    add_checkin(client, context, last, 60)
    add_event(client, context, "fall", "A fall was recorded", last)
    add_event(client, context, "activity", "Short walk recorded", last, {"duration_minutes": 15})
    add_event(
        client,
        context,
        "appointment",
        "GP review",
        last,
        {"provider": "Dr Green", "location": "Local clinic"},
    )
    message = client.post(
        f"/api/v1/care-profiles/{context['profile']['id']}/chat/messages",
        headers=auth(context["owner"]),
        json={"body": "PRIVATE CHAT MUST STAY EXCLUDED"},
    )
    assert message.status_code == 201
    add_event(
        client,
        context,
        "general_note",
        "Confirmed family observation",
        last,
        source_chat_message_id=message.json()["id"],
    )

    response = report(
        client,
        context,
        {
            "period": "custom",
            "start_date": (today - timedelta(days=3)).isoformat(),
            "end_date": today.isoformat(),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["wellbeing"]["average"] == 50
    assert body["wellbeing"]["minimum"] == 40
    assert body["wellbeing"]["maximum"] == 60
    assert body["wellbeing"]["trend"] == "higher"
    assert body["symptoms"][0]["recorded_count"] == 2
    assert body["falls"]["count"] == 1
    assert body["care_events"]["activity_count"] == 1
    assert body["appointments"][0]["provider"] == "Dr Green"
    assert any(item["source_chat_confirmed"] for item in body["care_events"]["items"])
    assert "PRIVATE CHAT MUST STAY EXCLUDED" not in response.text
    assert {item["record_type"] for item in body["evidence"]} >= {
        "wellbeing_checkin",
        "care_event",
    }
    audit = db.scalar(
        select(AuditLog).where(AuditLog.action == AuditAction.REPORT_PREVIEW_GENERATED)
    )
    assert audit is not None
    assert set(audit.after_state) == {"period"}


def test_medication_outcomes_keep_no_record_distinct_from_missed(client: TestClient) -> None:
    context = setup_medication_profile(client, "-report-doses")
    timezone = ZoneInfo("Australia/Melbourne")
    today = datetime.now(timezone).date()
    medication_response = create_medication(
        client,
        context,
        schedules=[{"local_time": "00:01", "days_of_week": list(range(7))}],
    )
    assert medication_response.status_code == 201
    medication = medication_response.json()
    start = today - timedelta(days=3)
    doses = client.get(
        f"/api/v1/care-profiles/{context['profile']['id']}/medication-doses",
        headers=auth(context["subject"]),
        params={"start": start.isoformat(), "end": today.isoformat()},
    )
    assert doses.status_code == 200
    occurrences = doses.json()
    for occurrence, status in zip(occurrences[:3], ["taken", "missed", "skipped"], strict=True):
        saved = client.post(
            f"/api/v1/care-profiles/{context['profile']['id']}/medication-doses",
            headers=auth(context["subject"]),
            json={
                "medication_id": medication["id"],
                "schedule_id": occurrence["schedule_id"],
                "scheduled_for": occurrence["scheduled_for"],
                "status": status,
            },
        )
        assert saved.status_code == 201, saved.text
    response = report(
        client,
        context,
        {"period": "custom", "start_date": start.isoformat(), "end_date": today.isoformat()},
    )
    assert response.status_code == 200
    medications = response.json()["medications"]
    assert medications["taken"] == 1
    assert medications["missed"] == 1
    assert medications["skipped"] == 1
    assert medications["not_recorded"] == 1
    assert medications["expected_scheduled_doses"] == 4
    assert {item["status"] for item in medications["doses"]} == {
        "taken",
        "missed",
        "skipped",
        "not_recorded",
    }


def test_sparse_and_empty_reports_do_not_fabricate_trends(client: TestClient) -> None:
    context = setup_medication_profile(client, "-empty-report")
    response = report(client, context)
    assert response.status_code == 200
    body = response.json()
    assert body["wellbeing"]["checkin_count"] == 0
    assert body["wellbeing"]["trend"] == "insufficient_data"
    assert body["falls"]["count"] == 0
    assert body["symptoms"] == []
    assert "No self-reported wellbeing" in body["narrative_summary"]
    assert "diagnos" in body["disclaimer"]


class FailingProvider(AIProvider):
    name = "failing"
    model = "failing-model"

    async def generate(self, context: AIContext) -> ProviderOutput:
        raise AIProviderError("provider unavailable")


class InventingProvider(AIProvider):
    name = "inventing"
    model = "inventing-model"

    async def generate(self, context: AIContext) -> ProviderOutput:
        return ProviderOutput(
            answer="The invented clinical score is 999 and medication should change."
        )


class AdvisingProvider(AIProvider):
    name = "advising"
    model = "advising-model"

    async def generate(self, context: AIContext) -> ProviderOutput:
        return ProviderOutput(answer="They should stop taking the recorded medication.")


@pytest.mark.parametrize(
    "provider", [FailingProvider(), InventingProvider(), AdvisingProvider()]
)
def test_ai_failure_or_invented_numbers_falls_back_to_safe_deterministic_report(
    client: TestClient, provider: AIProvider
) -> None:
    context = setup_medication_profile(client, f"-{provider.name}")
    app.dependency_overrides[get_ai_provider] = lambda: provider
    try:
        response = report(client, context)
    finally:
        app.dependency_overrides.pop(get_ai_provider, None)
    assert response.status_code == 200
    body = response.json()
    assert body["narrative_source"] == "deterministic"
    assert "999" not in body["narrative_summary"]
    assert "medication should change" not in body["narrative_summary"]


def test_report_and_pdf_are_membership_scoped(client: TestClient) -> None:
    context = setup_medication_profile(client, "-report-auth")
    outsider = setup_medication_profile(client, "-report-outsider")
    path = f"/api/v1/care-profiles/{context['profile']['id']}/reports"
    preview = client.post(f"{path}/preview", headers=auth(outsider["owner"]), json={})
    assert preview.status_code == 404
    assert client.post(f"{path}/pdf", headers=auth(outsider["owner"]), json={}).status_code == 404


def test_pdf_is_private_readable_and_contains_no_internal_diagnostics(
    client: TestClient, db: Session
) -> None:
    context = setup_medication_profile(client, "-report-pdf")
    response = client.post(
        f"/api/v1/care-profiles/{context['profile']['id']}/reports/pdf",
        headers=auth(context["family"]),
        json={"period": "7d"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.content.startswith(b"%PDF-1.4")
    assert b"CARE RELAY SUMMARY" in response.content
    for forbidden in (b"openrouter", b"api_key", b"Authorization", b"chain-of-thought"):
        assert forbidden not in response.content
    audit = db.scalar(select(AuditLog).where(AuditLog.action == AuditAction.REPORT_PDF_GENERATED))
    assert audit is not None
    assert set(audit.after_state) == {"period"}


def test_invalid_custom_ranges_are_rejected(client: TestClient) -> None:
    context = setup_medication_profile(client, "-bad-range")
    assert report(client, context, {"period": "custom"}).status_code == 422
    assert report(
        client,
        context,
        {"period": "custom", "start_date": "2026-02-02", "end_date": "2026-02-01"},
    ).status_code == 422
