# 项目长期记忆

## 目录与项目边界（重要）

- 本工作区 `AI-recruitment/dataset/`：**AI 简历深度追问数据集构建系统**（5000 份简历目标，
  当前仅 100 份试验数据，停在第三阶段人工验收前）。纯标准库、固定种子 20261114。
- 上级目录 `AI-recruitment/RISM/` 曾为 RISM-001，现被拆为：
  - `RISMv1/` = **冻结的 RISM-001 基线，全程只读**（35 文件，SHA-256 指纹记录在
    `RISMv2/outputs/rism002/rism001_baseline_manifest.json`）。
  - `RISMv2/` = **RISM-002 开发根**（含 RISM-001 原有 35 文件的副本，同样不修改）。
- 两个项目共享数据但用途不同：RISM-001 用 4 份 JSONL 训练 15 维多标签 MLP；
  RISM-002 只读这些数据构建 Claim / Evidence Gap / 追问方向 / Strategy 体系。
  **不要把 RISM-002 的产物写回 `dataset/` 或 `RISMv1/`。**

## 环境与依赖约定

- 系统 `python3` = 3.13，**无 numpy / pandas / PyYAML / torch**；
  `AI-recruitment/.venv/bin/python` = 3.12，含 torch / transformers / sentence-transformers（RISM-001 用）。
- 两个新项目都选**纯 Python 标准库**：配置用 JSON（`dataset/` 项目用自研 YAML 子集解析器），
  `.npy/.npz` 只读文件头不加载数组。这样系统 python3 即可跑全部新脚本，且不触碰模型栈。
- 禁止项（两个项目共同）：不训练模型、不生成新 Embedding、不调用外部 LLM/付费 API、
  不修改 RISM-001 权重 / 标签矩阵 / 划分文件。

## RISM-001 关键事实（供后续查阅）

- 15 个一级维度权威顺序：`embeddings/metadata.json["label_names"]`，**字母序**。
- 数据规模：100 简历 / 742 经历 / 1035 问题 / 300 追问链 / 471 多标签样本。
- Embedding `(471,512)×2` → concat 1024 → MLP `1024→128→15`，`BCEWithLogitsLoss` + `pos_weight`；
  划分 seed=42，按 `resume_id` 70/15/15（321/75/75），避免简历泄漏。
- 742 段经历中 **271 段从未被提问**：这是「未出现方向不能自动判 Negative」的现实依据。
- 已知缺陷 10 项，详见 `RISMv2/outputs/rism002/01_project_audit.md` §5；本次未修复（禁令）。

## 数据集合规设计原则（两个项目共通）

- **原文可追溯是硬门槛**：Claim `source_text` / 问题 `reference.original_text` 必须是经历
  `original_content` 的真实子串，字符偏移真实计算，不得编造、不得跨经历混合。
- **审核状态与标签状态严格分离**：`pending/approved/rejected` ≠ `positive/negative/unknown`；
  未审核记录不得进正式数据集；未出现方向保持 `unknown`，`negative` 只能由人工显式给出。
- AI / 规则 / 历史问题生成的内容一律为「候选」，不得自动标记为高可信或 reviewed。
- Evidence Gap 只表示「简历信息不足」，**不代表能力不足或造假**。
- 日志与报告只输出 ID / 计数 / 枚举，不输出姓名、电话、邮箱等个人信息。

## 用户偏好

- 中文沟通，要求详尽全面；成果习惯交付结构化文档（Word / PDF / Markdown 报告）便于编辑分发。
- 技术内容需附表格、代码示例与可复现的运行命令；报告需明确「已完成 / 未完成 / 待人工审核 / 是否改动旧资产」。
- 严格按分阶段推进，**不要跳过试验数据或人工验收阶段**；长任务可交后台执行。
