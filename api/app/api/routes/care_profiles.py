from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession, ProfileAdminAccess, ProfileMemberAccess
from app.models import CareMembership, CareProfile, ChatRoom, User
from app.models.enums import AuditAction, CareRole
from app.schemas.care_profile import (
    CareProfileCreate,
    CareProfileRead,
    CareProfileUpdate,
    MembershipCreate,
    MembershipRead,
)
from app.services.audit import add_audit_entry

router = APIRouter()


def profile_read(profile: CareProfile, membership: CareMembership) -> CareProfileRead:
    return CareProfileRead(
        id=profile.id,
        name=profile.name,
        role=membership.role,
        subject_user_id=profile.subject_user_id,
        timezone=profile.timezone,
        created_at=profile.created_at,
    )


@router.get("", response_model=list[CareProfileRead])
def list_care_profiles(db: DbSession, current_user: CurrentUser) -> list[CareProfileRead]:
    rows = db.execute(
        select(CareProfile, CareMembership)
        .join(CareMembership, CareMembership.care_profile_id == CareProfile.id)
        .where(CareMembership.user_id == current_user.id)
        .order_by(CareProfile.created_at.desc())
    ).all()
    return [profile_read(profile, membership) for profile, membership in rows]


@router.post("", response_model=CareProfileRead, status_code=status.HTTP_201_CREATED)
def create_care_profile(
    payload: CareProfileCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> CareProfileRead:
    profile = CareProfile(
        name=payload.name.strip(),
        timezone=payload.timezone,
        created_by_id=current_user.id,
    )
    membership = CareMembership(care_profile=profile, user_id=current_user.id, role=CareRole.ADMIN)
    db.add_all([profile, membership])
    db.flush()
    db.add(ChatRoom(care_profile_id=profile.id, name="Family chat"))
    db.commit()
    db.refresh(profile)
    db.refresh(membership)
    return profile_read(profile, membership)


@router.get("/{care_profile_id}", response_model=CareProfileRead)
def get_care_profile(
    care_profile_id: UUID,
    access: ProfileMemberAccess,
) -> CareProfileRead:
    return profile_read(access.profile, access.membership)


@router.patch("/{care_profile_id}", response_model=CareProfileRead)
def update_care_profile(
    care_profile_id: UUID,
    payload: CareProfileUpdate,
    db: DbSession,
    current_user: CurrentUser,
    access: ProfileAdminAccess,
) -> CareProfileRead:
    fields = payload.model_fields_set
    if "subject_user_id" in fields and payload.subject_user_id != access.profile.subject_user_id:
        if payload.subject_user_id is not None:
            is_member = db.scalar(
                select(CareMembership.id).where(
                    CareMembership.care_profile_id == access.profile.id,
                    CareMembership.user_id == payload.subject_user_id,
                )
            )
            if is_member is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="The profile subject must be a member of this care profile",
                )
        previous = access.profile.subject_user_id
        access.profile.subject_user_id = payload.subject_user_id
        add_audit_entry(
            db,
            care_profile_id=access.profile.id,
            actor_user_id=current_user.id,
            action=AuditAction.SUBJECT_CHANGED,
            target_type="care_profile",
            target_id=access.profile.id,
            before_state={"subject_user_id": str(previous) if previous else None},
            after_state={
                "subject_user_id": str(payload.subject_user_id) if payload.subject_user_id else None
            },
        )
    if "timezone" in fields and payload.timezone != access.profile.timezone:
        previous_timezone = access.profile.timezone
        access.profile.timezone = payload.timezone  # type: ignore[assignment]
        add_audit_entry(
            db,
            care_profile_id=access.profile.id,
            actor_user_id=current_user.id,
            action=AuditAction.TIMEZONE_CHANGED,
            target_type="care_profile",
            target_id=access.profile.id,
            before_state={"timezone": previous_timezone},
            after_state={"timezone": payload.timezone},
        )
    db.commit()
    db.refresh(access.profile)
    return profile_read(access.profile, access.membership)


@router.get("/{care_profile_id}/members", response_model=list[MembershipRead])
def list_members(
    care_profile_id: UUID,
    db: DbSession,
    access: ProfileMemberAccess,
) -> list[MembershipRead]:
    rows = db.execute(
        select(CareMembership, User)
        .join(User, User.id == CareMembership.user_id)
        .where(CareMembership.care_profile_id == access.profile.id)
        .order_by(CareMembership.created_at)
    ).all()
    return [
        MembershipRead(
            id=membership.id,
            user_id=user.id,
            display_name=user.display_name,
            email=user.email,
            role=membership.role,
            created_at=membership.created_at,
        )
        for membership, user in rows
    ]


@router.post(
    "/{care_profile_id}/members",
    response_model=MembershipRead,
    status_code=status.HTTP_201_CREATED,
)
def add_member(
    care_profile_id: UUID,
    payload: MembershipCreate,
    db: DbSession,
    access: ProfileAdminAccess,
) -> MembershipRead:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User must sign in before being added",
        )
    membership = CareMembership(
        care_profile_id=access.profile.id,
        user_id=user.id,
        role=payload.role,
    )
    db.add(membership)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member",
        ) from exc
    db.refresh(membership)
    return MembershipRead(
        id=membership.id,
        user_id=user.id,
        display_name=user.display_name,
        email=user.email,
        role=membership.role,
        created_at=membership.created_at,
    )
