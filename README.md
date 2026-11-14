# TTC · AI 招聘与人才挖掘平台

TTC 是一套面向企业招聘和候选人求职的双端 AI 辅助平台。系统把岗位 JD、简历、
外部证据、岗位适配评估、实时语音初筛和面试排期串成一条可复核的业务链路。
招聘方使用 HR 工作台，候选人使用独立的求职门户，二者共享同一套多租户 API 和业务数据。

项目当前是 **V1.0 功能实现快照**，不是单纯的前端原型。后端接口统一为
`/api/v1`，使用 PostgreSQL 持久化数据，并通过 Alembic 管理数据库结构。

## 核心特点

- **双账本评估**：分别记录证据可信度和岗位适配度，不把两者合并为一个“人才总分”。
- **证据可追溯**：简历声明保留原文、字符位置和版本；评估维度可关联声明与证据。
- **岗位版本化**：JD 版本、权重方案和面试方案与岗位绑定，修改不会覆盖历史版本。
- **授权式语音面试**：创建会话和服务端建立连接前均检查候选人授权，撤回后中断后续处理。
- **HR 自定义问题**：发起语音面试时可按行录入最多 5 个指定问题；系统将它们作为必问问题优先编排，再由简历和 JD 生成的 AI 问题补充。
- **HR 实时旁听与接管**：AI 只面向候选人；HR 默认静音旁听，点击专用按钮后才打开麦克风。HR 可以打断 AI、直接与候选人沟通，交回 AI 后继续沿上下文深入追问。
- **全场暂停与恢复**：HR 可一键暂停面试，AI 将向候选人播放暂停提示并停止自动回应；恢复时播放恢复提示，再基于完整上下文继续后续问题。
- **面试言行审核**：基于转写审核尊重、秩序、作答态度和职业化表达；严重扰乱、故意异常作答、辱骂威胁或不当言论必须绑定原始证据，并触发一票否决。实时通话中的明确严重辱骂由服务端强制结束，不再等待模型自行停口。
- **面试能力证据评分**：从回答中的具体职责、做法、取舍、结果和异常处理评估岗位知识与技能、相关经历深度、问题解决、个人贡献及学习迁移；无回答证据不评分，不以表达流利度替代能力。
- **招聘全流程**：覆盖岗位、候选人、投递、评估、排期、Offer、通知到隐私请求和审计。
- **双端体验**：HR 工作台负责招聘决策辅助；候选人门户负责浏览岗位、投递、查看进度和管理授权。
- **可运行的数据工程**：`dataset/` 提供独立、可复现的模拟简历与经历级面试问题生成流水线。

## 系统组成

| 模块 | 技术栈 | 职责 |
| --- | --- | --- |
| `apps/api` | Python 3.11+、FastAPI、SQLAlchemy Async、Alembic | REST API、鉴权、业务规则、异步任务和 WebSocket |
| `apps/web` | React 18、TypeScript、Vite、Tailwind、TanStack Query、Zustand | HR 招聘工作台 |
| `apps/candidate-web` | React 18、TypeScript、Vite、Tailwind | 候选人岗位广场、投递、语音面试和隐私管理 |
| `dataset` | Python 标准库、JSON/JSONL、YAML | 模拟简历、经历拆解、面试问题、追问链和统计报告 |
| `docs` | Markdown | 历史接口审计和项目说明 |

主要基础设施：

- PostgreSQL 16：业务数据、任务和审计记录。
- MinIO 或兼容 S3 的对象存储：简历文件、文本快照和音频对象。
- 后台 Worker：处理简历解析、Crossref 证据检索和实时通话超时收尾。
- OpenAI 兼容 LLM：JD 生成/抽取、简历声明抽取、匹配解释和面试纪要。
- 实时语音供应商：OpenAI Realtime SDP 代理或通义千问 Realtime WebSocket 中转。

## 业务流程

