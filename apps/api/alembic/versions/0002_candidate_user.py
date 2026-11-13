"""Link candidate records to their own tenant-scoped login for consent and privacy."""

from alembic import op

revision = "0002_candidate_user"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE candidate ADD COLUMN user_id uuid "
               "REFERENCES app_user(id) ON DELETE SET NULL")
    op.execute("CREATE UNIQUE INDEX ux_candidate_user ON candidate(user_id) "
               "WHERE user_id IS NOT NULL")


def downgrade() -> None:
    op.execute("DROP INDEX ux_candidate_user")
    op.execute("ALTER TABLE candidate DROP COLUMN user_id")
