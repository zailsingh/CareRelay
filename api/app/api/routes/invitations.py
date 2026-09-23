from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, ProfileAdminAccess
from app.core.config import Settings, get_settings
from app.models import CareInvitation, CareMembership
from app.models.enums import AuditAction, CareRole
from app.schemas.invitation import (
    InvitationAccept,
    InvitationAcceptResult,
    InvitationCreate,
    InvitationRead,
)
from app.services.audit import add_audit_entry
from app.services.email_provider import (
    EmailDeliveryError,
    EmailProvider,
    InvitationEmail,
    get_email_provider,
)
from app.services.invitations import (
    generate_invitation_token,
    hash_invitation_token,
    invitation_read,
    invitation_status,
)

router = APIRouter()
EmailProviderDep = Annotated[EmailProvider, Depends(get_email_provider)]


def _accept_url(settings: Settings, token: str) -> str:
    return f"{settings.invite_base_url.rstrip('/')}/{quote(token, safe='')}"


def _send(
    *,
    db: DbSession,
    invitation: CareInvitation,
    raw_token: str,
    provider: EmailProvider,
    settings: Settings,
    actor_user_id: UUID,
    action: AuditAction,
) -> str:
    accept_url = _accept_url(settings, raw_token)
    try:
        provider.send_invitation(
            InvitationEmail(
                recipient=invitation.invited_email,
                inviter_name=invitation.creator.display_name,
                profile_name=invitation.care_profile.name,
                intended_role=(
                    "subject" if invitation.is_subject_invite else invitation.intended_role.value
                ),
                accept_url=accept_url,
                expires_hours=settings.invite_expire_hours,
            )
        )
    except EmailDeliveryError:
        invitation.email_sent_at = None
        invitation.email_delivery_error = "Delivery failed. Check email configuration and retry."
        add_audit_entry(
            db,
            care_profile_id=invitation.care_profile_id,
            actor_user_id=actor_user_id,
            action=AuditAction.INVITATION_EMAIL_DELIVERY_FAILED,
            target_type="care_invitation",
            target_id=invitation.id,
        )
    else:
        invitation.email_sent_at = datetime.now(UTC)
        invitation.email_delivery_error = None
        add_audit_entry(
            db,
            care_profile_id=invitation.care_profile_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type="care_invitation",
            target_id=invitation.id,
        )
    db.commit()
    return accept_url


@router.get("/care-profiles/{care_profile_id}/invitations", response_model=list[InvitationRead])
def list_invitations(
    care_profile_id: UUID,
    db: DbSession,
    access: ProfileAdminAccess,
) -> list[InvitationRead]:
    invitations = db.scalars(
        select(CareInvitation)
        .where(CareInvitation.care_profile_id == access.profile.id)
        .order_by(CareInvitation.created_at.desc())
    ).all()
    return [invitation_read(item) for item in invitations]