```text
创建岗位 / JD 版本化
        |
        v
上传简历 -> 后台解析 -> Claims / 时间线
        |                       |
        |                       v
        |                  DOI 证据检索
        v
岗位匹配 / 双账本评估
        |
        v
授权式 AI 语音初筛 -> 初始问题 / 实时追问 / 转写 / 纪要 / 人工复核
        |
        v
面试排期 -> Offer -> 候选人确认或拒绝
```

后端按 `api -> domains -> adapters` 分层。API 路由负责鉴权与请求编排，
领域代码处理简历、面试计划和人才索引，外部模型、存储、实时语音和检索通过适配器接入。

## 功能概览

### 招聘工作台

- 岗位列表、创建、编辑、归档、发布和岗位统计。
- 手动粘贴 JD、AI 抽取或生成 JD，保存并选择 JD 版本。
- 配置岗位评估权重、面试轮次和维度。
- 管理候选人，上传 PDF、DOCX、TXT、PNG、JPEG 或 WebP 简历。
- 查看解析状态、claims、纯文本、时间线、证据和评估报告。
- 生成确定性双账本评估，人工修订单个维度并保留修订记录。
- 创建 AI 语音会话、录入 HR 指定问题、查看初始问题、动态追问、轮次、纪要、能力评分和四维言行评分。
- 安排面试、检测面试官/候选人时间冲突、登记面试状态。
- 创建、发送、撤回 Offer，并记录候选人决策。
- 人才库索引重建、自然语言检索和相似候选人查询。
- 团队成员、角色权限、通知、审计、指标、备份和隐私请求管理。

### 候选人门户

- 注册、登录、维护求职档案。
- 浏览企业已发布岗位并查看结构化 JD。
- 上传简历投递岗位，查看解析、匹配和投递状态。
- 查看 3～5 个初始问题，在浏览器中完成实时语音初筛；后续问题根据回答和岗位相关性动态生成。
- 逐项查看授权记录并撤回授权，提交访问、更正或删除等隐私请求。
- 查看招聘方发送的 Offer 并提交接受或拒绝决定。

### 数据集工程

- 30 个岗位类别，使用本地规则模板和岗位知识库生成虚拟候选人。
- 将简历拆成 8 类经历单元，每道问题绑定具体经历、原文片段和字符偏移。
- 生成 15 个维度的追问问题、题级评分和 4 至 5 层追问链。
- 提供严格校验、硬性质量门槛、去重分析、统计报告和断点续跑。

当前仓库中的 pilot 数据规模为：

| 指标 | 当前值 |
| --- | ---: |
| 模拟简历 | 100 |
| 岗位类别 | 30 |
| 经历单元 | 742 |
| 面试问题 | 1035 |
| 追问链 | 300 |

全量目标为 5000 份简历。pilot 阶段已经通过自动校验，但全量生成受人工验收闸门控制。

## 项目结构

```text
AI-recruitment/
├── apps/
│   ├── api/                         # FastAPI 后端
│   │   ├── alembic/                 # 数据库迁移，当前 head 为 0006
│   │   ├── scripts/                 # 演示租户和岗位数据
│   │   ├── src/ttc/
│   │   │   ├── api/v1/              # REST 与 WebSocket 路由
│   │   │   ├── adapters/            # LLM、存储、实时语音等适配器
│   │   │   ├── core/                # 配置、数据库、鉴权、审计、错误
│   │   │   ├── domains/             # 简历、面试计划、人才索引等领域逻辑
│   │   │   └── tasks/               # 后台任务消费者
│   │   └── tests/                   # API、领域与数据库测试
│   ├── web/                         # HR 工作台
│   └── candidate-web/               # 候选人门户
├── dataset/                         # 模拟简历与面试数据生成系统
├── docs/                            # 接口审计等文档
├── files/                           # 示例简历文本
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
- MinIO 或兼容 S3 的对象存储，生产环境必需

### 1. 安装并配置 API

```bash
cd apps/api
cp .env.example .env
uv sync --extra dev
```

编辑 `apps/api/.env`，至少确认以下值：

```dotenv
POSTGRES_DB=ttc
POSTGRES_USER=ttc
POSTGRES_PASSWORD=你的数据库密码
DATABASE_URL=postgresql+asyncpg://ttc:你的数据库密码@127.0.0.1:5432/ttc
JWT_SECRET=至少32字节的随机字符串
COLUMN_ENCRYPTION_KEY=Base64编码的32字节随机密钥
DEMO_MODE=true
S3_ACCESS_KEY=ttc-local-minio
S3_SECRET_KEY=change-me-local-minio-password
```

可以用下面的命令生成密钥，再将输出写入 `.env`：

```bash
python3 - <<'PY'
import base64
import secrets

