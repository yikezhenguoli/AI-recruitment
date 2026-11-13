# TTC HR Workbench (`apps/web`)

正式《详细设计说明书》规定的 HR 工作台：

- React 18 + TypeScript + Vite + Tailwind CSS
- 服务端状态：TanStack Query
- 本地状态：Zustand
- 不使用 Element Plus
- 候选人端为独立 `apps/candidate`（Next.js 15，当前仅预留）

## 运行环境

- Node 22.x LTS（正式文档要求 Node 20 LTS / 22）
- 当前机器默认 Node 为 26，本项目使用便携版 Node 22，不修改系统 PATH：
  `C:\Users\yikez\.local\node22\node-v22.23.5-win-x64`
- 后端：`apps/api`（FastAPI + DeepSeek）

## 安装与启动

```powershell
cd apps\web
npm install
npm run dev
```

默认地址：`http://localhost:5173/`

Vite 开发代理：

- `/api` → `http://localhost:8000`
- `/ws` → `ws://localhost:8000`
- `/health` → `http://localhost:8000`

如需独立部署，复制 `.env.example` 为 `.env` 并设置 `VITE_API_BASE_URL` / `VITE_WS_URL`。

## 构建

```powershell
npm run build
```

产物目录：`apps/web/dist/`

## 后端启动

```powershell
cd apps\api
..\..\.venv\Scripts\python.exe -m uvicorn server.main:app --reload --port 8000
```

未配置 `DEEPSEEK_API_KEY` 时，`/health` 仍可用，但 AI 解析接口会返回明确错误，不会生成假数据。

## 当前路由

| 路径 | 状态 |
|---|---|
| `/` | 已实现：HR 工作台首页 |
| `/jobs` | 已实现：已保存岗位列表 |
| `/jobs/new` | 已实现：JD 输入、AI 解析、评分维度编辑、保存岗位 |
| `/jobs/:id` | 已实现：岗位结构化信息、评分维度、原始 JD |
| `/jobs/:id/edit` | 占位：下一阶段 |
| `/candidates` | 已实现：岗位选择、PDF/DOCX 批量上传、WebSocket 进度、AI 排名与 Excel 导出 |
| `/candidates/:id` | 已实现：真实结构化简历、逐维度评分、优势/风险、联系方式脱敏 |
| `/candidates/:id/evidence` | 占位：M4 外部证据核验尚未接入 |
| `/candidates/:id/report` | 已实现：真实评分报告、维度依据、风险与待核实、导出入口 |
| `/sessions` | 已实现：本地麦克风波形预览（M6 后端未接入） |
| `/sessions/:id` | 占位：M6/M7 范围 |
| `/admin` | 占位：M1/M8 范围 |

本地麦克风预览：`/sessions` 仅在用户点击“开启麦克风”后请求权限，使用 Web Audio `AnalyserNode` 在浏览器本地绘制真实输入波形；音频不录音、不上传、不保存。真正的语音面试、实时转写与通话分析属于 M6/M7，后端尚未接入。

本轮不使用 `/screening` 或 `/dashboard` 作为正式主路由。

## API 现状

当前前端调用实际存在的 AI AFS 接口：

- `POST /api/jobs/parse`
- `GET /api/jobs/saved`
- `GET /api/jobs/saved/{name}`
- `POST /api/jobs/saved`
- `POST /api/resumes/process`
- `GET /api/resumes/results/{session_id}`
- `GET /api/resumes/detail/{session_id}/{candidate_id}`
- `GET /api/resumes/preview-file/{session_id}/{candidate_id}`
- `DELETE /api/resumes/session/{session_id}`
- `GET /api/export/{session_id}`
- `WS /ws/{session_id}`

API Service 已按业务拆分：

- `src/api/client.ts`：Axios 实例、Base URL、健康检查
- `src/api/jobs.ts`：岗位解析、列表、详情、保存
- `src/api/resumes.ts`：上传、关闭会话、PDF 预览 URL
- `src/api/candidates.ts`：会话结果、候选人详情
- `src/api/reports.ts`：Excel 导出 URL
- `src/api/websocket.ts`：WebSocket 连接工厂

**与正式详细设计的差异：** 正式契约为 `/api/v1/*`，当前后端尚未提供兼容层。
本版本使用上述 API Service 作为统一适配层，不声称已经完全符合 `/api/v1`。
完整映射、错误格式、分页、ID/时间、WS 协议与偏差见 `docs/API_CONTRACT.md`。

## 说明

- `frontend/` 的 Vue 3 项目已冻结，仅作为历史参考，不再扩展。
- 页面不会用演示数据冒充真实 AI 结果；未接入的模块显示“下一阶段接入”。
- API Key 仅在 `apps/api/.env` 中读取，不进入前端、README 或 Git。
