"""Add self-reported wellbeing check-ins and normalized symptoms."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260917_0002"
down_revision: str | None = "20260917_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "wellbeing_checkins",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("care_profile_id", sa.Uuid(), nullable=False),
        sa.Column("reported_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("voice_transcript", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="ck_wellbeing_checkins_score_range"),
        sa.ForeignKeyConstraint(["care_profile_id"], ["care_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reported_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_wellbeing_checkins_profile_occurred",
        "wellbeing_checkins",
        ["care_profile_id", "occurred_at"],
        unique=False,
    )

    op.create_table(
        "wellbeing_symptoms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("checkin_id", sa.Uuid(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "dizziness",
                "fatigue",
                "pain",
                "weakness",
                "nausea",
                "breathlessness",
                "poor_sleep",
                "low_appetite",
                "feeling_good",
                "other",
                name="symptomkind",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["checkin_id"], ["wellbeing_checkins.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checkin_id", "kind", name="uq_wellbeing_symptom_kind"),
    )
    op.create_index("ix_wellbeing_symptoms_kind", "wellbeing_symptoms", ["kind"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_wellbeing_symptoms_kind", table_name="wellbeing_symptoms")
    op.drop_table("wellbeing_symptoms")
    op.drop_index("ix_wellbeing_checkins_profile_occurred", table_name="wellbeing_checkins")
    op.drop_table("wellbeing_checkins")
