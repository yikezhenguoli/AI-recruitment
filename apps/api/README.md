# TTC API（后端接口与启动）

FastAPI + PostgreSQL 16 + async SQLAlchemy + Alembic。实现登录、岗位及 JD、候选人、同意、
简历解析、Crossref DOI 证据、谨慎的双账本评估、语音会话/逐轮转写、隐私删除、管理员与任务进度。
接口和交互文档见启动后的 `/docs`，以实际 API schema 为准；当前有 28 张表、20 个枚举。

**尚未交付**：OpenATS/Vekt 对接（需两者明确的 API 契约与凭证）；未配置实时语音账号时
服务端 SDP 代理 `/voice-sessions/{id}/connect` 返回 503；`/realtime/mint` 因无法在授权撤回时
切断直连通话，配置服务后返回 410，不再提供直连凭证。通话报告仅返回原样转写及“未评估”，不伪造能力评分。
证据检索只核验简历原文内存在的 DOI 并从 Crossref 获取元数据，**不证明作者身份**。
JD 生成/抽取及简历 claim 抽取需要设置 LLM 的 URL、模型及凭证，未配置返回 503。
评估没有岗位专属规则时不给虚构的适配度分数。样本只允许合成或明确授权的数据。

## 1. 环境准备

在仓库根目录下操作，需要 `uv`；Docker 可选（无 Docker 方式见下一节）：

```bash
cd apps/api
cp .env.example .env
python3 - <<'PY'
from pathlib import Path
import secrets

file = Path('.env')
file.write_text(file.read_text().replace('change-me-local', secrets.token_urlsafe(36)))
file.chmod(0o600)
PY
uv sync --extra dev
```

`.env` 被 `.gitignore` 忽略，切勿提交真实凭证；`POSTGRES_PASSWORD` 和 `DATABASE_URL`
中的密码须一致。API 在主机上运行时用 `127.0.0.1`，在 Compose 网络内运行时改为 `postgres`。
**更改已有数据卷的 `.env` 密码不会更改数据库角色密码**，需在数据库内显式修改。

## 2. 启动 PostgreSQL 16

有 Docker Compose v2 时：先在 `.env` 中配置强密码的 `POSTGRES_PASSWORD`、一致的
`DATABASE_URL`、至少 32 字节的 `JWT_SECRET`、有效的 `COLUMN_ENCRYPTION_KEY`，以及
`S3_ACCESS_KEY`/`S3_SECRET_KEY`（MinIO 使用相同凭证）。新建数据卷才会初始化 PostgreSQL
角色密码；已有卷须手动改库内密码，**不要用 `down -v` 修密码**。然后：

```bash
docker compose --env-file .env up -d --wait postgres
docker compose --env-file .env ps
docker compose --env-file .env exec postgres pg_isready -U ttc -d ttc
docker compose --env-file .env build api worker
docker compose --env-file .env run --rm api alembic upgrade head
docker compose --env-file .env up -d --wait api worker
```

仅暴露 `127.0.0.1:5432`；`ttc_pgdata` 命名卷持久化数据。`docker compose down`
保留卷；`down -v` 会删除数据，请勿误用。不要同时启动下面的本地数据库：两者都会占用 5432 端口。
Compose 中 API 仅监听宿主机 `127.0.0.1:8000`，生产需单独配置 TLS 反向代理。
如果本机的 PostgreSQL/API 占用 5432/8000，先停止相应本地进程，**先备份数据，不能让
两个不同的数据目录被误认为同一个数据库**。当前开发机使用下面的无 Docker 方式。

### 无 Docker / 无 sudo（当前开发机实际使用的方式）

在 Ubuntu 22.04 amd64 上，可把 PGDG PostgreSQL **16.16** 包解压到用户目录：

