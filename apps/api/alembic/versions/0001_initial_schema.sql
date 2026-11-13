-- Source: detailed design section 3; PostgreSQL 16.
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TYPE user_role       AS ENUM ('admin','hr','candidate','guest');
CREATE TYPE user_status     AS ENUM ('active','disabled','pending');
CREATE TYPE job_status      AS ENUM ('draft','published','locked','archived');
CREATE TYPE jd_source       AS ENUM ('ai_generated','manual','imported');
CREATE TYPE weight_mode     AS ENUM ('auto','template','custom');
CREATE TYPE candidate_source AS ENUM ('upload','invite','demo');
CREATE TYPE parse_status    AS ENUM ('queued','parsing','extracting','done','failed');
CREATE TYPE claim_type      AS ENUM ('education','work','project','publication',
                                     'patent','award','skill','contact','summary');
CREATE TYPE entity_type     AS ENUM ('school','company','lab','paper','patent',
                                     'project','award','venue','person');
CREATE TYPE relation_type   AS ENUM ('studied_at','worked_at','affiliated','participated',
                                     'published','invented','authored','supervised');
CREATE TYPE evidence_grade  AS ENUM ('A','B','C','D');
CREATE TYPE evidence_state  AS ENUM ('strong','partial','self_claim','missing');
CREATE TYPE consent_purpose AS ENUM ('resume_process','voice_interview','recording','model_training');
CREATE TYPE consent_status  AS ENUM ('pending','granted','denied','revoked','expired');
CREATE TYPE voice_scenario  AS ENUM ('screen','verify','skill','mock');
CREATE TYPE session_status  AS ENUM ('created','authorized','connecting','live','ended','failed','revoked');
CREATE TYPE turn_role       AS ENUM ('interviewer','candidate','system');
CREATE TYPE task_status     AS ENUM ('queued','running','succeeded','failed','canceled');
CREATE TYPE privacy_type    AS ENUM ('access','correct','revoke','delete');
CREATE TYPE privacy_status  AS ENUM ('submitted','in_progress','completed','rejected');

CREATE TABLE tenant (
  id          uuid PRIMARY KEY,
  name        text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 80),
  slug        text NOT NULL UNIQUE,
  plan        text NOT NULL DEFAULT 'demo',
  is_demo     boolean NOT NULL DEFAULT false,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE app_user (
  id             uuid PRIMARY KEY,
  tenant_id      uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  email          citext NOT NULL,
  display_name   text NOT NULL CHECK (char_length(display_name) BETWEEN 1 AND 80),
  password_hash  text,
  role           user_role NOT NULL DEFAULT 'hr',
  status         user_status NOT NULL DEFAULT 'active',
  last_login_at  timestamptz,
  created_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, email)
);

CREATE TABLE auth_session (
  id           uuid PRIMARY KEY,
  user_id      uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
  family_id    uuid NOT NULL,               -- 同一次登录的所有轮换共享
  token_hash   bytea NOT NULL UNIQUE,       -- sha256(refresh_token)
  user_agent   text,
  ip           inet,
  created_at   timestamptz NOT NULL DEFAULT now(),
  last_used_at timestamptz NOT NULL DEFAULT now(),
  expires_at   timestamptz NOT NULL,
  revoked_at   timestamptz,
  replaced_by  uuid REFERENCES auth_session(id)
);
CREATE INDEX ix_auth_session_family ON auth_session(family_id);

