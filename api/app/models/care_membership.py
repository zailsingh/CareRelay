from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import CareRole


class CareMembership(Base):
    __tablename__ = "care_memberships"
    __table_args__ = (
        UniqueConstraint("care_profile_id", "user_id", name="uq_profile_user_membership"),
        CheckConstraint(
            "role IN ('admin', 'family', 'carer', 'cared_person')",
            name="role",
        ),
        Index("ix_care_memberships_profile", "care_profile_id"),
        Index("ix_care_memberships_user", "user_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    care_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("care_profiles.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[CareRole] = mapped_column(
        Enum(
            CareRole, native_enum=False, values_callable=lambda enum: [item.value for item in enum]
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    care_profile: Mapped["CareProfile"] = relationship(back_populates="memberships")  # noqa: F821
    user: Mapped["User"] = relationship(back_populates="memberships")  # noqa: F821
