# TTC AI Recruitment API 契约审计与现状说明

> 文档性质：只读审计报告与前后端联调契约基线。
> 审计日期：2026-11-14。
> 审计对象：`apps/api` 当前运行实例 `http://127.0.0.1:8000`，以及 `apps/web/src` 的调用代码。
> 代码基线：`60dcea6`（`git rev-parse HEAD`）。注意 `apps/` 在当前工作区为未跟踪状态（`git status` 显示 `?? apps/`），因此本文件描述的 `apps/api` 代码并未进入该提交。
> 结论：当前可运行的是一套 **AI AFS 兼容的 `/api/*` 接口（11 个 REST 端点 + 1 个 WebSocket 端点）**；正式设计要求的 `/api/v1` 契约尚未实现。未发现任何后端同事分支、PR 或可确认的 `/api/v1` 后端代码。

---

## 0. 审计结论摘要

| 项目 | 现状 |
|---|---|
| 当前 REST 端点数 | 11 个（OpenAPI 实测） |
| 当前 WebSocket 端点数 | 1 个：`/ws/{session_id}` |
| API 前缀 | `/api/jobs`、`/api/resumes`、`/api/export`、`/health`、`/ws`；无 `/api/v1` |
| 正式 `/api/v1` 实现数量 | 0 个 |
| 数据持久化 | 会话与结果全部在进程内内存；岗位档案为本地 JSON；上传文件落本地磁盘 |
| SQLAlchemy 2.0 模型 | 未发现 |
| Alembic 迁移 | 目录存在但为空，未发现 `alembic.ini`、`env.py`、迁移脚本 |
| PostgreSQL | 未引入（依赖与代码均无） |
| MinIO / 对象存储 | 未引入 |
| Redis / Celery | 未引入 |
| 认证 / 权限 / 多租户 | 未实现，所有 REST 与 WS 端点匿名可访问 |
| 错误响应 | FastAPI 默认 `{"detail": ...}`；无 `{code, message, request_id, details}` 信封 |
| 分页 | 无；所有列表一次性返回 |
| 时间格式 | 仅保存岗位有 UTC 时间，格式为 `...+00:00`，非正式示例的 `Z` |
| ID 格式 | `session_id` / `candidate_id` 为 UUID v4；`jd_id` 为 SHA-256；非 UUID v7 |
| 文件上传 | PDF / DOCX，单文件 20 MB；不支持文件被静默跳过，全部无效才 400 |
| 后端同事代码 | 未发现。`apps/api/src/ttc`、`apps/api/alembic/versions`、`apps/api/tests` 均为空目录骨架 |

**关键风险**

1. 前端目前按 AI AFS 兼容接口联调，而正式设计基线是 `/api/v1`；两套契约在路径、认证、错误码、分页、ID、WebSocket 事件名上均不一致。
2. 会话只存在单进程内存，后端重启或多 worker 部署会丢失全部处理结果。
3. 无认证和租户隔离，简历、候选人评分、导出文件均可被匿名访问。
4. 文件错误语义与正式设计不一致：超限/类型不支持会静默跳过或返回 400，而不是 413/415/422 结构化错误。
5. OpenAPI 对 `/api/resumes/results`、预览、删除、导出、`/health` 没有响应模型，生成客户端无法获知真实结构；预览与导出实际是二进制，但 OpenAPI 声明为 `application/json` 空 schema。

---

## 1. 范围与事实来源

### 1.1 当前实现（行为事实来源）

- 代码：`apps/api/server/main.py`、`apps/api/server/routes/*.py`、`apps/api/models/schemas.py`、`apps/api/server/ws/manager.py`、`apps/api/agents/orchestrator.py`、`apps/api/agents/resume_agent.py`。
- 运行时：`http://127.0.0.1:8000`。
- 实测 OpenAPI：`/openapi.json`，`info.title = "AI AFS"`，`info.version = "1.0.0"`。
- 本文件所有“当前”行为均来自上述代码与实测，不来自猜测。

### 1.2 正式设计（目标契约来源）

- `TTC_AI人才挖掘平台_总体设计说明书(4).pdf`
- `TTC_AI人才挖掘平台_详细设计说明书(4).pdf`

本审计使用的正式要求位置：

| 要求 | 正式文档位置 | 内容 |
|---|---|---|
| API 前缀 | 详细设计 §4.1 | `/api/v1` |
| 认证 | 详细设计 §4.1 | `Authorization: Bearer <access_token>`；access 15 分钟，refresh 30 天轮换 |
| 租户 | 详细设计 §4.1 | 从令牌解析，不接受客户端传入 `tenant_id` |
| 幂等 | 详细设计 §4.1 | 写接口支持 `Idempotency-Key`，同 key 24 小时内返回首次结果 |
| 分页 | 详细设计 §1.3、§4.1 | 游标分页，`?cursor=<opaque>&limit=20`，默认 20、最大 100，响应含 `next_cursor` |
| 时间 | 详细设计 §1.3、§4.1 | RFC 3339 UTC，例如 `2026-11-13T07:30:00Z`；数据库 `timestamptz` |
| ID | 详细设计 §1.3 | 所有 ID 使用 UUID v7（时间有序） |
| 并发 | 详细设计 §4.1 | PATCH 携带 `If-Match: <updated_at>`，冲突返回 `TTC-2003` |
| 追踪 | 详细设计 §4.1 | 响应头 `X-Request-Id` |
| 通用错误 | 详细设计 §1.4 | `{code, message, request_id, details}` |
| 文件上传 | 详细设计 §4.3.4 | `pdf/docx/txt`；MIME 嗅探；≤20 MB；损坏检测；sha256 去重 |
| WS 进度 | 详细设计 §4.4.1 | `/ws/progress/{task_id}`，事件 `progress` / `done` / `error`，含 `percent`，按 `seq` 去重 |
| JSON Schema 契约 | 总体设计 §1.2 G5、§4.4.2；详细设计 §2、§7.2 | 模型输出必须符合 JSON Schema；`packages/contracts` 存放契约并进行契约测试 |

### 1.3 后端同事代码调查结果

| 检查项 | 命令/位置 | 结果 |
|---|---|---|
| 本地分支 | `git branch -a` | `feat/ai-screening-mvp`、`feat/frontend-resume`、`feat/react-hr-workbench`（当前）、`feat/ttc-platform-integration`、`main`、`remotes/origin/main` |
| 全部提交 | `git log --all --oneline --decorate` | 只有一个提交：`60dcea6 (HEAD -> feat/react-hr-workbench, tag: pre-react-hr-workbench-20261114, tag: phase1-audit-20261114, origin/main, main, feat/ttc-platform-integration, feat/frontend-resume, feat/ai-screening-mvp) feat: initialize TTC recruitment frontend` |
| 远程分支 | `git ls-remote --heads origin` | **失败**：`fatal: unable to access 'https://github.com/yikezhenguoli/AI-recruitment.git/': Failed to connect to github.com:443 after 21061 ms: Could not connect to server`（退出码 128） |
| PR 列表 | `gh pr list` | **无法执行**：`gh: command not found`（退出码 127） |
| 后端目标目录 | `apps/api/src/ttc/` | 仅有空目录：`adapters/`、`api/v1/`、`core/`、`domains/`、`tasks/`、`ws/`，无任何文件 |
| Alembic | `apps/api/alembic/` | 仅有空目录 `versions/`；无 `alembic.ini`、`env.py`、迁移文件 |
| 测试 | `apps/api/tests/` | 空目录 |
| 契约包 | `packages/contracts/` | 空目录 |
| 部署 | `deploy/`、`scripts/` | 空目录 |
| 版本控制状态 | `git status --short` | ` M .gitignore`、`?? TTC_Liquid_Glass_Kit/`、`?? apps/`；`apps/` 整体未被跟踪 |

