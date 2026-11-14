# TTC · AI 招聘与人才挖掘平台

TTC 是一套面向企业招聘与候选人求职的双端 AI 辅助平台。系统将岗位 JD、简历解析、
证据核验、岗位匹配、实时语音初筛、人工面试、Offer 与候选人反馈串联为一条可追溯、
可人工复核的业务链路。

> 当前文档对应 2026-11-15 的代码快照。API 版本为 `0.1.0`，数据库迁移当前 head 为
> `0010_interview_pause_state`。具体请求与响应结构以运行后的 `/docs` 和 `/openapi.json` 为准。

## 本次维护内容

- 求职者端跳转企业招聘端的默认端口修正为 `5173`，并支持环境变量覆盖。
- 企业端语音会话详情接入状态 WebSocket。候选人接通、结束或撤回授权后，页面自动刷新
  会话与已落库转写状态，无需手动刷新；WebSocket 不可用时保留 5 秒轮询兜底。
- AI 面试新增初始问题语义去重、运行期“已问问题账本”和每轮强约束，限制相同问题及
  同义改写问题重复出现。
- 更新仓库地图、启动步骤、环境变量、API 路由、测试方式与当前能力边界。

## 核心能力

- **双端业务闭环**：企业 HR 工作台负责招聘流程，候选人门户负责岗位、投递、面试、
  授权和 Offer 反馈。
- **多租户与角色隔离**：HR、管理员和候选人能力由后端权限校验，数据按租户隔离。
- **证据优先的评估**：简历声明保留原文、字符位置和版本，岗位匹配与证据可信度分别呈现。
- **岗位版本化**：JD、权重方案和面试方案与岗位版本绑定，历史记录不会被直接覆盖。
- **授权式实时语音面试**：建会话和接通前均检查候选人授权；撤回授权后停止后续处理。
- **AI 问题去重**：初始问题、HR 指定问题和实时追问共享去重约束，禁止同义改写重复提问。
- **HR 实时旁听与接管**：默认静音旁听；HR 显式操作后可暂停、恢复、接管麦克风并交还 AI。
- **独立面试评估**：能力证据、言行风险和岗位匹配分分开记录，不合并为“人才总分”。
- **可运行的数据工程**：仓库包含数据集生成、简历分类模型与 RISM 数据处理子项目。

## 系统组成

| 路径 | 技术栈 | 职责与当前状态 |
| --- | --- | --- |
| `apps/api` | Python 3.11+、FastAPI、SQLAlchemy Async、Alembic | REST API、WebSocket、鉴权、后台任务和业务规则 |
| `apps/web` | React 18、TypeScript、Vite、Tailwind、TanStack Query、Zustand | 企业 HR 工作台，默认端口 `5173` |
| `apps/candidate-web` | React 18、TypeScript、Vite、Tailwind | 候选人门户，默认端口 `5175` |
| `dataset` | Python 标准库、JSON/JSONL、YAML | 模拟简历、经历单元、面试问题和追问链流水线 |
| `resume-match` | PyTorch、Transformers | 24 类英文简历岗位分类模型，由 API 以子进程调用 |
| `RISMv1` | 本地研究快照 | 冻结的简历意图/模型实验资产，已排除出版本库 |
| `RISMv2` | 本地研究工具 | 可追溯的数据标注与处理工具，已排除出版本库 |
| `resume_html` | 归档资产 | 历史简历/JobFit 演示工程，不是当前双端应用的运行依赖 |
| `docs` | Markdown、图片 | 接口审计、数据资产和架构材料 |

主要基础设施：

- PostgreSQL 16：业务数据、任务队列、审计和版本记录。
- S3/MinIO 或本地私有目录：简历文件与文本快照。`DEMO_MODE=true` 时可使用本地存储。
- 后台 Worker：简历解析、Crossref 检索、实时通话超时收尾和报告任务。
- OpenAI 兼容 LLM：JD 生成/抽取、简历 claim、匹配解释、问题计划和面试报告。
- 实时语音：OpenAI Realtime SDP 代理，或通义千问 Realtime WebSocket 后端中转。
- 简历分类模型：通过 `resume-match/infer_cli.py` 子进程推理，API 不直接加载 PyTorch。

