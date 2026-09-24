import hashlib
import smtplib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.main import app
from app.models import CareInvitation, UserIdentity
from app.models.audit_log import AuditLog
from app.models.enums import AuditAction
from app.services.apple_auth import (
    AppleIdentity,
    AppleNotification,
    AppleTokenVerifier,
    AppleVerificationError,
    ProductionAppleTokenVerifier,
    get_apple_token_verifier,
)
from app.services.email_provider import (
    EmailDeliveryError,
    GmailSMTPProvider,
    InvitationEmail,
    MockEmailProvider,
    get_email_provider,
    invitation_message,
)
from tests.conftest import auth, login


class FixtureAppleVerifier(AppleTokenVerifier):
    def __init__(
        self,
        subject: str = "apple-subject",
        email: str | None = "relay@privaterelay.appleid.com",
    ) -> None:
        self.identity = AppleIdentity(subject=subject, email=email)
        self.notification = AppleNotification(subject=subject, event_type="consent-revoked")

    def verify(self, identity_token: str, nonce: str) -> AppleIdentity:
        if identity_token == "invalid":
            raise AppleVerificationError("invalid")
        return self.identity

    def verify_notification(self, signed_payload: str) -> AppleNotification:
        return self.notification


class FailingEmailProvider:
    def send_invitation(self, invitation: InvitationEmail) -> None:
        raise EmailDeliveryError("smtp password must not escape")


def apple_login(client: TestClient, verifier: AppleTokenVerifier, name: str = "Zail"):
    app.dependency_overrides[get_apple_token_verifier] = lambda: verifier
    try:
        return client.post(
            "/api/v1/auth/apple",
            json={"identity_token": "fixture", "nonce": "a" * 32, "display_name": name},
        )
    finally:
        app.dependency_overrides.pop(get_apple_token_verifier, None)


def profile(client: TestClient, token: str, *, for_self: bool = False) -> dict[str, Any]:
    response = client.post(
        "/api/v1/care-profiles",
        headers=auth(token),
        json={"name": "Deepika", "timezone": "Australia/Melbourne", "for_self": for_self},
    )
    assert response.status_code == 201, response.text
    return response.json()


def invite(
    client: TestClient,
    token: str,
    profile_id: str,
    *,
    email: str = "invitee@example.com",
    role: str = "family",
    subject: bool = False,
):
    return client.post(
        f"/api/v1/care-profiles/{profile_id}/invitations",
        headers=auth(token),
        json={"invited_email": email, "intended_role": role, "is_subject_invite": subject},
    )


def test_apple_login_uses_subject_not_email_and_repeats_same_user(
    client: TestClient, db: Session
) -> None:
    first = apple_login(client, FixtureAppleVerifier(email="shared@example.com"))
    assert first.status_code == 200
    assert first.json()["user"]["display_name"] == "Zail"
    other = login(client, "other@example.com", "Other")
    assert other
    second = apple_login(
        client,
        FixtureAppleVerifier(subject="apple-other", email="shared@example.com"),
        "Second",
    )
    assert second.status_code == 200
    assert second.json()["user"]["id"] != first.json()["user"]["id"]
    repeat = apple_login(client, FixtureAppleVerifier(email=None), "Ignored")
    assert repeat.json()["user"]["id"] == first.json()["user"]["id"]
    identity = db.scalar(
        select(UserIdentity).where(UserIdentity.provider_subject == "apple-subject")
    )
    assert identity is not None
    assert identity.email_at_signup == "shared@example.com"


def test_invalid_apple_token_is_rejected(client: TestClient) -> None:
    verifier = FixtureAppleVerifier()
    app.dependency_overrides[get_apple_token_verifier] = lambda: verifier
    try:
        response = client.post(
            "/api/v1/auth/apple",
            json={"identity_token": "invalid", "nonce": "b" * 32},
        )
    finally:
        app.dependency_overrides.pop(get_apple_token_verifier, None)
    assert response.status_code == 401


