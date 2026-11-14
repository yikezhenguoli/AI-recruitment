# RISM-002 阶段一：项目现状审计报告

- 审计时间：2026-11-14
- 审计方式：只读（目录遍历、脚本全文阅读、JSONL 实测解析、`.npy` header 只读解析、SHA-256 指纹）
- 审计期间**未修改、未删除、未覆盖任何 RISM-001 文件**
- 配套文档：`02_implementation_plan.md`

---

## 1. 重大环境变化与根目录决策

### 1.1 任务描述与实际情况不一致

任务书要求检查"当前项目"中的 `prepare_data.py`、`data/`、`embeddings/`、`models/`、`outputs/` 等。实测结果：

- 会话当前工作目录 `/Users/zhengrui/Documents/computer_programme/AI-recruitment/dataset/` 是**此前的模拟简历数据集构建项目**（纯标准库、无模型代码），其中 **没有** `data/`、`embeddings/`、`models/`、`outputs/`、`requirements.txt`，也没有任何 PyTorch 脚本。
- 真正的 RISM-001 位于上级目录 `/Users/zhengrui/Documents/computer_programme/AI-recruitment/RISM/`。

### 1.2 审计期间目录被外部拆分

审计进行中，`RISM/` 被外部进程（非本任务）拆分为两个**内容完全一致**的副本，`diff -rq RISMv1 RISMv2` 无任何差异，各 35 个文件、7.5 MiB：

| 路径 | 状态 | 定位 |
|---|---|---|
| `.../AI-recruitment/RISM/` | 已不存在 | 原 RISM-001 根目录 |
| `.../AI-recruitment/RISMv1/` | 存在，35 文件 | **冻结的 RISM-001 基线** |
| `.../AI-recruitment/RISMv2/` | 存在，35 文件 | **RISM-002 开发副本** |

### 1.3 本任务采用的根目录（重要决策）

> **开发根 `ROOT = /Users/zhengrui/Documents/computer_programme/AI-recruitment/RISMv2`**
> **冻结基线 `BASELINE = /Users/zhengrui/Documents/computer_programme/AI-recruitment/RISMv1`（全程零写入）**

理由：任务书要求"RISM-001 与 RISM-002 的数据、配置、输出互相隔离""不得覆盖模型权重/Embedding/标签矩阵/划分文件"。用户已把项目拆成 v1/v2，正符合该隔离意图。

**附加保护措施**：已生成 `outputs/rism002/rism001_baseline_manifest.json`，记录 RISMv1 全部 35 个文件的 SHA-256 与大小，最终阶段将重新比对以证明零改动。所有新资产一律放在 RISMv2 的**新增独立子目录**中，不复用旧文件名、不以 RISMv1 为 cwd、不运行任何 RISM-001 的写入型脚本。

若用户后续希望改回以 `RISM/` 或其它目录为根，只需修改 `configs/rism002.json` 的 `project_root`，所有脚本均基于 `__file__` 与配置定位，不依赖 cwd。

---

## 2. RISM-001 文件清单（实测）

### 2.1 Python 脚本（22 个要求核查，20 存在 + 2 缺失/额外）

| 脚本 | 行数 | 职责 | 写入文件 | 第三方库 |
|---|---:|---|---|---|
| `prepare_data.py` | — | **不存在**（全仓未找到） | — | — |
| `audit_dataset.py` | 215 | 三表外键校验 + 问题级训练样本 | `data/training_samples.jsonl` | stdlib |
| `build_multilabel_dataset.py` | 198 | 按 `experience_id` 合并为经历级多标签 | `data/multilabel_samples.jsonl` | stdlib |
| `generate_labels.py` | 68 | metadata → multi-hot | `embeddings/labels.npy` | numpy |
| `generate_embeddings.py` | 113 | bge 编码经历/岗位 | `embeddings/*.npy`, `metadata.json` | numpy, torch, sentence_transformers |
| `split_dataset.py` | 117 | 按 `resume_id` 70/15/15 划分 | `split_indices.npz`, `split_metadata.json` | numpy |
| `dataset.py` | 24 | `RISMDataset`（numpy → Tensor） | 无 | torch |
| `models/rism_model.py` | 25 | MLP `1024→128→15` | 无 | torch |
| `train.py` | 273 | 训练 + early stopping | `outputs/best_model.pth` | numpy, torch |
| `evaluate.py` | 291 | 阈值扫描 + 手写 P/R/F1 | 无 | numpy, torch |
| `predict.py` | 288 | 在线推理输出 JSON | `outputs/prediction_result.json` | torch, sentence_transformers |
| `calculate_pos_weight.py` | 46 | 打印负正比 | 无 | numpy, torch |
| `check_multilabel_data.py` | 26 | 多标签样本空值检查 | 无 | stdlib |
| `inspect_data.py` | 81 | 原始 JSONL 字段统计 | 无 | stdlib |
| `inspect_label_distribution.py` | 59 | 三集合标签分布 | 无 | numpy |
| `test_backward.py` / `test_dataloader.py` / `test_dataset.py` / `test_embedding.py` / `test_loss.py` / `models/test_model.py` | 21~77 | 训练链路自测 | 无 | torch |