## 总体架构

```text
企业 HR 浏览器 :5173                  候选人浏览器 :5175
          │                                  │
          └────────── /api、/ws ─────────────┘
                             │
                       Vite 开发代理
                             │
                       FastAPI :8000
          ┌──────────────────┼──────────────────┐
          │                  │                  │
      PostgreSQL         S3/MinIO          实时语音供应商
          │
       Worker
          │
  简历解析 / Crossref / 超时收尾 / 报告任务
```

后端按 `api -> domains -> adapters` 分层。API 路由负责鉴权、参数和事务边界；领域层负责
面试计划、能力评估、言行审核、人才索引等规则；外部模型、存储和实时通信统一经适配器接入。

## 业务流程

```text
创建岗位 / JD 版本化
        │
        ▼
上传简历 → 后台解析 → Claims / 时间线 → DOI 元数据核验
        │
        ▼
岗位匹配 / 证据评估 → 人工复核
        │
        ▼
授权 AI 语音初筛 → 初始问题 / 实时追问 / 转写 / 报告
        │
        ▼
人工面试排期 → Offer → 候选人接受或拒绝
```

## 功能概览

### 企业 HR 工作台

主要页面：

| 路由 | 功能 |
| --- | --- |
| `/` | 招聘工作台首页与当前业务概览 |
| `/jobs`、`/jobs/new`、`/jobs/:id` | 岗位列表、JD 创建/解析、版本、权重和发布 |
| `/candidates`、`/candidates/:id` | 候选人列表、简历、声明、证据和授权 |
| `/candidates/:id/report` | 评估报告、维度依据和人工修订 |
| `/sessions`、`/sessions/:id` | 语音会话创建、实时旁听、暂停、接管和报告 |
| `/interviews` | 面试排期、冲突检测、面试官空闲时间和状态 |
| `/offers` | Offer 创建、发送、撤回和结果跟踪 |
| `/talent` | 人才库检索与相似候选人 |
| `/team`、`/admin` | 团队成员、权限、审计、备份和集成状态 |

语音会话详情会监听 `/ws/voice/{session_id}`。候选人接通、结束或授权撤回后，企业端会
自动更新会话状态与已落库转写，无需手动刷新；候选人接通后实时旁听入口也会自动出现。
实时旁听仍需 HR 主动点击，以避免浏览器自动播放和麦克风权限策略导致意外接入。

### 候选人门户

主要页面：

| 路由 | 功能 |
| --- | --- |
| `/login`、`/register` | 候选人登录与注册 |
| `/`、`/jobs`、`/jobs/:id` | 求职中心、岗位广场和岗位详情 |
| `/applications`、`/applications/:id` | 投递、匹配结果、面试安排和简历更新 |
| `/interviews`、`/interviews/:id` | 我的 AI 面试、初始问题、实时通话和状态 |
| `/profile` | 求职档案、授权记录、隐私请求和数据处理 |

候选人登录页和主布局中的“企业招聘端”入口使用 `http://<host>:5173`。如企业端部署到
其他地址，可在 `apps/candidate-web/.env` 中配置：

```dotenv
VITE_EMPLOYER_URL=https://hr.example.com
```

### AI 语音面试

1. HR 为已完成简历解析且授予 `voice_interview` 授权的候选人创建会话。
2. 系统生成 3～5 个 AI 初始问题；HR 可追加最多 5 个指定问题，总初始问题最多 10 个。
3. 候选人接通后，系统优先使用已配置的 OpenAI Realtime SDP，否则使用通义千问
   WebSocket 中转。未配置任何实时语音凭证时，页面会明确提示不可接通。
4. 转写、助手文本、HR 旁听音频与控制事件通过服务端中转，供应商密钥不会进入浏览器。
5. HR 可暂停/恢复全局流程、旁听、打断 AI、接管麦克风和交还 AI。
6. 会话结束后生成基于转写的报告；能力评分和言行审核分别输出，并保留人工复核边界。