@pytest.mark.parametrize(
    "claims",
    [
        {"iss": "https://evil.example"},
        {"aud": "wrong.client"},
        {"exp": datetime.now(UTC) - timedelta(minutes=1)},
        {"nonce": "wrong-nonce"},
    ],
    ids=["issuer", "audience", "expired", "nonce"],
)
def test_production_apple_verifier_rejects_invalid_claims(claims) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nonce = "secure-random-nonce"
    payload = {
        "iss": "https://appleid.apple.com",
        "aud": "com.carerelay.mobile",
        "sub": "apple-sub",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
        "nonce": hashlib.sha256(nonce.encode()).hexdigest(),
        **claims,
    }
    token = jwt.encode(payload, key, algorithm="RS256", headers={"kid": "fixture"})
    verifier = ProductionAppleTokenVerifier("com.carerelay.mobile", "https://example.invalid")
    verifier.jwks = SimpleNamespace(
        get_signing_key_from_jwt=lambda value: SimpleNamespace(key=key.public_key())
    )
    with pytest.raises(AppleVerificationError):
        verifier.verify(token, nonce)


def test_production_apple_verifier_accepts_valid_signature_and_nonce() -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nonce = "secure-random-nonce"
    token = jwt.encode(
        {
            "iss": "https://appleid.apple.com",
            "aud": "com.carerelay.mobile",
            "sub": "apple-sub",
            "email": "Relay@PrivateRelay.AppleID.com",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
            "nonce": hashlib.sha256(nonce.encode()).hexdigest(),
        },
        key,
        algorithm="RS256",
        headers={"kid": "fixture"},
    )
    verifier = ProductionAppleTokenVerifier("com.carerelay.mobile", "https://example.invalid")
    verifier.jwks = SimpleNamespace(
        get_signing_key_from_jwt=lambda value: SimpleNamespace(key=key.public_key())
    )
    identity = verifier.verify(token, nonce)
    assert identity.subject == "apple-sub"
    assert identity.email == "relay@privaterelay.appleid.com"


@pytest.mark.parametrize("events_as_json_string", [False, True])
def test_production_apple_verifier_validates_server_notification(
    events_as_json_string: bool,
) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    events: dict[str, str] | str = {"type": "consent-revoked", "sub": "apple-sub"}
    if events_as_json_string:
        events = '{"type":"consent-revoked","sub":"apple-sub"}'
    token = jwt.encode(
        {
            "iss": "https://appleid.apple.com",
            "aud": "com.carerelay.mobile",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
            "events": events,
        },
        key,
        algorithm="RS256",
        headers={"kid": "fixture"},
    )
    verifier = ProductionAppleTokenVerifier("com.carerelay.mobile", "https://example.invalid")
    verifier.jwks = SimpleNamespace(
        get_signing_key_from_jwt=lambda value: SimpleNamespace(key=key.public_key())
    )
    notification = verifier.verify_notification(token)
    assert notification.subject == "apple-sub"
    assert notification.event_type == "consent-revoked"


def test_production_apple_verifier_rejects_invalid_signature() -> None:
    signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nonce = "secure-random-nonce"
    token = jwt.encode(
        {
            "iss": "https://appleid.apple.com",
            "aud": "com.carerelay.mobile",
            "sub": "apple-sub",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
            "nonce": hashlib.sha256(nonce.encode()).hexdigest(),
        },
        signing_key,
        algorithm="RS256",
        headers={"kid": "fixture"},
    )
    verifier = ProductionAppleTokenVerifier("com.carerelay.mobile", "https://example.invalid")
    verifier.jwks = SimpleNamespace(
        get_signing_key_from_jwt=lambda value: SimpleNamespace(key=other_key.public_key())
    )
    with pytest.raises(AppleVerificationError):
        verifier.verify(token, nonce)


