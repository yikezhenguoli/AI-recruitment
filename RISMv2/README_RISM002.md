# RISM-002 数据集体系与处理工具 · 使用说明

> 版本：`RISM-002.1` ｜ 状态：`awaiting_human_review`（待人工审核）
> 开发根目录：`/Users/zhengrui/Documents/computer_programme/AI-recruitment/RISMv2/`
> 冻结基线：`/Users/zhengrui/Documents/computer_programme/AI-recruitment/RISMv1/`（全程只读，未修改）

---

## 0. 一页速览

RISM-002 **只建设数据集体系与数据处理工具，不训练任何模型**。它把「简历经历 → 关键主张 → 证据缺口 → 追问方向 → 追问策略」组织为一条可追溯、可审核的链路，为未来的模型训练准备结构化样本。

**当前最重要的事实：正式数据集是空的（0 条样本），这是正确状态，不是失败。**
原因：28 个追问方向全部为 `candidate`，`data/annotations/` 下的人工审核记录全部为空。按需求约束「未经人工审核的候选结果不得进入正式训练数据集」，构建器因此产出 0 条样本并标记 `awaiting_human_review`。链路本身已用临时人工审核 fixture 端到端验证通过（见 §9）。

```bash
cd /Users/zhengrui/Documents/computer_programme/AI-recruitment/RISMv2

# 一键复核全部阶段（只读，安全）
python3 scripts/rism002/audit_source_data.py --strict          # ① 源数据审计
python3 scripts/rism002/analyze_question_intents.py --strict   # ② 意图分析
python3 scripts/rism002/build_ontology.py                      # ③ 重建目录（可选）
python3 scripts/rism002/validate_ontology.py --strict          # ④ 目录校验
python3 scripts/rism002/prepare_candidates.py                  # ⑤ 生成待审核候选
python3 scripts/rism002/build_dataset.py --validate            # ⑥ 构建 + 校验
python3 scripts/rism002/validate_dataset.py                    # ⑦ 独立校验
python3 scripts/rism002/dataset_report.py                      # ⑧ 统计报告

# 完整单元测试（20 项）
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/rism002 -p 'test_*.py' -v
```

---

## 1. 运行环境

- **Python 3.13（macOS / Apple clang 工具链）**；本项目 **只用 Python 标准库**。
- 不需要安装任何依赖：`configs/` 与 `rism002/schemas/` 均为 JSON；不依赖 PyYAML、numpy、pandas、torch、transformers。
- 不读取、不修改 `embeddings/*.npy/.npz` 的二进制内容（只解析文件头做只读盘点），因此不需要 numpy。
- 无需联网；外部 LLM 默认关闭且本任务全程未启用。

> 注意：RISMv1 / RISMv2 根目录均**没有** `requirements.txt`；RISM-001 原有的 torch / sentence-transformers 依赖属于旧版训练链路，RISM-002 不加载、不调用。

---

## 2. 目录结构与隔离原则

```
RISMv2/
│
├── README_RISM002.md                  ← 本文件（新增）
│
├── (RISM-001 原有文件，全部未改动)
│   ├── data/*.jsonl                   ← 只读源数据
│   ├── embeddings/                    ← 只读：Embedding、标签矩阵、划分文件、metadata
│   ├── models/rism_model.py           ← 只读：RISM-001 MLP
│   ├── outputs/best_model.pth         ← 只读：RISM-001 权重
│   └── prepare_data.py … predict.py   ← 只读：RISM-001 脚本
│
├── configs/                           ★ RISM-002 新增
│   ├── rism002.json                     主配置（路径、只读资产、审核策略、LLM、隐私、种子）
│   └── rism002_taxonomy.json            分类体系（15 一级维度 / 9 Claim / 9 Gap / 8 Strategy / 枚举 / 岗位族）
│
├── data/
│   ├── raw/source_manifest.json       ★ RISM-001 只读资产 SHA-256 指纹基线
│   ├── ontology/                      ★ 追问方向目录 + 岗位能力目录
│   ├── intermediate/                  ★ 候选方向、意图分析、候选 Claim/Gap/Strategy、Unknown 预览
│   ├── annotations/                   ★ 人工审核记录（当前为空 + 审核模板）
│   └── processed/rism002_samples.jsonl ★ 正式主数据集（当前 0 行，待人工审核）
│
├── rism002/                           ★ 纯标准库 Python 包
│   ├── schemas/                         definitions.json + 轻量 JSON Schema 校验器
│   ├── parsers/jsonl.py                 只读 JSONL / npy 头 / npz 成员解析
│   ├── analyzers/                       intent / ontology_builder / candidate_builder
│   ├── validators/                      source_audit / ontology / dataset_validator
│   ├── reports/render.py                Markdown 渲染
│   └── utils/core.py                   配置、路径、审核块、读写、时间
│
├── scripts/rism002/                   ★ 9 个命令行脚本（见 §6）
├── tests/rism002/test_rism002.py      ★ 20 项单元测试
└── outputs/rism002/                   ★ 全部报告与结果 JSON（见 §7）
```