print("JWT_SECRET=" + secrets.token_urlsafe(48))
print("COLUMN_ENCRYPTION_KEY=" + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
PY
```

`DEMO_MODE=true` 时，未配置 S3 的简历会写入本机私有目录，适合本地联调。
由于 Compose 会解析 MinIO 服务的必填变量，即使暂不启动 MinIO，也应先填写两个本地账号值。
如果要验证 MinIO 或生产对象存储，请配置：

```dotenv
DEMO_MODE=false
S3_ENDPOINT=http://127.0.0.1:9000
S3_ACCESS_KEY=你的对象存储账号
S3_SECRET_KEY=你的对象存储密码
S3_BUCKET_RESUMES=resumes
S3_BUCKET_AUDIO=audio
```

### 2. 启动 PostgreSQL 并迁移

使用仓库自带的 Compose 启动数据库：

```bash
cd apps/api
docker compose --env-file .env up -d --wait postgres
uv run alembic upgrade head
uv run alembic current
```

`alembic current` 应显示 `0006_offers_scheduling_ops (head)`。
如果 PostgreSQL 数据卷已经初始化过，仅修改 `.env` 中的 `POSTGRES_PASSWORD` 不会修改
数据库内的角色密码；需要在数据库中显式同步修改。

### 3. 启动 API 和后台 Worker

在两个终端中分别执行：

```bash
cd apps/api
uv run uvicorn ttc.main:app --app-dir src --host 127.0.0.1 --port 8000
```

```bash
cd apps/api
uv run python -m ttc.tasks.runner
```

- API 文档：`http://127.0.0.1:8000/docs`
- 进程存活：`http://127.0.0.1:8000/api/v1/health/live`
- 就绪检查：`http://127.0.0.1:8000/api/v1/health/ready`

简历解析、Crossref 检索和通话超时处理依赖 Worker，请不要只启动 API。

### 4. 创建本地账号和演示岗位

先创建演示租户和 HR 管理员：

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

再写入演示公司和岗位数据：

```bash
cd apps/api
TTC_SEED_PASSWORD='请替换为演示账号密码' \
uv run python scripts/seed_demo_companies.py
```

种子脚本是幂等的。候选人也可以从求职门户注册到 `demo` 租户。

### 5. 启动 HR 工作台

```bash
cd apps/web
npm ci
npm run dev
```

默认地址：`http://localhost:5173`。开发服务器会把 `/api`、`/ws` 和 `/health`
代理到 `http://localhost:8000`。

### 6. 启动候选人门户

```bash
cd apps/candidate-web
npm ci
npm run dev
```

默认地址：`http://localhost:5175`。

两个前端在本地开发时都可以保持 `VITE_API_BASE_URL` 为空，通过 Vite 代理访问后端。
如果前后端独立部署，在对应目录创建 `.env`：

```dotenv
VITE_API_BASE_URL=https://api.example.com
```

候选人端默认监听局域网地址。手机通过 `http://局域网IP:5175` 打开时，浏览器不会提供
麦克风权限。需要 HTTPS 时生成开发证书并重启 Vite：

```bash
cd apps/candidate-web
./scripts/make-dev-cert.sh 192.168.1.10
npm run dev
```

随后使用 `https://192.168.1.10:5175`。开发证书需要安装并信任，仅在本地开发使用。

### Docker Compose 运行完整后端

生产或集成联调时，可从 `apps/api` 启动 PostgreSQL、MinIO、API 和 Worker：

```bash
cd apps/api
docker compose --env-file .env build api worker
docker compose --env-file .env up -d --wait postgres minio
docker compose --env-file .env run --rm api alembic upgrade head
docker compose --env-file .env up -d --wait api worker
```

Compose 默认只把 PostgreSQL、MinIO 和 API 绑定到本机回环地址。对外部署时应在前端
和 API 前配置 TLS 反向代理，并替换所有演示密码和默认密钥。

## 环境变量

完整模板见 [`apps/api/.env.example`](apps/api/.env.example)。关键变量如下：

| 变量 | 作用 |
| --- | --- |
| `DATABASE_URL` | PostgreSQL 异步连接串；未配置时就绪检查返回 503 |
| `JWT_SECRET` | HS256 访问令牌密钥，至少 32 字节 |
| `COLUMN_ENCRYPTION_KEY` | 联系人等信息加密所需的 32 字节 AES-GCM 密钥 |
| `DEMO_MODE` | 本地演示开关；开启后允许本地文件存储并标识演示数据 |
| `S3_ENDPOINT` / `S3_*` | S3 或 MinIO 地址、凭证和桶名 |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | OpenAI 兼容 LLM 服务 |
| `DASHSCOPE_API_KEY` / `DASHSCOPE_*` | 通义千问实时语音 |
| `REALTIME_API_KEY` / `REALTIME_MODEL` | OpenAI Realtime SDP 代理 |
| `OCR_VLM_MODELS` / `OCR_VLM_API_KEY` | 扫描简历的视觉 OCR 模型链 |
| `EMBEDDING_*` | 人才库向量化服务；未配置时使用本地词法向量 |
| `OPENATS_*` / `VEKT_*` | 外部 ATS 和向量系统的预留配置 |

不要提交真实 `.env`、访问令牌、模型密钥或候选人资料。

## API 说明

所有业务接口位于 `/api/v1`。下表中的端点省略该前缀。HTTP 接口使用：

```http
Authorization: Bearer <access_token>
```

访问令牌默认 15 分钟有效，刷新令牌 30 天有效并轮换。候选人、HR 和 admin 的角色权限
由后端校验，`tenant_id` 从当前用户上下文解析。

错误响应采用统一结构：

```json
{
  "code": "TTC-2001",
  "message": "资源不存在",
  "request_id": "请求追踪 ID",
  "details": {}
}
```

常用接口：

| 领域 | 主要端点 |
| --- | --- |
| 健康与认证 | `/health/live`、`/health/ready`、`/auth/login`、`/auth/refresh`、`/auth/logout`、`/me` |
| 岗位 | `/jobs`、`/jobs/{id}/publish`、`/jobs/{id}/jd/versions`、`/jobs/{id}/weight-plan` |
| 候选人 | `/candidates`、`/candidates/{id}/resumes` |
| 简历 | `/resumes`、`/resumes/{id}/claims`、`/resumes/{id}/text`、`/resumes/{id}/timeline` |
| 证据与评估 | `/candidates/{id}/evidence-search`、`/candidates/{id}/assessments`、`/assessments/{id}` |
| 语音面试 | `/voice-sessions`、`/voice-sessions/{id}/realtime`、`/voice-sessions/{id}/turns`、`/voice-sessions/{id}/report` |
| HR 实时控制 | `/voice-sessions/{id}/observe` |
| 面试流程控制 | `/voice-sessions/{id}/flow-control` |
| 人工面试与 Offer | `/interviews`、`/interviews/{id}/status`、`/offers`、`/offers/{id}/decision` |
| 候选人门户 | `/portal/register`、`/portal/jobs`、`/portal/applications`、`/portal/interviews` |
| 治理与运营 | `/consents`、`/privacy/requests`、`/admin/audit-logs`、`/admin/backups`、`/talent/search` |
| 实时事件 | `/ws/progress/{task_id}`、`/ws/voice/{session_id}` |

进度和语音状态 WebSocket 建立连接后，客户端先发送：

```json
{"token":"<access_token>"}
```

具体请求体、响应结构和权限以启动后的 `/docs`、`/openapi.json` 为准。

## 数据集使用

进入数据集目录后，可执行 pilot 流程：

```bash
cd dataset
python3 scripts/run_pipeline.py --stage pilot
```

只重新校验和统计已有数据：

```bash
cd dataset
python3 scripts/run_pipeline.py --validate-only --strict
```

人工审阅 `dataset/reports/` 下的报告后，才可解除全量阶段闸门：

```bash
cd dataset
python3 scripts/run_pipeline.py --accept --note "人工验收通过"
python3 scripts/run_pipeline.py --stage full
```

核心输出：

- `dataset/dataset/resumes/resumes.jsonl`
- `dataset/dataset/resumes/resume_experiences.jsonl`
- `dataset/dataset/questions/interview_questions.jsonl`
- `dataset/dataset/questions/question_chains.jsonl`
- `dataset/dataset/metadata/`
- `dataset/reports/`

所有当前人物、学校、公司和联系方式均为合成数据。外部生成默认关闭，错误地使用真实
个人简历或未授权材料不在此工程的支持范围内。

## 测试与检查

后端：

```bash
cd apps/api
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p pytest_asyncio.plugin -q
uv run ruff check src tests alembic
```

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

## 当前边界

- LLM 未配置时，JD AI、简历 claim 抽取、匹配解释和面试纪要会返回明确的 503 或降级；
  言行审核仍会用窄规则兜底识别明确辱骂和威胁，其余情况标记为“待人工复核”。
  状态，不会生成伪造结果。
- 简历-岗位匹配需要可用的独立推理服务；模型未就绪时接口返回 503。可配置关键词兜底，
  但它只用于开发联调，不代表模型能力。
- 扫描 PDF 的 OCR 依赖视觉模型链，或服务器上的 `pdftoppm`、Tesseract 及对应语言包。
- Crossref 检索只对简历原文中可逐字定位的 DOI 查询作品元数据，不能证明候选人是作者。
- 通话报告整理已提交的转写轮次；言行分独立于岗位匹配分，只评价转写中可观察到的沟通行为，
  不评价外貌、声线、口音、情绪或敏感属性。严重事件必须能定位到候选人原始轮次才可自动否决。
- 实时语音中转层会检查候选人最终转写。明确辱骂或 AI 已发出严重言行终止警告时，服务端保存
  已完成轮次、将会话标记为 `conduct_violation`、断开来电并排队生成否决报告；若模型未正常
  收尾，最多 8 秒后同样强制终止。
- 面试能力评分为独立账本，不并入岗位匹配分。五个维度必须有候选人原始回答轮次支撑，有效
  权重不足 50% 或证据覆盖不足时标记为“证据不足/建议复核”；它只代表本次面试展示出的能力证据，
  不是通用智力、人格或长期绩效测评。
- OpenATS 同步和 Vekt 重建仍依赖尚未确定的外部协议与凭证，当前端点会明确返回未实现状态。
- 数据集全量 5000 份的生成需要先完成 pilot 人工验收；当前仓库记录的是 100 份试点数据。
- 演示账号、默认密码和开发证书仅可用于本机开发，不能直接用于生产环境。

## 相关文档

- 后端详细启动与边界：[`apps/api/README.md`](apps/api/README.md)
- 数据生成系统说明：[`dataset/README.md`](dataset/README.md)
- 历史接口审计：[`docs/API_CONTRACT.md`](docs/API_CONTRACT.md)
- 设计说明书：[`TTC_AI人才挖掘平台_详细设计说明书(6).pdf`](<TTC_AI人才挖掘平台_详细设计说明书(6).pdf>)