def test_onboarding_profile_admin_and_self_care(client: TestClient) -> None:
    token = apple_login(client, FixtureAppleVerifier()).json()["access_token"]
    someone_else = profile(client, token)
    assert someone_else["role"] == "admin"
    assert someone_else["subject_user_id"] is None
    self_profile = profile(client, token, for_self=True)
    assert (
        self_profile["subject_user_id"]
        == apple_login(client, FixtureAppleVerifier()).json()["user"]["id"]
    )


def test_invitation_token_is_hashed_accepts_different_apple_email_and_links_subject(
    client: TestClient, db: Session
) -> None:
    admin = login(client, "admin@example.com", "Zail")
    care_profile = profile(client, admin)
    response = invite(client, admin, care_profile["id"], subject=True)
    assert response.status_code == 201
    raw_token = response.json()["accept_url"].rsplit("/", 1)[-1]
    stored = db.get(CareInvitation, UUID(response.json()["id"]))
    assert stored is not None
    assert raw_token not in stored.token_hash
    audit_rows = db.scalars(
        select(AuditLog).where(AuditLog.care_profile_id == stored.care_profile_id)
    ).all()
    assert raw_token not in str([(row.before_state, row.after_state) for row in audit_rows])
    invitee = apple_login(
        client,
        FixtureAppleVerifier(subject="deepika-sub", email="different@privaterelay.appleid.com"),
        "Deepika",
    ).json()
    accepted = client.post(
        "/api/v1/invitations/accept",
        headers=auth(invitee["access_token"]),
        json={"token": raw_token},
    )
    assert accepted.status_code == 200
    assert accepted.json()["subject_linked"] is True
    assert (
        client.get(f"/api/v1/care-profiles/{care_profile['id']}", headers=auth(admin)).json()[
            "subject_user_id"
        ]
        == invitee["user"]["id"]
    )
    assert (
        client.post(
            "/api/v1/invitations/accept",
            headers=auth(invitee["access_token"]),
            json={"token": raw_token},
        ).status_code
        == 410
    )


def test_invitation_requires_admin_and_resend_rotates_token(client: TestClient) -> None:
    admin = login(client, "rotate-admin@example.com", "Admin")
    family = login(client, "rotate-family@example.com", "Family")
    care_profile = profile(client, admin)
    client.post(
        f"/api/v1/care-profiles/{care_profile['id']}/members",
        headers=auth(admin),
        json={"email": "rotate-family@example.com", "role": "family"},
    )
    assert invite(client, family, care_profile["id"]).status_code == 403
    created = invite(client, admin, care_profile["id"])
    old_token = created.json()["accept_url"].rsplit("/", 1)[-1]
    resent = client.post(
        f"/api/v1/care-profiles/{care_profile['id']}/invitations/{created.json()['id']}/resend",
        headers=auth(admin),
    )
    new_token = resent.json()["accept_url"].rsplit("/", 1)[-1]
    assert new_token != old_token
    assert (
        client.post(
            "/api/v1/invitations/accept", headers=auth(family), json={"token": old_token}
        ).status_code
        == 410
    )


def test_invitation_requires_auth_and_revoked_token_cannot_be_used(client: TestClient) -> None:
    admin = login(client, "revoke-admin@example.com", "Admin")
    invitee = login(client, "revoke-invitee@example.com", "Invitee")
    care_profile = profile(client, admin)
    created = invite(client, admin, care_profile["id"])
    raw_token = created.json()["accept_url"].rsplit("/", 1)[-1]
    assert client.post("/api/v1/invitations/accept", json={"token": raw_token}).status_code == 401
    assert (
        client.delete(
            f"/api/v1/care-profiles/{care_profile['id']}/invitations/{created.json()['id']}",
            headers=auth(admin),
        ).status_code
        == 204
    )
    assert (
        client.post(
            "/api/v1/invitations/accept", headers=auth(invitee), json={"token": raw_token}
        ).status_code
        == 410
    )


