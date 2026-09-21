from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import CareEventSource, CareEventType, ConfirmationStatus


class CareEvent(Base):
    __tablename__ = "care_events"
    __table_args__ = (
        Index("ix_care_events_profile_occurred", "care_profile_id", "occurred_at"),
        Index("ix_care_events_profile_type", "care_profile_id", "event_type"),
        Index("ix_care_events_entered_by", "entered_by_user_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    care_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("care_profiles.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[CareEventType] = mapped_column(
        Enum(
            CareEventType,
            name="careeventtype",
            native_enum=False,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    entered_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    source: Mapped[CareEventSource] = mapped_column(
        Enum(
            CareEventSource,
            name="careeventsource",
            native_enum=False,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    structured_data: Mapped[dict] = mapped_column(
        "metadata", JSON().with_variant(JSONB(), "postgresql"), default=dict, nullable=False
    )
    confirmation_status: Mapped[ConfirmationStatus] = mapped_column(
        Enum(
            ConfirmationStatus,
            name="confirmationstatus",
            native_enum=False,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=ConfirmationStatus.CONFIRMED,
        nullable=False,
    )
    source_chat_message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    entered_by: Mapped["User"] = relationship()  # noqa: F821
