# AI-recruitment

TTC（才多对）AI 招聘与人才挖掘平台。

- `frontend/`：前端项目；启动方式见 `frontend/README.md`。
- `apps/api/`：FastAPI 后端、PostgreSQL 16 数据库迁移、异步 worker、Docker Compose；安装、配置和接口说明见 `apps/api/README.md`。

后端先按 `apps/api/.env.example` 创建自己的 `apps/api/.env`，配置数据库、加密密钥等，再按后端 README 执行迁移并启动。**不要提交 `.env`、真实简历或真实候选人通话。**

当前后端包含简历解析、证据与评估、语音会话、授权和隐私接口。OpenATS/Vekt 外部对接、语音自动转写与模型通话评估尚未交付；请勿将未配置的接口视为已联通。
