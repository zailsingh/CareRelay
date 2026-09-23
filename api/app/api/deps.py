from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import CareMembership, CareProfile, User
from app.models.enums import CareRole

bearer_scheme = HTTPBearer(auto_error=False)
DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        user_id = decode_access_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token"
        ) from exc
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if user.deletion_requested_at is not None or (
        user.identities and all(identity.revoked_at is not None for identity in user.identities)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication identity is no longer active",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


@dataclass(frozen=True)
class ProfileAccess:
    profile: CareProfile
    membership: CareMembership


def require_profile_membership(
    care_profile_id: UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> ProfileAccess:
    row = db.execute(
        select(CareProfile, CareMembership)
        .join(CareMembership, CareMembership.care_profile_id == CareProfile.id)
        .where(
            CareProfile.id == care_profile_id,
            CareMembership.user_id == current_user.id,
        )
    ).one_or_none()
    if row is None:
        # A non-member cannot use this response to discover whether the profile exists.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Care profile not found")
    return ProfileAccess(profile=row[0], membership=row[1])


ProfileMemberAccess = Annotated[ProfileAccess, Depends(require_profile_membership)]


def require_profile_admin(access: ProfileMemberAccess) -> ProfileAccess:
    if access.membership.role != CareRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return access


ProfileAdminAccess = Annotated[ProfileAccess, Depends(require_profile_admin)]


def require_cared_person(access: ProfileMemberAccess) -> ProfileAccess:
    if access.membership.role != CareRole.CARED_PERSON:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the cared-for person can create a self report",
        )
    return access


ProfileCaredPersonAccess = Annotated[ProfileAccess, Depends(require_cared_person)]


def require_profile_subject(access: ProfileMemberAccess) -> ProfileAccess:
    if access.profile.subject_user_id != access.membership.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the person this care profile is about can create a self report",
        )
    return access


ProfileSubjectAccess = Annotated[ProfileAccess, Depends(require_profile_subject)]
