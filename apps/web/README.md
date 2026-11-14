# TTC HR Workbench (`apps/web`)

React 18 + TypeScript + Vite + Tailwind CSS 的招聘工作台，前端数据访问已全部切换到
后端正式契约 `/api/v1`。

- 服务端状态：TanStack Query
- 本地状态：Zustand（登录令牌与当前用户）
- 鉴权：Bearer access token（15 分钟）+ refresh token 自动续期
- 不使用 Element Plus；候选人端仍为独立的 `apps/candidate`（预留）

## 运行环境

- Node 20 / 22 LTS（本机可用便携版 Node 22）
- 后端：`apps/api`（FastAPI + PostgreSQL 16 + DeepSeek + Qwen Realtime）

## 启动后端

```bash
cd apps/api
# 首次：配置 .env（DATABASE_URL / JWT_SECRET / COLUMN_ENCRYPTION_KEY /
# LLM_API_KEY / DASHSCOPE_API_KEY），并执行迁移
uv run alembic upgrade head
uv run uvicorn ttc.main:app --app-dir src --host 127.0.0.1 --port 8001
# 另开终端启动任务 worker（简历解析、Crossref 检索、语音超时收尾）
uv run python -m ttc.tasks.runner
```

本仓库当前开发机的 `8000` 可能被旧 AI AFS 进程占用，因此前端默认代理到 `8001`；
如果后端跑在 8000，用 `VITE_DEV_API_TARGET=http://127.0.0.1:8000 npm run dev` 覆盖。

## 启动前端

```bash
cd apps/web
npm install
npm run dev
```

默认地址：`http://localhost:5173/`（端口被占用时 Vite 会自动递增）。

Vite 开发代理（`vite.config.ts`）：

- `/api` → `http://127.0.0.1:8001`，`ws: true`（`/api/v1/ws/*` 与语音中转共用）
- `/health` → `http://127.0.0.1:8001/api/v1/health/live`（旧标签页兼容）

**改动 `vite.config.ts` 后必须重启 dev server**，Vite 不会热重载代理配置。

## 构建

```bash
npm run typecheck
npm run build
```

产物目录：`apps/web/dist/`。

## 登录与演示账号

登录页调用 `POST /api/v1/auth/login`，需要 `tenant_slug + email + password`。
演示账号由后端 CLI 生成（密码仅保存在本机）：

```bash
cd apps/api
TTC_BOOTSTRAP_PASSWORD='...' PYTHONPATH=src uv run python -m ttc.cli \
  --tenant-slug ttc --tenant-name 'TTC 演示租户' \
  --email hr@ttc.local --name '招聘管理员' --role hr
```

角色：`hr`（招聘）、`admin`（管理后台）、`candidate`（候选人授权/隐私）。

## 路由与接口

| 路径 | 页面 | 主要 `/api/v1` 接口 |
|---|---|---|
| `/login` | 登录 | `POST /auth/login`、`GET /me` |
| `/` | 工作台首页 | `GET /health/live`、`/health/ready`、`/jobs`、`/candidates` |
| `/jobs` | 岗位列表 | `GET /jobs` |
| `/jobs/new` | 新建岗位 | `POST /jobs`、可选 `POST /jobs/{id}/jd/generate` |
| `/jobs/:id` | 岗位详情 | `GET/PATCH /jobs/{id}`、`GET /jobs/{id}/stats`、JD `extract/generate/versions/select`、`POST /jobs/{id}/publish`、`PUT /jobs/{id}/weight-plan`、`GET /jobs/{id}/interview-plans` |
| `/candidates` | 候选人筛选 | `GET/POST /candidates`、`GET /candidates/{id}/resumes`、`POST /resumes`、`WS /ws/progress/{task_id}`、`POST /resumes/{id}/match`、`GET /assessments/{id}` |
| `/candidates/:id` | 候选人详情 | `GET /candidates/{id}`、`GET /resumes/{id}`、`/claims`、`/timeline`、`POST /resumes/{id}/reparse`、`DELETE /resumes/{id}`、`POST /candidates/{id}/assessments` |
| `/candidates/:id/report` | 评估报告 | `GET /assessments/{id}`、`PATCH /assessments/{id}`、`GET /assessments/{id}/export` |
| `/candidates/:id/evidence` | 证据中心 | `GET /candidates/{id}/evidence`、`POST /candidates/{id}/evidence-search`、`POST /evidence/{id}/confirm` |
| `/sessions` | 语音会话 | `POST /voice-sessions`、`GET /voice-sessions/{id}`、`WS /voice-sessions/{id}/realtime`、`POST /voice-sessions/{id}/finish`、`GET /voice-sessions/{id}/report` |
| `/admin` | 管理后台（仅 admin） | `GET /admin/data-sources`、`PATCH /admin/data-sources/{id}`、`GET /admin/audit-logs`、`GET /admin/metrics`、`GET /integrations/status` |

## API Service

- `src/api/client.ts`：Axios 实例、Bearer 注入、401 自动 refresh、健康检查
- `src/api/auth.ts`：登录、当前用户、退出
- `src/api/jobs.ts`：岗位、JD 版本、权重与面试方案
- `src/api/candidates.ts`：候选人与候选人简历列表
- `src/api/resumes.ts`：上传、claims、时间线、重解析、删除
- `src/api/assessments.ts`：确定性评估、报告、导出、人工复核、小模型匹配
- `src/api/evidence.ts`：Crossref 证据检索/列表/确认
- `src/api/voice.ts`：语音会话与实时中转
- `src/api/admin.ts`：数据源、审计、指标、集成状态
- `src/api/progress.ts`：任务进度 WebSocket（连接后先发 access token）
- `src/api/websocket.ts`：鉴权 WebSocket 工厂

## 真实性与边界

- 页面不伪造 AI 结果；模型未配置、任务失败、授权缺失都会显示后端错误。
- 候选人电话/邮箱默认脱敏，原始值不下发前端。
- 语音会话要求候选人已授予 `voice_interview` consent；HR 不能代替候选人授权。
- 小模型权重缺失时，后端可回退关键词匹配并在 `fallback_reason` 中标注；前端原样展示。
- API Key 仅存于 `apps/api/.env`，不进入前端、README 或 Git。