**结论：不能确认存在任何后端同事实现。** 由于远程查询失败且未安装 `gh`，不能据此断言远程一定没有分支或 PR；但本地所有 ref 都指向同一个提交，且 `apps/` 未提交。因此凡涉及“后端计划如何实现 `/api/v1`”的内容，本文件一律标记为 `待后端负责人确认`，不自行补全。

### 1.4 证据等级约定

| 标记 | 含义 |
|---|---|
| 已实现 | 代码与运行实例均存在，OpenAPI 或实测可验证 |
| 正式要求 | 仅来自两份设计 PDF，当前无对应实现 |
| 待后端负责人确认 | 无后端分支/PR/代码可查，或需要产品/架构决策 |

---

## 2. 当前接口总表

以下 11 个 REST 端点均来自实测 `/openapi.json`。所有路径均为完整路径，无 `/api/v1` 前缀。

| 接口名称 | 方法 | 完整路径 | 请求参数 | 请求体 | 响应结构 | 错误响应 | 前端调用位置 | 状态 |
|---|---|---|---|---|---|---|---|---|
| 健康检查 | GET | `/health` | 无 | 无 | `{status:"ok", app:"AI AFS", provider:"deepseek", model:string, llm_configured:boolean}` | 正常情况下无业务错误；进程异常时由服务器返回 5xx | `apps/web/src/api/client.ts` `getHealth()`；`apps/web/src/components/layout/AppLayout.tsx:60`；`apps/web/src/pages/WorkbenchHome.tsx:57` | 已实现；OpenAPI 无响应模型 |
| JD 解析 | POST | `/api/jobs/parse` | 无 | JSON `{jd_text:string}` | `{jd_id:string, structured:JobDescriptionStructured, scoring_schema:ScoringSchema}` | 400 `jd_text` 为空；422 请求体校验失败；500 LLM/缓存失败 | `apps/web/src/api/jobs.ts` `parseJD()`；`apps/web/src/components/JobDescriptionForm.tsx:109`（由 `apps/web/src/pages/JobCreatePage.tsx` 渲染） | 已实现 |
| 已保存岗位列表 | GET | `/api/jobs/saved` | 无（无分页、无筛选） | 无 | `{jobs:[{name, role_title, updated_at}]}` | 500 读取失败 | `apps/web/src/api/jobs.ts` `listSavedJobs()`；`JobDescriptionForm.tsx:70`；`apps/web/src/pages/JobListPage.tsx:11`；`WorkbenchHome.tsx:53`；`CandidatesPage.tsx:52` | 已实现 |
| 已保存岗位详情 | GET | `/api/jobs/saved/{name}` | 路径 `name`（前端 `encodeURIComponent`） | 无 | `{job:{name, jd_text, structured:JobDescriptionStructured, scoring_schema:ScoringSchema, created_at, updated_at}}` | 404 `Saved job not found`；500 读取失败 | `apps/web/src/api/jobs.ts` `getSavedJob()`；`JobDescriptionForm.tsx:124`；`apps/web/src/pages/JobDetailPage.tsx:34`；`CandidatesPage.tsx:57`；`CandidateProfile.tsx:79` | 已实现；`name` 为业务键，不是 UUID |
| 保存岗位档案 | POST | `/api/jobs/saved` | 无 | JSON `{name, jd_text, structured:JobDescriptionStructured, scoring_schema:ScoringSchema}` | `{job:{name, jd_text, structured, scoring_schema, created_at, updated_at}}` | 400 名称或 JD 为空；409 同名已存在；422 请求体校验失败；500 写入失败 | `apps/web/src/api/jobs.ts` `saveJobProfile()`；`JobDescriptionForm.tsx:175` | 已实现；返回 200，不是 201 |
| 启动简历处理 | POST | `/api/resumes/process` | multipart 表单：`jd_text`（必填）、`files`（必填，可多文件）、`scoring_schema_json`（可选字符串）、`graduation_filter_json`（可选字符串） | `multipart/form-data`；文件仅 PDF/DOCX | `{session_id:string, total_files:number, message:string}` | 400 JD 为空、JSON 参数非法、无有效文件；422 缺少必填表单字段；500 JD 解析失败 | `apps/web/src/api/resumes.ts` `processResumes()`；`apps/web/src/components/ResumeUpload.tsx:91`；由 `CandidatesPage.tsx:331` 渲染 | 已实现；异步启动但返回 200，不是 202 |
| 查询会话结果 | GET | `/api/resumes/results/{session_id}` | 路径 `session_id` | 无 | `{session_id, status:"processing"\|"done", total, completed, failed, results:[CandidateResult]}`；`results` 按 `score` 降序 | 404 `Session not found` | `apps/web/src/api/candidates.ts` `getSessionResults()`；`ProcessingPanel.tsx`（轮询与完成拉取）；`CandidatesPage.tsx:86` | 已实现；OpenAPI 无响应模型 |
| 候选人详情 | GET | `/api/resumes/detail/{session_id}/{candidate_id}` | 路径 `session_id`、`candidate_id` | 无 | `ProcessedCandidateRecord`：`{candidate:CandidateResult, resume_structured:ResumeStructured}` | 404 会话不存在；404 会话内候选人不存在 | `apps/web/src/api/candidates.ts` `getCandidateDetail()`；`CandidateProfile.tsx:73`；由 `CandidateDetailPage.tsx`、`CandidateReportPage.tsx` 渲染 | 已实现（代码注释标注为 additive 只读端点） |
| 简历 PDF 预览 | GET | `/api/resumes/preview-file/{session_id}/{candidate_id}` | 路径 `session_id`、`candidate_id` | 无 | 二进制 `application/pdf`；`Content-Disposition: inline`；`Cache-Control: no-store`；`X-Content-Type-Options: nosniff` | 404 会话不存在；404 预览不可用；404 非 PDF；404 文件已不存在 | `apps/web/src/api/resumes.ts` `getResumePreviewUrl()`；`CandidateResults.tsx:385`；`CandidateProfile.tsx:214`；`ResultsTable.tsx:337`（该组件当前未被页面引用）；`ExportButton.tsx` 不调用此端点 | 已实现；仅 PDF；OpenAPI 声明为 JSON 空 schema |
| 关闭筛选会话 | DELETE | `/api/resumes/session/{session_id}` | 路径 `session_id` | 无 | `{message:"Session closed"}` | 404 `Session not found` | `apps/web/src/api/resumes.ts` `closeResumeSession()`；`CandidatesPage.tsx:118,153,167` | 已实现；OpenAPI 无响应模型 |
| 导出 Excel | GET | `/api/export/{session_id}` | 路径 `session_id` | 无 | 二进制 `.xlsx`；`Content-Disposition: attachment; filename="ai_afs_{session_id前8位}.xlsx"` | 404 会话不存在；404 无结果可导出；500 生成失败 | `apps/web/src/api/reports.ts` `getExportUrl()`；`CandidateResults.tsx:147`；`CandidateProfile.tsx:203`；`ExportButton.tsx:16`（该组件当前未被页面引用） | 已实现；OpenAPI 声明为 JSON 空 schema |

### 2.1 核心 Schema 摘要

`JobDescriptionStructured`：

```json
{
  "role_title": "string (required)",
  "seniority_level": "string|null",
  "required_skills": ["string"],
  "preferred_skills": ["string"],
  "min_years_experience": "integer|null",
  "preferred_years_experience": "integer|null",
  "education_requirements": {"level": "string|null", "field": "string|null", "required": "boolean"},
  "responsibilities": ["string"],
  "keywords": ["string"],
  "weighting_signals": {"string": "number"}
}
```