**隔离保证**：RISM-002 的所有写入路径都在 `configs/`、`data/{raw,ontology,intermediate,annotations,processed}/`、`rism002/`、`scripts/rism002/`、`tests/rism002/`、`outputs/rism002/` 之内。`configs/rism002.json` 的 `readonly_assets` 显式列出 RISM-001 不可覆盖资产，脚本按 SHA-256 指纹比对，任何改动都会被告警。

---

## 3. 数据体系

### 3.1 五类核心数据 + 兼容层

| 层 | 实体 | 关键字段 | 存放位置 |
|---|---|---|---|
| 源 | Resume Experience | `experience_id`, `resume_id`, `experience_type`, `original_content` | `data/resume_experiences.jsonl`（只读） |
| ① | Key Claim | `claim_id`, `claim_type`, `claim_text`, `source_text`, `review` | 候选 `intermediate/`，已审核 `annotations/claims.jsonl` |
| ② | Evidence Gap | `gap_id`, `related_claim_ids`, `gap_type`, `description`, `source_span`, `review` | 候选 `intermediate/`，已审核 `annotations/evidence_gaps.jsonl` |
| ③ | Investigation Direction | `direction_id`, `parent_dimensions`, `definition`, `inclusion_criteria`, `exclusion_criteria`, `evidence_types`, `typical_trigger_claims`, `related_directions`, `applicable_position_families`, `status`, `version` | `data/ontology/investigation_directions.json` |
| ④ | Investigation Strategy | `strategy_id`, `dimension`, `direction_id`, `trigger_claim_ids`, `trigger_gap_ids`, `rationale`, `investigation_goal`, `evidence_to_obtain`, `risk_signals`, `expected_answer_signals`, `follow_up_triggers`, `strategy_type`, `priority`, `difficulty`, `sequence`, `prerequisites`, `label_status` | 候选 `intermediate/`，已审核 `annotations/strategies.jsonl` |
| ⑤ | Sample | `sample_id`, `resume_id`, `candidate_id`, `experience`, `job`, `key_claims`, `evidence_gaps`, `investigation_strategies`, `direction_annotations`, `annotation` | `data/processed/rism002_samples.jsonl` |
| 兼容 | 15 个一级维度 | 与 RISM-001 字母序标签完全一致 | `configs/rism002_taxonomy.json` |
| 岗位 | Position Competency | `position_family`, `competency_id`, `competency_name`, `competency_definition`, `importance`, `related_direction_ids` | `data/ontology/position_competencies.json` |

**一级维度（15，兼容层，非预测目标）**：
`achievement_verification`, `business_understanding`, `data_evidence`, `innovation`, `leadership`, `learning_ability`, `personal_contribution`, `problem_solving`, `professional_depth`, `project_management`, `reflection`, `risk_awareness`, `teamwork`, `technical_decision`, `technical_implementation`

一级维度与二级方向为**多对多**：当前 28 个方向中 14 个关联 ≥2 个一级维度，最多 3 个；不因兼容层而限制新方向，也不自动合并语义相近但考察目标不同的方向。

**Claim 类型（9）**：`responsibility`, `technical_method`, `decision`, `quantified_achievement`, `qualitative_achievement`, `leadership`, `collaboration`, `innovation`, `problem_resolution`

