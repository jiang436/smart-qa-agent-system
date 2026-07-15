"""Initial schema — 创建所有业务表

Revision ID: 8f9d8bdcbf2f
Revises:
Create Date: 2026-07-15 12:08:42.292323

通过 `alembic upgrade head` 应用到数据库。
与 `init_db()` 的 `Base.metadata.create_all()` 等效，但支持版本追踪和回滚。
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision: str = "8f9d8bdcbf2f"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── sessions ──
    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("intent", sa.String(32), nullable=True),
        sa.Column("scenario", sa.String(32), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=True),
        sa.Column("messages", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
    )
    op.create_index("ix_sessions_session_id", "sessions", ["session_id"])
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    # ── user_devices ──
    op.create_table(
        "user_devices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("device_name", sa.String(128), nullable=False),
        sa.Column("device_model", sa.String(64), nullable=False),
        sa.Column("firmware_version", sa.String(32), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("bound_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_devices_user_id", "user_devices", ["user_id"])

    # ── consumable_orders ──
    op.create_table(
        "consumable_orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("device_model", sa.String(64), nullable=False),
        sa.Column("part_type", sa.String(64), nullable=False),
        sa.Column("part_name", sa.String(128), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("source", sa.String(32), nullable=True),
        sa.Column("ordered_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id"),
    )
    op.create_index("ix_consumable_orders_order_id", "consumable_orders", ["order_id"])
    op.create_index("ix_consumable_orders_user_id", "consumable_orders", ["user_id"])

    # ── device_usage_logs ──
    op.create_table(
        "device_usage_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("device_name", sa.String(128), nullable=False),
        sa.Column("device_model", sa.String(64), nullable=False),
        sa.Column("clean_area", sa.Float(), nullable=True),
        sa.Column("duration_minutes", sa.Float(), nullable=True),
        sa.Column("battery_consumed", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(8), nullable=True),
        sa.Column("status", sa.String(32), nullable=True),
        sa.Column("recorded_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_device_usage_logs_user_id", "device_usage_logs", ["user_id"])

    # ── knowledge_files ──
    op.create_table(
        "knowledge_files",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("filename", sa.String(256), nullable=False),
        sa.Column("file_type", sa.String(16), nullable=False),
        sa.Column("chunks", sa.Integer(), nullable=True),
        sa.Column("dimension", sa.Integer(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── user_profiles ──
    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("device_model", sa.String(64), nullable=True),
        sa.Column("device_sn", sa.String(64), nullable=True),
        sa.Column("preferred_mode", sa.String(32), nullable=True),
        sa.Column("mopping_enabled", sa.String(8), nullable=True),
        sa.Column("home_layout", sa.String(64), nullable=True),
        sa.Column("tags", sa.Text(), nullable=True),
        sa.Column("conversation_count", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_user_profiles_user_id", "user_profiles", ["user_id"])


def downgrade() -> None:
    """回滚 — 删除所有表"""
    op.drop_index("ix_user_profiles_user_id", table_name="user_profiles")
    op.drop_table("user_profiles")
    op.drop_table("knowledge_files")
    op.drop_index("ix_device_usage_logs_user_id", table_name="device_usage_logs")
    op.drop_table("device_usage_logs")
    op.drop_index("ix_consumable_orders_user_id", table_name="consumable_orders")
    op.drop_index("ix_consumable_orders_order_id", table_name="consumable_orders")
    op.drop_table("consumable_orders")
    op.drop_index("ix_user_devices_user_id", table_name="user_devices")
    op.drop_table("user_devices")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_index("ix_sessions_session_id", table_name="sessions")
    op.drop_table("sessions")
