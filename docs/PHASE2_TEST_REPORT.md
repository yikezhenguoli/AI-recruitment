# TTC Phase 2 — 候选人筛选与前后端联调测试报告

> 日期：2026-11-14
> 测试环境：Windows 11 / Node 22.23.5（便携版，未替换系统 Node 26）/ Vite 6.4.6 / FastAPI（DeepSeek `deepseek-flash`）/ 本机真实浏览器 Chrome
> 说明：本报告记录实际执行结果。语音波形子任务与最新 UI 修正已完成并补录最终构建/回归。未通过的测试不会标为通过。

## 1. 测试材料与边界

| 项目 | 内容 |
|---|---|
| 真实 PDF | `E:\Wechat chatting record\xwechat_files\wxid_p2urczelzhen22_2fad\msg\file\2026-11\姚霖锋-AI应用开发实习简历.pdf` |
| 真实 DOCX | `E:\Wechat chatting record\xwechat_files\wxid_p2urczelzhen22_2fad\msg\file\2026-11\何行健 251240251.docx` |
| 岗位 | `前端开发工程师（联调测试）`，真实 DeepSeek 解析生成 6 个评分维度，合计 100 分 |
| 数据边界 | 未把测试简历复制进仓库；后端上传/缓存目录已被 Git 忽略；详情与报告默认脱敏联系方式 |
| API 契约 | 当前为 AI AFS 兼容 `/api/*`；正式 `/api/v1` 未实现，详见 `docs/API_CONTRACT.md` |

## 2. 构建与静态检查

| 测试 | 结果 |
|---|---|
| `npm run build`（Node 22，最终） | 通过：`tsc` 无错误；Vite 1715 modules；CSS 81.99 KB（gzip 16.12 KB）；JS 395.79 KB（gzip 122.49 KB）；2.40s |
| TypeScript | 通过（`tsc` 包含在 build 中） |
| 控制台错误（核心页面） | 0（Playwright 捕获） |
| 横向溢出 390 / 768 / 1024 / 1440 | 0（候选流程与详情/报告；表格使用内部横向滚动） |

> 注：最终构建包含语音波形、API 模块拆分、姓名/头像/隐私/优势风险等最新修正。

## 3. DeepSeek 真实调用

| 测试 | 结果 |
|---|---|
| 基础连通性 + JSON 输出 | 通过：`{"status":"ok","provider":"deepseek"}` |
| JD 解析 | 通过：`AI Backend Engineer` |
| 评分 Schema 生成 | 通过：5 个维度，合计 100 |
| 评分链 | 通过：返回 5 个维度分数 |

## 4. 候选人筛选端到端（真实 PDF + DOCX）

| 步骤 | 实际结果 |
|---|---|
| 选择岗位 | `/candidates?job=前端开发工程师（联调测试）` |
| 上传 2 份简历 | PDF 174 KB + DOCX 795 KB，均进入待处理队列 |
| 不支持文件校验 | 上传 README.md 被拒绝，提示“仅支持 PDF / DOCX” |
| 启动处理 | `POST /api/resumes/process` 返回 session_id |
| WebSocket | 页面显示“实时连接中”，阶段事件驱动进度 |
| AI 解析与评分 | 2 份简历完成；排名：姚霖锋 42，何行健 17 |
| 结果页 | 2 行真实结果；搜索“姚霖锋”命中 1 行；已排名筛选 2 行；排序分数在 17/42 间切换 |
| 维度评分 | 展开行显示 6 个维度、分数、满分与理由 |
| 候选人详情 | 姚霖锋：真实结构化简历、教育/工作/项目；逐维度评分；相对优势/风险；联系方式默认脱敏；原始电话/邮箱未泄露 |
| 评估报告 | 显示岗位适配参考分、逐维度评分、评分依据、风险与待核实、人工复核声明、结构化简历 |
| Excel 导出 | 下载成功，文件名 `ai_afs_*.xlsx`，大小 10,264 bytes（最终回归） |
| 页面刷新恢复 | 刷新后通过 session store + 真实结果接口恢复 2 行 |
| 移动端 390 | 无横向溢出；页面可用 |
| 控制台错误 | 0 |

## 5. WebSocket 断线与重连

| 测试 | 结果 |
|---|---|
| 正常连接 | “实时连接中”；进度来自真实 `progress` / `result` / `complete` 事件 |
| 强制关闭 WS（Playwright `routeWebSocket` 每次 close） | 页面显示“连接中断，正在重连”；后端真实结果轮询仍完成，结果页 1 行；无控制台错误 |
| 页面刷新 | 重新建立会话结果恢复；处理中会话会重新连接/轮询 |
| 资源清理 | 组件卸载关闭 WS、清除定时器；无重复订阅（实现检查） |

