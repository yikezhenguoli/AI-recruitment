# RISM-002 阶段一：实施计划

- 配套审计报告：`01_project_audit.md`
- 开发根：`/Users/zhengrui/Documents/computer_programme/AI-recruitment/RISMv2`
- 冻结基线：`/Users/zhengrui/Documents/computer_programme/AI-recruitment/RISMv1`（零写入）
- 本次目标：**只建数据集体系与数据工程工具，不训练任何模型**

---

## 1. 总体设计原则

| 原则 | 落地方式 |
|---|---|
| 完全隔离 | 所有新增文件在 RISMv2 的**新子目录**；不占用 `data/` 下已有 6 个 JSONL、`embeddings/`、`outputs/` 下已有文件 |
| 原文可追溯 | 所有 `source_text` 必须是 `resume_experiences.original_content` 的真实子串；程序用 `in` 校验，必要时校验字符偏移 |
| 不假设字段 | 由 `audit_source_data.py` 实测字段；Schema 校验用必需字段 + 类型，允许额外字段 |
| 不自动批准 | 所有 AI/规则候选落 `data/intermediate/`，状态 `pending`、`annotation_source` 标明来源；只有 `approved` 且 `reviewed=true` 才能进 `data/processed/` |
| 不制造 Negative | 方向级标注三态 `positive / negative / unknown`；**只显式写出的 negative 才算**，缺失一律 Unknown |
| 不造假 | 证据缺口只描述"简历未提供"，不推断能力缺失或经历造假 |
| 零依赖 | 纯标准库，不 import torch/numpy；不加载模型、不生成 embedding |
| 零敏感信息 | 日志与报告只输出 ID、计数、类型；不输出 `resume_text`、`basic_info`、姓名/电话/邮箱 |

---

## 2. 目录设计（RISMv2 内新增）

```text
RISMv2/
├── configs/
│   ├── rism002.json                 # 路径、版本、审核策略、阈值（JSON，纯标准库解析）
│   └── rism002_taxonomy.json        # 15 一级维度、9 Claim 类型、9 Gap 类型、8 Strategy 类型、枚举值
│
├── data/
│   ├── raw/                         # 只读引用清单（不复制、不覆盖原始 JSONL）
│   │   └── source_manifest.json
│   ├── ontology/
│   │   ├── investigation_directions.json
│   │   └── position_competencies.json
│   ├── intermediate/                # 规则/历史分析候选产物（pending，不进训练）
│   │   ├── candidate_directions.jsonl
│   │   ├── question_intent_analysis.json
│   │   └── candidate_claims.jsonl / candidate_gaps.jsonl / candidate_strategies.jsonl
│   ├── annotations/                 # 人工审核记录（唯一可信来源）
│   │   ├── claims.jsonl
│   │   ├── evidence_gaps.jsonl
│   │   ├── strategies.jsonl
│   │   └── direction_annotations.jsonl
│   └── processed/
│       └── rism002_samples.jsonl    # 最终样本（仅由 approved 数据构建）
│
├── rism002/                         # 独立 Python 包（不 import 任何 RISM-001 模块）
│   ├── __init__.py
│   ├── schemas/                     # JSON Schema（draft-07 子集）+ 轻量校验器
│   ├── parsers/                     # JSONL 读取、路径解析、npy 只读 header
│   ├── analyzers/                   # 意图归纳、相似问题、Claim/Gap/Strategy 候选推导
│   ├── validators/                  # 本体校验、数据集校验
│   ├── reports/                     # 报告渲染
│   └── utils/                       # 常量、ID、审核状态、脱敏、IO
│
├── scripts/rism002/
│   ├── audit_source_data.py
│   ├── analyze_question_intents.py
│   ├── validate_ontology.py
│   ├── build_dataset.py
│   ├── validate_dataset.py
│   └── dataset_report.py
│
├── tests/rism002/
│   └── test_rism002.py              # 15 项测试
│
├── outputs/rism002/                 # 全部报告与统计
│   ├── 01_project_audit.md
│   ├── 02_implementation_plan.md
│   ├── rism001_baseline_manifest.json
│   ├── 03_source_audit_report.md
│   ├── 04_intent_analysis_report.md
│   ├── 05_ontology_validation_report.md
│   ├── 06_dataset_validation_report.md
│   ├── 07_dataset_statistics.md / .json
│   ├── 08_test_report.md
│   ├── 09_impact_analysis.md
│   └── 10_final_report.md
│
└── README_RISM002.md
```

---

## 3. 数据 Schema 设计

### 3.1 五类核心数据 + 两类辅助

