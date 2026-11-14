"""Add evidence-backed interview capability scoring."""

from alembic import op

revision = "0008_interview_capability"
down_revision = "0007_interview_conduct"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE call_report "
        "ADD COLUMN capability_status text NOT NULL DEFAULT 'unassessed', "
        "ADD COLUMN capability_score numeric(5,2) "
        "  CHECK (capability_score BETWEEN 0 AND 100), "
        "ADD COLUMN capability_json jsonb, "
        "ADD COLUMN capability_model_version text"
    )
    op.execute(
        "ALTER TABLE call_report ADD CONSTRAINT call_report_capability_status_check "
        "CHECK (capability_status IN ('assessed','unassessed'))"
    )
    op.execute(
        "CREATE INDEX ix_call_report_capability_score "
        "ON call_report(capability_score DESC NULLS LAST, updated_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_call_report_capability_score")
    op.execute(
        "ALTER TABLE call_report DROP CONSTRAINT call_report_capability_status_check"
    )
    op.execute(
        "ALTER TABLE call_report "
        "DROP COLUMN capability_model_version, "
        "DROP COLUMN capability_json, "
        "DROP COLUMN capability_score, "
        "DROP COLUMN capability_status"
    )