@pytest.mark.parametrize("role", ["family", "carer"])
def test_invitation_creates_requested_member_role(client: TestClient, role: str) -> None:
    admin = login(client, f"{role}-admin@example.com", "Admin")
    invitee = login(client, f"{role}-invitee@example.com", "Invitee")
    care_profile = profile(client, admin)
    created = invite(
        client,
        admin,
        care_profile["id"],
        email=f"{role}-invitee@example.com",
        role=role,
    )
    raw_token = created.json()["accept_url"].rsplit("/", 1)[-1]
    accepted = client.post(
        "/api/v1/invitations/accept", headers=auth(invitee), json={"token": raw_token}
    )
    assert accepted.status_code == 200
    assert accepted.json()["role"] == role


def test_duplicate_membership_is_preserved_without_duplicate(client: TestClient) -> None:
    admin = login(client, "duplicate-admin@example.com", "Admin")
    member = login(client, "duplicate-member@example.com", "Member")
    care_profile = profile(client, admin)
    added = client.post(
        f"/api/v1/care-profiles/{care_profile['id']}/members",
        headers=auth(admin),
        json={"email": "duplicate-member@example.com", "role": "family"},
    )
    assert added.status_code == 201
    created = invite(
        client,
        admin,
        care_profile["id"],
        email="duplicate-member@example.com",
        role="carer",
    )
    raw_token = created.json()["accept_url"].rsplit("/", 1)[-1]
    accepted = client.post(
        "/api/v1/invitations/accept", headers=auth(member), json={"token": raw_token}
    )
    assert accepted.status_code == 200
    assert accepted.json()["role"] == "family"
    rows = client.get(
        f"/api/v1/care-profiles/{care_profile['id']}/members", headers=auth(admin)
    ).json()
    assert len([row for row in rows if row["email"] == "duplicate-member@example.com"]) == 1


def test_revoked_expired_and_conflicting_subject_invites_fail(
    client: TestClient, db: Session
) -> None:
    admin = login(client, "states-admin@example.com", "Admin")
    first_subject = login(client, "states-first@example.com", "First")
    invitee = login(client, "states-invitee@example.com", "Invitee")
    care_profile = profile(client, admin)
    client.post(
        f"/api/v1/care-profiles/{care_profile['id']}/members",
        headers=auth(admin),
        json={"email": "states-first@example.com", "role": "family"},
    )
    first_user = client.get("/api/v1/auth/me", headers=auth(first_subject)).json()
    client.patch(
        f"/api/v1/care-profiles/{care_profile['id']}",
        headers=auth(admin),
        json={"subject_user_id": first_user["id"]},
    )
    created = invite(client, admin, care_profile["id"], subject=True)
    token = created.json()["accept_url"].rsplit("/", 1)[-1]
    assert (
        client.post(
            "/api/v1/invitations/accept", headers=auth(invitee), json={"token": token}
        ).status_code
        == 409
    )
    stored = db.get(CareInvitation, UUID(created.json()["id"]))
    stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert (
        client.post(
            "/api/v1/invitations/accept", headers=auth(invitee), json={"token": token}
        ).status_code
        == 410
    )


def test_email_delivery_failure_is_safe_and_retryable(client: TestClient, caplog) -> None:
    admin = login(client, "email-admin@example.com", "Admin")
    care_profile = profile(client, admin)
    app.dependency_overrides[get_email_provider] = lambda: FailingEmailProvider()
    try:
        created = invite(client, admin, care_profile["id"])
    finally:
        app.dependency_overrides.pop(get_email_provider, None)
    assert created.status_code == 201
    assert created.json()["delivery_status"] == "failed"
    assert "smtp" not in created.text.lower()
    assert "smtp password must not escape" not in caplog.text


def test_email_delivery_success_is_recorded(client: TestClient) -> None:
    admin = login(client, "sent-admin@example.com", "Admin")
    care_profile = profile(client, admin)
    created = invite(client, admin, care_profile["id"])
    assert created.status_code == 201
    assert created.json()["delivery_status"] == "sent"
    assert created.json()["email_sent_at"] is not None
    assert "medication" not in created.text.lower()
    assert "wellbeing" not in created.text.lower()


