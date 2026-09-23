from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.models.audit_log import AuditLog
from app.models.enums import AuditAction
from app.schemas.ask import ProviderOutput
from app.services.ai_provider import AIContext, AIProvider, get_ai_provider
from app.services.medications import local_schedule_instant
from tests.conftest import auth, login


def setup_medication_profile(client: TestClient, suffix: str = "") -> dict[str, Any]:
    owner = login(client, f"med-owner{suffix}@example.com", "Owner")
    family = login(client, f"med-family{suffix}@example.com", "Family")
    carer = login(client, f"med-carer{suffix}@example.com", "Carer")
    subject = login(client, f"med-subject{suffix}@example.com", "Mum")
    other_cared = login(client, f"other-cared{suffix}@example.com", "Other")
    profile_response = client.post(
        "/api/v1/care-profiles",
        headers=auth(owner),
        json={"name": "Mum", "timezone": "Australia/Melbourne"},
    )
    assert profile_response.status_code == 201
    profile = profile_response.json()
    memberships = {}
    for key, email, role in (
        ("family", f"med-family{suffix}@example.com", "family"),
        ("carer", f"med-carer{suffix}@example.com", "carer"),
        ("subject", f"med-subject{suffix}@example.com", "cared_person"),
        ("other_cared", f"other-cared{suffix}@example.com", "cared_person"),
    ):
        response = client.post(
            f"/api/v1/care-profiles/{profile['id']}/members",
            headers=auth(owner),
            json={"email": email, "role": role},
        )
        assert response.status_code == 201
        memberships[key] = response.json()
    subject_update = client.patch(
        f"/api/v1/care-profiles/{profile['id']}",
        headers=auth(owner),
        json={"subject_user_id": memberships["subject"]["user_id"]},
    )
    assert subject_update.status_code == 200
    return {
        "profile": subject_update.json(),
        "owner": owner,
        "family": family,
        "carer": carer,
        "subject": subject,
        "other_cared": other_cared,
    }


def create_medication(
    client: TestClient,
    context: dict[str, Any],
    *,
    token_key: str = "owner",
    name: str = "Metformin",
    schedule_type: str = "scheduled",
    schedules: list[dict] | None = None,
):
    return client.post(
        f"/api/v1/care-profiles/{context['profile']['id']}/medications",
        headers=auth(context[token_key]),
        json={
            "name": name,
            "strength_text": "500 mg",
            "form": "tablet",
            "instructions_text": "Entered family instruction",
            "schedule_type": schedule_type,
            "schedules": schedules or [],
        },
    )


def record_dose(
    client: TestClient,
    context: dict[str, Any],
    medication: dict,
    status: str,
    *,
    schedule: dict | None = None,
    scheduled_for: str | None = None,
    token_key: str = "subject",
    note: str | None = None,
):
    return client.post(
        f"/api/v1/care-profiles/{context['profile']['id']}/medication-doses",
        headers=auth(context[token_key]),
        json={
            "medication_id": medication["id"],
            "schedule_id": schedule["id"] if schedule else None,
            "scheduled_for": scheduled_for,
            "status": status,
            "note": note,
        },
    )


def local_today() -> date:
    return datetime.now(ZoneInfo("Australia/Melbourne")).date()


def occurrence_for(day: date, local_time: str) -> str:
    parsed_time = datetime.strptime(local_time, "%H:%M").time()
    return local_schedule_instant(day, parsed_time, "Australia/Melbourne").isoformat()


def test_medication_permissions_profile_isolation_and_subject_view(
    client: TestClient,
) -> None:
    first = setup_medication_profile(client, "-one")
    second = setup_medication_profile(client, "-two")

    for role in ("owner", "family", "carer"):
        response = create_medication(
            client,
            first,
            token_key=role,
            name=f"Medication by {role}",
            schedule_type="as_needed",
        )
        assert response.status_code == 201, response.text
    assert (
        create_medication(client, first, token_key="subject", schedule_type="as_needed").status_code
        == 403
    )

    profile_id = first["profile"]["id"]
    subject_list = client.get(
        f"/api/v1/care-profiles/{profile_id}/medications",
        headers=auth(first["subject"]),
    )
    assert subject_list.status_code == 200
    assert len(subject_list.json()) == 3
    assert (
        client.get(
            f"/api/v1/care-profiles/{profile_id}/medications",
            headers=auth(second["owner"]),
        ).status_code
        == 404
    )