`ScoringSchema`：

```json
{
  "dimensions": [
    {"name": "string", "label": "string", "description": "string", "max_points": "integer"}
  ]
}
```

说明：当前使用 `max_points`，前端要求所有维度合计等于 100；正式设计要求 `weight_pct` 且总和 100。二者字段名和语义不同。

`CandidateResult`：

```json
{
  "candidate_id": "string (required, UUID v4)",
  "file_name": "string (required)",
  "name": "string|null",
  "email": "string|null",
  "phone": "string|null",
  "score": "integer 0-100|null",
  "explanation": ["string"],
  "stage": "queued|parsing|extracting|screening|evaluating|done|error|skipped|filtered|review",
  "error": "string|null",
  "parse_method": "primary|ocr|null",
  "screening_outcome": "ranked|filtered|review|duplicate|error",
  "screening_reason": "string|null",
  "graduation_year_info": {
    "selected_degree": "string|null",
    "graduation_year": "integer|null",
    "source": "explicit|inferred|unknown|not_applicable"
  },
  "preview_available": "boolean",
  "dimension_scores": [{"name": "string", "score": "integer", "reason": "string"}]
}
```

`ResumeStructured`：

```json
{
  "personal_info": {"first_name": "string|null", "last_name": "string|null", "email": "string|null", "phone": "string|null", "location": "string|null"},
  "skills": ["string"],
  "education": [{"institution": "string|null", "degree": "string|null", "field": "string|null", "score_gpa": "string|null", "start_date": "string|null", "end_date": "string|null"}],
  "work_experience": [{"organization": "string|null", "role": "string|null", "start_date": "string|null", "end_date": "string|null", "responsibilities": ["string"]}],
  "projects": [{"name": "string|null", "description": "string|null", "technologies": ["string"]}],
  "publications": [{"title": "string|null", "journal": "string|null", "year": "string|null"}],
  "certifications": [{"name": "string|null", "issuer": "string|null", "date": "string|null"}],
  "additional_info": {"string": "any"}
}
```

---

## 3. 当前接口明细与行为说明

### 3.1 `POST /api/jobs/parse`

- 请求：`{"jd_text": "..."}`。
- 处理：`jd_id = SHA-256(jd_text.strip())`，作为 JD 与评分 Schema 的磁盘缓存键。
- 响应：
  - `jd_id`：64 位十六进制 SHA-256，不是 UUID。
  - `structured`：LLM 抽取并 Pydantic 校验后的 `JobDescriptionStructured`。
  - `scoring_schema`：LLM 生成的维度列表，字段为 `max_points`。
- 错误：
  - `400 {"detail":"jd_text cannot be empty"}`。
  - `422` FastAPI 请求体校验错误。
  - `500 {"detail":"JD parsing failed: ..."}`，异常文本可能包含上游/模型细节。
- 前端：`apps/web/src/api/jobs.ts:7-15`。

### 3.2 `GET /api/jobs/saved`

- 无查询参数、无分页、无筛选。
- 返回 `jobs`，按 `(updated_at, name.lower())` 倒序。
- 存储：`apps/api/cache/saved_jobs.json`（由 `SAVED_JOBS_FILE` 指定），文件不存在时返回空列表。
- 错误：读取/解析 JSON 失败时 `500 {"detail":"Failed to list saved jobs: ..."}`。

### 3.3 `GET /api/jobs/saved/{name}` 与 `POST /api/jobs/saved`

- 名称按 `strip().lower()` 归一化后作为键，因此保存名称大小写不敏感；响应返回保存时的展示名称。
- 重复保存返回 `409 {"detail":"A saved job named '...' already exists"}`。
- POST 返回 200，非 201；没有 `Location` 头。
- `created_at` / `updated_at` 由 `datetime.now(timezone.utc).isoformat()` 生成，例如 `2026-11-13T18:04:59.236028+00:00`。

### 3.4 `POST /api/resumes/process`

执行顺序：

1. 校验 `jd_text.strip()`。
2. 调用 `parse_job_description(jd_text)`，命中缓存则复用；失败返回 500。
3. 若传入 `scoring_schema_json`，用 `ScoringSchema(**json.loads(...))` 校验；非法返回 400。
4. 若传入 `graduation_filter_json`，用 `GraduationYearFilterConfig(**...)` 校验；非法返回 400。
5. 逐个文件判定类型、读取全部字节、检查空文件与 20 MB 上限。无效文件加入 `skipped` 列表并继续。
6. 若没有任何有效文件，返回 400 `No valid resume files could be processed`。
7. 创建内存会话，`asyncio.create_task(run_pipeline(...))` 启动后台处理，立即返回 200。
8. `total_files` 只统计有效文件；被跳过文件的文件名只拼接在 `message` 字符串中，没有结构化字段。

注意：`files` 在 FastAPI 签名中为必填，缺失时框架先返回 422；处理器内部的 `if not files` 分支通常不可达。

### 3.5 `GET /api/resumes/results/{session_id}`

- 返回当前内存会话状态与候选结果。
- `total` = 有效文件数；`completed` = `stage == "done"` 数量；`failed` = 非 `done` 且非 `skipped` 的数量；`skipped` 不在响应顶层字段中，只在 `results[].stage` / `screening_outcome` 体现。
- `results` 按 `(score or -1)` 降序，未评分/错误/重复项排在最后。
- 会话只存在于当前进程内存，后端重启后返回 404。

### 3.6 `GET /api/resumes/detail/{session_id}/{candidate_id}`

- 返回 `ProcessedCandidateRecord`，包含完整 `resume_structured`。
- 数据仍来自内存会话，不触发新的 LLM 调用。
- 候选不存在和会话不存在都返回 404，`detail` 文本不同。

### 3.7 `GET /api/resumes/preview-file/{session_id}/{candidate_id}`

- 仅对 PDF 生效；预览文件来自上传临时目录。
- PDF 在流水线完成后保留，直到 `DELETE /api/resumes/session/{session_id}` 清理；DOCX 在处理完成后删除。
- 响应头包含 `Content-Disposition: inline; filename="..."`、`Cache-Control: no-store`、`X-Content-Type-Options: nosniff`。
- 非 PDF、预览不存在、文件已删除均返回 404。

### 3.8 `DELETE /api/resumes/session/{session_id}`

- 从内存移除会话、结果和预览映射，并尝试删除预览文件。
- 返回 `{"message":"Session closed"}`；会话不存在返回 404。
- 不清理 WebSocket 管理器中该会话的缓冲消息（代码中无对应清理逻辑）。

### 3.9 `GET /api/export/{session_id}`

- 使用 openpyxl 生成 `Candidate Rankings` 工作表。
- 列：Name、Email、Phone、Score、Outcome、Reason、Graduation Year、Grad Year Source、Explanation、Location、Skills、Education、Work Experience、Projects、Publications、Certifications、Additional Info。
- `done` 候选人优先并按分数降序；其他状态排在后面。
- 无结果返回 404；生成异常返回 500。

### 3.10 `GET /health`

- 始终返回 200（除非进程不可用）。
- `llm_configured` 取决于 `DEEPSEEK_API_KEY` 是否非空；未配置时健康检查仍为 200。
- 前端每 30 秒轮询一次，用于顶部状态指示。

---

## 4. WebSocket 事件协议

### 4.1 连接

