from datetime import datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.ask import ProviderOutput
from app.services.ai_provider import AIContext, AIProvider, AIProviderError, get_ai_provider
from app.services.care_insights import CareDataTools, ToolCallLimitExceeded
from tests.conftest import auth, login
from tests.test_wellbeing import create_checkin, setup_profile


def local_day(offset: int = 0):
    return datetime.now(ZoneInfo("Australia/Melbourne")).date() + timedelta(days=offset)


def timestamp(day) -> str:
    return f"{day.isoformat()}T10:00:00+10:00"


def local_timestamp(day, hour: int, minute: int) -> str:
    return datetime.combine(
        day,
        time(hour=hour, minute=minute),
        ZoneInfo("Australia/Melbourne"),
    ).isoformat()


def ask(client: TestClient, profile_id: str, token: str, question: str):
    return client.post(
        f"/api/v1/care-profiles/{profile_id}/ask",
        headers=auth(token),
        json={"question": question},
    )


def test_wellbeing_answer_metrics_evidence_and_visualization_are_deterministic(
    client: TestClient,
) -> None:
    context = setup_profile(client)
    profile_id = context["profile"]["id"]
    create_checkin(
        client, profile_id, context["cared"], 40, timestamp(local_day(-1)), ["dizziness"]
    )
    create_checkin(client, profile_id, context["cared"], 80, timestamp(local_day()), ["fatigue"])

    response = ask(
        client, profile_id, context["owner"], "How has Mum been feeling over the last 7 days?"
    )
    assert response.status_code == 200, response.text
    result = response.json()
    metrics = result["metrics"]["get_wellbeing_summary"]
    assert metrics["average_score"] == 60.0
    assert metrics["checkin_count"] == 2
    assert result["visualization"]["average"] == 60.0
    assert result["visualization"]["checkin_count"] == 2
    assert len(result["evidence"]) == 2
    assert {item["record_type"] for item in result["evidence"]} == {"wellbeing_checkin"}
    assert result["period"]["timezone"] == "Australia/Melbourne"


def test_profile_isolation_and_non_member_404(client: TestClient) -> None:
    context = setup_profile(client)
    outsider = login(client, "ask-outsider@example.com", "Outsider")
    response = ask(
        client,
        context["profile"]["id"],
        outsider,
        "Summarise the last 7 days",
    )
    assert response.status_code == 404


def test_controlled_tools_do_not_mix_data_between_profiles(client: TestClient) -> None:
    first = setup_profile(client)
    first_profile_id = first["profile"]["id"]
    create_checkin(client, first_profile_id, first["cared"], 25, timestamp(local_day()))

    second_profile = client.post(
        "/api/v1/care-profiles",
        headers=auth(first["owner"]),
        json={"name": "Second profile", "timezone": "Australia/Melbourne"},
    ).json()
    member = client.post(
        f"/api/v1/care-profiles/{second_profile['id']}/members",
        headers=auth(first["owner"]),
        json={"email": "cared@example.com", "role": "cared_person"},
    )
    assert member.status_code == 201
    create_checkin(client, second_profile["id"], first["cared"], 99, timestamp(local_day()))

    result = ask(client, first_profile_id, first["owner"], "Summarise the last 7 days")
    assert result.status_code == 200
    assert result.json()["metrics"]["get_wellbeing_summary"]["average_score"] == 25.0
    assert len(result.json()["evidence"]) == 1


def test_ask_period_uses_profile_timezone_at_local_midnight(client: TestClient) -> None:
    context = setup_profile(client)
    first_local_day = local_day(-6)
    create_checkin(
        client,
        context["profile"]["id"],
        context["cared"],
        44,
        local_timestamp(first_local_day, 0, 30),
    )

    result = ask(
        client,
        context["profile"]["id"],
        context["owner"],
        "Summarise the last 7 days",
    )
    assert result.status_code == 200
    body = result.json()
    assert body["period"]["start_date"] == first_local_day.isoformat()
    assert body["metrics"]["get_wellbeing_summary"]["checkin_count"] == 1
    assert body["metrics"]["get_wellbeing_summary"]["daily_averages"][0] == {
        "date": first_local_day.isoformat(),
        "checkin_count": 1,
        "average_score": 44.0,
    }


def test_period_comparison_and_symptom_frequency(client: TestClient) -> None:
    context = setup_profile(client)
    profile_id = context["profile"]["id"]
    today = local_day()
    current_monday = today - timedelta(days=today.weekday())
    create_checkin(
        client,
        profile_id,
        context["cared"],
        80,
        timestamp(current_monday),
        ["dizziness"],
    )
    create_checkin(
        client,
        profile_id,
        context["cared"],
        60,
        timestamp(current_monday - timedelta(days=7)),
        ["dizziness"],
    )
    comparison = ask(client, profile_id, context["owner"], "Was this week better than last week?")
    assert comparison.status_code == 200
    assert comparison.json()["metrics"]["compare_wellbeing_periods"]["difference"] == 20.0

    symptoms = ask(client, profile_id, context["owner"], "How often has dizziness been reported?")
    assert symptoms.status_code == 200
    assert symptoms.json()["metrics"]["get_symptom_frequency"]["symptom_frequency"] == {
        "dizziness": 2
    }
    assert len(symptoms.json()["evidence"]) == 2


