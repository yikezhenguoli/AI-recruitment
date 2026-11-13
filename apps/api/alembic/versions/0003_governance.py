"""Persist source policy and retain anonymized deletion request status."""

from alembic import op

revision = "0003_governance"
down_revision = "0002_candidate_user"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE privacy_request ADD COLUMN requester_id uuid "
               "REFERENCES app_user(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE privacy_request ALTER COLUMN candidate_id DROP NOT NULL")
    op.execute("ALTER TABLE privacy_request DROP CONSTRAINT privacy_request_candidate_id_fkey")
    op.execute("ALTER TABLE privacy_request ADD CONSTRAINT privacy_request_candidate_id_fkey "
               "FOREIGN KEY (candidate_id) REFERENCES candidate(id) ON DELETE SET NULL")
    op.execute("CREATE TABLE data_source ("
               "id uuid PRIMARY KEY, tenant_id uuid NOT NULL "
               "REFERENCES tenant(id) ON DELETE CASCADE, "
               "name text NOT NULL, enabled boolean NOT NULL DEFAULT true, "
               "rate_limit integer NOT NULL DEFAULT 30 CHECK (rate_limit BETWEEN 1 AND 300), "
               "UNIQUE (tenant_id, name))")


def downgrade() -> None:
    op.execute("DROP TABLE data_source")
    op.execute("DELETE FROM privacy_request WHERE candidate_id IS NULL")
    op.execute("ALTER TABLE privacy_request DROP CONSTRAINT privacy_request_candidate_id_fkey")
    op.execute("ALTER TABLE privacy_request DROP COLUMN requester_id")
    op.execute("ALTER TABLE privacy_request ALTER COLUMN candidate_id SET NOT NULL")
    op.execute("ALTER TABLE privacy_request ADD CONSTRAINT privacy_request_candidate_id_fkey "
               "FOREIGN KEY (candidate_id) REFERENCES candidate(id) ON DELETE CASCADE")