| 项目 | 当前实现 |
|---|---|
| 路径 | `WS /ws/{session_id}` |
| 认证 | 无；任意 `session_id` 都可连接 |
| 协议 | 仅服务端向客户端推送；客户端发送的文本被 `receive_text()` 丢弃，不做业务处理 |
| 连接管理 | `ConnectionManager` 每个 `session_id` 只保留一个连接；新连接覆盖旧连接 |
| 缓冲 | 客户端未连接时消息进入该会话缓冲区；连接建立后按顺序补发并清空缓冲区 |
| 去重 | 无 `seq`、无消息 ID；重连补发与轮询结果可能产生重复展示 |
| 会话校验 | 不校验 `session_id` 是否存在；未知会话会连接成功但永远收不到消息 |
| 缓冲区清理 | 会话关闭时不清理缓冲区，存在内存增长风险 |

### 4.2 事件表

| 事件 `type` | 方向 | 字段 | 触发时机 | 前端处理 |
|---|---|---|---|---|
| `progress` | S→C | `type:"progress"`, `session_id`, `candidate_id`, `stage`, `message`, `data`（通常为 `{}`） | 流水线阶段切换：`queued`、`parsing`、`extracting`、`screening`、`evaluating`；OCR 回退可能再次发送 `parsing` | `ProcessingPanel.tsx` 更新候选人阶段；`ProgressDashboard.tsx`（当前未被页面引用）也处理 |
| `result` | S→C | `type:"result"`, `session_id`, `candidate_id`, `result:CandidateResult` | `done` 时由 `evaluate_node` 发送；`error` / `filtered` / `review` 时由 orchestrator 补发；重复文件由 `run_pipeline` 发送 | `ProcessingPanel.tsx` 用完整候选人结果覆盖条目 |
| `complete` | S→C | `type:"complete"`, `session_id`, `total`, `completed`, `failed`, `skipped` | 所有任务结束，会话状态置为 `done` 后发送 | `ProcessingPanel.tsx` 收到后拉取最终结果并结束；`ProgressDashboard.tsx` 仅关闭连接 |

说明：`WSCompleteMessage` Pydantic 模型只定义 `type/session_id/total/completed/failed`，运行时额外发送 `skipped`；前端 TypeScript 类型将其定义为可选字段。

### 4.3 阶段枚举

| 阶段 | 含义 | 是否作为 `progress.stage` 发送 | 是否出现在 `result.result.stage` |
|---|---|---|---|
| `queued` | 排队，任务开始 | 是 | 可能（异常前） |
| `parsing` | 读取并解析 PDF/DOCX，必要时 OCR | 是 | 可能（异常） |
| `extracting` | LLM 抽取结构化简历 | 是 | 可能（异常） |
| `screening` | 毕业年份筛选 | 是 | 可能（`filtered` / `review`） |
| `evaluating` | LLM 逐维度评分 | 是 | 可能（异常） |
| `done` | 完成并评分 | 否 | 是 |
| `error` | 解析/抽取/评分失败 | 否 | 是 |
| `skipped` | 重复文件跳过 | 否 | 是 |
| `filtered` | 被毕业年份条件过滤 | 否 | 是 |
| `review` | 需人工复核（毕业年份未知） | 否 | 是 |

### 4.4 计数语义

- `total`：上传阶段通过校验的有效文件数；不含因类型不支持、空文件、超 20 MB、读取失败而被跳过的文件。
- `completed`：`stage == "done"`。
- `failed`：非 `done` 且非 `skipped`（包含 `error`、`filtered`、`review`）。
- `skipped`：本批次内 SHA-256 重复而跳过的文件数；不包含上传阶段跳过的文件。

### 4.5 重连语义

- 服务端在客户端离线期间缓冲该会话消息，连接建立时补发。
- 没有序号，无法区分补发消息与新消息；前端按 `candidate_id` 覆盖，通常可达到最终一致，但不是严格去重。
- 前端 `ProcessingPanel.tsx`：
  - 同时每 3 秒调用 `GET /api/resumes/results/{session_id}` 兜底轮询。
  - WS 断开后最多重连 5 次，延迟为 1s、2s、4s、8s、8s。
  - 5 次失败后停止重连并提示，但轮询继续。
  - 收到 `complete` 或轮询发现 `status == "done"` 时结束并拉取最终结果。
- 前端 `ProgressDashboard.tsx` 只连接一次，无重连与轮询；该组件当前未被任何页面引用。

### 4.6 与正式设计 WS 的差异

| 项目 | 正式设计 | 当前实现 |
|---|---|---|
| 路径 | `/ws/progress/{task_id}` | `/ws/{session_id}` |
| 认证 | 已认证 | 无认证 |
| 事件 | `progress`、`done`、`error` | `progress`、`result`、`complete` |
| 进度字段 | 含 `percent`、`task_id`、`stage`、`message` | 无 `percent`、无 `task_id`，用 `session_id`/`candidate_id` |
| 错误事件 | `{type:"error", code, message}` | 通过 `result` 事件中的 `stage:"error"` 与 `error` 字段表达 |
| 去重 | 客户端按 `seq` 去重 | 无 `seq` |
| 历史补发 | 连接时补发历史消息 | 有缓冲补发，但无序号与持久化 |

---

## 5. 文件上传规范

### 5.1 请求

- 端点：`POST /api/resumes/process`
- 内容类型：`multipart/form-data`
- 字段：

| 字段 | 必填 | 类型 | 说明 |
|---|---|---|---|
| `jd_text` | 是 | 文本 | JD 原文；空字符串返回 400 |
| `files` | 是 | 文件数组 | 可一次上传多个文件 |
| `scoring_schema_json` | 否 | JSON 字符串 | 用户自定义评分维度；结构须符合 `ScoringSchema` |
| `graduation_filter_json` | 否 | JSON 字符串 | 结构须符合 `GraduationYearFilterConfig` |

### 5.2 类型识别

当前逻辑为“扩展名命中 **或** `Content-Type` 命中”：

| 判定 | 条件 | 结果类型 |
|---|---|---|
| PDF | 扩展名 `.pdf` 或 `Content-Type` 含 `pdf` | `pdf` |
| DOCX | 扩展名 `.docx` 或 `Content-Type` 含 `wordprocessingml` / `openxmlformats` | `docx` |
| 其他 | 其余情况 | 跳过 |

代码中定义了 `ALLOWED_TYPES` 常量（PDF/DOCX MIME 映射），但实际判定未使用该常量。

### 5.3 大小与跳过/错误矩阵

| 情况 | 实际行为 | HTTP 结果 |
|---|---|---|
| 单文件为空（0 字节） | 跳过，记录文件名 | 请求继续；若全部无效则 400 |
| 单文件 > 20 MB | 跳过，记录文件名 | 请求继续；若全部无效则 400 |
| 扩展名/MIME 不支持 | 跳过，记录文件名 | 请求继续；若全部无效则 400 |
| 文件读取异常 | 跳过，记录文件名 | 请求继续；若全部无效则 400 |
| 至少一个有效文件 | 启动后台流水线 | 200 + `{session_id,total_files,message}` |
| 所有文件均无效 | 不创建会话 | 400 `No valid resume files could be processed` |
| 缺少 `files` 字段 | FastAPI 校验失败 | 422 |
| 缺少 `jd_text` 字段 | FastAPI 校验失败 | 422 |
| 同批次 SHA-256 重复 | 生成一个 `stage:"skipped"`, `screening_outcome:"duplicate"` 的候选人记录 | 仍计入 `total_files`，并计入 `complete.skipped` |

### 5.4 处理与存储

- 每个文件先完整读入内存，再写入 `UPLOAD_DIR` 下的临时文件；没有请求级总大小或文件数量限制。
- PDF：处理完成后保留临时文件用于预览，`DELETE /api/resumes/session/{id}` 时删除。
- DOCX：处理完成后删除临时文件。
- 重复检测仅在同一批次内生效（`seen_hashes` 为 `run_pipeline` 局部变量），不跨会话、不跨候选人持久化。
- 未做 MIME 魔数嗅探、扩展名与内容一致性校验、损坏检测预检；损坏文件会在解析阶段变成候选人 `stage:"error"`，而不是请求级 422。