```bash
cd apps/api
pgroot="$HOME/.local/opt/ttc-postgresql16"
mkdir -p "$pgroot"
base=https://apt.postgresql.org/pub/repos/apt/pool/main/p/postgresql-16
curl -fL "$base/postgresql-16_16.16-1.pgdg22.04+1_amd64.deb" -o /tmp/ttc-pg-server.deb
curl -fL "$base/postgresql-client-16_16.16-1.pgdg22.04+1_amd64.deb" -o /tmp/ttc-pg-client.deb
dpkg-deb -x /tmp/ttc-pg-server.deb "$pgroot"
dpkg-deb -x /tmp/ttc-pg-client.deb "$pgroot"
pg="$pgroot/usr/lib/postgresql/16/bin"
data="$HOME/.local/share/ttc-postgresql16"
share="$pgroot/usr/share/postgresql/16"
mkdir -p "$data"
pwfile=$(mktemp)
chmod 600 "$pwfile"
sed -n 's/^POSTGRES_PASSWORD=//p' .env > "$pwfile"
"$pg/initdb" -D "$data" -L "$share" -U ttc --auth-local=trust --auth-host=scram-sha-256 --pwfile="$pwfile"
rm "$pwfile"
"$pg/pg_ctl" -D "$data" -l "$data/server.log" -o "-h 127.0.0.1 -p 5432 -k $data -c unix_socket_permissions=0700" -w start
"$pg/createdb" -h "$data" -U ttc -O ttc ttc
"$pg/psql" -h "$data" -U ttc -d ttc -c 'SELECT version();'
```

`initdb` 和 `createdb` **仅首次执行**；已存在 `"$data/PG_VERSION"` 则跳过初始化。
重启数据库仅需上述 `pg_ctl ... start`；停止执行 `"$pg/pg_ctl" -D "$data" -w stop`。
本地 Unix socket 目录仅所有者可访问；TCP 只监听本机且使用 SCRAM 密码。
其他系统/架构请选择对应 PostgreSQL 16 安装包。

## 3. 执行迁移，启动 API

无论用哪种数据库启动方式，均从 `apps/api` 目录执行：

```bash
uv run alembic upgrade head
uv run alembic current                 # 0004_realtime_call (head)
uv run uvicorn ttc.main:app --app-dir src --host 127.0.0.1 --port 8000
```

另开一个终端启动任务消费进程（简历解析、Crossref 检索依赖它）：

```bash
cd apps/api
uv run python -m ttc.tasks.runner
```

仅将 `DEMO_MODE=true` 用于本地合成样本；生产环境配置 S3/MinIO 的
`S3_ENDPOINT/S3_ACCESS_KEY/S3_SECRET_KEY`，不要把真实候选人资料放入 demo 私有目录。
AI 简历字段必须从原文连续片段定位；扫描 PDF 暂不支持 OCR。实时语音填入
`REALTIME_API_KEY`、`REALTIME_MODEL` 后，由候选人端把 SDP offer 以 `application/sdp` 发至
`POST /api/v1/voice-sessions/{id}/connect`，服务端转发并返回 SDP answer。未经真实服务账号联调；
撤回/隐私删除会优先排队挂断已登记的 provider call；worker 也会在 `max_seconds` 到期后
排队挂断并生成标注“未评估”的转写报告，故需保持 worker 运行。媒体流尚未自动转写、
没有模型能力评估；文字轮次须由候选人端以 `/voice-sessions/{id}/turns` 上报，
否则报告只有空轮次摘要，不代表完整通话内容。
通话转写兜底上报使用 `/voice-sessions/{id}/turns`。进度 WebSocket 连接后 10 秒内先发送
`{"token":"<短期 Bearer access_token>"}`，不在 URL 中传递令牌。

在另一个终端验证：

```bash
curl -fsS http://127.0.0.1:8000/api/v1/health/live
curl -fsS http://127.0.0.1:8000/api/v1/health/ready
cd apps/api
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p pytest_asyncio.plugin -q
uv run ruff check src tests alembic
```

`/health/live` 只验证进程，`/health/ready` 会运行 PostgreSQL `SELECT 1`；
未配置或连接失败返回 503。未配置 `DATABASE_URL` 时集成测试跳过 DB 检查；
配置了却无法连接时测试失败。初始迁移额外补齐 `job.current_version_id` 外键，
并使用 `pg_trgm` 对实体名/别名建立本地检索索引。
禁用第三方 pytest 插件自动加载是因为本开发机的全局 ROS 插件依赖缺失；
显式加载项目的 `pytest_asyncio` 插件以保留异步测试能力。

只在**可清空数据的开发库**运行 `uv run alembic downgrade base` / `uv run alembic upgrade head`
验证回滚：downgrade 会删除全部业务表及其数据，不可在生产库直接执行。