def test_multiple_daily_times_weekdays_and_expected_generation(client: TestClient) -> None:
    context = setup_medication_profile(client)
    monday = date(2026, 9, 21)
    medication = create_medication(
        client,
        context,
        schedules=[
            {"local_time": "08:00", "days_of_week": list(range(7))},
            {"local_time": "20:00", "days_of_week": list(range(7))},
            {"local_time": "09:00", "days_of_week": [0, 2, 4]},
        ],
    )
    assert medication.status_code == 201, medication.text
    schedules = medication.json()["schedules"]
    assert len(schedules) == 3
    assert schedules[2]["days_of_week"] == [0, 2, 4]

    doses = client.get(
        f"/api/v1/care-profiles/{context['profile']['id']}/medication-doses",
        headers=auth(context["subject"]),
        params={"start": monday.isoformat(), "end": (monday + timedelta(days=1)).isoformat()},
    )
    assert doses.status_code == 200, doses.text
    assert [
        (item["scheduled_local_date"], item["scheduled_local_time"]) for item in doses.json()
    ] == [
        ("2026-09-21", "08:00:00"),
        ("2026-09-21", "09:00:00"),
        ("2026-09-21", "20:00:00"),
        ("2026-09-22", "08:00:00"),
        ("2026-09-22", "20:00:00"),
    ]
    assert {item["status"] for item in doses.json()} == {"not_recorded"}


def test_timezone_and_dst_keep_intended_local_schedule(client: TestClient) -> None:
    context = setup_medication_profile(client)
    dst_start = date(2026, 10, 4)
    medication = create_medication(
        client,
        context,
        schedules=[{"local_time": "02:30", "days_of_week": [6]}],
    ).json()
    result = client.get(
        f"/api/v1/care-profiles/{context['profile']['id']}/medication-doses",
        headers=auth(context["owner"]),
        params={"start": dst_start.isoformat(), "end": dst_start.isoformat()},
    )
    assert result.status_code == 200
    occurrence = result.json()[0]
    assert occurrence["scheduled_local_time"] == "02:30:00"
    assert occurrence["scheduled_timezone"] == "Australia/Melbourne"
    assert datetime.fromisoformat(occurrence["scheduled_for"]).astimezone(UTC) == (
        local_schedule_instant(
            dst_start, datetime.strptime("02:30", "%H:%M").time(), "Australia/Melbourne"
        )
    )
    assert medication["schedules"][0]["local_time"] == "02:30:00"


def test_future_and_elapsed_absence_remain_not_recorded(client: TestClient) -> None:
    context = setup_medication_profile(client)
    today = local_today()
    medication = create_medication(
        client,
        context,
        schedules=[{"local_time": "08:00", "days_of_week": list(range(7))}],
    ).json()
    result = client.get(
        f"/api/v1/care-profiles/{context['profile']['id']}/medication-doses",
        headers=auth(context["family"]),
        params={
            "start": (today - timedelta(days=1)).isoformat(),
            "end": (today + timedelta(days=1)).isoformat(),
        },
    ).json()
    yesterday, tomorrow = result[0], result[-1]
    assert yesterday["status"] == "not_recorded"
    assert yesterday["due_state"] == "elapsed"
    assert tomorrow["status"] == "not_recorded"
    assert tomorrow["due_state"] == "upcoming"
    assert medication["schedule_type"] == "scheduled"
    future_missed = record_dose(
        client,
        context,
        medication,
        "missed",
        schedule=medication["schedules"][0],
        scheduled_for=tomorrow["scheduled_for"],
    )
    assert future_missed.status_code == 422