def test_only_confirmed_care_events_are_evidence_and_chat_is_excluded(client: TestClient) -> None:
    context = setup_profile(client)
    profile_id = context["profile"]["id"]
    occurred_at = timestamp(local_day())
    converted_message = client.post(
        f"/api/v1/care-profiles/{profile_id}/chat/messages",
        headers=auth(context["owner"]),
        json={"body": "Mum may have fallen"},
    ).json()
    raw_message = client.post(
        f"/api/v1/care-profiles/{profile_id}/chat/messages",
        headers=auth(context["owner"]),
        json={"body": "This ordinary chat message must not be AI evidence"},
    )
    assert raw_message.status_code == 201
    confirmed_id = None
    for confirmation in ("draft", "confirmed"):
        source_chat_message_id = converted_message["id"] if confirmation == "confirmed" else None
        response = client.post(
            f"/api/v1/care-profiles/{profile_id}/care-events",
            headers=auth(context["owner"]),
            json={
                "event_type": "fall",
                "occurred_at": occurred_at,
                "summary": f"Fall {confirmation}",
                "metadata": {},
                "confirmation_status": confirmation,
                "source_chat_message_id": source_chat_message_id,
            },
        )
        assert response.status_code == 201
        if confirmation == "confirmed":
            confirmed_id = response.json()["id"]

    result = ask(client, profile_id, context["owner"], "Have there been any falls recently?").json()
    assert result["metrics"]["get_event_frequency"]["event_frequency"] == {"fall": 1}
    assert len(result["evidence"]) == 1
    assert result["evidence"][0]["record_type"] == "care_event"
    assert result["evidence"][0]["record_id"] == confirmed_id


def test_insufficient_data_does_not_extrapolate_or_require_provider(client: TestClient) -> None:
    context = setup_profile(client)
    result = ask(
        client,
        context["profile"]["id"],
        context["owner"],
        "How has Mum been feeling over the last 30 days?",
    )
    assert result.status_code == 200
    assert "not enough recorded information" in result.json()["answer"].lower()
    assert result.json()["evidence"] == []
    assert result.json()["visualization"] is None


class InventingProvider(AIProvider):
    name = "bad"
    model = "bad-model"

    async def generate(self, context: AIContext) -> ProviderOutput:
        return ProviderOutput(answer="The average was 999 points.")


class FailingProvider(AIProvider):
    name = "failing"
    model = "failing-model"

    async def generate(self, context: AIContext) -> ProviderOutput:
        raise AIProviderError("provider unavailable")


class MalformedProvider(AIProvider):
    name = "malformed"
    model = "malformed-model"

    async def generate(self, context: AIContext):
        return {"unexpected": "shape"}


class UnsafeMedicalProvider(AIProvider):
    name = "unsafe"
    model = "unsafe-model"

    def __init__(self) -> None:
        self.called = False

    async def generate(self, context: AIContext) -> ProviderOutput:
        self.called = True
        return ProviderOutput(answer="Stop the medication immediately.")


def test_medical_advice_question_uses_only_deterministic_record_context(
    client: TestClient,
) -> None:
    context = setup_profile(client)
    profile_id = context["profile"]["id"]
    event = client.post(
        f"/api/v1/care-profiles/{profile_id}/care-events",
        headers=auth(context["owner"]),
        json={
            "event_type": "medication_taken",
            "occurred_at": timestamp(local_day()),
            "summary": "Morning medication recorded as taken",
            "metadata": {"medication_name": "Recorded medicine"},
            "confirmation_status": "confirmed",
        },
    )
    assert event.status_code == 201
    provider = UnsafeMedicalProvider()
    app.dependency_overrides[get_ai_provider] = lambda: provider
    try:
        response = ask(
            client,
            profile_id,
            context["owner"],
            "Should Mum stop taking her medication?",
        )
    finally:
        app.dependency_overrides.pop(get_ai_provider, None)

    assert response.status_code == 200
    assert provider.called is False
    medication_metrics = response.json()["metrics"]["get_medication_summary"]
    assert medication_metrics["taken"] == 1
    assert medication_metrics["missed"] == 0
    assert medication_metrics["not_recorded"] == 0
    assert medication_metrics["legacy_medication_event_count"] == 1
    assert "cannot diagnose" in response.json()["answer"].lower()
    assert "recommend treatment" in response.json()["answer"].lower()


@pytest.mark.parametrize("provider", [InventingProvider(), FailingProvider(), MalformedProvider()])
def test_malformed_or_failed_provider_returns_controlled_error(
    client: TestClient, provider: AIProvider
) -> None:
    context = setup_profile(client)
    create_checkin(
        client,
        context["profile"]["id"],
        context["cared"],
        70,
        timestamp(local_day()),
    )
    app.dependency_overrides[get_ai_provider] = lambda: provider
    try:
        response = ask(
            client,
            context["profile"]["id"],
            context["owner"],
            "Summarise the last 7 days",
        )
    finally:
        app.dependency_overrides.pop(get_ai_provider, None)
    assert response.status_code == 502
    assert response.json()["detail"] == "Ask CareRelay could not produce a verified answer"


def test_tool_call_limit_and_profile_scope(db) -> None:
    tools = CareDataTools(db, UUID(int=1), "UTC", max_calls=1)
    tools.get_wellbeing_summary(local_day(), local_day())
    with pytest.raises(ToolCallLimitExceeded):
        tools.get_care_events(local_day(), local_day())