问题去重由两层组成：

- **生成期去重**：对模型生成的初始问题、HR 指定问题做规范化、主题与考察意图比较，
  相同或高度同义的问句只保留一条。
- **运行期去重**：从面试官实际转写中维护 `QuestionLedger`。每次显式生成回答和
  VAD 自动生成的下一轮回答都会携带已问清单，禁止换同义词、调整语序、扩缩范围或
  “再具体说说”式变相重问。

唯一例外是候选人明确表示“没听清/请再说一遍”，此时允许原样复述刚才的问题一次。
语义判断采用确定性规则，不额外调用语义模型，以控制延迟与外部数据暴露。

## 项目结构

```text
AI-recruitment/
├── apps/
│   ├── api/
│   │   ├── alembic/versions/       # 0001 ～ 0010 数据库迁移
│   │   ├── scripts/                # 演示租户和业务数据种子
│   │   ├── src/ttc/
│   │   │   ├── api/v1/             # REST 与 WebSocket 路由
│   │   │   ├── adapters/            # LLM、存储、匹配、实时语音
│   │   │   ├── core/                # 配置、数据库、鉴权、审计、错误
│   │   │   ├── domains/             # 简历、面试、能力、人才等领域逻辑
│   │   │   └── tasks/               # 后台任务消费者
│   │   └── tests/                   # API、领域、数据库和实时通信测试
│   ├── web/                         # 企业 HR 工作台
│   └── candidate-web/               # 候选人门户
├── dataset/                         # 模拟简历与面试数据流水线
├── resume-match/                     # 简历分类模型
├── RISMv1/                           # 本地历史研究资产（gitignored）
├── RISMv2/                           # 本地数据标注工具（gitignored）
├── resume_html/                      # 归档演示工程
├── docs/                             # 架构、接口与数据文档
├── files/                            # 示例简历
└── README.md
```

## 快速开始

### 环境要求

- Python 3.11 或更高版本
- Node.js `>=20.19 <23`
- npm
- PostgreSQL 16
- `uv`
- Docker Compose v2，可选
- MinIO、S3 兼容对象存储或 `DEMO_MODE=true` 本地存储

### 1. 安装并配置 API

```bash
cd apps/api
cp .env.example .env
uv sync --extra dev
```

至少检查以下配置：

```dotenv
APP_ENV=development
API_PREFIX=/api/v1
POSTGRES_DB=ttc
POSTGRES_USER=ttc
POSTGRES_PASSWORD=请替换为强密码
DATABASE_URL=postgresql+asyncpg://ttc:请替换为强密码@127.0.0.1:5432/ttc
JWT_SECRET=至少32字节的随机字符串
COLUMN_ENCRYPTION_KEY=Base64编码的32字节随机密钥
DEMO_MODE=true
```

可先生成密钥，再写入 `.env`：

```bash
python3 - <<'PY'
import base64
import secrets

print("JWT_SECRET=" + secrets.token_urlsafe(48))
print("COLUMN_ENCRYPTION_KEY=" + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
PY
```

未配置 LLM、匹配模型或实时语音凭证时，对应接口会返回明确错误或进入已声明的降级路径，
不会伪造模型结果。

### 2. 启动 PostgreSQL 并迁移

使用仓库自带的 Compose 启动数据库：

```bash
cd apps/api
docker compose --env-file .env up -d --wait postgres
uv run alembic upgrade head
uv run alembic current
```

当前应显示：

```text
0010_interview_pause_state (head)
```

Compose 中的 MinIO 服务会读取 `S3_ACCESS_KEY` 和 `S3_SECRET_KEY`；即使只启动 PostgreSQL，
也建议先在 `.env` 中填写这两个本地值。

### 3. 启动 API 与 Worker

在两个终端中分别执行：

```bash
cd apps/api
uv run uvicorn ttc.main:app --app-dir src --host 127.0.0.1 --port 8000
```

```bash
cd apps/api
uv run python -m ttc.tasks.runner
```

检查地址：

