"""Add HR as a recorded live interview speaker."""

from alembic import op

revision = "0009_hr_live_participant"
down_revision = "0008_interview_capability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE turn_role ADD VALUE IF NOT EXISTS 'hr'")


def downgrade() -> None:
    # PostgreSQL does not support removing a value from an enum without
    # rebuilding the type and every dependent column. Retaining 'hr' is safer
    # than risking transcript loss during a downgrade.
    pass