**Evidence Gap 类型（9）**：`missing_process`, `missing_technical_details`, `missing_decision_basis`, `missing_measurement_method`, `missing_baseline`, `missing_attribution`, `missing_business_impact`, `missing_risk_handling`, `missing_result_validation`

> **语义底线**：Evidence Gap 只表示「简历没有提供足够信息」，**不代表候选人能力不足、更不代表经历造假**。校验器会拒绝含造假指控措辞的描述。

**Strategy 类型（8）**：`process_reconstruction`, `principle_verification`, `decision_verification`, `evidence_verification`, `contribution_verification`, `scenario_extension`, `counterfactual_analysis`, `reflection_analysis`

**枚举**：`priority ∈ {high, medium, low}`；`difficulty ∈ {L1, L2, L3, L4}`（基础确认 / 过程还原 / 深度分析 / 高阶推演）；`label_status ∈ {positive, negative, unknown}`；`annotation_status ∈ {pending, approved, rejected}`；`direction.status ∈ {candidate, approved, deprecated}`。

### 3.2 原文可追溯性（硬门槛）

- `Claim.source_text` 必须是所属经历 `original_content` 的**真实子串**，校验器按字符定位，编造原文直接判不合格。
- `EvidenceGap.source_span` 同样按原文定位；Gap 必须关联至少一个真实 Claim。
- 每条 Strategy 必须通过 `trigger_claim_ids` / `trigger_gap_ids` 追溯到同一经历内的 Claim 或 Gap，且 `direction_id` 必须存在于已批准方向目录。
- 每个 Sample 的 `experience.experience_text` 直接取源经历原文，不改写。

### 3.3 审核状态与标签状态严格分离

| 概念 | 字段 | 取值 | 由谁决定 |
|---|---|---|---|
| 审核状态 | `review.annotation_status` | `pending` / `approved` / `rejected` | 只能由人工通过 `record_review.py` 写入 |
| 标注来源 | `review.annotation_source` | `human` / `historical_question` / `rule_based` / `llm` / `unknown` | 生成时记录，不自动提升 |
| 标签状态 | `label_status` / `direction_annotations[].label_status` | `positive` / `negative` / `unknown` | 方向级只能由人工显式给出 |

硬性规则（`configs/rism002.json → review`）：
- `auto_approve: false`、`approved_requires_sources: ["human"]`：非人工来源永远不能变成 approved。
- `default_label_status: "unknown"`：**未出现的方向一律 Unknown，绝不自动转 Negative**。
- `negative_requires_reviewed: true`：Negative 必须 `reviewed=true` 且 `annotation_source=human`。
- `allow_unreviewed_in_processed: false`：未审核记录不得进入正式数据集。
- 保留 `annotator_id` / `reviewed_at` / `review_reason` / `ontology_version`。

### 3.4 Schema

`rism002/schemas/definitions.json` 定义 `claim` / `evidence_gap` / `direction` / `competency` / `strategy` / `direction_annotation` / `sample` / `review` 等实体，支持 `$ref` 到 `$defs`。`rism002/schemas/validator.py` 是纯标准库的轻量校验器（type / required / properties / items / enum / minItems / minLength / `$ref`），`self_check()` 会在构建时自检定义完整性。

---

## 4. 数据生成 / 构建流水线

```
[RISM-001 只读源数据]
  resumes / experiences / questions / chains / multilabel / embeddings metadata
        │
        ├─ ① audit_source_data.py      → 字段、ID、关联、引用偏移、只读资产指纹
        │
        ├─ ② analyze_question_intents.py → 意图签名 / 相似问题 / 同原文异目标 / 过宽维度
        │                                   → 28 个 candidate 方向（annotation_source=historical_question）
        │
        ├─ ③ build_ontology.py         → investigation_directions.json + position_competencies.json
        ├─ ④ validate_ontology.py      → ID/维度引用/关联/状态/必需字段/循环依赖
        │
        ├─ ⑤ prepare_candidates.py    → candidate_claims / gaps / strategies（全部 pending）
        │                                   + human_review_template.jsonl（审核工作表）
        │                                   + rism002_unknown_preview.jsonl（Unknown 预览，不进正式集）
        │
        ├─ ★ 人工审核（唯一能改变状态的入口：record_review.py）★
        │
        ├─ ⑥ build_dataset.py          → 只消费 approved 记录 → rism002_samples.jsonl
        ├─ ⑦ validate_dataset.py      → 全量内容级校验
        └─ ⑧ dataset_report.py        → 统计 + 安全合规报告
```

