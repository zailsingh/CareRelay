from datetime import datetime
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.enums import AuditAction
from tests.conftest import auth, login


def setup_event_profile(client: TestClient) -> dict[str, Any]:
    owner = login(client, "owner@example.com", "Owner")
    family = login(client, "family@example.com", "Sarah")
    carer = login(client, "carer@example.com", "Zail")
    subject = login(client, "subject@example.com", "Mum")
    profile = client.post(
        "/api/v1/care-profiles",
        headers=auth(owner),
        json={"name": "Mum", "timezone": "Australia/Melbourne"},
    ).json()
    members = {}
    for email, role in [
        ("family@example.com", "family"),
        ("carer@example.com", "carer"),
        ("subject@example.com", "cared_person"),
    ]:
        response = client.post(
            f"/api/v1/care-profiles/{profile['id']}/members",
            headers=auth(owner),
            json={"email": email, "role": role},
        )
        assert response.status_code == 201
        members[role] = response.json()
    client.patch(
        f"/api/v1/care-profiles/{profile['id']}",
        headers=auth(owner),
        json={"subject_user_id": members["cared_person"]["user_id"]},
    )
    return {
        "profile": profile,
        "owner": owner,
        "family": family,
        "carer": carer,
        "subject": subject,
        "members": members,
    }


def create_event(
    client: TestClient,
    profile_id: str,
    token: str,
    event_type: str = "family_observation",
    summary: str = "Mum seemed tired after lunch",
    occurred_at: str = "2026-09-17T14:00:00+10:00",
    metadata: dict | None = None,
):
    return client.post(
        f"/api/v1/care-profiles/{profile_id}/care-events",
        headers=auth(token),
        json={
            "event_type": event_type,
            "occurred_at": occurred_at,
            "summary": summary,
            "metadata": metadata or {},
        },
    )


def test_family_carer_and_admin_can_create_with_server_derived_source(
    client: TestClient,
) -> None:
    context = setup_event_profile(client)
    profile_id = context["profile"]["id"]
    for token, expected_source in [
        (context["family"], "family"),
        (context["carer"], "carer"),
        (context["owner"], "admin"),
    ]:
        response = create_event(client, profile_id, token)
        assert response.status_code == 201, response.text
        assert response.json()["source"] == expected_source
        assert response.json()["entered_by_user_id"] == response.json()["entered_by"]["id"]

    assert create_event(client, profile_id, context["subject"]).status_code == 403


def test_event_metadata_is_type_validated(client: TestClient) -> None:
    context = setup_event_profile(client)
    profile_id = context["profile"]["id"]
    valid = create_event(
        client,
        profile_id,
        context["carer"],
        event_type="activity",
        summary="Walked around the garden",
        metadata={"activity": "walking", "duration_minutes": 15},
    )
    assert valid.status_code == 201
    assert valid.json()["metadata"]["duration_minutes"] == 15

    arbitrary = create_event(
        client,
        profile_id,
        context["family"],
        metadata={"uncontrolled": {"anything": True}},
    )
    assert arbitrary.status_code == 422


def test_non_member_receives_404_for_event_routes(client: TestClient) -> None:
    context = setup_event_profile(client)
    profile_id = context["profile"]["id"]
    event = create_event(client, profile_id, context["family"]).json()
    outsider = login(client, "outsider@example.com", "Outsider")
    assert (
        client.get(
            f"/api/v1/care-profiles/{profile_id}/care-events", headers=auth(outsider)
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/care-profiles/{profile_id}/care-events/{event['id']}",
            headers=auth(outsider),
        ).status_code
        == 404
    )
    assert create_event(client, profile_id, outsider).status_code == 404


def test_event_filters_and_ordering(client: TestClient) -> None:
    context = setup_event_profile(client)
    profile_id = context["profile"]["id"]
    create_event(
        client,
        profile_id,
        context["family"],
        "family_observation",
        "Early observation",
        "2026-09-16T09:00:00+10:00",
    )
    activity = create_event(
        client,
        profile_id,
        context["carer"],
        "activity",
        "Walked 15 minutes",
        "2026-09-17T09:00:00+10:00",
        {"duration_minutes": 15},
    ).json()
    create_event(
        client,
        profile_id,
        context["family"],
        "fall",
        "Slipped beside chair",
        "2026-09-18T09:00:00+10:00",
    )
    url = f"/api/v1/care-profiles/{profile_id}/care-events"

    activity_result = client.get(
        url,
        headers=auth(context["owner"]),
        params={"event_type": "activity"},
    ).json()
    assert [event["id"] for event in activity_result] == [activity["id"]]

    carer_result = client.get(
        url,
        headers=auth(context["owner"]),
        params={"entered_by": context["members"]["carer"]["user_id"]},
    ).json()
    assert [event["id"] for event in carer_result] == [activity["id"]]

    range_result = client.get(
        url,
        headers=auth(context["owner"]),
        params={
            "start_at": "2026-09-16T12:00:00+10:00",
            "end_at": "2026-09-19T00:00:00+10:00",
            "order": "oldest",
        },
    ).json()
    assert [event["event_type"] for event in range_result] == ["activity", "fall"]
    assert datetime.fromisoformat(range_result[0]["occurred_at"]) < datetime.fromisoformat(
        range_result[1]["occurred_at"]
    )


def test_update_delete_permissions_and_audits(client: TestClient, db: Session) -> None:
    context = setup_event_profile(client)
    profile_id = context["profile"]["id"]
    event = create_event(client, profile_id, context["family"]).json()
    forbidden = client.patch(
        f"/api/v1/care-profiles/{profile_id}/care-events/{event['id']}",
        headers=auth(context["carer"]),
        json={"summary": "Should not work"},
    )
    assert forbidden.status_code == 403

    updated = client.patch(
        f"/api/v1/care-profiles/{profile_id}/care-events/{event['id']}",
        headers=auth(context["family"]),
        json={"summary": "Mum seemed rested after lunch"},
    )
    assert updated.status_code == 200
    deleted = client.delete(
        f"/api/v1/care-profiles/{profile_id}/care-events/{event['id']}",
        headers=auth(context["owner"]),
    )
    assert deleted.status_code == 204
    actions = db.scalars(
        select(AuditLog.action)
        .where(AuditLog.target_type == "care_event")
        .order_by(AuditLog.created_at, AuditLog.action)
    ).all()
    assert set(actions) == {
        AuditAction.CARE_EVENT_CREATED,
        AuditAction.CARE_EVENT_UPDATED,
        AuditAction.CARE_EVENT_DELETED,
    }


def test_self_report_and_care_event_remain_separate(client: TestClient) -> None:
    context = setup_event_profile(client)
    profile_id = context["profile"]["id"]
    checkin = client.post(
        f"/api/v1/care-profiles/{profile_id}/wellbeing-checkins",
        headers=auth(context["subject"]),
        json={"score": 78, "occurred_at": "2026-09-17T10:00:00+10:00"},
    )
    event = create_event(
        client,
        profile_id,
        context["family"],
        summary="Mum appeared tired this afternoon",
        occurred_at="2026-09-17T15:00:00+10:00",
    )
    assert checkin.status_code == 201
    assert event.status_code == 201
    assert (
        len(
            client.get(
                f"/api/v1/care-profiles/{profile_id}/wellbeing-checkins",
                headers=auth(context["owner"]),
            ).json()
        )
        == 1
    )
    assert (
        len(
            client.get(
                f"/api/v1/care-profiles/{profile_id}/care-events",
                headers=auth(context["owner"]),
            ).json()
        )
        == 1
    )
    assert event.json()["metadata"] == {}
    assert checkin.json()["score"] == 78
