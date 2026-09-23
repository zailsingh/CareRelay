from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CareProfile(Base):
    __tablename__ = "care_profiles"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120))
    subject_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    timezone: Mapped[str] = mapped_column(String(100), default="UTC", server_default="UTC")
    created_by_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    memberships: Mapped[list["CareMembership"]] = relationship(  # noqa: F821
        back_populates="care_profile", cascade="all, delete-orphan"
    )
    subject_user: Mapped["User | None"] = relationship(foreign_keys=[subject_user_id])  # noqa: F821
    medications: Mapped[list["Medication"]] = relationship(  # noqa: F821
        cascade="all, delete-orphan"
    )