**关键设计**：历史问题中出现某方向只作为 **Positive 候选**（`annotation_source=historical_question`），**绝不自动成为完整正负标签**；某经历没出现某方向也**不推导 Negative**。

---

## 5. 外部 LLM 与数据安全

- `configs/rism002.json → llm.enabled = false`，`provider/endpoint/model = null`，`fields_to_send = []`，`require_explicit_confirm = true`。
- `analyze_question_intents.py` 默认走**纯本地规则模式**；即使传 `--enable-llm`，若配置未启用或未同时传 `--confirm-external`，脚本只打印「将发送哪些字段、发送到哪个服务」并拒绝执行，不会发出任何请求。
- 隐私开关：`log_experience_text=false`、`log_resume_text=false`、`log_basic_info=false`、`id_only_in_reports=true`。日志与报告只出现 ID、统计值和脱敏后的短片段，不输出姓名/电话/邮箱/身份证号。
- 原始 RISM-001 数据全程只读；脚本从不调用 `write` 到 `data/*.jsonl`、`embeddings/`、`outputs/best_model.pth`。
- 不上传任何数据到第三方。

---

## 6. 脚本运行手册

所有脚本都从 `RISMv2/` 根目录运行，支持 `--config <path>` 覆盖主配置。

| # | 脚本 | 作用 | 常用参数 | 主要输出 |
|---|---|---|---|---|
| 1 | `audit_source_data.py` | 只读审计源数据 | `--strict`, `--json-only` | `outputs/rism002/03_source_audit_report.md`, `source_audit_result.json` |
| 2 | `analyze_question_intents.py` | 历史意图归纳与候选方向发现 | `--strict`, `--enable-llm`, `--confirm-external` | `data/intermediate/question_intent_analysis.json`, `candidate_directions.jsonl`, `04_intent_analysis_report.md` |
| 3 | `build_ontology.py` | 由候选方向构建目录 + 岗位能力 | `--config` | `data/ontology/investigation_directions.json`, `position_competencies.json` |
| 4 | `validate_ontology.py` | 目录校验（含循环依赖） | `--strict` | `05_ontology_validation_report.md`, `ontology_validation_result.json` |
| 5 | `prepare_candidates.py` | 生成待审核 Claim / Gap / Strategy | `--config` | `data/intermediate/candidate_*.jsonl`, `data/annotations/human_review_template.jsonl`, `rism002_unknown_preview.jsonl` |
| 6 | `record_review.py` | **人工逐条记录审核决定** | 见下方 | `data/annotations/*.jsonl` |
| 7 | `build_dataset.py` | 构建正式数据集 | `--validate`, `--include-pending-as-unknown` | `data/processed/rism002_samples.jsonl`, `build_result.json` |
| 8 | `validate_dataset.py` | 正式数据集全量校验 | `--strict`, `--samples`, `--no-report` | `06_dataset_validation_report.md`, `dataset_validation_result.json` |
| 9 | `dataset_report.py` | 统计与安全合规报告 | `--json-only` | `dataset_report.md`, `dataset_report.json` |

### 6.1 人工审核（唯一改变状态的入口）

`record_review.py` **一次只处理一条**，且必须同时给出 `--annotator`、`--reason`、`--confirm-human-review`，缺一即拒绝执行（已实测：缺少确认参数会退出非零且审核文件保持 0 行）。