### 5.5 与正式设计的差异

| 项目 | 正式设计 §4.3.4 | 当前实现 |
|---|---|---|
| 允许类型 | `pdf`、`docx`、`txt` | 仅 PDF、DOCX |
| MIME 校验 | 声明 MIME 与嗅探 MIME 一致 | 扩展名或声明 MIME 任一命中即可 |
| 大小超限 | 413 `TTC-3002` | 跳过；全无效时 400 |
| 类型不支持 | 415 `TTC-3001` | 跳过；全无效时 400 |
| 损坏/内容不符 | 422 `TTC-3003` / `TTC-3004` | 解析阶段候选人级 error |
| 去重 | 按候选人 + sha256，持久化 | 仅同批次内去重 |
| 存储 | MinIO 私有桶 | 本地 `uploads/` 临时目录 |
| 返回码 | 202 Accepted + `resume_id/task_id/checks` | 200 + `session_id/total_files/message` |

---

## 6. 错误响应格式与正式 `{code,...}` 差距

### 6.1 当前实际格式

所有业务错误通过 `fastapi.HTTPException` 抛出，未注册全局异常处理器：

```json
{"detail": "Saved job not found"}
```

请求体/表单校验失败由 FastAPI 默认处理：

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "jd_text"],
      "msg": "Field required",
      "input": {}
    }
  ]
}
```

实测样例：

| 请求 | HTTP | 响应 |
|---|---|---|
| `POST /api/jobs/parse`，`jd_text` 为空白 | 400 | `{"detail":"jd_text cannot be empty"}` |
| `POST /api/jobs/parse`，请求体 `{}` | 422 | `{"detail":[{"type":"missing","loc":["body","jd_text"],"msg":"Field required","input":{}}]}` |
| `GET /api/jobs/saved/__missing__` | 404 | `{"detail":"Saved job not found"}` |
| `GET /api/resumes/results/nope` | 404 | `{"detail":"Session not found"}` |
| `GET /api/export/nope` | 404 | `{"detail":"Session not found"}` |

当前格式没有：`code`、`request_id`、`details`、`X-Request-Id` 响应头、稳定的机器可读错误分类。500 响应可能把上游异常文本直接拼入 `detail`。

前端 `apps/web/src/lib/apiError.ts` 直接从 `error.response.data.detail` 读取字符串或数组并拼接 `msg`，因此当前前端与 `detail` 格式是匹配的；一旦后端切换到 `{code,...}` 信封，前端错误解析需要同步修改。

### 6.2 正式错误信封与错误码

正式要求（详细设计 §1.4）：

```json
{
  "code": "TTC-4001",
  "message": "候选人尚未授予语音沟通授权",
  "request_id": "01J9Z8K3...",
  "details": {"consent_id": "..."}
}
```

| 错误码 | HTTP | 含义 |
|---|---|---|
| `TTC-1001` | 401 | 未认证或令牌过期 |
| `TTC-1002` | 403 | 无权限 |
| `TTC-1003` | 403 | 跨租户访问 |
| `TTC-2001` | 404 | 资源不存在 |
| `TTC-2002` | 409 | 当前状态不允许该操作 |
| `TTC-2003` | 409 | 版本冲突（乐观锁） |
| `TTC-3001` | 415 | 文件类型不支持 |
| `TTC-3002` | 413 | 文件超过大小上限 |
| `TTC-3003` | 422 | 文件损坏或无法解析 |
| `TTC-3004` | 422 | 文件内容与扩展名不符 |
| `TTC-4001` | 403 | 同意未授予或已撤回 |
| `TTC-4002` | 409 | 会话已结束/已撤销 |
| `TTC-5001` | 504 | 上游服务超时 |
| `TTC-5002` | 502 | 模型输出不符合契约 |
| `TTC-5003` | 429 | 触发限流 |
| `TTC-5004` | 503 | 供应商不可用（可降级） |

**差距：当前没有任何一个端点返回 `code` 字段或使用上述错误码。** 所有错误都必须视为“未对齐正式契约”。

### 6.3 端点错误状态对照

| 端点 | 当前可返回状态 | 正式设计期望（如有） |
|---|---|---|
| `POST /api/jobs/parse` | 400、422、500 | 应有统一错误信封；模型契约失败应为 `TTC-5002` |
| `GET /api/jobs/saved` | 500 | 应分页并返回统一错误 |
| `GET /api/jobs/saved/{name}` | 404、500 | 404 应映射 `TTC-2001` |
| `POST /api/jobs/saved` | 400、409、422、500 | 409 应映射 `TTC-2002`/`TTC-2003`，并可能要求幂等键 |
| `POST /api/resumes/process` | 400、422、500 | 应 202；文件错误应有 413/415/422 与 `TTC-300x` |
| `GET /api/resumes/results/{session_id}` | 404 | 404 应映射 `TTC-2001` |
| `GET /api/resumes/detail/...` | 404 | 404 应映射 `TTC-2001` |
| `GET /api/resumes/preview-file/...` | 404 | 404 应映射 `TTC-2001` |
| `DELETE /api/resumes/session/{session_id}` | 404 | 404 应映射 `TTC-2001` |
| `GET /api/export/{session_id}` | 404、500 | 未在正式端点表中定义 |
| `GET /health` | 200 | 正式设计未定义 |

---

## 7. 分页、时间、ID、认证、CORS、环境变量与启动配置

### 7.1 分页

- 当前：**无分页**。`GET /api/jobs/saved` 返回全部岗位，`GET /api/resumes/results/{session_id}` 返回全部候选人。
- 没有 `cursor`、`limit`、`next_cursor`，也没有默认 20/最大 100 的约束。
- 正式要求：所有列表接口默认 20 条、最大 100 条，使用不透明游标，响应含 `next_cursor`。
- 影响：岗位数量或候选人数增长后，响应体与前端渲染都会线性膨胀；未来迁移到正式契约时，前端需要改造列表状态与“加载更多/无限滚动”逻辑。

### 7.2 时间格式

- 当前只有保存岗位档案返回时间字段：`created_at`、`updated_at`。
- 生成方式：

```python
datetime.now(timezone.utc).isoformat()
```

- 实测格式：`2026-11-13T18:04:59.236028+00:00`。
- 该格式是 RFC 3339 允许的“数字偏移”形式，但与正式示例 `2026-11-13T07:30:00Z` 的 `Z` 形式不同；没有统一到 `Z`，也没有固定毫秒/微秒精度。
- `session_id`、`candidate_id`、结果、健康检查均不带时间戳。
- 简历中的 `start_date` / `end_date` / `publication.year` 等是 LLM 返回的自由字符串，未做 RFC 3339 或 `YYYY-MM` 校验。
- 正式要求：所有对外时间 RFC 3339 UTC，数据库列 `timestamptz`；当前无数据库，无法满足。

### 7.3 ID 格式

| ID | 当前生成方式 | 示例/形态 | 正式要求 |
|---|---|---|---|
| `session_id` | `str(uuid.uuid4())` | 标准 UUID v4，如 `550e8400-e29b-41d4-a716-446655440000` | UUID v7 |
| `candidate_id` | `str(uuid.uuid4())` | UUID v4 | UUID v7 |
| `jd_id` | `sha256(jd_text.strip())` | 64 位十六进制 | 正式为 `job_version.id` UUID v7 |
| 岗位档案标识 | `name.strip().lower()` | 业务名称字符串 | 正式为 `job.id` UUID v7 |

- 依赖中未发现 UUID v7 库。
- 前端把所有 ID 当作不透明字符串处理，因此换用 UUID v7 不会破坏当前前端类型，但会影响可读性和后端索引/分页策略。

### 7.4 认证、权限、租户

- 当前：**无认证、无权限、无租户**。
- 所有 REST 端点匿名可访问；WebSocket 匿名可连接任意 `session_id`。
- 没有 `Authorization`、`Bearer`、JWT、refresh token、RBAC、`tenant_id`、审计日志。
- 正式要求：Bearer access token（15 分钟）+ refresh token（30 天轮换）；角色 `hr/admin/candidate`；租户从令牌解析；跨租户返回 `TTC-1003`；写操作审计。
- 影响：当前 API 只能用于受控本地演示，不能直接暴露到公网；任何拿到 `session_id` 的人都能读取候选人结果、下载简历 PDF 和 Excel。

### 7.5 CORS

当前 `CORSMiddleware` 配置：

| 配置 | 值 |
|---|---|
| `allow_origins` | `CORS_ORIGINS` 逗号分隔列表；默认 `http://localhost:5173,http://127.0.0.1:5173` |
| `allow_credentials` | `true` |
| `allow_methods` | `["*"]` |
| `allow_headers` | `["*"]` |

