"""Add production identities and secure care invitations."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260923_0007"
down_revision: str | None = "20260922_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("email", existing_type=sa.String(length=320), nullable=True)
        batch_op.add_column(sa.Column("deletion_requested_at", sa.DateTime(timezone=True)))
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.alter_column(
            "action",
            existing_type=sa.String(length=27),
            type_=sa.String(length=32),
            existing_nullable=False,
        )

    op.create_table(
        "user_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("provider_subject", sa.String(length=255), nullable=False),
        sa.Column("email_at_signup", sa.String(length=320), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_subject", name="uq_identity"),
    )
    op.create_index("ix_user_identities_user_id", "user_identities", ["user_id"])
    op.execute(
        "INSERT INTO user_identities "
        "(id, user_id, provider, provider_subject, email_at_signup, created_at) "
        "SELECT id, id, 'apple', apple_subject, email, created_at FROM users "
        "WHERE apple_subject IS NOT NULL"
    )

    op.create_table(
        "care_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("care_profile_id", sa.Uuid(), nullable=False),
        sa.Column("invited_email", sa.String(length=320), nullable=False),
        sa.Column(
            "intended_role",
            sa.Enum("admin", "family", "carer", "cared_person", name="carerole", native_enum=False),
            nullable=False,
        ),
        sa.Column("is_subject_invite", sa.Boolean(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_delivery_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["accepted_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["care_profile_id"], ["care_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_invitations_profile_created", "care_invitations", ["care_profile_id", "created_at"]
    )
    op.create_index("ix_invitations_token_hash", "care_invitations", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_invitations_token_hash", table_name="care_invitations")
    op.drop_index("ix_invitations_profile_created", table_name="care_invitations")
    op.drop_table("care_invitations")
    op.drop_index("ix_user_identities_user_id", table_name="user_identities")
    op.drop_table("user_identities")
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.alter_column(
            "action",
            existing_type=sa.String(length=32),
            type_=sa.String(length=27),
            existing_nullable=False,
        )
    op.execute(
        "UPDATE users SET email = 'downgrade-' || CAST(id AS VARCHAR) || "
        "'@identity.invalid' WHERE email IS NULL"
    )
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("deletion_requested_at")
        batch_op.alter_column("email", existing_type=sa.String(length=320), nullable=False)