额外文件：`input_resume.json`（predict 默认输入样例）。
**缺失**：`requirements.txt`、任何 `.yaml/.toml/.ini` 配置、README、`models/__init__.py`。所有配置以字面量硬编码在脚本内。

### 2.2 数据文件（`RISMv2/data/`，只读）

| 文件 | 行数 | 说明 |
|---|---:|---|
| `resumes.jsonl` | 100 | 完整简历（含 `resume_text`、`basic_info`） |
| `resume_experiences.jsonl` | 742 | 经历单元，`original_content` 为可追溯原文 |
| `interview_questions.jsonl` | 1035 | 问题，含 `reference.original_text` + 字符偏移 |
| `question_chains.jsonl` | 300 | 追问链（**RISM-001 完全未使用**） |
| `training_samples.jsonl` | 1035 | `audit_dataset.py` 输出 |
| `multilabel_samples.jsonl` | 471 | `build_multilabel_dataset.py` 输出 |

### 2.3 Embedding / 标签 / 划分（只读）

| 文件 | 实测 |
|---|---|
| `experience_embeddings.npy` | `(471, 512) float32` |
| `job_embeddings.npy` | `(471, 512) float32` |
| `labels.npy` | `(471, 15) float32` |
| `metadata.json` | 4 键：`resume_ids`(471)、`experience_ids`(471)、`labels`(471)、`label_names`(15) |
| `split_indices.npz` | `train_indices`/`val_indices`/`test_indices` |
| `split_metadata.json` | 70/15/15 份简历 ID |

### 2.4 模型与输出（只读）

- `outputs/best_model.pth`：535035 字节，`state_dict`，`Linear(1024,128)→ReLU→Linear(128,15)`
- `outputs/prediction_result.json`：2740 字节，历史推理结果

---

## 3. 实际数据字段（已实测，未做任何假设）

### 3.1 `resumes.jsonl` 顶层字段

```
resume_id, candidate_id, target_position, position_id, family,
career_level, career_level_label, total_work_years,
resume_quality, resume_quality_label, basic_info,
education, work_experiences, project_experiences, internship_experiences,
skills, achievements, certifications, research_experiences, competitions,
achievement_experiences, skill_application_experiences,
quality_signals, generation, resume_text, quality_score
```

- `basic_info` 含 `name/age/city/phone/email/is_fictional` → **含敏感字段**，RISM-002 所有日志与报告必须只取 `resume_id/candidate_id`，绝不输出这些内容。
- `family` 是中文岗位族（如「算法与数据」），`position_id` 是英文岗位 ID，`career_level` 为 `fresh/junior/mid/senior/expert`。

### 3.2 `resume_experiences.jsonl` 字段

```
experience_id, resume_id, experience_type, title, organization,
start_date, end_date, original_content, key_points, skills_involved,
achievements, potential_risks, missing_information, fact_count,
position_id, career_level, quality_score
```

**对 RISM-002 极有价值**：`potential_risks` 与 `missing_information` 是现成的、可信的规则化 Evidence Gap 线索；`key_points` 是 Claim 候选来源；`original_content` 是所有 `source_text` 的唯一合法出处。

### 3.3 `interview_questions.jsonl` 字段

```
question_id, resume_id, experience_id, experience_type,
reference{original_text,start_offset,end_offset},
dimension, secondary_dimensions[], question_type, question, reason,
expected_investigation[], priority(high|medium|low),
difficulty(easy|medium|hard), follow_up_questions[], quality_score
```

- `reference.original_text` 是真实子串，`start_offset/end_offset` 可用 → 可直接作为 Claim 的 `source_text` 锚点。
- `secondary_dimensions` **存在但 RISM-001 从未使用**。

### 3.4 `question_chains.jsonl` 字段

```
chain_id, resume_id, experience_id, root_question_id, dimension,
theme, chain_depth, stop_condition,
questions[{sequence, level, question, purpose, expected_investigation, trigger_condition}],
quality_score
```

`level`（如 `fact_confirmation`）与 `trigger_condition` 是 RISM-002 追问深度、递进关系、`follow_up_triggers` 的现成依据。

### 3.5 数据关联方式

```
resumes.resume_id ──1:N──> resume_experiences.resume_id
resume_experiences.experience_id ──1:N──> interview_questions.experience_id
                                  └──1:N──> question_chains.experience_id
question_chains.root_question_id ──> interview_questions.question_id
interview_questions.reference.original_text ⊂ resume_experiences.original_content
```

