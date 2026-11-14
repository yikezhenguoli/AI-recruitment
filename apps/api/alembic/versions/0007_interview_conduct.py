"""Add evidence-backed interview conduct scoring and veto state."""

from alembic import op

revision = "0007_interview_conduct"
down_revision = "0006_offers_scheduling_ops"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE call_report "
        "ADD COLUMN conduct_status text NOT NULL DEFAULT 'unassessed', "
        "ADD COLUMN conduct_score numeric(5,2) "
        "  CHECK (conduct_score BETWEEN 0 AND 100), "
        "ADD COLUMN conduct_veto boolean NOT NULL DEFAULT false, "
        "ADD COLUMN conduct_json jsonb, "
        "ADD COLUMN conduct_model_version text"
    )
    op.execute(
        "ALTER TABLE call_report ADD CONSTRAINT call_report_conduct_status_check "
        "CHECK (conduct_status IN ('assessed','unassessed','vetoed'))"
    )
    op.execute(
        "CREATE INDEX ix_call_report_conduct_veto "
        "ON call_report(conduct_veto, updated_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_call_report_conduct_veto")
    op.execute(
        "ALTER TABLE call_report DROP CONSTRAINT call_report_conduct_status_check"
    )
    op.execute(
        "ALTER TABLE call_report "
        "DROP COLUMN conduct_model_version, "
        "DROP COLUMN conduct_json, "
        "DROP COLUMN conduct_veto, "
        "DROP COLUMN conduct_score, "
        "DROP COLUMN conduct_status"
    )
