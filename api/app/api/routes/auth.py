from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.config import Settings, get_settings
from app.core.security import create_access_token
from app.models import User
from app.schemas.auth import AppleLoginRequest, DevLoginRequest, TokenResponse
from app.schemas.user import UserRead
from app.services.apple_auth import AppleTokenVerifier, get_apple_token_verifier

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
        identity = verifier.verify(payload.identity_token)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Apple Sign-In is not configured",
        ) from exc

    user = db.scalar(select(User).where(User.apple_subject == identity.subject))
    if user is None:
        user = User(
            email=identity.email.lower(),
            display_name=(payload.display_name or identity.email.split("@", 1)[0]).strip(),
            apple_subject=identity.subject,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return TokenResponse(
        access_token=create_access_token(user.id), user=UserRead.model_validate(user)
    )


@router.get("/me", response_model=UserRead)
def me(current_user: CurrentUser) -> User:
    return current_user