实测 ID 唯一性：100 / 742 / 1035 / 300 全部唯一；471 个经历有历史问题（742 - 471 = 271 个经历**从未被提问**，这正是"不得把未出现方向当 Negative"的现实依据）。

---

## 4. 标签结构（RISM-001 现状）

- 15 个一级维度，权威来源为 `embeddings/metadata.json["label_names"]`，**按字母序**排列：
  `achievement_verification, business_understanding, data_evidence, innovation, leadership, learning_ability, personal_contribution, problem_solving, professional_depth, project_management, reflection, risk_awareness, teamwork, technical_decision, technical_implementation`
- `labels.npy` 的列语义、`best_model.pth` 最后 15 个输出单元都绑定此顺序。
- `generate_labels.py` 全零初始化后命中置 1：**未出现的方向一律被当作 Negative**，无 mask、无 ignore-index、无 Unknown 类。
- `audit_dataset.py` 只取 `question["dimension"]`，丢弃 `secondary_dimensions`。
- `pos_weight = (N_train - pos) / pos`，在 `train.py` 内即时计算（未落盘）；损失 `BCEWithLogitsLoss`。
- 特征 = `concat(经历 512 归一化向量, 岗位 512 归一化向量)` = 1024 维。
- 划分：`seed=42`，按 `resume_id` 分组，70/15/15 → 321/75/75 条经历，避免简历泄漏。

---

## 5. 已识别的 RISM-001 问题（RISM-002 必须规避）

| # | 问题 | 对 RISM-002 的影响 |
|---|---|---|
| 1 | 未出现方向自动 = Negative | RISM-002 引入 `unknown`，未审核方向**绝不**转 negative |
| 2 | 丢弃 `secondary_dimensions` | 作为历史意图分析的补充信号回收 |
| 3 | `question_chains.jsonl` 完全未用 | 用于追问深度、递进、trigger 条件建模 |
| 4 | 15 维过宽，无法表达具体意图 | 建立二级 `investigation_directions`，与一级多对多 |
| 5 | `generate_embeddings.py` 训练侧 `normalize_embeddings=True`，`predict.py` 推理侧未设置 | 训练/推理分布偏移；本任务不训练，仅记录 |
| 6 | 所有脚本用相对路径、隐含 cwd = RISM 根 | RISM-002 一律基于 `__file__` + 配置定位 |
| 7 | `split_dataset.py` 硬断言 471/100/512/15 | 新数据集不得复用/重算旧划分 |
| 8 | 无 requirements.txt / 配置 / README / metadata 版本信息 | RISM-002 全部补齐 |
| 9 | `test_indices` 存在但 `evaluate.py` 只评估 `val_indices` | 记录，不在本任务处理 |
| 10 | `metadata.json` 无模型名/归一化标志/种子 | RISM-002 所有产物带 `ontology_version` 与生成元信息 |

---

## 6. RISM-001 受保护资产清单（零写入）

- `RISMv1/` 全部 35 个文件（指纹已固化于 `outputs/rism002/rism001_baseline_manifest.json`）
- `RISMv2/` 中原有的 35 个 RISM-001 文件同样不修改（虽为副本，仍按"不直接修改旧版文件实现新版功能"执行）
- 明令不得运行：`audit_dataset.py`、`build_multilabel_dataset.py`、`generate_embeddings.py`、`generate_labels.py`、`split_dataset.py`、`train.py`、`predict.py`（这 7 个会原地覆盖资产）
- **本次任务不会执行任何训练、Embedding 生成、标签矩阵生成、数据划分、模型评估、模型推理**

---

## 7. 运行环境

| 项 | 实测 |
|---|---|
| 系统 | macOS / Apple Silicon |
| 系统 `python3` | 3.13，**无 numpy / pandas / PyYAML** |
| 项目虚拟环境 | `/Users/zhengrui/Documents/computer_programme/AI-recruitment/.venv/bin/python`（3.12，含 numpy/torch/transformers/sentence-transformers） |
| RISM-002 依赖策略 | **纯 Python 标准库**，不 import torch/numpy/sentence_transformers；因此用系统 `python3` 即可运行全部新脚本与测试，且不触碰模型栈 |

---

## 8. 审计结论

1. RISM-001 代码与资产完整，但缺少配置化、文档化和 Unknown 语义。
2. 现有 4 份 JSONL 数据质量高、关联完整、引用可追溯，足以支撑 RISM-002 的 **Claim / Evidence Gap / 追问深度** 冷启动，无需重新造数据。
3. 已具备实施 RISM-002 的全部前提；可以按 `02_implementation_plan.md` 的八阶段顺序推进。
4. 本次审计未修改任何文件，仅新增 `outputs/rism002/` 下的报告与基线指纹文件。