- API 文档：`http://127.0.0.1:8000/docs`
- 进程存活：`http://127.0.0.1:8000/api/v1/health/live`
- 就绪检查：`http://127.0.0.1:8000/api/v1/health/ready`

简历解析、Crossref 检索、实时通话超时收尾和报告任务都依赖 Worker，不能只启动 API。

### 4. 创建本地账号和演示数据

创建演示租户与管理员：

```bash
cd apps/api
TTC_BOOTSTRAP_PASSWORD='请替换为至少12位密码' \
uv run python -m ttc.cli \
  --tenant-slug demo \
  --tenant-name '演示企业' \
  --email web.test.hr@ttc.local \
  --name '演示 HR' \
  --role admin
```

写入演示公司和岗位：

```bash
cd apps/api
TTC_SEED_PASSWORD='请替换为演示账号密码' \
uv run python scripts/seed_demo_companies.py
```

种子脚本是幂等的。候选人也可以直接在求职者门户注册到 `demo` 租户。

演示测试完成后，可以清空全部业务记录并恢复当前账号基线：

```bash
cd apps/api
uv run python scripts/reset_demo_database.py --dry-run
uv run python scripts/reset_demo_database.py --yes
```

恢复脚本保留数据库结构和迁移版本，重建 `demo` 租户、默认管理员、HR 和候选人账号，
并清除测试产生的登录会话。默认开发账号为：管理员 `web.test.hr@ttc.local`、
招聘专员 `hr.demo@ttc.local`、候选人 `demo.candidate@ttc.local`，密码均为
`SeedDemo#2026`。重置还会预置 5 个已发布岗位：高级后端工程师、
机器学习工程师、AI 产品经理、内容营销经理和供应链运营专员。每个岗位都包含
JD 版本、评估权重和面试方案；重复执行岗位预置逻辑不会产生同名重复岗位。
执行前应先停止正在处理任务的 Worker。

### 5. 启动 HR 工作台

```bash
cd apps/web
npm ci
npm run dev
```

默认地址：`http://localhost:5173`。

### 6. 启动候选人门户

```bash
cd apps/candidate-web
npm ci
npm run dev
```

默认地址：`http://localhost:5175`。

本地开发时两个前端的 `VITE_API_BASE_URL` 均可留空，由 Vite 将 `/api`、`/ws` 和
`/health` 代理到 `http://localhost:8000`。独立部署时至少配置：

```dotenv
VITE_API_BASE_URL=https://api.example.com
VITE_WS_URL=wss://api.example.com
```

候选人端默认监听局域网地址。手机通过 `http://局域网IP:5175` 访问时，浏览器通常不会提供
麦克风权限。需要 HTTPS 时：

```bash
cd apps/candidate-web
./scripts/make-dev-cert.sh 192.168.1.10
npm run dev
```

随后使用 `https://192.168.1.10:5175`。开发证书仅用于本地联调，不应进入生产环境。

## 环境变量

完整 API 模板见 `apps/api/.env.example`，前端模板分别位于 `apps/web/.env.example` 和
`apps/candidate-web/.env.example`。

