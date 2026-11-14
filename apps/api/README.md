# TTC API（后端接口与启动）

FastAPI + PostgreSQL 16 + async SQLAlchemy + Alembic。实现登录、岗位及 JD、候选人、同意、
简历解析、Crossref DOI 证据、谨慎的双账本评估、语音会话/逐轮转写、隐私删除、管理员与任务进度。
接口和交互文档见启动后的 `/docs`，以实际 API schema 为准；当前有 36 张表、20 个枚举。

**尚未交付**：OpenATS/Vekt 对接（需两者明确的 API 契约与凭证）；未配置实时语音账号时
服务端 SDP 代理 `/voice-sessions/{id}/connect` 返回 503；`/realtime/mint` 因无法在授权撤回时
切断直连通话，配置服务后返回 410，不再提供直连凭证。通话报告保留原样转写，
并在配置 LLM 后生成能力问答纪要；言行审核独立评分，严重事件必须绑定候选人原始轮次才可一票否决。
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
uv run alembic current                 # 0007_interview_conduct (head)
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
排队挂断并生成转写报告，故需保持 worker 运行。媒体流尚未自动转写、
没有独立技能测试；文字轮次须由候选人端以 `/voice-sessions/{id}/turns` 上报，
否则报告只有空轮次摘要，不代表完整通话内容。
言行审核使用 `respect`、`order`、`integrity`、`professionalism` 四维评分。模型不可用时，
明确辱骂/威胁由窄规则兜底；模型提出的严重事件必须引用候选人原始 `voice_turn.id`，
否则不会触发一票否决，其余结果标记人工复核。只评价转写中的言语行为，不评价外貌、声线或口音。
实时中转层还会对最终候选人转写执行窄规则检查；命中明确辱骂，或 AI 已明确宣告因言行严重
不当而结束时，服务端会在当前警告回复完成后关闭上游和浏览器连接，保存已完成轮次并将
`end_reason` 写为 `conduct_violation`。模型未正常收尾时最多等待 8 秒便强制断开，并排队
生成 `voice_report` 报告任务，不依赖用户点击“结束通话”。
通话报告同时生成独立的面试能力证据评分，维度为岗位知识与技能 20%、相关经历深度 25%、
问题解决 20%、个人贡献与结果 20%、学习与迁移 15%。有分数的维度必须引用候选人原始
`voice_turn.id`；无回答证据的维度保持 `null`，有效权重不足 50% 时不输出总分。该分数用于
本次面试的能力证据复核，不并入岗位匹配分，也不能替代专业笔试、技能测试或人工面试。
每份完成的语音面试还会生成并持久化一份 Markdown 报告，包含能力图谱、问答概括、
亮点/重点/疑点、待确认事项、HR 进一步提问方向和参考岗位结论。HR 可通过
`GET /api/v1/voice-sessions/{id}/report/markdown` 下载；候选人和未授权访问者不能读取。
重新整理纪要会同步刷新 Markdown，同一会话的 Markdown 生成是幂等的。
创建语音会话时可额外传入 `custom_questions: string[]`，最多 5 个、每项不超过 200 字。
服务端会去重并把这些问句置于 `plan_json.questions` 前部，标记 `source:"hr"`、
`required:true`；实时指令要求优先覆盖 HR 指定问题，时间不足时压缩 AI 生成问题。
候选人专用音频通道 `WS /voice-sessions/{id}/realtime` 会拒绝 HR/admin 建立连接，
避免企业端误把 HR 当成被面试者。HR 只能在候选人接通后使用
`WS /voice-sessions/{id}/observe` 实时旁听。加入旁听不会请求或开启麦克风。
`control.take` 会取消当前 AI 回答并暂停自动回应；`hr_audio.start` 和
`hr_audio.append` 只有在 HR 显式点击麦克风按钮后才会启用，将 HR 的
16 kHz PCM16 音频实时转发给候选人，同时进入 AI 输入转录链路。`control.release`
会恢复自动回应，并让 AI 基于 HR 与候选人的完整对话上下文继续追问。HR 转写以
`turn_role='hr'` 保存，且不会计入候选人能力或言行评分。
当前实时房间路由保存在 API 进程内，单进程或粘性会话部署可直接使用；多 API 实例
需要共享房间总线（如 Redis Pub/Sub）或保证同一会话固定路由到同一实例。
`POST /voice-sessions/{id}/flow-control` 接受 `{"action":"pause"}` 或
`{"action":"resume"}`。暂停会持久化 `voice_session.is_paused`、取消当前 AI 回答并
要求模型只播放“面试流程被HR暂停，请等待面试流程恢复进行。”；恢复会播放
“面试流程已恢复，可以继续进行交流。”并根据完整上下文继续，不重新开始问题清单。
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