CREATE TABLE job (
  id               uuid PRIMARY KEY,
  tenant_id        uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  title            text NOT NULL CHECK (char_length(title) BETWEEN 1 AND 160),
  department       text,
  owner_id         uuid NOT NULL REFERENCES app_user(id),
  status           job_status NOT NULL DEFAULT 'draft',
  current_version_id uuid,                  -- 指向 job_version，发布时锁定
  headcount        integer CHECK (headcount > 0),
  external_system  text,                    -- 外部主数据系统，如 'openats'
  external_id      text,                    -- 外部系统主键，用于幂等同步
  published_at     timestamptz,
  archived_at      timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_job_tenant_status ON job(tenant_id, status, updated_at DESC);
CREATE UNIQUE INDEX ux_job_external
  ON job(tenant_id, external_system, external_id) WHERE external_id IS NOT NULL;

CREATE TABLE job_version (
  id             uuid PRIMARY KEY,
  job_id         uuid NOT NULL REFERENCES job(id) ON DELETE CASCADE,
  version_no     integer NOT NULL CHECK (version_no > 0),
  jd_text        text NOT NULL CHECK (char_length(jd_text) BETWEEN 20 AND 20000),
  structured     jsonb NOT NULL,            -- JobDescriptionStructured
  source         jd_source NOT NULL,
  generation_id  uuid,                      -- 同一轮 AI 生成的多个候选共享
  is_saved       boolean NOT NULL DEFAULT false,  -- “暂存到概览”
  created_by     uuid NOT NULL REFERENCES app_user(id),
  created_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (job_id, version_no)
);
CREATE INDEX ix_job_version_generation ON job_version(generation_id);

CREATE TABLE weight_plan (
  id           uuid PRIMARY KEY,
  tenant_id    uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  job_id       uuid REFERENCES job(id) ON DELETE CASCADE,  -- NULL = 租户级模板
  name         text NOT NULL,
  mode         weight_mode NOT NULL DEFAULT 'auto',
  dimensions   jsonb NOT NULL,              -- [{key,label,description,weight_pct}]
  total_pct    numeric(5,2) NOT NULL DEFAULT 100 CHECK (total_pct = 100),
  is_active    boolean NOT NULL DEFAULT true,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_weight_plan_job ON weight_plan(job_id) WHERE is_active;

CREATE TABLE interview_plan (
  id            uuid PRIMARY KEY,
  tenant_id     uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  job_id        uuid REFERENCES job(id) ON DELETE CASCADE,
  name          text NOT NULL,
  duration_min  integer NOT NULL DEFAULT 20 CHECK (duration_min BETWEEN 5 AND 120),
  rounds        jsonb NOT NULL,             -- [{name,focus,question_budget}]
  dimensions    jsonb NOT NULL,             -- [{key,label,weight_pct}]
  is_active     boolean NOT NULL DEFAULT true,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE candidate (
  id               uuid PRIMARY KEY,
  tenant_id        uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  display_name     text NOT NULL,           -- 默认为合成姓名或脱敏名
  contact_enc      bytea,                   -- AES-GCM 加密的邮箱/手机
  contact_masked   text,                    -- 展示用遮罩值
  source           candidate_source NOT NULL DEFAULT 'upload',
  job_id           uuid REFERENCES job(id) ON DELETE SET NULL,
  is_synthetic     boolean NOT NULL DEFAULT false,  -- 合成数据标识
  external_system  text,                    -- 外部主数据系统，如 'openats'
  external_id      text,
  created_by       uuid REFERENCES app_user(id),
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_candidate_tenant_job ON candidate(tenant_id, job_id, created_at DESC);
CREATE UNIQUE INDEX ux_candidate_external
  ON candidate(tenant_id, external_system, external_id) WHERE external_id IS NOT NULL;

CREATE TABLE consent (
  id            uuid PRIMARY KEY,
  candidate_id  uuid NOT NULL REFERENCES candidate(id) ON DELETE CASCADE,
  purpose       consent_purpose NOT NULL,
  status        consent_status NOT NULL DEFAULT 'pending',
  scope         jsonb NOT NULL,             -- {recording:false, transcription:true, model:["llm"], ...}
  text_version  text NOT NULL,              -- 告知文本版本，例如 v1.2
  accepted_at   timestamptz,
  revoked_at    timestamptz,
  expires_at    timestamptz,
  ip            inet,
  user_agent    text,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_consent_candidate_purpose ON consent(candidate_id, purpose, status);

CREATE TABLE resume (
  id            uuid PRIMARY KEY,
  candidate_id  uuid NOT NULL REFERENCES candidate(id) ON DELETE CASCADE,
  file_name     text NOT NULL,
  mime          text NOT NULL,
  size_bytes    bigint NOT NULL CHECK (size_bytes > 0 AND size_bytes <= 20971520),
  file_hash     bytea NOT NULL,             -- sha256 原文
  file_uri      text NOT NULL,              -- s3://resumes/{tenant}/{candidate}/{id}
  page_count    integer,
  parse_status  parse_status NOT NULL DEFAULT 'queued',
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (candidate_id, file_hash)          -- 同人重复上传去重
);

CREATE TABLE resume_version (
  id               uuid PRIMARY KEY,
  resume_id        uuid NOT NULL REFERENCES resume(id) ON DELETE CASCADE,
  version_no       integer NOT NULL,
  extractor_model  text NOT NULL,           -- 例如 deepseek-chat@2026-10
  prompt_version   text NOT NULL,
  text_uri         text,                    -- 纯文本快照
  status           parse_status NOT NULL,
  error            text,
  parsed_at        timestamptz,
  UNIQUE (resume_id, version_no)
);

CREATE TABLE resume_claim (
  id                 uuid PRIMARY KEY,
  resume_version_id  uuid NOT NULL REFERENCES resume_version(id) ON DELETE CASCADE,
  claim_type         claim_type NOT NULL,
  ordinal            integer NOT NULL,      -- 同类内顺序
  raw_text           text NOT NULL,         -- 简历原文片段
  normalized         jsonb NOT NULL,        -- {org, role, start, end, title, doi...}
  page_no            integer,
  char_start         integer,
  char_end           integer,
  confidence         numeric(4,3) NOT NULL DEFAULT 0.000 CHECK (confidence BETWEEN 0 AND 1),
  needs_review       boolean NOT NULL DEFAULT false,
  created_at         timestamptz NOT NULL DEFAULT now(),
  CHECK (char_end IS NULL OR char_start IS NULL OR char_end >= char_start)
);
CREATE INDEX ix_claim_version_type ON resume_claim(resume_version_id, claim_type, ordinal);

CREATE TABLE entity (
  id              uuid PRIMARY KEY,
  tenant_id       uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  entity_type     entity_type NOT NULL,
  canonical_name  text NOT NULL,
  external_ids    jsonb NOT NULL DEFAULT '{}',  -- {doi, patent_no, uscc, orcid, openalex_id}
  attributes      jsonb NOT NULL DEFAULT '{}',  -- 学校院系、公司业务、期刊等
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, entity_type, canonical_name)
);

CREATE TABLE entity_alias (
  id         uuid PRIMARY KEY,
  entity_id  uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  alias      text NOT NULL,
  source     text NOT NULL DEFAULT 'resume',
  UNIQUE (entity_id, alias)
);
CREATE INDEX ix_entity_alias_alias ON entity_alias(lower(alias));

CREATE TABLE relation (
  id              uuid PRIMARY KEY,
  src_entity_id   uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  dst_entity_id   uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  relation_type   relation_type NOT NULL,
  time_start      date,
  time_end        date,
  claim_id        uuid REFERENCES resume_claim(id) ON DELETE SET NULL,
  confidence      numeric(4,3) NOT NULL DEFAULT 0.500,
  origin          text NOT NULL DEFAULT 'resume'  -- resume | public | inferred
);
CREATE INDEX ix_relation_src ON relation(src_entity_id, relation_type);

CREATE TABLE evidence (
  id                uuid PRIMARY KEY,
  tenant_id         uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  entity_id         uuid REFERENCES entity(id) ON DELETE CASCADE,
  claim_id          uuid REFERENCES resume_claim(id) ON DELETE SET NULL,
  source_type       text NOT NULL,          -- api | official_page | academic | registry
  source_name       text NOT NULL,          -- Crossref / OpenAlex / 学校官网 ...
  source_url        text NOT NULL,
  title             text NOT NULL,
  snippet           text,
  published_at      date,
  accessed_at       timestamptz NOT NULL,
  grade             evidence_grade NOT NULL,
  content_hash      bytea NOT NULL,
  snapshot_uri      text,                   -- MinIO 快照
  match_method      text NOT NULL,          -- doi | title_exact | name+org+year | fuzzy
  match_confidence  numeric(4,3) NOT NULL CHECK (match_confidence BETWEEN 0 AND 1),
  verified_by       uuid REFERENCES app_user(id),
  created_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (entity_id, source_url, content_hash)
);
CREATE INDEX ix_evidence_entity_grade ON evidence(entity_id, grade, published_at DESC);

CREATE TABLE evidence_conflict (
  id            uuid PRIMARY KEY,
  entity_id     uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  field_name    text NOT NULL,              -- title | author_order | year | legal_status
  value_a       text NOT NULL,
  source_a_id   uuid NOT NULL REFERENCES evidence(id),
  value_b       text NOT NULL,
  source_b_id   uuid NOT NULL REFERENCES evidence(id),
  resolution    text NOT NULL DEFAULT 'unresolved',  -- unresolved|prefer_a|prefer_b|manual
  resolved_by   uuid REFERENCES app_user(id),
  resolved_at   timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE assessment (
  id               uuid PRIMARY KEY,
  candidate_id     uuid NOT NULL REFERENCES candidate(id) ON DELETE CASCADE,
  job_id           uuid NOT NULL REFERENCES job(id) ON DELETE CASCADE,
  resume_version_id uuid NOT NULL REFERENCES resume_version(id),
  weight_plan_id   uuid NOT NULL REFERENCES weight_plan(id),
  evidence_score   numeric(5,2) CHECK (evidence_score BETWEEN 0 AND 100),
  evidence_grade   evidence_grade,
  match_score      numeric(5,2) CHECK (match_score BETWEEN 0 AND 100),
  status           text NOT NULL DEFAULT 'generating', -- generating|ready|failed|revised
  report_json      jsonb,
  model_version    text,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (candidate_id, job_id, resume_version_id, weight_plan_id)
);

CREATE TABLE dimension_score (
  id                uuid PRIMARY KEY,
  assessment_id     uuid NOT NULL REFERENCES assessment(id) ON DELETE CASCADE,
  dimension_key     text NOT NULL,
  label             text NOT NULL,
  weight_pct        numeric(5,2) NOT NULL,
  score             numeric(5,2) CHECK (score BETWEEN 0 AND 100),
  evidence_state    evidence_state NOT NULL,
  evidence_ids      uuid[] NOT NULL DEFAULT '{}',
  source_claim_ids  uuid[] NOT NULL DEFAULT '{}',
  reasoning         text NOT NULL,
  status            text NOT NULL DEFAULT 'ai',   -- ai|confirmed|revised|rejected
  UNIQUE (assessment_id, dimension_key)
);

CREATE TABLE assessment_revision (
  id             uuid PRIMARY KEY,
  assessment_id  uuid NOT NULL REFERENCES assessment(id) ON DELETE CASCADE,
  editor_id      uuid NOT NULL REFERENCES app_user(id),
  diff           jsonb NOT NULL,
  note           text,
  created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE voice_session (
  id            uuid PRIMARY KEY,
  candidate_id  uuid NOT NULL REFERENCES candidate(id) ON DELETE CASCADE,
  job_id        uuid NOT NULL REFERENCES job(id) ON DELETE CASCADE,
  consent_id    uuid NOT NULL REFERENCES consent(id),
  assessment_id uuid REFERENCES assessment(id) ON DELETE SET NULL,
  scenario      voice_scenario NOT NULL DEFAULT 'screen',
  status        session_status NOT NULL DEFAULT 'created',
  provider      text NOT NULL,              -- openai_realtime | gemini_live | local_s2s | stub
  model         text NOT NULL,
  plan_json     jsonb NOT NULL,             -- QuestionPlan
  max_seconds   integer NOT NULL DEFAULT 1200 CHECK (max_seconds BETWEEN 60 AND 7200),
  started_at    timestamptz,
  ended_at      timestamptz,
  end_reason    text,                       -- completed|timeout|candidate_end|error|revoked
  error         text,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_voice_session_status ON voice_session(status, created_at);

CREATE TABLE voice_turn (
  id           uuid PRIMARY KEY,
  session_id   uuid NOT NULL REFERENCES voice_session(id) ON DELETE CASCADE,
  turn_index   integer NOT NULL,
  role         turn_role NOT NULL,
  text         text NOT NULL,
  audio_uri    text,                        -- 默认 NULL（不存原始音频）
  question_id  text,                        -- 对应 plan_json 中的问题 ID
  started_at   timestamptz NOT NULL,
  ended_at     timestamptz,
  asr_confidence numeric(4,3),
  UNIQUE (session_id, turn_index)
);

CREATE TABLE call_report (
  id             uuid PRIMARY KEY,
  session_id     uuid NOT NULL UNIQUE REFERENCES voice_session(id) ON DELETE CASCADE,
  status         text NOT NULL DEFAULT 'generating',
  summary        jsonb,                     -- 动机/期望/关键经历/限制
  dimensions     jsonb,                     -- [{key,label,score,evidence_state,quote_ids}]
  quotes         jsonb,                     -- [{turn_id,text,ts,question_id}]
  crosscheck     jsonb,                     -- 与简历一致/补充/不一致/待核实
  followups      jsonb,                     -- 建议人工深挖
  model_version  text,
  error          text,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE privacy_request (
  id           uuid PRIMARY KEY,
  tenant_id    uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  candidate_id uuid NOT NULL REFERENCES candidate(id) ON DELETE CASCADE,
  request_type privacy_type NOT NULL,
  status       privacy_status NOT NULL DEFAULT 'submitted',
  payload      jsonb NOT NULL DEFAULT '{}',
  result       jsonb,
  handled_by   uuid REFERENCES app_user(id),
  created_at   timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);

CREATE TABLE audit_log (
  id             bigserial PRIMARY KEY,
  tenant_id      uuid,
  actor_id       uuid,
  action         text NOT NULL,
  resource_type  text NOT NULL,
  resource_id    uuid,
  request_id     text NOT NULL,
  ip             inet,
  detail         jsonb NOT NULL DEFAULT '{}',   -- 已脱敏
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_audit_resource ON audit_log(resource_type, resource_id, created_at DESC);
CREATE INDEX ix_audit_actor ON audit_log(actor_id, created_at DESC);

CREATE TABLE task (
  id            uuid PRIMARY KEY,
  tenant_id     uuid NOT NULL,
  type          text NOT NULL,              -- resume_parse | evidence_search | assessment | call_report
  resource_type text NOT NULL,
  resource_id   uuid NOT NULL,
  status        task_status NOT NULL DEFAULT 'queued',
  payload       jsonb NOT NULL DEFAULT '{}',
  attempts      integer NOT NULL DEFAULT 0,
  max_attempts  integer NOT NULL DEFAULT 3,
  error         text,
  started_at    timestamptz,
  finished_at   timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_task_active
  ON task(type, resource_id)
  WHERE status IN ('queued','running');   -- 同一资源同时只有一个活跃任务

CREATE TABLE vector_ref (
  id               uuid PRIMARY KEY,
  tenant_id        uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  object_type      text NOT NULL CHECK (object_type IN ('claim','entity','evidence','job_version')),
  object_id        uuid NOT NULL,
  collection       text NOT NULL,           -- Vekt 集合/命名空间
  embedding_model  text NOT NULL,           -- 如 text-embedding-3-small
  dim              integer NOT NULL,        -- 维度，换模型必须重建索引
  status           text NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending','indexed','failed')),
  indexed_at       timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (object_type, object_id, embedding_model)
);
CREATE INDEX ix_vector_ref_status ON vector_ref(status, created_at);

ALTER TABLE job ADD CONSTRAINT fk_job_current_version FOREIGN KEY (current_version_id) REFERENCES job_version(id) ON DELETE SET NULL;
CREATE INDEX ix_entity_name_trgm ON entity USING gin (canonical_name gin_trgm_ops);
CREATE INDEX ix_entity_alias_trgm ON entity_alias USING gin (alias gin_trgm_ops);