前端开发服务器 `apps/web/vite.config.ts` 将 `/api`、`/ws`、`/health` 代理到 `http://localhost:8000`，因此本地开发通常不依赖 CORS；生产分离部署时需要正确设置 `CORS_ORIGINS`。

### 7.6 环境变量

后端 `apps/api/core/config.py` 从 `apps/api/.env` 读取（路径相对于代码文件，不依赖启动目录），使用 `pydantic-settings`，未知变量忽略。

| 变量 | 默认值 | 用途 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 空字符串 | DeepSeek API Key；为空时 `/health` 仍 200，但 `llm_configured=false`，调用 LLM 的接口报错 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | OpenAI 兼容 API 基地址 |
| `DEEPSEEK_MODEL` | `deepseek-flash` | 模型名 |
| `MAX_CONCURRENCY` | `5` | 单会话并发处理简历数（信号量） |
| `MAX_LLM_RETRIES` | `3` | LLM 重试次数 |
| `LLM_RETRY_MIN_WAIT` | `1.0` | 重试最小等待秒数 |
| `LLM_RETRY_MAX_WAIT` | `10.0` | 重试最大等待秒数 |
| `LLM_TIMEOUT_SECONDS` | `120.0` | 单次 LLM 请求超时 |
| `CACHE_DIR` | `./cache` | JD/Schema/评估缓存目录；启动时创建 |
| `UPLOAD_DIR` | `./uploads` | 上传临时目录；启动时创建 |
| `SAVED_JOBS_FILE` | `./cache/saved_jobs.json` | 岗位档案 JSON 路径 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | 允许的前端源，逗号分隔 |

前端环境变量：

| 变量 | 代码中的实际使用 | 说明 |
|---|---|---|
| `VITE_API_BASE_URL` | `apps/web/src/api/client.ts:11` | Axios 基地址；为空时使用同源 + Vite 代理 |
| `VITE_WS_URL` | `apps/web/src/api/websocket.ts:8` | WebSocket 基地址；为空时按当前页面协议与 host 推导 |
| `VITE_API_URL` | **已移除** | 前端已统一为 `VITE_API_BASE_URL`；代码与 `apps/web/.env.example` 均已使用新名称 |

`.env` 已被根 `.gitignore` 忽略；本审计不复制、不输出任何密钥值。

### 7.7 启动配置

- 启动命令（`apps/api/README.md`）：

```powershell
cd apps/api
..\..\.venv\Scripts\python.exe -m uvicorn server.main:app --reload --port 8000
```

- FastAPI 元数据：`title="AI AFS"`、`version="1.0.0"`、描述为 “AI-powered Resume Filtering & Candidate Ranking System”。
- `lifespan` 启动时创建 `CACHE_DIR` 与 `UPLOAD_DIR`，记录结构化启动日志；退出时记录关闭日志。
- 默认开启 FastAPI `/docs`、`/redoc`、`/openapi.json`（未自定义关闭）。
- 单进程内存会话；`--reload` 或多 worker 会导致会话不共享、重启即丢失。
- 结构化日志使用 `structlog`，但未配置请求级 `X-Request-Id` 或审计日志。
- 没有 `Idempotency-Key`、`If-Match`、限流、请求体总大小限制、文件数量限制。

### 7.8 数据层与外部组件核查

| 组件 | 是否引入 | 证据 |
|---|---|---|
| SQLAlchemy 2.0 模型 | 否 | `requirements.txt` 无 SQLAlchemy；`apps/api` 无 ORM 模型文件 |
| Alembic 迁移 | 否 | `apps/api/alembic/versions` 为空；无 `alembic.ini`/`env.py` |
| PostgreSQL | 否 | 无驱动、无连接串、无迁移 |
| MinIO / S3 / boto3 | 否 | 无依赖、无存储适配器 |
| Redis / Celery | 否 | 无依赖、无任务队列 |
| 认证/JWT/密码哈希 | 否 | 无 `jwt`、`passlib`、`oauth`、`fastapi-users` 等实现 |
| 单元/集成测试 | 否 | `apps/api/tests` 为空 |
| 契约 JSON Schema | 否 | `packages/contracts` 为空；模型输出仅依赖 Pydantic + `response_format=json_object` |
| 当前持久化 | 本地 | 会话/结果为内存字典；JD/Schema/评估为 `diskcache`；岗位为 JSON 文件；文件为本地 `uploads/` |

---

## 8. 与正式设计的偏差清单