```bash
# 批准一个追问方向（把 candidate → approved）
python3 scripts/rism002/record_review.py --entity direction \
  --id hist_data_verification__data_evidence --decision approved \
  --annotator human_01 --reason "已核对该方向定义与排除条件" \
  --confirm-human-review

# 批准一条 Claim / Gap / Strategy
python3 scripts/rism002/record_review.py --entity claim \
  --id CLM_037707_01 --decision approved \
  --annotator human_01 --reason "已核对原文与字符偏移" --confirm-human-review

# 唯一能产生 negative 的入口：人工确认某经历某方向明确不值得追问
python3 scripts/rism002/record_review.py --entity direction_annotation \
  --experience-id EXP_00037707 --direction-id hist_data_verification__data_evidence \
  --label-status negative --annotator human_01 \
  --reason "人工确认该经历与数据核实无关" --confirm-human-review
```

`--entity` 可选：`direction` / `claim` / `gap` / `strategy` / `direction_annotation`；`--decision` 为 `approved` / `rejected`。
审核工作表在 `data/annotations/human_review_template.jsonl`（102 行，含来源、原文片段、建议结论，**全部仅供参考、不自动写入**）。

### 6.2 审核完成后重建正式数据集

```bash
python3 scripts/rism002/build_dataset.py --validate
python3 scripts/rism002/validate_dataset.py --strict
python3 scripts/rism002/dataset_report.py
```

> 当前空集状态会有 1 条「正式数据集为空，处于 awaiting_human_review」的**预期警告**，`validate_dataset.py --strict` 因此返回退出码 3。日常复核请省略 `--strict`；待正式样本产出、警告消失后再启用 `--strict` 作为门禁。

`--include-pending-as-unknown` 只影响 **Unknown 预览**，不会把未审核记录写进正式样本；正式数据集始终只消费 `annotation_status=approved` 且 `annotation_source=human` 的记录。

---

## 7. 输出报告清单

| 文件 | 内容 |
|---|---|
| `01_project_audit.md` | RISM-001 项目现状审计（脚本、数据、embedding、模型、标签结构） |
| `02_implementation_plan.md` | 八阶段实施计划与目录设计 |
| `03_source_audit_report.md` | 源数据字段、ID、关联、引用偏移、只读资产核验 |
| `04_intent_analysis_report.md` | 意图签名、相似问题、同原文异目标、过宽维度、候选方向 |
| `05_ontology_validation_report.md` | 方向目录 / 岗位能力校验结果 |
| `06_dataset_validation_report.md` | 正式数据集校验结果（当前为空集，预期状态） |
| `07_final_report.md` | 最终交付报告（已完成 / 未完成 / 待审核 / 文件清单 / 训练行为结论） |
| `08_rism001_impact_analysis.md` | RISM-001 代码与资产影响分析 |
| `dataset_report.md` / `.json` | 全维度统计 + 安全合规扫描 |
| `*_result.json` | 各阶段机器可读结果（`source_audit` / `ontology_validation` / `dataset_validation` / `build` / `candidate_build`） |
| `rism001_baseline_manifest.json` | RISMv1 全部文件 SHA-256 基线，用于证明零改动 |

---

## 8. 当前完成情况与待人工审核项

### 已完成（阶段一 ~ 八）
- 项目审计、隔离目录、Schema、分类体系、配置层。
- 4 类工具链：审计 / 意图分析 / 目录校验 / 数据集构建与校验。
- 人工审核机制、统计报告、20 项单元测试（全部通过）。
- 本 README、最终报告、影响分析报告。

### 已完成但**需要人工审核**才能投产
| 项目 | 当前数量 | 状态 | 需要处理 |
|---|---:|---|---|
| 追问方向 | 28 | 全部 `candidate` | 逐条审核定义/包含/排除条件 → `approved` 或 `deprecated` |
| 候选 Claim | 45 | 全部 `pending` | 核对 `source_text` 与原文、类型是否准确 |
| 候选 Evidence Gap | 39 | 全部 `pending` | 核对是否确属「信息缺失」而非能力/造假判断 |
| 候选 Strategy | 18 | 全部 `pending` | 核对触发 Claim/Gap、方向、优先级、难度 |
| 方向级标注 | 0 | 无记录 | 人工给出 positive / negative；其余保持 unknown |
| 正式样本 | **0** | `awaiting_human_review` | 上述审核完成后重建 |
| Unknown 预览样本 | 12 | 仅预览，标注全为 unknown | 不是训练数据，仅用于审核界面 |

