# TTC 招聘前端

先配置 `apps/api/.env`，执行数据库迁移并启动 API 与解析 worker。使用已有的 HR/管理员租户账号登录；密钥不应提交到 Git。

```bash
cd apps/api
uv run alembic upgrade head
env -u ALL_PROXY -u all_proxy uv run uvicorn ttc.main:app --app-dir src --host 127.0.0.1 --port 8001
# 在另一终端：cd apps/api && env -u ALL_PROXY -u all_proxy uv run python -m ttc.tasks.runner
cd ../../frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

访问 `http://127.0.0.1:5173/login`，输入租户 slug、邮箱和密码。Vite 默认将 `/api/*` 代理到 `http://127.0.0.1:8001`；如后端地址不同，启动前设置 `VITE_API_PROXY_TARGET=http://127.0.0.1:8000`。浏览器仅请求同源 `/api/v1`，不会接触 LLM 凭证。

上述 `env -u` 仅针对本开发机的 `ALL_PROXY=socks://…`（httpx 不接受该 URI scheme）；其他环境若不含此设置可直接启动。若需使用 SOCKS5，请配置标准 `socks5://` 地址。

登录、岗位列表/创建/编辑/JD 版本与 AI 生成、合成候选人列表/创建/简历上传及解析结果均请求真实接口。其他导航页仍是占位模块，候选人页面不显示虚构的评分或简历字段。

`npm run build` 进行类型检查与生产构建。生产部署需另外配置 `/api/*` 反向代理；开发代理不适用于生产。
