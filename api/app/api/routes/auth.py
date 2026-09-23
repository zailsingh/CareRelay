from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.core.config import Settings, get_settings
from app.core.security import create_access_token
from app.models import CareMembership, CareProfile, User, UserIdentity
from app.models.enums import AuditAction, CareRole
from app.schemas.auth import (
    AppleLoginRequest,
    AppleNotificationRequest,
    DevLoginRequest,
    TokenResponse,
)
from app.schemas.user import UserRead
from app.services.apple_auth import (
    AppleTokenVerifier,
    AppleVerificationError,
    get_apple_token_verifier,
)
from app.services.audit import add_audit_entry

router = APIRouter()


@router.post("/dev-login", response_model=TokenResponse)
def dev_login(
    payload: DevLoginRequest,
    db: DbSession,
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    if not settings.dev_login_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    email = payload.email.lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, display_name=payload.display_name.strip())
        db.add(user)
    else:
        user.display_name = payload.display_name.strip()
    db.commit()
    db.refresh(user)
    return TokenResponse(
        access_token=create_access_token(user.id), user=UserRead.model_validate(user)
    )


@router.post("/apple", response_model=TokenResponse)
def apple_login(
    payload: AppleLoginRequest,
    db: DbSession,
    verifier: Annotated[AppleTokenVerifier, Depends(get_apple_token_verifier)],
) -> TokenResponse:
    try:
        identity = verifier.verify(payload.identity_token, payload.nonce)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Apple Sign-In is not configured",
        ) from exc

    except AppleVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Apple identity token is invalid or expired",
        ) from exc

    provider_identity = db.scalar(
        select(UserIdentity).where(
            UserIdentity.provider == "apple",
            UserIdentity.provider_subject == identity.subject,
        )
    )
    if provider_identity is not None and provider_identity.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Apple authorization revoked"
        )
    if provider_identity is None:
        email = identity.email
        if email and db.scalar(select(User.id).where(User.email == email)) is not None:
            email = None
        display_name = payload.display_name or (identity.email or "CareRelay user").split("@", 1)[0]
        user = User(
            email=email,
            display_name=display_name.strip(),
        )
        provider_identity = UserIdentity(
            user=user,
            provider="apple",
            provider_subject=identity.subject,
            email_at_signup=identity.email,
        )
        db.add_all([user, provider_identity])
        db.commit()
        db.refresh(user)
    else:
        user = provider_identity.user
    return TokenResponse(
        access_token=create_access_token(user.id), user=UserRead.model_validate(user)
    )


@router.post("/apple/notifications", status_code=status.HTTP_204_NO_CONTENT)
def apple_notification(
    payload: AppleNotificationRequest,
    db: DbSession,
    verifier: Annotated[AppleTokenVerifier, Depends(get_apple_token_verifier)],
) -> Response:
    try:
        event = verifier.verify_notification(payload.payload)
    except (AppleVerificationError, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Apple notification"
        ) from exc
    identity = db.scalar(
        select(UserIdentity).where(
            UserIdentity.provider == "apple",
            UserIdentity.provider_subject == event.subject,
        )
    )
    if identity and event.event_type in {
        "consent-revoked",
        "account-delete",
        "account-deleted",
    }:
        identity.revoked_at = datetime.now(UTC)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
def request_account_deletion(db: DbSession, current_user: CurrentUser) -> Response:
    admin_profiles = list(
        db.scalars(
            select(CareMembership.care_profile_id).where(
                CareMembership.user_id == current_user.id,
                CareMembership.role == CareRole.ADMIN,
            )
        ).all()
    )
    for profile_id in admin_profiles:
        admin_count = db.scalar(
            select(func.count(CareMembership.id)).where(
                CareMembership.care_profile_id == profile_id,
                CareMembership.role == CareRole.ADMIN,
            )
        )
        if int(admin_count or 0) <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Transfer administration before deleting your account",
            )
    memberships = list(
        db.scalars(select(CareMembership).where(CareMembership.user_id == current_user.id)).all()
    )
    for membership in memberships:
        profile = db.get(CareProfile, membership.care_profile_id)
        if profile and profile.subject_user_id == current_user.id:
            profile.subject_user_id = None
        add_audit_entry(
            db,
            care_profile_id=membership.care_profile_id,
            actor_user_id=current_user.id,
            action=AuditAction.ACCOUNT_DELETION_REQUESTED,
            target_type="user",
            target_id=current_user.id,
        )
        db.delete(membership)
    for identity in current_user.identities:
        identity.revoked_at = datetime.now(UTC)
    current_user.deletion_requested_at = datetime.now(UTC)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserRead)
def me(current_user: CurrentUser) -> User:
    return current_user
