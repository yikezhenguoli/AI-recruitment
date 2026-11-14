"""Persist the HR-controlled interview pause state."""

from alembic import op

revision = "0010_interview_pause_state"
down_revision = "0009_hr_live_participant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE voice_session ADD COLUMN is_paused boolean NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE voice_session DROP COLUMN is_paused")
