from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, index=True, nullable=True)
    display_name: Mapped[str] = mapped_column(String(120))
    apple_subject: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    deletion_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    memberships: Mapped[list["CareMembership"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    identities: Mapped[list["UserIdentity"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
