from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import SymptomKind


class WellbeingCheckin(Base):
    __tablename__ = "wellbeing_checkins"
    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 100", name="score_range"),
        Index("ix_wellbeing_checkins_profile_occurred", "care_profile_id", "occurred_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    care_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("care_profiles.id", ondelete="CASCADE"), nullable=False
    )
    reported_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    voice_transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    reported_by: Mapped["User"] = relationship()  # noqa: F821
    symptoms: Mapped[list["WellbeingSymptom"]] = relationship(
        back_populates="checkin",
        cascade="all, delete-orphan",
        order_by="WellbeingSymptom.kind",
    )


class WellbeingSymptom(Base):
    __tablename__ = "wellbeing_symptoms"
    __table_args__ = (
        UniqueConstraint("checkin_id", "kind", name="uq_wellbeing_symptom_kind"),
        Index("ix_wellbeing_symptoms_kind", "kind"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    checkin_id: Mapped[UUID] = mapped_column(
        ForeignKey("wellbeing_checkins.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[SymptomKind] = mapped_column(
        Enum(
            SymptomKind,
            name="symptomkind",
            native_enum=False,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )

    checkin: Mapped[WellbeingCheckin] = relationship(back_populates="symptoms")
