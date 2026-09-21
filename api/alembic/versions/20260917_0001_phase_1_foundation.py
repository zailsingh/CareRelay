"""Phase 1 identity and care profile foundation."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260917_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("apple_subject", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("apple_subject"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "care_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "care_memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("care_profile_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "admin",
                "family",
                "carer",
                "cared_person",
                name="carerole",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "role IN ('admin', 'family', 'carer', 'cared_person')",
            name="ck_care_memberships_role",
        ),
        sa.ForeignKeyConstraint(["care_profile_id"], ["care_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("care_profile_id", "user_id", name="uq_profile_user_membership"),
    )
    op.create_index(
        "ix_care_memberships_profile", "care_memberships", ["care_profile_id"], unique=False
    )
    op.create_index("ix_care_memberships_user", "care_memberships", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_care_memberships_user", table_name="care_memberships")
    op.drop_index("ix_care_memberships_profile", table_name="care_memberships")
    op.drop_table("care_memberships")
    op.drop_table("care_profiles")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
