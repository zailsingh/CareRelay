from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import auth, login


def setup_profile(client: TestClient) -> dict[str, Any]:
    owner_token = login(client, "owner@example.com", "Owner")
    cared_token = login(client, "cared@example.com", "Jamie")
    profile_response = client.post(
        "/api/v1/care-profiles",
        headers=auth(owner_token),
        json={"name": "Jamie", "timezone": "Australia/Melbourne"},
    )
    assert profile_response.status_code == 201
    profile = profile_response.json()
    member_response = client.post(
        f"/api/v1/care-profiles/{profile['id']}/members",
        headers=auth(owner_token),
        json={"email": "cared@example.com", "role": "cared_person"},
    )
    assert member_response.status_code == 201
    subject_response = client.patch(
        f"/api/v1/care-profiles/{profile['id']}",
        headers=auth(owner_token),
        json={"subject_user_id": member_response.json()["user_id"]},
    )
    assert subject_response.status_code == 200
    profile = subject_response.json()
    return {"profile": profile, "owner": owner_token, "cared": cared_token}


def create_checkin(
    client: TestClient,
    profile_id: str,
    token: str,
    score: int,
    occurred_at: str = "2026-09-17T09:00:00+10:00",
    symptoms: list[str] | None = None,
    note: str | None = None,
):
    return client.post(
        f"/api/v1/care-profiles/{profile_id}/wellbeing-checkins",
        headers=auth(token),
        json={
            "score": score,
            "occurred_at": occurred_at,
            "symptoms": symptoms or [],
            "note": note,
        },
    )


@pytest.mark.parametrize("score", [0, 100])
def test_score_boundaries_are_valid(client: TestClient, score: int) -> None:
    context = setup_profile(client)
    response = create_checkin(client, context["profile"]["id"], context["cared"], score)
    assert response.status_code == 201, response.text
    assert response.json()["score"] == score
    assert response.json()["reported_by"]["display_name"] == "Jamie"


@pytest.mark.parametrize("score", [-1, 101])
def test_score_outside_range_is_rejected(client: TestClient, score: int) -> None:
    context = setup_profile(client)
    response = create_checkin(client, context["profile"]["id"], context["cared"], score)
    assert response.status_code == 422


def test_multiple_checkins_on_same_day_are_preserved(client: TestClient) -> None:
    context = setup_profile(client)
    profile_id = context["profile"]["id"]
    create_checkin(client, profile_id, context["cared"], 35, "2026-09-17T08:00:00+10:00")
    create_checkin(client, profile_id, context["cared"], 75, "2026-09-17T18:00:00+10:00")

    response = client.get(
        f"/api/v1/care-profiles/{profile_id}/wellbeing-checkins",
        headers=auth(context["cared"]),
    )
    assert response.status_code == 200
    assert [item["score"] for item in response.json()] == [75, 35]


def test_non_member_gets_404_for_profile_scoped_wellbeing(client: TestClient) -> None:
    context = setup_profile(client)
    outsider = login(client, "outsider@example.com", "Outsider")
    profile_id = context["profile"]["id"]
    checkin = create_checkin(client, profile_id, context["cared"], 62).json()

    endpoints = [
        f"/api/v1/care-profiles/{profile_id}/wellbeing-checkins",
        f"/api/v1/care-profiles/{profile_id}/wellbeing-checkins/{checkin['id']}",
        (
            f"/api/v1/care-profiles/{profile_id}/wellbeing-checkins/summary"
            "?start_date=2026-09-17&end_date=2026-09-17"
        ),
    ]
    for endpoint in endpoints:
        assert client.get(endpoint, headers=auth(outsider)).status_code == 404


def test_admin_and_family_can_view_but_cannot_create_self_reports(client: TestClient) -> None:
    context = setup_profile(client)
    profile_id = context["profile"]["id"]
    family_token = login(client, "family-viewer@example.com", "Family")
    client.post(
        f"/api/v1/care-profiles/{profile_id}/members",
        headers=auth(context["owner"]),
        json={"email": "family-viewer@example.com", "role": "family"},
    )
    checkin = create_checkin(client, profile_id, context["cared"], 68).json()

    for token in [context["owner"], family_token]:
        read = client.get(
            f"/api/v1/care-profiles/{profile_id}/wellbeing-checkins/{checkin['id']}",
            headers=auth(token),
        )
        assert read.status_code == 200
        create = create_checkin(client, profile_id, token, 99)
        assert create.status_code == 403

    update = client.patch(
        f"/api/v1/care-profiles/{profile_id}/wellbeing-checkins/{checkin['id']}",
        headers=auth(context["owner"]),
        json={"score": 90},
    )
    assert update.status_code == 403


