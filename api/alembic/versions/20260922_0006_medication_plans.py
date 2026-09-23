"""Add medication plans, normalized schedules, and authoritative dose records."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260922_0006"
down_revision: str | None = "20260918_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("care_events") as batch_op:
        batch_op.alter_column(
            "source",
            existing_type=sa.String(length=6),
            type_=sa.String(length=7),
            existing_nullable=False,
        )
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.alter_column(
            "action",
            existing_type=sa.String(length=18),
            type_=sa.String(length=27),
            existing_nullable=False,
        )

    op.create_table(
        "medications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("care_profile_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("strength_text", sa.String(length=200), nullable=True),
        sa.Column("form", sa.String(length=100), nullable=True),
        sa.Column("instructions_text", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "schedule_type",
            sa.Enum("scheduled", "as_needed", name="medicationscheduletype", native_enum=False),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="medication_date_range",
        ),
        sa.ForeignKeyConstraint(["care_profile_id"], ["care_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_medications_profile_active", "medications", ["care_profile_id", "active"])

    op.create_table(
        "medication_schedules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("medication_id", sa.Uuid(), nullable=False),
        sa.Column("local_time", sa.Time(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="medication_schedule_date_range",
        ),
        sa.ForeignKeyConstraint(["medication_id"], ["medications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_medication_schedules_medication_active",
        "medication_schedules",
        ["medication_id", "active"],
    )

    op.create_table(
        "medication_schedule_days",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("schedule_id", sa.Uuid(), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.CheckConstraint("day_of_week >= 0 AND day_of_week <= 6", name="day_of_week_range"),
        sa.ForeignKeyConstraint(["schedule_id"], ["medication_schedules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("schedule_id", "day_of_week", name="uq_schedule_day"),
    )

    op.create_table(
        "medication_dose_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("medication_id", sa.Uuid(), nullable=False),
        sa.Column("schedule_id", sa.Uuid(), nullable=True),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_local_date", sa.Date(), nullable=False),
        sa.Column("scheduled_local_time", sa.Time(), nullable=False),
        sa.Column("scheduled_timezone", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            sa.Enum("taken", "missed", "skipped", name="medicationdosestatus", native_enum=False),
            nullable=False,
        ),
        sa.Column("recorded_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("care_event_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["care_event_id"], ["care_events.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["medication_id"], ["medications.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["schedule_id"], ["medication_schedules.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("care_event_id"),
        sa.UniqueConstraint("schedule_id", "scheduled_for", name="uq_scheduled_dose_outcome"),
    )
    op.create_index(
        "ix_medication_doses_medication_scheduled",
        "medication_dose_records",
        ["medication_id", "scheduled_for"],
    )
    op.create_index(
        "ix_medication_doses_recorded_by",
        "medication_dose_records",
        ["recorded_by_user_id"],
    )


def downgrade() -> None:
    # Linked projections remain as historical CareEvents when the structured source is removed.
    op.drop_index("ix_medication_doses_recorded_by", table_name="medication_dose_records")
    op.drop_index("ix_medication_doses_medication_scheduled", table_name="medication_dose_records")
    op.drop_table("medication_dose_records")
    op.drop_table("medication_schedule_days")
    op.drop_index("ix_medication_schedules_medication_active", table_name="medication_schedules")
    op.drop_table("medication_schedules")
    op.drop_index("ix_medications_profile_active", table_name="medications")
    op.drop_table("medications")
    op.execute(
        "DELETE FROM audit_logs WHERE target_type IN "
        "('medication', 'medication_schedule', 'medication_dose')"
    )
    op.execute("UPDATE care_events SET source = 'family' WHERE source = 'subject'")
    op.execute(
        "UPDATE care_events SET event_type = 'general_note' WHERE event_type = 'medication_skipped'"
    )
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.alter_column(
            "action",
            existing_type=sa.String(length=27),
            type_=sa.String(length=18),
            existing_nullable=False,
        )
    with op.batch_alter_table("care_events") as batch_op:
        batch_op.alter_column(
            "source",
            existing_type=sa.String(length=7),
            type_=sa.String(length=6),
            existing_nullable=False,
        )
