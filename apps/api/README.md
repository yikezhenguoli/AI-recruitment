# TTC AI Recruitment API

本目录的后端代码复用自开源项目 **AI AFS — AI-Powered Resume Filtering & Candidate Ranking System**。

## 来源与许可

- 原始项目：AI AFS
- 原始版权：Copyright (c) 2026 Pavan Tanneru
- 许可证：MIT License，完整文本见同目录 `LICENSE`
- 本仓库仅将其 FastAPI 后端接入 TTC 项目，前端仍为 `frontend/` 下的 Vue 3 应用，未复制原 React 前端。

## 能力范围

- 岗位描述（JD）解析与结构化
- 评分 Schema 动态生成（维度权重合计 100）
- PDF / DOCX 简历解析（扫描 PDF 可选 OCR 回退）
- LangGraph 简历处理流水线：解析 → LLM 提取 → 筛选 → 逐维度评分
- 并发处理、重复文件识别
- WebSocket 实时进度
- 排名结果查询、PDF 原文预览
- Excel 排名导出
- 命名岗位档案保存/读取（本地 JSON）

## LLM 供应商：DeepSeek

服务端使用 LangChain `ChatOpenAI`（OpenAI-compatible SDK）调用 DeepSeek 官方 API。

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 空 | 必填；仅后端读取，禁止进入前端或 Git |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | 官方 OpenAI-compatible 地址 |
| `DEEPSEEK_MODEL` | `deepseek-flash` | 可通过环境变量切换为 `deepseek-v4-pro` |
| `LLM_TIMEOUT_SECONDS` | `120` | 单次模型请求超时（秒） |

配置读取位置：

- `core/config.py` — `Settings` 从 `apps/api/.env` 读取，不受启动目录影响。
- `agents/llm_client.py` — 唯一构造 `ChatOpenAI` 的位置。
- `server/main.py` — `/health` 返回当前 `provider/model/llm_configured`。

未配置 `DEEPSEEK_API_KEY` 时：

- `/health` 仍返回 200，但 `llm_configured` 为 `false`。
- 调用真实 LLM 的接口会返回明确错误：`DEEPSEEK_API_KEY is not configured. Set DEEPSEEK_API_KEY in apps/api/.env and retry.`
- 不会发起任何伪造的 AI 结果。

## 环境要求

- Python 3.12
- 项目根目录 `.venv` 或独立虚拟环境
- 可访问的 DeepSeek API

## 安装

在仓库根目录执行：

```powershell
.\.venv\Scripts\pip.exe install -r apps\api\requirements.txt
```

## 配置

在 `apps/api` 目录执行：

```powershell
Copy-Item .env.example .env
```

编辑 `.env`：

```env
DEEPSEEK_API_KEY=你的真实密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
```

> `.env` 已被根 `.gitignore` 忽略，禁止提交真实密钥。
> 如果 `.env` 已存在，请保留并只补充/修改 DeepSeek 变量，不要覆盖其他本地配置。

## 启动

在 `apps/api` 目录下：

```powershell
..\..\.venv\Scripts\python.exe -m uvicorn server.main:app --reload --port 8000
```

健康检查：

```powershell
curl http://127.0.0.1:8000/health
```

预期返回（未配置 Key 时 `llm_configured` 为 `false`）：

```json
{
  "status": "ok",
  "app": "AI AFS",
  "provider": "deepseek",
  "model": "deepseek-flash",
  "llm_configured": true
}
```

## DeepSeek 连通性测试

独立脚本：

```powershell
# 基础连通性 + JSON 输出验证
..\..\.venv\Scripts\python.exe scripts\test_deepseek.py

# 额外验证 JD 解析、评分 Schema 生成和评分模块的模型调用
..\..\.venv\Scripts\python.exe scripts\test_deepseek.py --full
```

脚本会：

1. 检查 `DEEPSEEK_API_KEY` 是否存在；缺失时以退出码 2 结束并给出明确提示。
2. 使用与生产相同的 `ChatOpenAI` 配置发起一次真实请求。
3. 要求并解析 JSON 输出。
4. `--full` 时调用真实 JD 解析、Schema 生成和评分链。
5. 不打印、不写入 API Key。

## 模型输出与 JSON 模式

- `agents/llm_client.py` 使用 `model_kwargs={"response_format": {"type": "json_object"}}`。
- 所有 Prompt（`prompts/*.yaml`）均明确要求只返回 JSON。
- 保持原有 Pydantic 数据结构和评分 Schema 不变。
- JSON 解析失败、空响应、超时、API 错误会由现有异常处理链向上抛出，路由返回 500 与具体错误信息。

## 主要接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/jobs/parse` | JD 解析 |
| POST | `/api/resumes/process` | 上传简历并启动流水线 |
| GET | `/api/resumes/results/{session_id}` | 查询结果（含逐维度分数 `dimension_scores`） |
| GET | `/api/resumes/detail/{session_id}/{candidate_id}` | 只读详情：候选人结果 + 完整 `resume_structured` |
| GET | `/api/resumes/preview-file/{session_id}/{candidate_id}` | PDF 预览 |
| DELETE | `/api/resumes/session/{session_id}` | 关闭会话 |
| GET | `/api/export/{session_id}` | Excel 导出 |
| WS | `/ws/{session_id}` | 实时进度 |

## 运行数据

- `cache/`：JD/评分 Schema/评估结果缓存，以及保存的岗位档案。
- `uploads/`：临时上传文件。
- 两者均已被 `.gitignore` 忽略。
- 会话状态保存在进程内存中；后端重启后旧 session 失效。

## 可选 OCR 依赖

扫描版 PDF 需要系统安装：

- Tesseract OCR
- Poppler（`pdftoppm`）

未安装时，文本型 PDF 与 DOCX 仍可正常处理。

## 未引入的组件

为保持 MVP 简单，本目录**未引入** PostgreSQL、Redis、MinIO、Celery 等组件。