def test_cared_person_can_update_and_delete_only_own_checkin(client: TestClient) -> None:
    context = setup_profile(client)
    profile_id = context["profile"]["id"]
    other_token = login(client, "other-cared@example.com", "Other cared person")
    client.post(
        f"/api/v1/care-profiles/{profile_id}/members",
        headers=auth(context["owner"]),
        json={"email": "other-cared@example.com", "role": "cared_person"},
    )
    own = create_checkin(client, profile_id, context["cared"], 51).json()

    forbidden = client.patch(
        f"/api/v1/care-profiles/{profile_id}/wellbeing-checkins/{own['id']}",
        headers=auth(other_token),
        json={"score": 88},
    )
    assert forbidden.status_code == 403

    updated = client.patch(
        f"/api/v1/care-profiles/{profile_id}/wellbeing-checkins/{own['id']}",
        headers=auth(context["cared"]),
        json={"score": 52, "symptoms": ["feeling_good"], "note": None},
    )
    assert updated.status_code == 200
    assert updated.json()["score"] == 52
    assert updated.json()["symptoms"] == ["feeling_good"]

    deleted = client.delete(
        f"/api/v1/care-profiles/{profile_id}/wellbeing-checkins/{own['id']}",
        headers=auth(context["cared"]),
    )
    assert deleted.status_code == 204
    assert (
        client.get(
            f"/api/v1/care-profiles/{profile_id}/wellbeing-checkins/{own['id']}",
            headers=auth(context["owner"]),
        ).status_code
        == 404
    )


def test_summary_calculates_date_range_daily_averages_and_symptoms(
    client: TestClient,
) -> None:
    context = setup_profile(client)
    profile_id = context["profile"]["id"]
    create_checkin(
        client,
        profile_id,
        context["cared"],
        20,
        "2026-09-17T00:30:00+10:00",
        ["dizziness", "fatigue"],
    )
    create_checkin(
        client,
        profile_id,
        context["cared"],
        80,
        "2026-09-17T23:30:00+10:00",
        ["dizziness", "feeling_good"],
    )
    create_checkin(
        client,
        profile_id,
        context["cared"],
        100,
        "2026-09-18T00:30:00+10:00",
        ["feeling_good"],
    )

    response = client.get(
        f"/api/v1/care-profiles/{profile_id}/wellbeing-checkins/summary",
        headers=auth(context["owner"]),
        params={
            "start_date": "2026-09-17",
            "end_date": "2026-09-18",
        },
    )
    assert response.status_code == 200, response.text
    summary = response.json()
    assert summary["checkin_count"] == 3
    assert summary["latest_score"] == 100
    assert summary["average_score"] == 66.7
    assert summary["minimum_score"] == 20
    assert summary["maximum_score"] == 100
    assert summary["daily_averages"] == [
        {"date": "2026-09-17", "checkin_count": 2, "average_score": 50.0},
        {"date": "2026-09-18", "checkin_count": 1, "average_score": 100.0},
    ]
    assert summary["symptom_frequency"]["dizziness"] == 2
    assert summary["symptom_frequency"]["fatigue"] == 1
    assert summary["symptom_frequency"]["feeling_good"] == 2
    assert summary["symptom_frequency"]["pain"] == 0


def test_day_grouping_uses_profile_timezone_not_utc(client: TestClient) -> None:
    context = setup_profile(client)
    profile_id = context["profile"]["id"]
    create_checkin(
        client,
        profile_id,
        context["cared"],
        40,
        "2026-09-17T00:30:00+10:00",  # 2026-09-16 in UTC
    )

    melbourne = client.get(
        f"/api/v1/care-profiles/{profile_id}/wellbeing-checkins/summary",
        headers=auth(context["owner"]),
        params={
            "start_date": "2026-09-17",
            "end_date": "2026-09-17",
        },
    ).json()
    timezone_change = client.patch(
        f"/api/v1/care-profiles/{profile_id}",
        headers=auth(context["owner"]),
        json={"timezone": "UTC"},
    )
    assert timezone_change.status_code == 200
    utc = client.get(
        f"/api/v1/care-profiles/{profile_id}/wellbeing-checkins/summary",
        headers=auth(context["owner"]),
        params={
            "start_date": "2026-09-17",
            "end_date": "2026-09-17",
        },
    ).json()
    assert melbourne["checkin_count"] == 1
    assert melbourne["daily_averages"][0]["average_score"] == 40.0
    assert utc["checkin_count"] == 0
    assert utc["daily_averages"][0]["average_score"] is None


def test_summary_rejects_invalid_range_and_profile_rejects_invalid_timezone(
    client: TestClient,
) -> None:
    context = setup_profile(client)
    url = f"/api/v1/care-profiles/{context['profile']['id']}/wellbeing-checkins/summary"
    invalid_range = client.get(
        url,
        headers=auth(context["owner"]),
        params={"start_date": "2026-09-18", "end_date": "2026-09-17"},
    )
    invalid_timezone = client.patch(
        f"/api/v1/care-profiles/{context['profile']['id']}",
        headers=auth(context["owner"]),
        json={"timezone": "Mars/Olympus"},
    )
    assert invalid_range.status_code == 422
    assert invalid_timezone.status_code == 422
