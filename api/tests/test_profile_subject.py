from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.enums import AuditAction
from tests.conftest import auth, login


def user_id(client: TestClient, token: str) -> str:
    return client.get("/api/v1/auth/me", headers=auth(token)).json()["id"]


def create_profile(client: TestClient, owner: str, timezone: str = "UTC") -> dict:
    response = client.post(
        "/api/v1/care-profiles",
        headers=auth(owner),
        json={"name": "Mum", "timezone": timezone},
    )
    assert response.status_code == 201, response.text
    return response.json()


def checkin(client: TestClient, profile_id: str, token: str):
    return client.post(
        f"/api/v1/care-profiles/{profile_id}/wellbeing-checkins",
        headers=auth(token),
        json={"score": 72, "occurred_at": "2026-09-17T12:00:00+10:00"},
    )


def test_admin_who_is_subject_can_create_self_report(client: TestClient) -> None:
    owner = login(client, "owner@example.com", "Owner")
    profile = create_profile(client, owner)
    assigned = client.patch(
        f"/api/v1/care-profiles/{profile['id']}",
        headers=auth(owner),
        json={"subject_user_id": user_id(client, owner)},
    )
    assert assigned.status_code == 200
    assert assigned.json()["role"] == "admin"
    assert checkin(client, profile["id"], owner).status_code == 201


def test_subject_identity_is_independent_of_membership_role(client: TestClient) -> None:
    owner = login(client, "owner@example.com", "Owner")
    family = login(client, "family@example.com", "Family subject")
    profile = create_profile(client, owner)
    member = client.post(
        f"/api/v1/care-profiles/{profile['id']}/members",
        headers=auth(owner),
        json={"email": "family@example.com", "role": "family"},
    ).json()
    client.patch(
        f"/api/v1/care-profiles/{profile['id']}",
        headers=auth(owner),
        json={"subject_user_id": member["user_id"]},
    )
    assert checkin(client, profile["id"], family).status_code == 201
    assert checkin(client, profile["id"], owner).status_code == 403


def test_cared_person_role_without_subject_identity_cannot_self_report(
    client: TestClient,
) -> None:
    owner = login(client, "owner@example.com", "Owner")
    legacy_cared = login(client, "legacy@example.com", "Legacy cared role")
    profile = create_profile(client, owner)
    client.post(
        f"/api/v1/care-profiles/{profile['id']}/members",
        headers=auth(owner),
        json={"email": "legacy@example.com", "role": "cared_person"},
    )
    assert checkin(client, profile["id"], legacy_cared).status_code == 403


def test_subject_must_be_a_profile_member(client: TestClient) -> None:
    owner = login(client, "owner@example.com", "Owner")
    outsider = login(client, "outsider@example.com", "Outsider")
    profile = create_profile(client, owner)
    response = client.patch(
        f"/api/v1/care-profiles/{profile['id']}",
        headers=auth(owner),
        json={"subject_user_id": user_id(client, outsider)},
    )
    assert response.status_code == 422


def test_timezone_validation_and_profile_audits(client: TestClient, db: Session) -> None:
    owner = login(client, "owner@example.com", "Owner")
    profile = create_profile(client, owner)
    response = client.patch(
        f"/api/v1/care-profiles/{profile['id']}",
        headers=auth(owner),
        json={
            "subject_user_id": user_id(client, owner),
            "timezone": "Australia/Melbourne",
        },
    )
    assert response.status_code == 200
    assert response.json()["timezone"] == "Australia/Melbourne"

    invalid = client.patch(
        f"/api/v1/care-profiles/{profile['id']}",
        headers=auth(owner),
        json={"timezone": "Not/AZone"},
    )
    assert invalid.status_code == 422
    actions = db.scalars(select(AuditLog.action).order_by(AuditLog.created_at)).all()
    assert actions == [AuditAction.SUBJECT_CHANGED, AuditAction.TIMEZONE_CHANGED]
