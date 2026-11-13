"""Candidate portal: one person may apply to many jobs.

`candidate.job_id` only records the HR-side target job and
`ux_candidate_user` keeps one candidate row per login, so multi-job
applications need their own table.
"""

from alembic import op

revision = "0005_candidate_application"
down_revision = "0004_realtime_call"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE application ("
        "  id uuid PRIMARY KEY,"
        "  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,"
        "  candidate_id uuid NOT NULL REFERENCES candidate(id) ON DELETE CASCADE,"
        "  job_id uuid NOT NULL REFERENCES job(id) ON DELETE CASCADE,"
        "  resume_id uuid REFERENCES resume(id) ON DELETE SET NULL,"
        "  status text NOT NULL DEFAULT 'submitted',"
        "  created_at timestamptz NOT NULL DEFAULT now(),"
        "  updated_at timestamptz NOT NULL DEFAULT now(),"
        "  UNIQUE (candidate_id, job_id)"
        ")"
    )
    op.execute("CREATE INDEX ix_application_candidate "
               "ON application(candidate_id, created_at DESC)")
    op.execute("CREATE INDEX ix_application_job ON application(job_id, created_at DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX ix_application_job")
    op.execute("DROP INDEX ix_application_candidate")
    op.execute("DROP TABLE application")
