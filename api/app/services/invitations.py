import hashlib
import secrets
from datetime import UTC, datetime

from app.models.invitation import CareInvitation
from app.schemas.invitation import InvitationRead
from app.services.wellbeing_summary import as_utc


def generate_invitation_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, hash_invitation_token(token)


def hash_invitation_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def invitation_status(invitation: CareInvitation) -> str:
    if invitation.accepted_at is not None:
        return "accepted"
    if invitation.revoked_at is not None:
        return "revoked"
    if as_utc(invitation.expires_at) <= datetime.now(UTC):
        return "expired"
    return "pending"


def invitation_read(invitation: CareInvitation, *, accept_url: str | None = None) -> InvitationRead:
    delivery = (
        "sent"
        if invitation.email_sent_at is not None
        else "failed"
        if invitation.email_delivery_error
        else "pending"
    )
    return InvitationRead(
        id=invitation.id,
        care_profile_id=invitation.care_profile_id,
        invited_email=invitation.invited_email,
        intended_role=invitation.intended_role,
        is_subject_invite=invitation.is_subject_invite,
        status=invitation_status(invitation),
        expires_at=invitation.expires_at,
        accepted_at=invitation.accepted_at,
        email_sent_at=invitation.email_sent_at,
        delivery_status=delivery,
        accept_url=accept_url,
        created_at=invitation.created_at,
    )
