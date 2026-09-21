"""Add profile chat, unread state, attachments metadata, and event source links."""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "20260918_0004"
down_revision: str | None = "20260917_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_rooms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("care_profile_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["care_profile_id"], ["care_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("care_profile_id"),
    )

    bind = op.get_bind()
    profiles = bind.execute(sa.text("SELECT id FROM care_profiles")).fetchall()
    for profile in profiles:
        bind.execute(
            sa.text(
                "INSERT INTO chat_rooms (id, care_profile_id, name) "
                "VALUES (:id, :care_profile_id, :name)"
            ),
            {
                "id": str(uuid4()),
                "care_profile_id": profile[0],
                "name": "Family chat",
            },
        )

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chat_room_id", sa.Uuid(), nullable=False),
        sa.Column("sender_user_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column(
            "sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["chat_room_id"], ["chat_rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_chat_messages_room_sent",
        "chat_messages",
        ["chat_room_id", "sent_at", "id"],
    )
    op.create_index("ix_chat_messages_sender", "chat_messages", ["sender_user_id"])

    op.create_table(
        "chat_read_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chat_room_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("last_read_message_id", sa.Uuid(), nullable=True),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["chat_room_id"], ["chat_rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["last_read_message_id"], ["chat_messages.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_room_id", "user_id", name="uq_chat_read_state_room_user"),
    )
    op.create_index("ix_chat_read_states_user", "chat_read_states", ["user_id"])

    op.create_table(
        "chat_attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chat_message_id", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["chat_message_id"], ["chat_messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )

    with op.batch_alter_table("care_events") as batch_op:
        batch_op.add_column(sa.Column("source_chat_message_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_care_events_source_chat_message_id_chat_messages",
            "chat_messages",
            ["source_chat_message_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_care_events_source_chat_message_id", ["source_chat_message_id"])


def downgrade() -> None:
    with op.batch_alter_table("care_events") as batch_op:
        batch_op.drop_index("ix_care_events_source_chat_message_id")
        batch_op.drop_constraint(
            "fk_care_events_source_chat_message_id_chat_messages", type_="foreignkey"
        )
        batch_op.drop_column("source_chat_message_id")
    op.drop_table("chat_attachments")
    op.drop_index("ix_chat_read_states_user", table_name="chat_read_states")
    op.drop_table("chat_read_states")
    op.drop_index("ix_chat_messages_sender", table_name="chat_messages")
    op.drop_index("ix_chat_messages_room_sent", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_table("chat_rooms")
