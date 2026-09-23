from datetime import date, datetime, time
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import MedicationDoseStatus, MedicationScheduleType


class Medication(Base):
    __tablename__ = "medications"
    __table_args__ = (
        Index("ix_medications_profile_active", "care_profile_id", "active"),
        CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="medication_date_range",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    care_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("care_profiles.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    strength_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    form: Mapped[str | None] = mapped_column(String(100), nullable=True)
    instructions_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    schedule_type: Mapped[MedicationScheduleType] = mapped_column(
        Enum(
            MedicationScheduleType,
            name="medicationscheduletype",
            native_enum=False,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    created_by: Mapped["User"] = relationship()  # noqa: F821
    schedules: Mapped[list["MedicationSchedule"]] = relationship(
        back_populates="medication", cascade="all, delete-orphan"
    )
    dose_records: Mapped[list["MedicationDoseRecord"]] = relationship(back_populates="medication")


class MedicationSchedule(Base):
    __tablename__ = "medication_schedules"
    __table_args__ = (
        Index("ix_medication_schedules_medication_active", "medication_id", "active"),
        CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="medication_schedule_date_range",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    medication_id: Mapped[UUID] = mapped_column(
        ForeignKey("medications.id", ondelete="CASCADE"), nullable=False
    )
    local_time: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    medication: Mapped[Medication] = relationship(back_populates="schedules")
    days: Mapped[list["MedicationScheduleDay"]] = relationship(
        back_populates="schedule", cascade="all, delete-orphan"
    )
    dose_records: Mapped[list["MedicationDoseRecord"]] = relationship(back_populates="schedule")


class MedicationScheduleDay(Base):
    __tablename__ = "medication_schedule_days"
    __table_args__ = (
        UniqueConstraint("schedule_id", "day_of_week", name="uq_schedule_day"),
        CheckConstraint("day_of_week >= 0 AND day_of_week <= 6", name="day_of_week_range"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    schedule_id: Mapped[UUID] = mapped_column(
        ForeignKey("medication_schedules.id", ondelete="CASCADE"), nullable=False
    )
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)

    schedule: Mapped[MedicationSchedule] = relationship(back_populates="days")


class MedicationDoseRecord(Base):
    __tablename__ = "medication_dose_records"
    __table_args__ = (
        UniqueConstraint("schedule_id", "scheduled_for", name="uq_scheduled_dose_outcome"),
        Index("ix_medication_doses_medication_scheduled", "medication_id", "scheduled_for"),
        Index("ix_medication_doses_recorded_by", "recorded_by_user_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    medication_id: Mapped[UUID] = mapped_column(
        ForeignKey("medications.id", ondelete="RESTRICT"), nullable=False
    )
    schedule_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("medication_schedules.id", ondelete="RESTRICT"), nullable=True
    )
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_local_date: Mapped[date] = mapped_column(Date, nullable=False)
    scheduled_local_time: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    scheduled_timezone: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[MedicationDoseStatus] = mapped_column(
        Enum(
            MedicationDoseStatus,
            name="medicationdosestatus",
            native_enum=False,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    care_event_id: Mapped[UUID] = mapped_column(
        ForeignKey("care_events.id", ondelete="RESTRICT"), unique=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    medication: Mapped[Medication] = relationship(back_populates="dose_records")
    schedule: Mapped[MedicationSchedule | None] = relationship(back_populates="dose_records")
    recorded_by: Mapped["User"] = relationship()  # noqa: F821
    care_event: Mapped["CareEvent"] = relationship()  # noqa: F821