@router.post(
    "/care-profiles/{care_profile_id}/invitations",
    response_model=InvitationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_invitation(
    care_profile_id: UUID,
    payload: InvitationCreate,
    db: DbSession,
    current_user: CurrentUser,
    access: ProfileAdminAccess,
    provider: EmailProviderDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> InvitationRead:
    now = datetime.now(UTC)
    existing = db.scalars(
        select(CareInvitation).where(
            CareInvitation.care_profile_id == access.profile.id,
            CareInvitation.invited_email == payload.invited_email.lower(),
            CareInvitation.accepted_at.is_(None),
            CareInvitation.revoked_at.is_(None),
        )
    ).all()
    for item in existing:
        item.revoked_at = now
        add_audit_entry(
            db,
            care_profile_id=access.profile.id,
            actor_user_id=current_user.id,
            action=AuditAction.INVITATION_REVOKED,
            target_type="care_invitation",
            target_id=item.id,
            after_state={"reason": "superseded"},
        )
    raw_token, token_hash = generate_invitation_token()
    invitation = CareInvitation(
        care_profile_id=access.profile.id,
        care_profile=access.profile,
        invited_email=payload.invited_email.lower(),
        intended_role=CareRole(payload.intended_role),
        is_subject_invite=payload.is_subject_invite,
        token_hash=token_hash,
        created_by_user_id=current_user.id,
        creator=current_user,
        expires_at=now + timedelta(hours=settings.invite_expire_hours),
    )
    db.add(invitation)
    db.flush()
    add_audit_entry(
        db,
        care_profile_id=access.profile.id,
        actor_user_id=current_user.id,
        action=AuditAction.INVITATION_CREATED,
        target_type="care_invitation",
        target_id=invitation.id,
        after_state={"role": payload.intended_role, "is_subject_invite": payload.is_subject_invite},
    )
    db.commit()
    db.refresh(invitation)
    accept_url = _send(
        db=db,
        invitation=invitation,
        raw_token=raw_token,
        provider=provider,
        settings=settings,
        actor_user_id=current_user.id,
        action=AuditAction.INVITATION_EMAIL_SENT,
    )
    return invitation_read(
        invitation,
        accept_url=accept_url if settings.app_env.lower() != "production" else None,
    )


def _invitation_or_404(db: DbSession, profile_id: UUID, invitation_id: UUID) -> CareInvitation:
    invitation = db.scalar(
        select(CareInvitation).where(
            CareInvitation.id == invitation_id,
            CareInvitation.care_profile_id == profile_id,
        )
    )
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
    return invitation


@router.post(
    "/care-profiles/{care_profile_id}/invitations/{invitation_id}/resend",
    response_model=InvitationRead,
)
def resend_invitation(
    care_profile_id: UUID,
    invitation_id: UUID,
    db: DbSession,
    current_user: CurrentUser,
    access: ProfileAdminAccess,
    provider: EmailProviderDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> InvitationRead:
    invitation = _invitation_or_404(db, access.profile.id, invitation_id)
    if invitation.accepted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Invitation already accepted"
        )
    raw_token, invitation.token_hash = generate_invitation_token()
    invitation.revoked_at = None
    invitation.expires_at = datetime.now(UTC) + timedelta(hours=settings.invite_expire_hours)
    invitation.email_sent_at = None
    invitation.email_delivery_error = None
    add_audit_entry(
        db,
        care_profile_id=access.profile.id,
        actor_user_id=current_user.id,
        action=AuditAction.INVITATION_RESENT,
        target_type="care_invitation",
        target_id=invitation.id,
    )
    db.commit()
    accept_url = _send(
        db=db,
        invitation=invitation,
        raw_token=raw_token,
        provider=provider,
        settings=settings,
        actor_user_id=current_user.id,
        action=AuditAction.INVITATION_EMAIL_SENT,
    )
    return invitation_read(
        invitation,
        accept_url=accept_url if settings.app_env.lower() != "production" else None,
    )


@router.delete(
    "/care-profiles/{care_profile_id}/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_invitation(
    care_profile_id: UUID,
    invitation_id: UUID,
    db: DbSession,
    current_user: CurrentUser,
    access: ProfileAdminAccess,
) -> Response:
    invitation = _invitation_or_404(db, access.profile.id, invitation_id)
    if invitation.accepted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Invitation already accepted"
        )
    invitation.revoked_at = datetime.now(UTC)
    add_audit_entry(
        db,
        care_profile_id=access.profile.id,
        actor_user_id=current_user.id,
        action=AuditAction.INVITATION_REVOKED,
        target_type="care_invitation",
        target_id=invitation.id,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/invitations/accept", response_model=InvitationAcceptResult)
def accept_invitation(
    payload: InvitationAccept,
    db: DbSession,
    current_user: CurrentUser,
) -> InvitationAcceptResult:
    invitation = db.scalar(
        select(CareInvitation)
        .where(CareInvitation.token_hash == hash_invitation_token(payload.token))
        .with_for_update()
    )
    if invitation is None or invitation_status(invitation) != "pending":
        raise HTTPException(
            status_code=status.HTTP_410_GONE, detail="Invitation is no longer valid"
        )
    if invitation.is_subject_invite and invitation.care_profile.subject_user_id not in {
        None,
        current_user.id,
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This profile already has a different linked subject",
        )
    membership = db.scalar(
        select(CareMembership).where(
            CareMembership.care_profile_id == invitation.care_profile_id,
            CareMembership.user_id == current_user.id,
        )
    )
    created = membership is None
    if membership is None:
        membership = CareMembership(
            care_profile_id=invitation.care_profile_id,
            user_id=current_user.id,
            role=invitation.intended_role,
        )
        db.add(membership)
        db.flush()
    subject_linked = False
    if invitation.is_subject_invite and invitation.care_profile.subject_user_id is None:
        invitation.care_profile.subject_user_id = current_user.id
        subject_linked = True
    invitation.accepted_at = datetime.now(UTC)
    invitation.accepted_by_user_id = current_user.id
    add_audit_entry(
        db,
        care_profile_id=invitation.care_profile_id,
        actor_user_id=current_user.id,
        action=AuditAction.INVITATION_ACCEPTED,
        target_type="care_invitation",
        target_id=invitation.id,
        after_state={"membership_created": created, "subject_linked": subject_linked},
    )
    if created:
        add_audit_entry(
            db,
            care_profile_id=invitation.care_profile_id,
            actor_user_id=current_user.id,
            action=AuditAction.MEMBERSHIP_CREATED,
            target_type="care_membership",
            target_id=membership.id,
            after_state={"role": membership.role.value},
        )
    if subject_linked:
        add_audit_entry(
            db,
            care_profile_id=invitation.care_profile_id,
            actor_user_id=current_user.id,
            action=AuditAction.SUBJECT_LINKED,
            target_type="care_profile",
            target_id=invitation.care_profile_id,
        )
    db.commit()
    return InvitationAcceptResult(
        care_profile_id=invitation.care_profile_id,
        membership_id=membership.id,
        role=membership.role,
        subject_linked=subject_linked,
    )