| 变量 | 作用 |
| --- | --- |
| `APP_ENV`、`API_PREFIX` | 运行环境和 API 路由前缀 |
| `DATABASE_URL` | PostgreSQL 异步连接串 |
| `JWT_SECRET` | 访问/刷新令牌签名密钥 |
| `COLUMN_ENCRYPTION_KEY` | 联系人和敏感字段加密密钥 |
| `DEMO_MODE` | 本地合成数据模式；生产环境应关闭 |
| `S3_ENDPOINT`、`S3_ACCESS_KEY`、`S3_SECRET_KEY` | 对象存储连接 |
| `S3_BUCKET_RESUMES`、`S3_BUCKET_AUDIO` | 简历和音频桶名 |
| `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` | OpenAI 兼容文本模型 |
| `RESUME_MATCH_MODEL_DIR` | 简历分类模型目录 |
| `RESUME_MATCH_PYTHON`、`RESUME_MATCH_TIMEOUT_SECONDS` | 分类模型推理进程与超时 |
| `RESUME_MATCH_ALLOW_KEYWORD_FALLBACK` | 开发阶段是否允许关键词兜底 |
| `REALTIME_API_KEY`、`REALTIME_MODEL` | OpenAI Realtime SDP 代理 |
| `DASHSCOPE_API_KEY` | 通义千问实时语音凭证 |
| `DASHSCOPE_REALTIME_MODEL`、`DASHSCOPE_REALTIME_VOICE` | 千问实时模型与音色 |
| `OCR_VLM_MODELS`、`OCR_VLM_API_KEY` | 扫描简历视觉 OCR 模型链 |
| `EMBEDDING_BASE_URL`、`EMBEDDING_API_KEY`、`EMBEDDING_MODEL` | 人才库向量化服务 |
| `OPENATS_*`、`VEKT_*` | 外部 ATS/Vekt 配置；真实同步尚未实现 |
| `VITE_API_BASE_URL`、`VITE_WS_URL` | 前端独立部署时的后端地址 |
| `VITE_EMPLOYER_URL`、`VITE_EMPLOYER_PORT` | 候选人端跳转企业端的地址或端口 |

不要提交真实 `.env`、模型密钥、访问令牌或候选人资料。

## API 概览

所有业务接口统一位于 `/api/v1`。HTTP 请求使用：

```http
Authorization: Bearer <access_token>
```

访问令牌默认短期有效，刷新令牌会轮换。错误响应结构：

```json
{
  "code": "TTC-2001",
  "message": "资源不存在",
  "request_id": "请求追踪 ID",
  "details": {}
}
```

主要端点：

| 领域 | 端点 |
| --- | --- |
| 健康与认证 | `/health/live`、`/health/ready`、`/auth/login`、`/auth/refresh`、`/auth/logout`、`/me` |
| 岗位 | `/jobs`、`/jobs/{id}/publish`、`/jobs/{id}/jd/versions`、`/jobs/{id}/weight-plan` |
| 候选人 | `/candidates`、`/candidates/{id}`、`/candidates/{id}/resumes` |
| 简历 | `/resumes`、`/resumes/{id}/claims`、`/resumes/{id}/text`、`/resumes/{id}/timeline` |
| 评估与证据 | `/candidates/{id}/assessments`、`/candidates/{id}/evidence-search`、`/evidence/{id}` |
| 语音会话 | `/voice-sessions`、`/voice-sessions/{id}/turns`、`/voice-sessions/{id}/report` |
| 候选人实时通道 | `WS /voice-sessions/{id}/realtime`、`POST /voice-sessions/{id}/connect` |
| HR 实时通道 | `WS /voice-sessions/{id}/observe`、`/voice-sessions/{id}/flow-control` |
| 人工面试与 Offer | `/interviews`、`/interviewers`、`/offers`、`/offers/{id}/decision` |
| 候选人门户 | `/portal/register`、`/portal/jobs`、`/portal/applications`、`/portal/interviews` |
| 授权与隐私 | `/consents`、`/consents/{id}/revoke`、`/privacy/requests` |
| 治理与运营 | `/notifications`、`/admin/audit-logs`、`/admin/backups`、`/talent/search` |
| 状态 WebSocket | `/ws/progress/{task_id}`、`/ws/voice/{session_id}` |

所有 WebSocket 连接建立后先发送令牌：

```json
{"token":"<access_token>"}
```

实时语音房间当前保存在 API 进程内。单进程或带粘性会话的部署可直接使用；多 API 实例部署
需要共享房间总线，或保证同一会话固定路由到同一实例。

## 测试与检查

后端单元和集成测试：

```bash
cd apps/api
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p pytest_asyncio.plugin -q
uv run ruff check src tests alembic
```

只运行面试计划、问题去重和实时语音相关测试：

```bash
cd apps/api
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p pytest_asyncio.plugin -q \
  tests/test_interview_plan.py tests/test_realtime.py
```

集成测试需要已迁移的本地 PostgreSQL。数据库已配置但无法连接时，相关测试会失败，
而不是静默跳过。

前端：

```bash
cd apps/web
npm run typecheck
npm run build
```

