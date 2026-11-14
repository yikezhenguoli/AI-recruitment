"""Offers, interview scheduling, notifications, role permissions and talent index.

Everything here is additive: no existing table is altered, so an older client
keeps working against the same database.
"""

from alembic import op

revision = "0006_offers_scheduling_ops"
down_revision = "0005_candidate_application"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE offer ("
        "  id uuid PRIMARY KEY,"
        "  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,"
        "  application_id uuid NOT NULL REFERENCES application(id) ON DELETE CASCADE,"
        "  candidate_id uuid NOT NULL REFERENCES candidate(id) ON DELETE CASCADE,"
        "  job_id uuid NOT NULL REFERENCES job(id) ON DELETE CASCADE,"
        "  position_title text NOT NULL CHECK (char_length(position_title) BETWEEN 1 AND 160),"
        "  salary_monthly numeric(10,2) CHECK (salary_monthly >= 0),"
        "  salary_months integer CHECK (salary_months BETWEEN 1 AND 24),"
        "  start_date date,"
        "  expires_at timestamptz,"
        "  status text NOT NULL DEFAULT 'draft' CHECK (status IN "
        "    ('draft','sent','accepted','declined','withdrawn','expired')),"
        "  note text,"
        "  created_by uuid REFERENCES app_user(id) ON DELETE SET NULL,"
        "  sent_at timestamptz,"
        "  decided_at timestamptz,"
        "  created_at timestamptz NOT NULL DEFAULT now(),"
        "  updated_at timestamptz NOT NULL DEFAULT now(),"
        "  UNIQUE (application_id)"
        ")"
    )
    op.execute("CREATE INDEX ix_offer_tenant_status "
               "ON offer(tenant_id, status, created_at DESC)")
    op.execute("CREATE INDEX ix_offer_candidate ON offer(candidate_id, created_at DESC)")

    op.execute(
        "CREATE TABLE offer_event ("
        "  id uuid PRIMARY KEY,"
        "  offer_id uuid NOT NULL REFERENCES offer(id) ON DELETE CASCADE,"
        "  actor_id uuid REFERENCES app_user(id) ON DELETE SET NULL,"
        "  from_status text,"
        "  to_status text NOT NULL,"
        "  note text,"
        "  created_at timestamptz NOT NULL DEFAULT now()"
        ")"
    )
    op.execute("CREATE INDEX ix_offer_event_offer ON offer_event(offer_id, created_at)")

    op.execute(
        "CREATE TABLE interview_slot ("
        "  id uuid PRIMARY KEY,"
        "  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,"
        "  application_id uuid REFERENCES application(id) ON DELETE CASCADE,"
        "  candidate_id uuid NOT NULL REFERENCES candidate(id) ON DELETE CASCADE,"
        "  job_id uuid NOT NULL REFERENCES job(id) ON DELETE CASCADE,"
        "  plan_id uuid REFERENCES interview_plan(id) ON DELETE SET NULL,"
        "  interviewer_id uuid REFERENCES app_user(id) ON DELETE SET NULL,"
        "  scheduled_at timestamptz NOT NULL,"
        "  duration_min integer NOT NULL DEFAULT 45 CHECK (duration_min BETWEEN 15 AND 240),"
        "  mode text NOT NULL DEFAULT 'video' CHECK (mode IN ('onsite','video','phone')),"
        "  location text,"
        "  status text NOT NULL DEFAULT 'scheduled' CHECK (status IN "
        "    ('scheduled','confirmed','completed','canceled','no_show')),"
        "  note text,"
        "  created_by uuid REFERENCES app_user(id) ON DELETE SET NULL,"
        "  created_at timestamptz NOT NULL DEFAULT now(),"
        "  updated_at timestamptz NOT NULL DEFAULT now()"
        ")"
    )
    op.execute("CREATE INDEX ix_interview_slot_tenant_time "
               "ON interview_slot(tenant_id, scheduled_at)")
    op.execute("CREATE INDEX ix_interview_slot_candidate "
               "ON interview_slot(candidate_id, scheduled_at DESC)")
    op.execute("CREATE INDEX ix_interview_slot_interviewer "
               "ON interview_slot(interviewer_id, scheduled_at)")

    op.execute(
        "CREATE TABLE notification ("
        "  id uuid PRIMARY KEY,"
        "  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,"
        "  user_id uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,"
        "  kind text NOT NULL,"
        "  title text NOT NULL,"
        "  body text,"
        "  link text,"
        "  read_at timestamptz,"
        "  created_at timestamptz NOT NULL DEFAULT now()"
        ")"
    )
    op.execute("CREATE INDEX ix_notification_user "
               "ON notification(user_id, created_at DESC)")
    op.execute("CREATE INDEX ix_notification_unread "
               "ON notification(user_id) WHERE read_at IS NULL")

    op.execute(
        "CREATE TABLE role_permission ("
        "  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,"
        "  role user_role NOT NULL,"
        "  permission text NOT NULL,"
        "  PRIMARY KEY (tenant_id, role, permission)"
        ")"
    )

    op.execute(
        "CREATE TABLE talent_index ("
        "  id uuid PRIMARY KEY,"
        "  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,"
        "  candidate_id uuid NOT NULL REFERENCES candidate(id) ON DELETE CASCADE,"
        "  resume_version_id uuid NOT NULL REFERENCES resume_version(id) ON DELETE CASCADE,"
        "  backend text NOT NULL CHECK (backend IN ('embedding','lexical')),"
        "  model text NOT NULL,"
        "  dim integer NOT NULL CHECK (dim > 0),"
        "  vector double precision[] NOT NULL,"
        "  norm double precision NOT NULL,"
        "  content_hash text NOT NULL,"
        "  updated_at timestamptz NOT NULL DEFAULT now(),"
        "  UNIQUE (candidate_id, resume_version_id, backend, model)"
        ")"
    )
    op.execute("CREATE INDEX ix_talent_index_tenant ON talent_index(tenant_id)")

    op.execute(
        "CREATE TABLE backup_snapshot ("
        "  id uuid PRIMARY KEY,"
        "  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,"
        "  uri text NOT NULL,"
        "  table_counts jsonb NOT NULL,"
        "  checksum text NOT NULL,"
        "  size_bytes bigint NOT NULL,"
        "  created_by uuid REFERENCES app_user(id) ON DELETE SET NULL,"
        "  created_at timestamptz NOT NULL DEFAULT now()"
        ")"
    )


def downgrade() -> None:
    op.execute("DROP TABLE backup_snapshot")
    op.execute("DROP TABLE talent_index")
    op.execute("DROP TABLE role_permission")
    op.execute("DROP TABLE notification")
    op.execute("DROP TABLE interview_slot")
    op.execute("DROP TABLE offer_event")
    op.execute("DROP TABLE offer")
