"""Create the TTC PostgreSQL schema from detailed design section 3."""

from pathlib import Path

from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA_FILE = Path(__file__).with_suffix(".sql")

TABLES = (
    "tenant", "app_user", "auth_session", "job", "job_version", "weight_plan",
    "interview_plan", "candidate", "consent", "resume", "resume_version",
    "resume_claim", "entity", "entity_alias", "relation", "evidence",
    "evidence_conflict", "assessment", "dimension_score", "assessment_revision",
    "voice_session", "voice_turn", "call_report", "privacy_request", "audit_log",
    "task", "vector_ref",
)

ENUMS = (
    "user_role", "user_status", "job_status", "jd_source", "weight_mode",
    "candidate_source", "parse_status", "claim_type", "entity_type",
    "relation_type", "evidence_grade", "evidence_state", "consent_purpose",
    "consent_status", "voice_scenario", "session_status", "turn_role",
    "task_status", "privacy_type", "privacy_status",
)


def upgrade() -> None:
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    statements = "\n".join(line.split("--", 1)[0] for line in sql.splitlines())
    for statement in statements.split(";"):
        if statement.strip():
            op.execute(statement.strip())


def downgrade() -> None:
    op.execute("ALTER TABLE job DROP CONSTRAINT fk_job_current_version")
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE {table}")
    for enum in reversed(ENUMS):
        op.execute(f"DROP TYPE {enum}")