```bash
cd apps/candidate-web
npm run typecheck
npm run build
```

数据集：

```bash
cd dataset
python3 scripts/run_pipeline.py --validate-only --strict
```

## 数据集与模型子项目

### `dataset`

pilot 当前包含 100 份模拟简历、742 个经历单元、1035 道面试问题和 300 条追问链。
生成流程内置人工验收闸门，未经确认不能直接进入全量阶段：

```bash
cd dataset
python3 scripts/run_pipeline.py --stage pilot
python3 scripts/run_pipeline.py --validate-only --strict
```

人工审阅 `dataset/reports/` 后，才能执行 `--accept` 并启动全量阶段。详细说明见
`dataset/README.md`。

### `resume-match`

该子项目输出 24 类岗位分类概率，不是在线简历-JD 语义分数。API 通过子进程调用
`resume-match/infer_cli.py`，模型目录由 `RESUME_MATCH_MODEL_DIR` 指定。训练、评估和
推理说明见 `resume-match/README-train.md`。

### `RISMv1` 与 `RISMv2`

`RISMv1` 是冻结的历史研究快照；`RISMv2` 提供可追溯的 Claim、Gap、追问方向和策略
数据处理工具。两者及其 CSV/ZIP 数据资产仅在本地保留，不进入远程版本库。RISMv2 当前
处于等待人工审核状态，正式数据集按设计要求保持 0 条，未经审核的候选结果不会进入正式
训练集。需要查看说明时，请使用本地 `RISMv2/README_RISM002.md`。

## 当前边界

- 未配置 LLM 时，JD AI、claim 抽取、匹配解释、问题计划和报告生成会返回明确的 503
  或依照既有逻辑降级，不会生成伪造模型结果。
- 简历-岗位匹配依赖 `resume-match` 模型和对应 Python 环境；关键词兜底仅用于开发联调。
- 证据检索只对简历原文中可定位的 DOI 查询 Crossref 元数据，不能证明候选人是作者。
- 扫描 PDF 的 OCR 依赖视觉模型链，或服务器上的 PDF 渲染、Tesseract 与语言包。
- 能力评分只代表本次面试中出现的岗位相关证据，不是通用智力、人格或长期绩效测评。
- 言行审核只评价转写中可观察到的言语行为，严重事件必须定位到候选人原始轮次。
- 实时语音中转会检查明确的严重辱骂或终止警告；命中后保存已完成轮次、断开会话并排队
  生成报告。模型未正常收尾时最多等待 8 秒。
- OpenATS 和 Vekt 目前只有配置与状态接口，真实同步/重建尚未交付。
- RISMv2 正式数据集等待人工审核；`resume_html` 是归档演示资产，不属于当前生产依赖。
- 演示账号、默认密码和开发证书仅可用于本机开发。

## 安全与数据原则

- 真实候选人数据必须有明确授权，演示流程只使用合成样本。
- 前端不保存模型密钥；所有供应商凭证只从后端环境变量读取。
- HR 默认不能建立候选人实时音频通道，必须通过 `observe` 连接按权限旁听和接管。
- 原始面试音频默认不落盘，系统以转写文本生成报告；如启用音频留存，应单独取得授权。
- 传递 `X-Request-Id` 可关联请求、审计和错误记录。

## 相关文档

- 后端实现细节（版本信息以根 README 为准）：[apps/api/README.md](apps/api/README.md)
- 数据生成流水线：[dataset/README.md](dataset/README.md)
- 数据资产说明：[docs/data-assets.md](docs/data-assets.md)
- 简历分类模型：[resume-match/README-train.md](resume-match/README-train.md)
- RISM-002 数据工具：本地 `RISMv2/README_RISM002.md`（不随远程仓库发布）
- 历史接口审计：[docs/API_CONTRACT.md](docs/API_CONTRACT.md)
- 架构图：[docs/architecture.png](docs/architecture.png)
- 设计说明书：[TTC_AI人才挖掘平台_详细设计说明书(6).pdf](<TTC_AI人才挖掘平台_详细设计说明书(6).pdf>)