def test_subject_family_and_carer_record_outcomes_without_duplicates(
    client: TestClient,
) -> None:
    context = setup_medication_profile(client)
    dose_day = local_today() - timedelta(days=1)
    times_and_roles = [
        ("08:00", "taken", "subject"),
        ("12:00", "missed", "family"),
        ("20:00", "skipped", "carer"),
    ]
    medication = create_medication(
        client,
        context,
        schedules=[
            {"local_time": item[0], "days_of_week": [dose_day.weekday()]}
            for item in times_and_roles
        ],
    ).json()
    created = []
    for schedule, (clock, dose_status, role) in zip(
        medication["schedules"], times_and_roles, strict=True
    ):
        response = record_dose(
            client,
            context,
            medication,
            dose_status,
            schedule=schedule,
            scheduled_for=occurrence_for(dose_day, clock),
            token_key=role,
            note="Factual note",
        )
        assert response.status_code == 201, response.text
        created.append(response.json())

    duplicate = record_dose(
        client,
        context,
        medication,
        "taken",
        schedule=medication["schedules"][0],
        scheduled_for=occurrence_for(dose_day, "08:00"),
        token_key="family",
    )
    assert duplicate.status_code == 409
    assert [item["status"] for item in created] == ["taken", "missed", "skipped"]
    assert [item["recorded_by"]["display_name"] for item in created] == [
        "Mum",
        "Family",
        "Carer",
    ]

    events = client.get(
        f"/api/v1/care-profiles/{context['profile']['id']}/care-events",
        headers=auth(context["owner"]),
    ).json()
    assert len(events) == 3
    assert {event["event_type"] for event in events} == {
        "medication_taken",
        "medication_missed",
        "medication_skipped",
    }
    assert {event["metadata"]["medication_dose_id"] for event in events} == {
        item["id"] for item in created
    }


def test_non_subject_cared_person_cannot_record_dose(client: TestClient) -> None:
    context = setup_medication_profile(client)
    today = local_today()
    medication = create_medication(
        client,
        context,
        schedules=[{"local_time": "08:00", "days_of_week": [today.weekday()]}],
    ).json()
    response = record_dose(
        client,
        context,
        medication,
        "taken",
        schedule=medication["schedules"][0],
        scheduled_for=occurrence_for(today, "08:00"),
        token_key="other_cared",
    )
    assert response.status_code == 403


def test_as_needed_has_no_expected_doses_and_only_allows_taken(client: TestClient) -> None:
    context = setup_medication_profile(client)
    medication = create_medication(client, context, schedule_type="as_needed", schedules=[]).json()
    today = local_today()
    before = client.get(
        f"/api/v1/care-profiles/{context['profile']['id']}/medication-doses",
        headers=auth(context["subject"]),
        params={"start": today.isoformat(), "end": today.isoformat()},
    ).json()
    assert before == []
    assert record_dose(client, context, medication, "missed").status_code == 422
    taken = record_dose(client, context, medication, "taken")
    assert taken.status_code == 201
    after = client.get(
        f"/api/v1/care-profiles/{context['profile']['id']}/medication-doses",
        headers=auth(context["subject"]),
        params={"start": today.isoformat(), "end": today.isoformat()},
    ).json()
    assert len(after) == 1
    assert after[0]["due_state"] == "as_needed"
    assert after[0]["status"] == "taken"


def test_dose_correction_updates_linked_event_and_blocks_direct_event_edit(
    client: TestClient,
) -> None:
    context = setup_medication_profile(client)
    dose_day = local_today() - timedelta(days=1)
    medication = create_medication(
        client,
        context,
        schedules=[{"local_time": "08:00", "days_of_week": [dose_day.weekday()]}],
    ).json()
    dose = record_dose(
        client,
        context,
        medication,
        "missed",
        schedule=medication["schedules"][0],
        scheduled_for=occurrence_for(dose_day, "08:00"),
    ).json()
    direct = client.patch(
        f"/api/v1/care-profiles/{context['profile']['id']}/care-events/{dose['care_event_id']}",
        headers=auth(context["owner"]),
        json={"summary": "Divergent edit"},
    )
    assert direct.status_code == 409
    direct_delete = client.delete(
        f"/api/v1/care-profiles/{context['profile']['id']}/care-events/{dose['care_event_id']}",
        headers=auth(context["owner"]),
    )
    assert direct_delete.status_code == 409
    corrected = client.patch(
        f"/api/v1/care-profiles/{context['profile']['id']}/medication-doses/{dose['id']}",
        headers=auth(context["family"]),
        json={"status": "taken", "note": "Corrected after checking the record"},
    )
    assert corrected.status_code == 200
    assert corrected.json()["status"] == "taken"
    event = client.get(
        f"/api/v1/care-profiles/{context['profile']['id']}/care-events/{dose['care_event_id']}",
        headers=auth(context["owner"]),
    ).json()
    assert event["event_type"] == "medication_taken"
    assert event["metadata"]["dose_status"] == "taken"


