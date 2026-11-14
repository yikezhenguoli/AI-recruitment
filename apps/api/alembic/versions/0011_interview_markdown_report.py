"""Persist a Markdown report for every completed interview."""

from alembic import op

revision = "0011_interview_markdown_report"
down_revision = "0010_interview_pause_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE call_report "
        "ADD COLUMN markdown_content text, "
        "ADD COLUMN markdown_hash text, "
        "ADD COLUMN markdown_generated_at timestamptz"
    )
    op.execute(
        "ALTER TABLE call_report ADD CONSTRAINT call_report_markdown_hash_check "
        "CHECK (markdown_hash IS NULL OR markdown_hash ~ '^[0-9a-f]{64}$')"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE call_report DROP CONSTRAINT call_report_markdown_hash_check"
    )
    op.execute(
        "ALTER TABLE call_report "
        "DROP COLUMN markdown_generated_at, "
        "DROP COLUMN markdown_hash, "
        "DROP COLUMN markdown_content"
    )