| 实体 | 必需字段 | 关键约束 |
|---|---|---|
| Resume Experience | `experience_id, resume_id, experience_text` | `experience_text` = 原始 `original_content`，不改写 |
| Key Claim | `claim_id, experience_id, claim_type, claim_text, source_text, review` | `source_text ∈ experience_text`；类型取自 9 类枚举 |
| Evidence Gap | `gap_id, experience_id, related_claim_ids[], gap_type, description, review` | `related_claim_ids` 必须存在且同经历；描述不得含"造假/能力不足" |
| Investigation Direction | `direction_id, direction_name, parent_dimensions[], definition, inclusion_criteria, exclusion_criteria, evidence_types, typical_trigger_claims, related_directions, applicable_position_families, status, version` | ID 稳定唯一；`parent_dimensions ⊆ 15 维`；`status ∈ candidate/approved/deprecated`；`related_directions` 无环 |
| Investigation Strategy | `strategy_id, experience_id, dimension, direction_id, direction_name, trigger_claim_ids[], trigger_gap_ids[], rationale, investigation_goal, evidence_to_obtain[], risk_signals[], expected_answer_signals[], follow_up_triggers[], strategy_type, priority, difficulty, sequence, prerequisites[], label_status, review` | 可追溯到同经历的 Claim + Gap；`direction_id` 必须是 `approved`；`label_status ∈ positive/negative/unknown` |
| Position Competency | `position_family, competency_id, competency_name, competency_definition, importance, related_direction_ids[]` | 与方向多对多；不靠岗位名称文本相似度 |
| Annotation Record | `annotation_source, annotation_status, annotator_id, reviewed_at, review_reason, ontology_version, reviewed` | `annotation_status ∈ pending/approved/rejected`；`reviewed` 与标签状态**分离** |

### 3.2 主样本 `rism002_samples.jsonl`

每行 = 一段经历 × 一个目标岗位，字段严格按任务书：
`sample_id, resume_id, candidate_id, experience{}, job{}, key_claims[], evidence_gaps[], investigation_strategies[], direction_annotations[], annotation{}`。

`direction_annotations` 三态语义：
- `positive` = 明确值得追问（需 `reviewed=true`）
- `negative` = **经人工审核**明确不值得追问（需 `reviewed=true` + `annotation_source=human`）
- `unknown` = 未判断/信息不足（默认；`reviewed=false`）

**禁止**：把未出现在方向列表中的方向自动补成 negative；把 `annotation_source != human` 的条目设为 `reviewed=true`。

### 3.3 一级维度兼容层

保留 `embeddings/metadata.json["label_names"]` 的 15 个英文标签及字母序，在 `configs/rism002_taxonomy.json` 中固化。一个方向可关联 1~N 个一级维度，一级维度可关联 N 个方向；**不为兼容性限制新方向发现**。一级维度不是 RISM-002 的预测目标，本任务不生成任何标签矩阵。

### 3.4 审核状态机

```
规则/历史候选 (pending, source=historical_question|rule_based)
        │ 人工审核
        ├── approved + reviewed=true + annotator_id + reviewed_at  → 可进入 processed
        ├── rejected                                             → 留在 intermediate/annotations，不进入
        └── 未处理 (pending)                                     → 构建器直接跳过并计数
```

`annotation_status`（审核流程）与 `label_status`（方向标注三态）是两个独立字段，不互相推导。

---

## 4. 八阶段执行计划

| 阶段 | 交付 | 通过条件（不通过则不进入下游） |
|---|---|---|
| 一 项目审计与计划 | `01_project_audit.md`、`02_implementation_plan.md`、基线指纹 | 实测字段确认、根目录决策明确、零改动验证 |
| 二 Schema 与目录 | `configs/`、`rism002/schemas/`、目录骨架、taxonomy | 配置可解析、Schema 自校验通过、RISMv1 指纹不变 |
| 三 原始数据审计 | `audit_source_data.py` + `03_source_audit_report.md` | 4 类 JSONL 全部可解析、ID 唯一、外键全通、只读断言通过 |
| 四 历史意图分析 | `analyze_question_intents.py` + 候选意图产物 + `04_intent_analysis_report.md` | 1035 问题 + 300 追问链全量处理；候选方向全部 `candidate/pending`；LLM 开关默认关闭 |
| 五 方向目录与校验 | 两份 ontology JSON + `validate_ontology.py` + 报告 | ID 唯一、维度引用合法、无环、状态合法、定义字段齐全 |
| 六 数据集构建与校验 | Claim/Gap/Strategy 结构、`build_dataset.py`、`validate_dataset.py`、样本文件 | 未审核数据零泄漏、source_text 全为原文子串、Unknown 不被转 Negative |
| 七 审核状态与统计 | `dataset_report.py` + 统计 JSON/MD | 报告无敏感信息、统计与实测一致 |
| 八 测试与交付文档 | 15 项单元测试全通过、README、影响分析、最终报告 | 测试 15/15、RISMv1 指纹一致、无任何训练行为证据 |

### 4.1 历史数据利用方式（阶段四）