def test_mock_and_gmail_email_providers_exclude_care_data(monkeypatch) -> None:
    invitation = InvitationEmail(
        recipient="person@example.com",
        inviter_name="Zail",
        profile_name="Deepika",
        intended_role="family",
        accept_url="https://example.com/invite/token",
        expires_hours=168,
    )
    mock = MockEmailProvider()
    mock.send_invitation(invitation)
    assert mock.sent == [invitation]
    message = invitation_message(invitation, "CareRelay <care@example.com>")
    rendered = message.as_string()
    plain_body = message.get_body(preferencelist=("plain",)).get_content()
    html_body = message.get_body(preferencelist=("html",)).get_content()
    assert 'href="https://example.com/invite/token"' in html_body
    assert ">Accept invitation</a>" in html_body
    assert "If the button does not work, copy this link into Safari:" in html_body
    assert "https://example.com/invite/token" in html_body
    assert "If the button does not work, copy this link into Safari:" in plain_body
    assert "https://example.com/invite/token" in plain_body
    assert "medication" not in rendered.lower()
    assert "wellbeing" not in rendered.lower()

    calls: list[str] = []

    class SMTPFixture:
        def __init__(self, host, port, timeout):
            calls.append(f"connect:{host}:{port}:{timeout}")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            calls.append("close")

        def ehlo(self):
            calls.append("ehlo")

        def starttls(self, context):
            calls.append("starttls")

        def login(self, username, password):
            calls.append("login")

        def send_message(self, message):
            calls.append("send")

    monkeypatch.setattr(smtplib, "SMTP", SMTPFixture)
    settings = Settings(
        _env_file=None,
        email_provider="gmail",
        smtp_username="care@gmail.com",
        smtp_password="app-password",
        email_from="CareRelay <care@gmail.com>",
    )
    GmailSMTPProvider(settings).send_invitation(invitation)
    assert "starttls" in calls and "login" in calls and "send" in calls and "close" in calls
    assert "app-password" not in " ".join(calls)


def test_development_invitation_landing_page_opens_existing_app_route(
    client: TestClient,
) -> None:
    response = client.get("/invite/token-with_symbols", follow_redirects=False)
    assert response.status_code == 200
    assert 'content="0;url=carerelay://invite/token-with_symbols"' in response.text
    assert 'href="carerelay://invite/token-with_symbols"' in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_final_admin_protected_and_role_management_audited(client: TestClient, db: Session) -> None:
    admin = login(client, "members-admin@example.com", "Admin")
    login(client, "members-family@example.com", "Family")
    care_profile = profile(client, admin)
    owner_membership = client.get(
        f"/api/v1/care-profiles/{care_profile['id']}/members", headers=auth(admin)
    ).json()[0]
    assert (
        client.delete(
            f"/api/v1/care-profiles/{care_profile['id']}/members/{owner_membership['id']}",
            headers=auth(admin),
        ).status_code
        == 409
    )
    added = client.post(
        f"/api/v1/care-profiles/{care_profile['id']}/members",
        headers=auth(admin),
        json={"email": "members-family@example.com", "role": "family"},
    ).json()
    changed = client.patch(
        f"/api/v1/care-profiles/{care_profile['id']}/members/{added['id']}",
        headers=auth(admin),
        json={"role": "carer"},
    )
    assert changed.status_code == 200 and changed.json()["role"] == "carer"
    removed = client.delete(
        f"/api/v1/care-profiles/{care_profile['id']}/members/{added['id']}",
        headers=auth(admin),
    )
    assert removed.status_code == 204
    actions = set(db.scalars(select(AuditLog.action)).all())
    assert AuditAction.MEMBERSHIP_ROLE_CHANGED in actions
    assert AuditAction.MEMBERSHIP_REMOVED in actions