def test_medication_schedule_and_dose_actions_are_audited(client: TestClient, db: Session) -> None:
    context = setup_medication_profile(client)
    today = local_today()
    medication = create_medication(
        client,
        context,
        schedules=[{"local_time": "08:00", "days_of_week": [today.weekday()]}],
    ).json()
    schedule = medication["schedules"][0]
    updated_schedule = client.patch(
        f"/api/v1/care-profiles/{context['profile']['id']}/medications/{medication['id']}/schedules/{schedule['id']}",
        headers=auth(context["owner"]),
        json={"local_time": "09:00"},
    )
    assert updated_schedule.status_code == 200
    dose = record_dose(
        client,
        context,
        medication,
        "taken",
        schedule=updated_schedule.json(),
        scheduled_for=occurrence_for(today, "09:00"),
    ).json()
    client.patch(
        f"/api/v1/care-profiles/{context['profile']['id']}/medication-doses/{dose['id']}",
        headers=auth(context["subject"]),
        json={"status": "skipped"},
    )
    client.delete(
        f"/api/v1/care-profiles/{context['profile']['id']}/medications/{medication['id']}/schedules/{schedule['id']}",
        headers=auth(context["owner"]),
    )
    client.delete(
        f"/api/v1/care-profiles/{context['profile']['id']}/medications/{medication['id']}",
        headers=auth(context["owner"]),
    )
    actions = set(db.scalars(select(AuditLog.action)).all())
    assert {
        AuditAction.MEDICATION_CREATED,
        AuditAction.MEDICATION_SCHEDULE_CREATED,
        AuditAction.MEDICATION_SCHEDULE_UPDATED,
        AuditAction.MEDICATION_SCHEDULE_REMOVED,
        AuditAction.MEDICATION_DOSE_RECORDED,
        AuditAction.MEDICATION_DOSE_CORRECTED,
        AuditAction.MEDICATION_DEACTIVATED,
    }.issubset(actions)


class UnsafeDoseAdviceProvider(AIProvider):
    name = "unsafe"
    model = "unsafe"

    def __init__(self) -> None:
        self.called = False

    async def generate(self, context: AIContext) -> ProviderOutput:
        self.called = True
        return ProviderOutput(answer="Take two tablets tonight.")


def test_ask_medication_counts_evidence_no_record_semantics_and_safety(
    client: TestClient,
) -> None:
    context = setup_medication_profile(client)
    dose_day = local_today() - timedelta(days=1)
    medication = create_medication(
        client,
        context,
        schedules=[
            {"local_time": clock, "days_of_week": [dose_day.weekday()]}
            for clock in ("08:00", "12:00", "20:00")
        ],
    ).json()
    for schedule, clock, dose_status in zip(
        medication["schedules"], ("08:00", "12:00"), ("taken", "missed"), strict=False
    ):
        response = record_dose(
            client,
            context,
            medication,
            dose_status,
            schedule=schedule,
            scheduled_for=occurrence_for(dose_day, clock),
        )
        assert response.status_code == 201

    ask_response = client.post(
        f"/api/v1/care-profiles/{context['profile']['id']}/ask",
        headers=auth(context["family"]),
        json={"question": "What medication doses were recorded yesterday?"},
    )
    assert ask_response.status_code == 200
    result = ask_response.json()
    metrics = result["metrics"]["get_medication_summary"]
    assert (metrics["taken"], metrics["missed"], metrics["not_recorded"]) == (1, 1, 1)
    assert {item["record_type"] for item in result["evidence"]} == {
        "medication",
        "medication_dose",
    }
    assert "1 missed" in result["answer"]
    assert "1 expected doses have no recorded outcome" in result["answer"]

    provider = UnsafeDoseAdviceProvider()
    app.dependency_overrides[get_ai_provider] = lambda: provider
    try:
        safety = client.post(
            f"/api/v1/care-profiles/{context['profile']['id']}/ask",
            headers=auth(context["family"]),
            json={
                "question": (
                    "Yesterday Mum missed her morning tablet. Should she take two tonight?"
                )
            },
        )
    finally:
        app.dependency_overrides.pop(get_ai_provider, None)
    assert safety.status_code == 200
    assert provider.called is False
    assert "cannot advise" in safety.json()["answer"].lower()
    assert "pharmacist" in safety.json()["answer"].lower()