| 编号 | 项目 | 正式设计要求 | 当前实现 | 影响/状态 |
|---|---|---|---|---|
| D1 | API 前缀 | `/api/v1` | `/api/*`、`/health`、`/ws` | 所有正式客户端无法直接复用；需要兼容层或迁移 |
| D2 | 端点范围 | M1–M9 共 53 个 REST + 2 个 WS（详细设计 §4.2） | 11 个 REST + 1 个 WS | 认证、岗位 CRUD、候选人、证据、评估、语音、隐私、管理、集成均缺失 |
| D3 | 认证 | Bearer access/refresh，RBAC，租户隔离 | 无 | 不能公网部署；无审计 |
| D4 | 错误信封 | `{code,message,request_id,details}` + `TTC-xxxx` | `{"detail":...}`；422 为 FastAPI 数组 | 前端与监控无法稳定按错误码处理 |
| D5 | 分页 | 游标分页，默认 20、最大 100，`next_cursor` | 无分页 | 列表接口不可扩展 |
| D6 | ID | UUID v7 | `session_id`/`candidate_id` 为 UUID v4；`jd_id` 为 SHA-256；岗位用名称 | 与正式表结构、分页、索引策略不一致 |
| D7 | 时间 | RFC 3339 UTC `Z`，数据库 `timestamptz` | 仅岗位档案时间，`+00:00`；无数据库 | 格式不统一；大量资源无时间字段 |
| D8 | JSON Schema 契约 | `packages/contracts` + 服务端校验 + 契约测试 | 仅 Pydantic 模型 + LangChain `json_object` | 模型输出契约不可跨语言复用，无契约测试 |
| D9 | 上传类型 | PDF/DOCX/TXT | PDF/DOCX | TXT 被静默跳过 |
| D10 | 上传校验 | 扩展名 + MIME 嗅探一致性、损坏检测 | 扩展名或声明 MIME 任一命中；无嗅探/损坏预检 | 伪造扩展名可通过请求层，后续变成候选人 error |
| D11 | 上传错误码 | 413/415/422 + `TTC-300x` | 跳过；全无效时 400 通用文本 | 调用方无法区分“部分跳过”和“全部失败” |
| D12 | 上传返回 | 202 + `resume_id`/`task_id`/`checks` | 200 + `session_id`/`total_files`/`message` | 语义与状态码不一致 |
| D13 | 存储 | MinIO + PostgreSQL，会话/任务落库 | 本地磁盘 + 内存字典 | 重启丢失；多进程不可用 |
| D14 | 去重 | 按候选人 + sha256 持久化 | 同批次内 sha256 | 跨批次重复上传不会识别 |
| D15 | WS 路径与事件 | `/ws/progress/{task_id}`；`progress`/`done`/`error`；`percent`；`seq` 去重 | `/ws/{session_id}`；`progress`/`result`/`complete`；无 `percent`/`seq` | 正式前端无法直接接入 |
| D16 | WS 认证 | 已认证 | 无认证 | 任意 session 可监听 |
| D17 | 评分模型 | 双账本（证据账本/匹配账本），`weight_pct` 总和 100，`evidence_ids`/`source_claim_ids`，缺失证据时分数为 null | 单一 `fit_score` + 3 条解释 + `dimension_scores`；`max_points` 合计 100 | 与正式 M5 报告结构完全不一致 |
| D18 | 毕业年份筛选 | 总体设计 §4.4.1 明确“不搬”graduation_screening，MVP 不做自动过滤；仅 P2 显式岗位条件且人工确认 | 已实现自动筛选，输出 `filtered`/`review` | 存在合规与“隐性歧视”风险，需要产品决策 |
| D19 | 幂等/并发/追踪 | `Idempotency-Key`、`If-Match`、`X-Request-Id` | 均无 | 写接口重试可能重复创建；无法追踪请求 |
| D20 | 状态码 | POST 创建 201、异步 202 | 统一 200 | 客户端无法按语义区分 |
| D21 | OpenAPI 完整性 | 所有端点有请求/响应契约 | 结果、预览、删除、导出、健康检查无响应模型；预览/导出实际二进制却声明 JSON | 生成客户端不可用；契约测试无法覆盖 |
| D22 | 岗位档案 | PostgreSQL `job`/`job_version`，UUID v7，版本管理、发布、锁定 | 本地 JSON，按名称保存，无版本/状态机 | 无法支持正式岗位管理流程 |
| D23 | 测试 | 单元/契约/集成/前端/安全分层 | 无测试目录 | 回归风险高 |

### 8.1 实测补充发现：评分可复现性

- 同一份 PDF、同一已保存岗位评分 Schema，在两次独立会话中分别得到 **42** 和 **47**。这属于已观察到的真实结果，不是前端展示误差。
- 当前评估缓存键为 `eval:v2:{file_hash}:{jd_hash}`，未包含评分 Schema 哈希；如果 Schema 变化，理论上可能复用旧评分。
- 建议后端负责人确认：
  1. 缓存键是否应加入评分 Schema 哈希（或整个评分请求的哈希）；
  2. DeepSeek `temperature=0` 是否仍存在供应商侧结果波动；
  3. 前端是否应继续将分数标注为“岗位适配参考分”，而不是绝对结论（当前前端已这样标注）。

---

## 9. 待后端负责人确认

以下事项无法从当前代码、分支、PR 或提交历史确认，**不得自行假设**：

1. `apps/api/src/ttc/`、`apps/api/alembic/versions/`、`apps/api/tests/` 的空目录是否为后端同事预留的骨架？是否有尚未推送的本地分支或未提交代码？
2. 正式 `/api/v1` 的实现计划、负责人、时间表；是否会保留当前 `/api/*` 作为兼容层？
3. 正式 `/api/v1` 端点的最终请求/响应 Schema 是否完全采用详细设计 §4.3 的示例，还是会有调整？
4. 是否引入 SQLAlchemy 2.0、Alembic、PostgreSQL 16、MinIO；迁移策略与现有本地 JSON/内存数据如何迁移？
5. 是否实现 Bearer + refresh token、RBAC、租户隔离；`tenant_id` 的来源与默认值如何处理？
6. 是否统一采用 `{code,message,request_id,details}` 错误信封与 `TTC-xxxx` 错误码；现有前端 `detail` 解析何时切换？
7. 是否采用 UUID v7；`jd_id`（SHA-256）如何映射到正式 `job_version.id`；岗位档案名称键如何迁移到 `job.id`？
8. 是否统一 RFC 3339 `Z` 时间格式；哪些资源需要新增 `created_at`/`updated_at`/`updated_at` 版本字段？
9. 游标分页的 `cursor` 编码、默认 20/最大 100 的校验位置，以及前端列表如何适配 `next_cursor`？
10. WebSocket 最终采用 `/ws/progress/{task_id}` 还是保留 `/ws/{session_id}`；事件名是否改为 `progress`/`done`/`error`；是否增加 `seq`、`percent`、认证和持久化补发？
11. `complete` 事件是否正式包含 `skipped` 字段？当前 Pydantic 模型与运行时不一致，应以哪边为准？
12. 文件上传最终允许类型是否包含 TXT；MIME 嗅探、损坏检测、413/415/422 错误码是否按详细设计落地；部分文件被跳过时是否需要结构化返回？
13. 毕业年份自动筛选是否保留？总体设计明确不搬，但当前实现已启用；需要产品/合规确认。
14. 评分 Schema 是否从 `max_points` 改为 `weight_pct`，以及是否需要双账本、`evidence_ids`、`source_claim_ids`、缺失证据时分数为 null。
15. 前端生产部署时的实际 API/WS 地址与 CORS 白名单；当前前端已统一使用 `VITE_API_BASE_URL` / `VITE_WS_URL`，需后端确认部署域名。
16. 当前未使用的组件 `ProgressDashboard.tsx`、`ResultsTable.tsx`、`ExportButton.tsx` 是否保留；如保留，是否也需要跟随正式契约改造。
17. 当前 `POST /api/resumes/process` 返回 200 且异步执行，正式是否改为 202 + `task_id`；前端轮询/WS 的会话标识如何映射到 `task_id`。

---

## 10. 正式设计 `/api/v1` 端点基线（未实现，来源：详细设计 §4.2）

以下路径逐条摘自详细设计说明书 §4.2，**不是对后端计划的推测**。除特别标注的 WS 外，均以 `/api/v1` 为前缀。当前实现数量为 0，全部标记为未实现；最终是否按此实现 `待后端负责人确认`。