> 覆盖范围说明：候选 Claim/Gap/Strategy 目前只覆盖 **12 段经历**（配置 `dataset.sample_experience_limit = 12`），是可供人工审核的**首批工作集**，并非 742 段经历的全量转换。需求明确禁止「将全部简历自动转换为已审核标签」，因此刻意不做全量自动标注。

### 明确未完成（本次任务范围外）
模型训练、RISM-002 Embedding、新 multi-hot 标签矩阵、数据集划分、RISM-001 MLP/pos_weight/训练参数调整、新模型评估、自动生成自然语言面试问题、自动批准新方向。

---

## 9. 链路有效性验证

在**不触碰正式审核文件**的前提下，用临时目录注入「显式人工审核 fixture」（2 个方向 approved + 1 段经历内 3 Claim / 3 Gap / 1 Strategy + 人工 positive/negative 方向标注）做过端到端验证：

- 构建产出 **1 条合格正式样本**，`validate_dataset.py` 校验 **0 错误 0 警告**；
- `negative_directions_created = 0`（Negative 全部来自人工记录，未自动产生）；
- 未审核策略被正确拒绝；
- 验证结束后临时目录已删除，`data/annotations/` 与 `data/processed/` 仍保持 0 行。

这证明：只要人工审核记录真实写入，构建链路即可产出合格数据；**当前空集完全由「尚无审核记录」这一合规约束造成**。

---

## 10. 测试

```bash
cd /Users/zhengrui/Documents/computer_programme/AI-recruitment/RISMv2
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/rism002 -p 'test_*.py' -v
```

20 项覆盖需求 §11 的全部 15 项，另加 5 项：原文子串真实性、Gap 不指控造假、Strategy 可追溯、ontology_version 一致性、LLM/隐私默认关闭。测试用临时目录构造 fixture，不读写正式源数据；`PYTHONDONTWRITEBYTECODE=1` 避免生成 `__pycache__`。

---

## 11. 已知限制

1. 正式数据集为空是**预期状态**，需人工审核后才有训练样本。
2. 28 个方向由历史问题的「问题类型 × 一级维度」组合归纳，是**统计归纳 + 规则命名**，语义精确度需人工逐条校准；`applicable_position_families` 目前由经验分布推导，不是岗位能力的因果判断。
3. 岗位能力目录只含 **8 个岗位族 / 24 条能力**，按需求允许第一阶段不覆盖所有行业岗位。
4. 相似问题识别基于字符 n-gram 骨架与「同原文不同考察目标」的可判定信号，不等同于语义向量聚类；不做外部 Embedding 调用。
5. 源数据为 100 份试验简历（`0.1.0-pilot` 规模）复制过来的 RISM-001 数据，不是 5000 份全量；RISM-002 结论的规模受此约束。
6. 报告中的「安全扫描」为 AST 级静态检查（真实 import / 训练调用），不是运行时行为监控。
7. 审核工具一次一条，没有批量审核接口——这是刻意的合规设计，大批量审核需人工逐条执行或自行扩展带审计日志的批处理。

---

## 12. 如何继续（下一步）

1. 打开 `data/annotations/human_review_template.jsonl` 与 `outputs/rism002/04_intent_analysis_report.md`，逐条审核 28 个方向。
2. 用 `record_review.py` 写入审核决定（务必带 `--confirm-human-review`）。
3. 审核 Claim / Gap / Strategy 与方向级标注。
4. 重跑 `build_dataset.py --validate` → `validate_dataset.py --strict` → `dataset_report.py`。
5. 若方向定义需要修改，**只改中文名称与定义，不复用/篡改 `direction_id`**；废弃用 `deprecated` 而非删除，保证 ID 稳定。
6. 之后才进入后续版本：Embedding、multi-hot 标签矩阵、数据划分、模型训练（本次全部禁止）。

---

**最后再次确认：本仓库的 RISM-002 部分不含任何模型训练代码，未产生任何模型训练行为，未修改 RISM-001 的任何文件。**
