"""Track server-mediated Realtime calls for consent revocation."""

from alembic import op

revision = "0004_realtime_call"
down_revision = "0003_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE voice_session ADD COLUMN provider_call_id text")
    op.execute("CREATE UNIQUE INDEX ux_voice_provider_call ON voice_session(provider_call_id) "
               "WHERE provider_call_id IS NOT NULL")


def downgrade() -> None:
    op.execute("DROP INDEX ux_voice_provider_call")
    op.execute("ALTER TABLE voice_session DROP COLUMN provider_call_id")