def test_dev_login_production_gate_and_gmail_config_validation() -> None:
    assert Settings(_env_file=None, app_env="development").dev_login_enabled
    with pytest.raises(ValueError, match="SMTP_USERNAME"):
        Settings(_env_file=None, email_provider="gmail")
    production = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret="x" * 32,
        apple_client_id="com.carerelay.mobile",
    )
    assert not production.dev_login_enabled


@pytest.mark.parametrize(
    ("overrides", "missing"),
    [
        (
            {"smtp_username": "", "smtp_password": "app-password"},
            "SMTP_USERNAME",
        ),
        (
            {"smtp_username": "care@gmail.com", "smtp_password": ""},
            "SMTP_PASSWORD",
        ),
    ],
)
def test_gmail_requires_each_credential(overrides: dict[str, str], missing: str) -> None:
    with pytest.raises(ValueError, match=missing):
        Settings(
            _env_file=None,
            email_provider="gmail",
            email_from="CareRelay <care@gmail.com>",
            **overrides,
        )


def test_production_invitation_response_never_returns_raw_link(client: TestClient) -> None:
    admin = login(client, "production-invite-admin@example.com", "Admin")
    care_profile = profile(client, admin)
    settings = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret="x" * 32,
        apple_client_id="com.carerelay.mobile",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        created = invite(client, admin, care_profile["id"])
    finally:
        app.dependency_overrides.pop(get_settings, None)
    assert created.status_code == 201
    assert created.json()["accept_url"] is None


def test_production_dev_login_endpoint_is_not_available(client: TestClient) -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret="x" * 32,
        apple_client_id="com.carerelay.mobile",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        response = client.post(
            "/api/v1/auth/dev-login",
            json={"email": "blocked@example.com", "display_name": "Blocked"},
        )
    finally:
        app.dependency_overrides.pop(get_settings, None)
    assert response.status_code == 404


def test_apple_notification_revokes_auth_identity(client: TestClient, db: Session) -> None:
    verifier = FixtureAppleVerifier(subject="revoked-sub")
    result = apple_login(client, verifier)
    assert result.status_code == 200
    app.dependency_overrides[get_apple_token_verifier] = lambda: verifier
    try:
        response = client.post("/api/v1/auth/apple/notifications", json={"payload": "fixture"})
    finally:
        app.dependency_overrides.pop(get_apple_token_verifier, None)
    assert response.status_code == 204
    identity = db.scalar(select(UserIdentity).where(UserIdentity.provider_subject == "revoked-sub"))
    assert identity is not None and identity.revoked_at is not None
    assert (
        client.get("/api/v1/auth/me", headers=auth(result.json()["access_token"])).status_code
        == 401
    )


def test_account_deletion_requires_admin_transfer(client: TestClient) -> None:
    admin = login(client, "delete-admin@example.com", "Admin")
    profile(client, admin)
    response = client.delete("/api/v1/auth/account", headers=auth(admin))
    assert response.status_code == 409
    assert "Transfer administration" in response.json()["detail"]


def test_account_deletion_with_another_admin_unlinks_subject(client: TestClient) -> None:
    owner = login(client, "delete-owner@example.com", "Owner")
    second_admin = login(client, "delete-second@example.com", "Second")
    care_profile = profile(client, owner, for_self=True)
    added = client.post(
        f"/api/v1/care-profiles/{care_profile['id']}/members",
        headers=auth(owner),
        json={"email": "delete-second@example.com", "role": "admin"},
    )
    assert added.status_code == 201
    assert client.delete("/api/v1/auth/account", headers=auth(owner)).status_code == 204
    assert client.get("/api/v1/auth/me", headers=auth(owner)).status_code == 401
    remaining = client.get(
        f"/api/v1/care-profiles/{care_profile['id']}", headers=auth(second_admin)
    )
    assert remaining.status_code == 200
    assert remaining.json()["subject_user_id"] is None