## 5.1 语音会话波形（本地麦克风预览）

| 测试 | 结果 |
|---|---|
| 页面 | `/sessions` 已从占位页替换为本地麦克风预览页 |
| 自动请求麦克风 | 否；加载时 `getUserMedia` 调用数为 0，点击“开启麦克风”后才请求 |
| 真实波形 | `AudioContext` + `AnalyserNode` + `requestAnimationFrame`；Canvas 实时变化 |
| 停止与清理 | 停止后释放音轨、关闭 AudioContext；页面卸载后再次释放；可重新开启 |
| 重复流 | 状态/ref 守卫阻止重复获取 |
| 权限拒绝 / 无设备 / 不支持 | 均有明确中文状态与重试路径 |
| `prefers-reduced-motion` | 静态波形，像素在 800ms 内不变，无 rAF/analyser 调用 |
| 页面隐藏 | 暂停绘制，恢复可见后继续 |
| 移动端 390 | 无横向溢出；无控制台错误 |
| 真实性 | 明确标注“M6 语音面试后端尚未接入 · 当前仅展示本地麦克风波形”；无伪造转写/面试评价 |

> Headless 验证使用 Chrome 假麦克风与测试 WAV；真实设备/真实语音尚未测试。真正的 M6/M7 语音后端、实时转写和通话分析未接入。

## 6. 异常与边界测试

| 测试 | 实际结果 |
|---|---|
| 仅不支持文件 | 后端 400 `{"detail":"No valid resume files could be processed"}` |
| 部分解析失败 | 1 份 PDF 完成（score 47，6 维度）+ 1 份 corrupt.pdf 失败（`No /Root object! - Is this really a PDF?`）；导出 200，8,863 bytes |
| 重复上传（同批次同文件） | 1 份完成（score 47，6 维度）+ 1 份 `skipped`（Duplicate）；导出 200，9,138 bytes |
| 未授权请求 | 当前后端无鉴权，`GET /api/jobs/saved` 无 Token 返回 200；无法验证 401/403，标记为后端缺口 |
| 空结果/无有效文件 | 400，前端在未启动处理前也阻止空提交 |
| DeepSeek 超时 | 未执行真实超时故障注入；代码已配置 120s 超时 + tenacity 重试，需后端联调时补测 |
| 后端重启/多 worker | 未测试；当前会话在内存中，重启会丢失，属于已知缺口 |

## 7. 已观察到的评分可复现性问题

- 同一 PDF、同一已保存岗位 Schema，在两次独立会话中分别得到 **42** 和 **47**。
- 当前评估缓存键为 `eval:v2:{file_hash}:{jd_hash}`，未包含评分 Schema 哈希。
- 建议后端负责人确认缓存键与模型可复现性；前端继续将分数标注为“岗位适配参考分”，不作为绝对结论。

## 8. API 审计结果

详见 `docs/API_CONTRACT.md`。关键结论：

- 当前实际实现为 AI AFS 兼容 `/api/*`：11 个 REST + 1 个 WS，无 `/api/v1`。
- 未发现后端同事分支/PR/代码；远程查询失败且 `gh` 未安装，无法排除未推送代码。
- 无 PostgreSQL / SQLAlchemy 模型 / Alembic 迁移 / MinIO / Redis / 认证/RBAC；会话与结果在进程内存。
- 无游标分页、UUID v7、RFC 3339 `Z`、统一 `{code,...}` 错误信封；WS 事件名为 `progress`/`result`/`complete`。
- 23 项偏差、17 项待后端负责人确认；未凭空编造 `/api/v1` 接口。

## 9. 尚未完成/需确认

1. 正式 `/api/v1` 契约与后端同事实现确认。
2. 后端鉴权、RBAC、租户隔离、PostgreSQL/Alembic/MinIO。
3. 后端持久化（当前重启丢会话）。
4. DeepSeek 超时/供应商错误的真实故障注入测试。
5. 语音面试真实后端接入（当前仅本地麦克风波形预览）。
6. 视觉设计改版（只读审查已完成，等待项目负责人批准后实施）。
7. 真实设备麦克风 / 真实语音后端未测试。

## 10. 截图

目录：`C:\Users\yikez\Desktop\TTC-React-Screenshots\`

- `stage2-upload.png`
- `stage2-processing.png`
- `stage2-results.png`
- `stage2-results-expanded.png`
- `stage2-detail.png`
- `stage2-report.png`
- `stage2-results-mobile.png`
- `stage2-ws-fallback.png`