| 模块 | 正式设计端点 | 当前状态 |
|---|---|---|
| M1 身份与租户 | `POST /auth/login`；`POST /auth/refresh`；`POST /auth/logout`；`GET /me` | 未实现 |
| M2 岗位画像 | `GET /jobs`；`POST /jobs`；`GET /jobs/{id}`；`PATCH /jobs/{id}`；`DELETE /jobs/{id}`；`POST /jobs/{id}/jd/generate`；`POST /jobs/{id}/jd/extract`；`GET /jobs/{id}/jd/versions`；`POST /jobs/{id}/jd/versions/{vid}/select`；`POST /jobs/{id}/publish`；`GET /jobs/{id}/stats`；`GET /weight-plans/templates`；`PUT /jobs/{id}/weight-plan`；`GET /jobs/{id}/interview-plans` | 未实现 |
| M3 简历解析 | `POST /candidates`；`GET /candidates`；`GET /candidates/{id}`；`POST /resumes`；`GET /resumes/{id}`；`GET /resumes/{id}/claims`；`GET /resumes/{id}/timeline`；`POST /resumes/{id}/reparse`；`DELETE /resumes/{id}` | 未实现 |
| M4 实体与证据 | `POST /candidates/{id}/evidence-search`；`GET /candidates/{id}/evidence`；`GET /evidence/{id}`；`POST /evidence/{id}/confirm` | 未实现 |
| M5 评估与报告 | `POST /candidates/{id}/assessments`；`GET /assessments/{id}`；`PATCH /assessments/{id}`；`GET /assessments/{id}/export` | 未实现 |
| M6 语音会话 | `POST /consents`；`POST /consents/{id}/revoke`；`POST /voice-sessions`；`GET /voice-sessions/{id}`；`POST /realtime/mint`；`POST /voice-sessions/{id}/turns`；`POST /voice-sessions/{id}/finish` | 未实现 |
| M7 通话分析 | `GET /voice-sessions/{id}/report` | 未实现 |
| M8 治理合规 | `POST /privacy/requests`；`GET /privacy/requests/{id}`；`GET /admin/data-sources`；`PATCH /admin/data-sources/{id}`；`GET /admin/audit-logs`；`GET /admin/metrics` | 未实现 |
| M9 任务、通知与集成 | `POST /integrations/openats/sync`；`GET /integrations/openats/status`；`POST /integrations/vekt/rebuild`；`GET /integrations/status` | 未实现 |
| WS 实时 | `WS /ws/progress/{task_id}`；`WS /ws/voice/{session_id}`（均不在 `/api/v1` 下） | 未实现 |

正式设计的关键报文示例见详细设计 §4.3（创建岗位、JD 生成、JD 识别、上传简历、claims、证据检索、评估、语音会话、mint、finish、通话报告、隐私申请）。在后台负责人确认前，前端不应调用上述 `/api/v1` 路径。

---

## 11. 前端调用位置汇总

### 11.1 API 模块到端点

| 前端模块 | 函数 | 端点 | 主要消费方 |
|---|---|---|---|
| `apps/web/src/api/client.ts` | `getHealth()` | `GET /health` | `components/layout/AppLayout.tsx:60`；`pages/WorkbenchHome.tsx:57` |
| `apps/web/src/api/jobs.ts` | `parseJD()` | `POST /api/jobs/parse` | `components/JobDescriptionForm.tsx:109`（`JobCreatePage.tsx` 渲染） |
| `apps/web/src/api/jobs.ts` | `listSavedJobs()` | `GET /api/jobs/saved` | `JobDescriptionForm.tsx:70`；`JobListPage.tsx:11`；`WorkbenchHome.tsx:53`；`CandidatesPage.tsx:52` |
| `apps/web/src/api/jobs.ts` | `getSavedJob()` | `GET /api/jobs/saved/{name}` | `JobDescriptionForm.tsx:124`；`JobDetailPage.tsx:34`；`CandidatesPage.tsx:57`；`CandidateProfile.tsx:79` |
| `apps/web/src/api/jobs.ts` | `saveJobProfile()` | `POST /api/jobs/saved` | `JobDescriptionForm.tsx:175` |
| `apps/web/src/api/resumes.ts` | `processResumes()` | `POST /api/resumes/process` | `ResumeUpload.tsx:91`（`CandidatesPage.tsx:331` 渲染） |
| `apps/web/src/api/resumes.ts` | `getResumePreviewUrl()` | `GET /api/resumes/preview-file/{session_id}/{candidate_id}` | `CandidateResults.tsx:385`；`CandidateProfile.tsx:214`；`ResultsTable.tsx:337`（组件未使用） |
| `apps/web/src/api/resumes.ts` | `closeResumeSession()` | `DELETE /api/resumes/session/{session_id}` | `CandidatesPage.tsx:118,153,167` |
| `apps/web/src/api/candidates.ts` | `getSessionResults()` | `GET /api/resumes/results/{session_id}` | `ProcessingPanel.tsx`（轮询与完成拉取）；`CandidatesPage.tsx:86` |
| `apps/web/src/api/candidates.ts` | `getCandidateDetail()` | `GET /api/resumes/detail/{session_id}/{candidate_id}` | `CandidateProfile.tsx:73`（`CandidateDetailPage.tsx`、`CandidateReportPage.tsx` 渲染） |
| `apps/web/src/api/reports.ts` | `getExportUrl()` | `GET /api/export/{session_id}` | `CandidateResults.tsx:147`；`CandidateProfile.tsx:203`；`ExportButton.tsx:16`（组件未使用） |
| `apps/web/src/api/websocket.ts` | `createWebSocket()` | `WS /ws/{session_id}` | `ProcessingPanel.tsx:255`；`ProgressDashboard.tsx:70`（组件未使用） |

### 11.2 前端环境与代理

- `apps/web/vite.config.ts` 将 `/api`、`/ws`、`/health` 代理到 `http://localhost:8000`；WS 使用 `ws://localhost:8000`。
- `apps/web/src/api/client.ts` 使用 `VITE_API_BASE_URL`；`websocket.ts` 使用 `VITE_WS_URL`。
- `apps/web/.env.example` 已统一为 `VITE_API_BASE_URL` 与 `VITE_WS_URL`；代码读取的变量与模板一致。
- Axios 超时 120 秒，与 `LLM_TIMEOUT_SECONDS=120` 相同；长耗时 JD 解析或评分可能正好触及超时边界。
- 前端错误解析依赖 `detail` 字符串/数组（`apps/web/src/lib/apiError.ts`），与当前后端格式匹配，但与正式 `{code,...}` 不匹配。

### 11.3 未使用的组件

以下组件在当前 `apps/web/src` 中没有被页面或其他组件引用（仅文件自身定义）：

- `apps/web/src/components/ProgressDashboard.tsx`
- `apps/web/src/components/ResultsTable.tsx`
- `apps/web/src/components/ExportButton.tsx`

它们仍包含旧端点调用或旧 WS 处理逻辑；如后续启用，需要同步改造。

### 11.4 Vue `frontend/`

`frontend/src` 未发现任何 `/api`、`/ws`、`axios`、`fetch` 或 `WebSocket` 调用（grep 无结果）。当前实际联调前端是 `apps/web`（React 18 + Vite + TypeScript + Tailwind）。

---

## 12. 附录：审计命令与运行时快照

```bash
git branch -a
git log --all --oneline --decorate
git ls-remote --heads origin          # 失败：无法连接 github.com:443
gh pr list                            # 失败：gh: command not found
git rev-parse HEAD                    # 60dcea6feb0cde93fdb53d9cbbe0665407985d21
git status --short                    # .gitignore 修改；apps/ 未跟踪

curl -s http://127.0.0.1:8000/openapi.json
curl -s http://127.0.0.1:8000/health
```

实测 OpenAPI 路径：

```text
POST   /api/jobs/parse
GET    /api/jobs/saved
POST   /api/jobs/saved
GET    /api/jobs/saved/{name}
POST   /api/resumes/process
GET    /api/resumes/results/{session_id}
GET    /api/resumes/detail/{session_id}/{candidate_id}
GET    /api/resumes/preview-file/{session_id}/{candidate_id}
DELETE /api/resumes/session/{session_id}
GET    /api/export/{session_id}
GET    /health
```

WebSocket（不在 OpenAPI 中）：

```text
WS /ws/{session_id}
```

实测健康检查响应：

```json
{"status":"ok","app":"AI AFS","provider":"deepseek","model":"deepseek-flash","llm_configured":true}
```

---

*本文件是只读审计产物。除本文件外，未修改 `apps/api`、`apps/web`、`frontend/` 或任何后端代码；未执行 `git fetch`、checkout、commit 或 push。*
