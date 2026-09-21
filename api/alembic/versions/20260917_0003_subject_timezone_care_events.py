"""Add profile subject, timezone, structured care events, and immutable audits."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260917_0003"
down_revision: str | None = "20260917_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("care_profiles") as batch_op:
        batch_op.add_column(sa.Column("subject_user_id", sa.Uuid(), nullable=True))
        batch_op.add_column(
            sa.Column("timezone", sa.String(length=100), server_default="UTC", nullable=False)
        )
        batch_op.create_foreign_key(
            "fk_care_profiles_subject_user_id_users",
            "users",
            ["subject_user_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    # Preserve Phase 2 behavior only when the legacy cared_person role identifies one
    # unambiguous member. Profiles with zero or multiple candidates remain subjectless.
    op.execute(
        """
        UPDATE care_profiles
        SET subject_user_id = (
            SELECT care_memberships.user_id
            FROM care_memberships
            WHERE care_memberships.care_profile_id = care_profiles.id
              AND care_memberships.role = 'cared_person'
        )
        WHERE 1 = (
            SELECT COUNT(*)
            FROM care_memberships
            WHERE care_memberships.care_profile_id = care_profiles.id
              AND care_memberships.role = 'cared_person'
        )
        """
    )

    op.create_table(
        "care_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("care_profile_id", sa.Uuid(), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(
                "family_observation",
                "symptom_observation",
                "medication_taken",
                "medication_missed",
                "fall",
                "activity",
                "sleep_observation",
                "appointment",
                "general_note",
                name="careeventtype",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entered_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "source",
            sa.Enum("admin", "family", "carer", name="careeventsource", native_enum=False),
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "confirmation_status",
            sa.Enum("draft", "confirmed", name="confirmationstatus", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["care_profile_id"], ["care_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["entered_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_care_events_profile_occurred",
        "care_events",
        ["care_profile_id", "occurred_at"],
    )
    op.create_index("ix_care_events_profile_type", "care_events", ["care_profile_id", "event_type"])
    op.create_index("ix_care_events_entered_by", "care_events", ["entered_by_user_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("care_profile_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "action",
            sa.Enum(
                "subject_changed",
                "timezone_changed",
                "care_event_created",
                "care_event_updated",
                "care_event_deleted",
                name="auditaction",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column(
            "before_state",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "after_state",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["care_profile_id"], ["care_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_logs_profile_created", "audit_logs", ["care_profile_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_profile_created", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_care_events_entered_by", table_name="care_events")
    op.drop_index("ix_care_events_profile_type", table_name="care_events")
    op.drop_index("ix_care_events_profile_occurred", table_name="care_events")
    op.drop_table("care_events")
    with op.batch_alter_table("care_profiles") as batch_op:
        batch_op.drop_constraint("fk_care_profiles_subject_user_id_users", type_="foreignkey")
        batch_op.drop_column("timezone")
        batch_op.drop_column("subject_user_id")
