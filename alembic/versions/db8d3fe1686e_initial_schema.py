"""initial schema

Revision ID: db8d3fe1686e
Revises:
Create Date: 2026-03-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "db8d3fe1686e"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Test sessions ---
    op.create_table(
        "test_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.String(100), unique=True, nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), server_default="pending", nullable=False),
        sa.Column("priority", sa.String(20), nullable=True),
        sa.Column("created_by", sa.String(100), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("idx_test_sessions_status", "test_sessions", ["status"])
    op.create_index("idx_test_sessions_created_at", "test_sessions", ["created_at"])

    # --- Test results ---
    op.create_table(
        "test_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.String(100), nullable=False),
        sa.Column("test_id", sa.String(100), nullable=False),
        sa.Column("test_name", sa.String(500), nullable=False),
        sa.Column("test_description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("severity", sa.String(20), nullable=True),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("component", sa.String(100), nullable=True),
        sa.Column("agent_name", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("stack_trace", sa.Text(), nullable=True),
        sa.Column("execution_time_ms", sa.Integer(), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("test_data", sa.JSON(), nullable=True),
        sa.Column("expected_result", sa.JSON(), nullable=True),
        sa.Column("actual_result", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("idx_test_results_session_id", "test_results", ["session_id"])
    op.create_index("idx_test_results_status", "test_results", ["status"])
    op.create_index("idx_test_results_created_at", "test_results", ["created_at"])
    op.create_index("idx_test_results_test_id", "test_results", ["test_id"])

    # --- Test metrics ---
    op.create_table(
        "test_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.String(100), nullable=False),
        sa.Column("metric_name", sa.String(100), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=False),
        sa.Column("metric_unit", sa.String(20), nullable=True),
        sa.Column(
            "recorded_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("idx_test_metrics_session_id", "test_metrics", ["session_id"])
    op.create_index("idx_test_metrics_recorded_at", "test_metrics", ["recorded_at"])

    # --- Test reports ---
    op.create_table(
        "test_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.String(100), nullable=False),
        sa.Column("report_type", sa.String(50), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("pass_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("fail_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("skip_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("pass_rate", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("generated_by", sa.String(100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("idx_test_reports_session_id", "test_reports", ["session_id"])
    op.create_index("idx_test_reports_created_at", "test_reports", ["created_at"])

    # --- Tenants ---
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(50), unique=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(100), unique=True, nullable=False),
        sa.Column("status", sa.String(20), server_default="trial", nullable=False),
        sa.Column("owner_email", sa.String(255), nullable=False),
        sa.Column("plan", sa.String(50), server_default="free", nullable=False),
        sa.Column("max_sessions", sa.Integer(), server_default="10", nullable=False),
        sa.Column("max_agents", sa.Integer(), server_default="6", nullable=False),
        sa.Column(
            "max_storage_mb", sa.Integer(), server_default="1000", nullable=False
        ),
        sa.Column(
            "redis_key_prefix", sa.String(50), server_default="default", nullable=False
        ),
        sa.Column("rabbitmq_vhost", sa.String(100), nullable=True),
        sa.Column("custom_domain", sa.String(255), nullable=True),
        sa.Column("webhook_url", sa.String(500), nullable=True),
        sa.Column("settings", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("trial_ends_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_id"),
        sa.UniqueConstraint("slug", name="uq_tenant_slug"),
    )

    # --- Tenant users ---
    op.create_table(
        "tenant_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("user_id", sa.String(100), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), server_default="member", nullable=False),
        sa.Column("is_owner", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_admin", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_tenant_user"),
    )

    # --- Tenant API keys ---
    op.create_table(
        "tenant_api_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("key_id", sa.String(50), unique=True, nullable=False),
        sa.Column("key_hash", sa.String(255), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("rate_limit", sa.Integer(), server_default="100", nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tenant_id", "key_id", name="uq_tenant_api_key"),
    )


def downgrade() -> None:
    op.drop_table("tenant_api_keys")
    op.drop_table("tenant_users")
    op.drop_table("tenants")
    op.drop_table("test_reports")
    op.drop_table("test_metrics")
    op.drop_table("test_results")
    op.drop_table("test_sessions")