- `interview_questions.jsonl`：按 `question_type` × `dimension` × `reason/expected_investigation` 关键词归纳意图签名；识别「语义重复但表达不同」（归一化签名相同）与「文本相似但考察目标不同」（同一 `reference.original_text` 对应不同 `dimension/question_type`）。
- `question_chains.jsonl`：统计 `level` 递进序列、`trigger_condition` 类型、`chain_depth`，用于 Strategy 的 `difficulty`、`follow_up_triggers`、`sequence`。
- 候选方向默认 `annotation_source = historical_question`、`status = candidate`、`annotation_status = pending`，**不得自动批准**。
- 基础分析模式（默认）：纯规则 + 关键词 + 归一化签名，不依赖外部服务。LLM 模式：`configs/rism002.json` 中 `llm.enabled` 默认 `false`；即便开启，脚本也必须先打印将发送的数据字段清单与目标服务并要求显式 `--confirm-external`，本任务全程不开启。

### 4.2 冷启动标注策略（阶段六，关键）

任务书禁止"把所有 5000 份简历自动转换为已审核标签"，也禁止未审核 AI 输出标高可信度。因此：

- 从 471 个**有历史问题**的经历中，选取一小批（默认 12 段，覆盖不同岗位族与经历类型）作为**示例标注集**。
- 这些标注由本地规则从「可验证的结构化事实」生成：`key_points` → Claim，`potential_risks`/`missing_information` → Gap，历史问题 `dimension/question_type` → 方向线索。
- 每一条都带 `annotation_source = human_review_required` 占位，`annotation_status = pending`，`reviewed = false`；**默认不进入正式样本**。
- `build_dataset.py` 提供 `--include-pending-as-unknown` 开关（默认关闭）：开启时仅生成 `direction_annotations` 的 `unknown` 三态占位样本，用于验证 Schema 与流水线，**不产生任何 positive/negative 标签**。
- 真正进入 `data/processed/` 的样本，必须由 `data/annotations/` 中 `approved + reviewed=true + annotation_source=human` 的记录驱动。为演示闭环，附带一份 `annotations/human_review_template.jsonl` 与审核说明，用户可用一条明确的 `--approve-sample` 操作把示例转成人工已审核，或直接编辑审核文件。

> 这样既保证流水线端到端可运行、可测试，又严守"未经人工审核不进正式数据集"的底线。

---

## 5. 测试计划（15 项，对应任务书第十一节）

| # | 测试 |
|---|---|
| 1 | 正常 JSONL 能读取 |
| 2 | 错误 JSONL 被识别 |
| 3 | 缺少必需字段报错 |
| 4 | 重复 ID 报错 |
| 5 | 无效 `resume_id` 被识别 |
| 6 | 无效 `experience_id` 被识别 |
| 7 | 不存在的 `direction_id` 被识别 |
| 8 | 未审核 AI 标签不得进入正式数据集 |
| 9 | `unknown` 不被转换为 `negative` |
| 10 | 同一经历可对应多个 Claim |
| 11 | 同一经历可对应多个 Evidence Gap |
| 12 | 同一经历可对应多个 Strategy |
| 13 | 一个方向可关联多个一级维度 |
| 14 | 构建过程不修改 RISM-001 文件（指纹比对） |
| 15 | 不执行任何模型训练（源码扫描 + 运行时 import 检查） |

测试使用 `unittest`（标准库），在临时目录构造数据，不触碰真实资产。

---

## 6. 安全与合规

1. 日志/报告不输出完整简历文本、`basic_info`、姓名、电话、邮箱、身份证号；只输出 ID、计数、枚举分布。
2. `data/*.jsonl` 与 `embeddings/`、`outputs/best_model.pth` 全部以只读方式打开。
3. 外部 LLM 默认关闭；本任务无任何网络调用、无任何上传。
4. 所有新脚本不 import `torch` / `numpy` / `sentence_transformers`，不执行 `model.train()`、不调用 `np.save`、不写 `.pth`、不划分训练/验证/测试集。
5. 最终以 SHA-256 指纹比对证明 RISMv1 的 35 个文件零改动。

---

## 7. 风险与应对

| 风险 | 应对 |
|---|---|
| 用户可能希望以 `RISM/` 而非 `RISMv2/` 为根 | 所有路径由 `configs/rism002.json` 的 `project_root` 决定，可一键切换；新增资产为独立子目录，易迁移 |
| 历史问题由规则生成，意图边界可能不清晰 | 候选一律 `pending`，不自动批准；报告列出低置信度样本供人工判断 |
| 「相似但考察目标不同」难以用规则完全区分 | 采用「同原文 + 不同 dimension/question_type」的可判定信号，并在报告中声明规则局限 |
| 无第三方依赖导致 JSON Schema 需自实现 | 实现 draft-07 常用子集（type/required/properties/items/enum/minItems/pattern），并附自校验测试 |
| 示例标注集被误认为正式标签 | 文件命名 `candidate_*` + 审核状态字段 + README 加粗声明 + 校验器硬门槛 |
| 中文分词影响相似问题判定 | 使用字符 n-gram + 关键词表，不依赖分词库；阈值可配置 |

---

## 8. 阶段一结论

审计已完成，未修改任何 RISM-001 资产；实施计划已确定，满足"先报告、后开发"与"严格按阶段推进、不跳过、某阶段失败不构建下游"的要求。现进入阶段二。
