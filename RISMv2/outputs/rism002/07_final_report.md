# RISM-002 最终交付报告

> 生成时间：2026-11-14 17:32 (GMT+8)
> 版本：`RISM-002.1` ｜ 开发根：`AI-recruitment/RISMv2/` ｜ 冻结基线：`AI-recruitment/RISMv1/`
> 数据集状态：`awaiting_human_review`（**正式样本 0 条，属预期合规状态**）

---

## 结论摘要

本次任务按需求 §13 的八个阶段顺序全部执行完毕，未跳阶段、未在下层阶段失败时继续构建。**RISM-002 已建成一套结构清晰、语义准确、可审核、可追溯的数据集体系与处理工具链**；**没有训练任何模型，没有修改 RISM-001 的任何文件**。

最需要向交付对象说明的一点：
> `data/processed/rism002_samples.jsonl` 当前为 **0 行**。这不是构建失败，而是硬性合规约束的直接结果——28 个追问方向全部是 `candidate`、人工审核记录全部为空，需求规定「未经审核的候选结果不得自动进入正式训练数据集」，因此构建器主动产出空集并标记 `awaiting_human_review`。构建链路的正确性已用临时人工审核 fixture 端到端验证（§6）。

---

## 一、已完成的功能

| 阶段 | 交付内容 | 结果 |
|---|---|---|
| 一 项目审计与计划 | `01_project_audit.md`、`02_implementation_plan.md`、`rism001_baseline_manifest.json` | 完成。确认 RISM-001 已拆分为 `RISMv1`（冻结基线）与 `RISMv2`（开发副本，二者 `diff -rq` 无差异），确立 RISMv2 为开发根、RISMv1 全程只读 |
| 二 Schema 与隔离目录 | `configs/` 2 份 JSON、`rism002/` 6 个子包、`data/{raw,ontology,intermediate,annotations,processed}/`、`scripts/rism002/`、`tests/rism002/`、`outputs/rism002/` | 完成。Schema 自检 0 错误；纯标准库，无新增依赖 |
| 三 原始数据审计 | `audit_source_data.py` + `validators/source_audit.py` + `03_source_audit_report.md` | 完成。100 简历 / 742 经历 / 1035 问题 / 300 追问链，ID 唯一、关联 0 孤儿、**1035 条原文引用与字符偏移 100% 通过**、14 个只读资产零改动 |
| 四 历史意图分析 | `analyze_question_intents.py` + `analyzers/intent.py` + `04_intent_analysis_report.md` | 完成。28 个意图签名、1234 对相似问题、759 对「同原文不同考察目标」、9 个语义过宽一级维度、28 个候选方向；**LLM 全程关闭** |
| 五 方向目录与校验 | `build_ontology.py`、`validate_ontology.py` + 2 份 ontology 文件 + `05_ontology_validation_report.md` | 完成。28 方向（14 个多父维度、最多 3 个父维度）、24 条岗位能力 / 8 岗位族 / 136 条能力-方向关联；ID 唯一、维度引用有效、0 循环依赖、**0 错误 0 警告** |
| 六 数据结构与构建 | `prepare_candidates.py`、`build_dataset.py`、`validate_dataset.py`、`dataset_validator.py` + 4 类候选文件 | 完成。45 Claim / 39 Gap / 18 Strategy / 12 Unknown 预览全部 `pending`；构建器只消费人工 approved 记录；端到端 fixture 验证通过（§6） |
| 七 审核机制与统计 | `record_review.py`、`dataset_report.py` + `dataset_report.md/.json` | 完成。审核工具强制 `--confirm-human-review` + 审核员 + 理由，缺一拒绝；AST 级训练扫描 0 命中、基线 0 改动、隐私开关全部关闭 |
| 八 测试与文档 | `tests/rism002/test_rism002.py`（20 项）、`README_RISM002.md`、本报告、`08_rism001_impact_analysis.md` | 完成。**20/20 测试通过**（15.04s） |

### 关键合规实现（逐条对照需求）

| 约束 | 实现位置 | 验证方式 |
|---|---|---|
| 不得删除/覆盖 RISM-001 原始数据、权重、Embedding、标签矩阵、划分文件 | `configs/rism002.json → readonly_assets` + SHA-256 基线比对 | `dataset_report.safety.rism001_baseline_changed = []`、`readonly_source_changed = []`；测试 14 |
| 不直接修改旧版文件，优先新增独立模块 | 所有新增代码在 `rism002/`、`scripts/rism002/` | 影响分析报告 §3 |
| 不假设字段，读取实际数据验证 | 阶段一、三实测字段与枚举 | 源审计报告记录每个字段的 100% 填充率 |
| 未审核 AI 输出不得标高可信度标签 | `review.auto_approve=false`、`approved_requires_sources=["human"]` | 测试 8、测试 20 |
| 未出现方向不得自动转 Negative | `review.default_label_status="unknown"`、`negative_requires_reviewed=true` | 测试 9、`build_result.negative_directions_created = 0` |
| 不调用外部 LLM API | `llm.enabled=false`；`--enable-llm` + `--confirm-external` 双开关且默认拒绝 | 测试 20、`llm_used: false` |
| 不训练模型 | 无 torch / trainer / Embedding 生成代码 | AST 级静态扫描 0 命中；测试 15 |
| Claim `source_text` 不得编造 | 真实子串 + 字符定位 | 测试 16 |
| Gap 不代表造假 | 描述文案与校验器措辞检查 | 测试 17 |
| Strategy 必须可追溯到 Claim/Gap | `trigger_claim_ids` / `trigger_gap_ids` 引用校验 | 测试 18 |
| 一级维度与二级方向多对多，不强制合并 | `parent_dimensions` 数组，14 个方向含 ≥2 父维度 | 测试 13、目录统计 |
| 日志/报告不输出个人信息 | `privacy` 四项开关 | `dataset_report.safety.privacy_flags` |
| 历史问题只作 Positive 候选 | `annotation_source=historical_question`、`status=candidate` | 候选方向文件全量校验 |

---

## 二、尚未完成的功能（本次任务范围外）

严格按需求 §12，以下**全部未做，且不应在本阶段做**：

1. 未训练 PyTorch 模型（RISM-002 无模型代码，RISM-001 MLP 未改动）。
2. 未生成 RISM-002 Embedding，未调用 `BAAI/bge-small-zh-v1.5`。
3. 未创建新的 Multi-hot 标签矩阵。
4. 未执行训练 / 验证 / 测试集划分。
5. 未修改 RISM-001 的 MLP 结构、pos_weight、训练参数。
6. 未执行新模型评估、未调用 `predict.py`。
7. 未自动生成自然语言面试问题（策略记录的是**考察目标与证据需求**，不是问题文本）。
8. 未自动批准任何新追问方向（28 个全部 `candidate`）。
9. 未把 100 份简历（742 段经历）自动转换为已审核标签。
10. 未启用外部 LLM，未做语义向量聚类。

此外：岗位能力目录只覆盖 **8 个岗位族 / 24 条能力**（需求 §7 允许第一阶段不覆盖所有行业岗位）；候选 Claim/Gap/Strategy 只覆盖 **12 段经历**（`dataset.sample_experience_limit=12`），是首批人工审核工作集。

---

## 三、需要人工审核的数据（明确清单）

| # | 文件 | 记录数 | 当前状态 | 人工需要做什么 |
|---|---|---:|---|---|
| 1 | `data/ontology/investigation_directions.json` | 28 | 全部 `candidate` | 逐条审阅 `definition` / `inclusion_criteria` / `exclusion_criteria` / `evidence_types` / `parent_dimensions` / `applicable_position_families`；决定 `approved` / `deprecated`；可改中文名与定义，**不得篡改 `direction_id`** |
| 2 | `data/intermediate/candidate_directions.jsonl` | 28 | `candidate` + `review.pending` + `annotation_source=historical_question` | 与 #1 对照，确认候选来源是否合理 |
| 3 | `data/intermediate/candidate_claims.jsonl` | 45 | 全部 `pending` | 核对 `source_text` 是否确为经历原文子串、`claim_type` 是否准确、`claim_text` 是否忠实于原文 |
| 4 | `data/intermediate/candidate_gaps.jsonl` | 39 | 全部 `pending` | 确认描述的是「信息缺失」而非能力不足/造假；核对 `related_claim_ids` 与 `source_span` |
| 5 | `data/intermediate/candidate_strategies.jsonl` | 18 | 全部 `pending` | 核对触发 Claim/Gap、`direction_id`、`strategy_type`、`priority`、`difficulty`、递进 `sequence` |
| 6 | `data/annotations/human_review_template.jsonl` | 102 | 审核工作表（仅供参考） | 作为逐条审核的操作清单；**不会自动写入任何结论** |
| 7 | `data/annotations/direction_annotations.jsonl` | 0 | 无记录 | 人工显式给出方向级 `positive` / `negative`；**其余方向保持 `unknown`，不得批量填 negative** |
| 8 | `data/intermediate/rism002_unknown_preview.jsonl` | 12 | 方向标注全部 `unknown` | 仅预览用，不是训练数据；确认 Unknown 语义未被误改 |
| 9 | `data/processed/rism002_samples.jsonl` | 0 | `awaiting_human_review` | 上述审核完成后由 `build_dataset.py` 重建 |

审核入口唯一：`scripts/rism002/record_review.py`，一次一条，必须带 `--annotator`、`--reason`、`--confirm-human-review`。已实测：缺少确认参数时脚本拒绝执行，审核文件保持 0 行。

---

## 四、生成的文件清单

### 4.1 配置与 Schema（4 个核心文件 + 9 个包初始化文件）
```
configs/rism002.json                        主配置
configs/rism002_taxonomy.json               分类体系（15 维 / 9 Claim / 9 Gap / 8 Strategy / 枚举 / 8 岗位族）
rism002/schemas/definitions.json           JSON Schema 实体定义
rism002/schemas/validator.py               轻量 Schema 校验器
rism002/__init__.py 等 9 个包初始化文件（含 scripts/rism002 与 tests/rism002）
```

### 4.2 Python 包（8 个模块）
```
rism002/utils/core.py                      配置、路径、审核块、JSONL 读写、时间
rism002/parsers/jsonl.py                   JSONL / npy 头 / npz 成员只读解析
rism002/reports/render.py                  Markdown 表格渲染
rism002/analyzers/intent.py                历史意图分析
rism002/analyzers/ontology_builder.py      方向目录 / 岗位能力构建
rism002/analyzers/candidate_builder.py     Claim / Gap / Strategy 候选生成
rism002/validators/source_audit.py         源数据审计
rism002/validators/ontology.py             本体校验
rism002/validators/dataset_validator.py    数据集全量校验
```

### 4.3 命令行脚本（9 个）+ 测试（1 个）
```
scripts/rism002/audit_source_data.py
scripts/rism002/analyze_question_intents.py
scripts/rism002/build_ontology.py
scripts/rism002/validate_ontology.py
scripts/rism002/prepare_candidates.py
scripts/rism002/record_review.py
scripts/rism002/build_dataset.py
scripts/rism002/validate_dataset.py
scripts/rism002/dataset_report.py
tests/rism002/test_rism002.py               20 项单元测试
```

### 4.4 数据文件
```
data/raw/source_manifest.json                        只读资产 SHA-256 基线
data/ontology/investigation_directions.json          28 方向
data/ontology/position_competencies.json             24 能力 / 8 岗位族
data/intermediate/question_intent_analysis.json      意图分析结果
data/intermediate/candidate_directions.jsonl         28
data/intermediate/candidate_claims.jsonl             45
data/intermediate/candidate_gaps.jsonl               39
data/intermediate/candidate_strategies.jsonl         18
data/intermediate/rism002_unknown_preview.jsonl      12
data/annotations/human_review_template.jsonl        102（审核工作表）
data/annotations/{claims,evidence_gaps,strategies,direction_annotations}.jsonl   0（空，待人工）
data/processed/rism002_samples.jsonl                 0（空，待人工）
```

### 4.5 报告与结果 JSON
```
outputs/rism002/01_project_audit.md
outputs/rism002/02_implementation_plan.md
outputs/rism002/03_source_audit_report.md
outputs/rism002/04_intent_analysis_report.md
outputs/rism002/05_ontology_validation_report.md
outputs/rism002/06_dataset_validation_report.md
outputs/rism002/07_final_report.md              ← 本文件
outputs/rism002/08_rism001_impact_analysis.md
outputs/rism002/dataset_report.md / .json
outputs/rism002/source_audit_result.json
outputs/rism002/ontology_validation_result.json
outputs/rism002/dataset_validation_result.json
outputs/rism002/build_result.json
outputs/rism002/candidate_build_result.json
outputs/rism002/rism001_baseline_manifest.json
RISMv2/README_RISM002.md                        使用说明
```

---

## 五、每个脚本的运行方式

统一在 `RISMv2/` 根目录执行；所有脚本支持 `--config <path>` 覆盖主配置。

```bash
cd /Users/zhengrui/Documents/computer_programme/AI-recruitment/RISMv2

# ① 原始数据只读审计（--strict：有警告也非零退出；--json-only：不写 Markdown）
python3 scripts/rism002/audit_source_data.py --strict

# ② 历史追问意图分析（默认纯本地规则；外部 LLM 需配置开启 + 双确认，本任务未启用）
python3 scripts/rism002/analyze_question_intents.py --strict
#   可选：--enable-llm --confirm-external（会先打印将发送的字段与目标服务，未授权则拒绝执行）

# ③ 构建方向目录与岗位能力目录
python3 scripts/rism002/build_ontology.py

# ④ 目录校验
python3 scripts/rism002/validate_ontology.py --strict

# ⑤ 生成待审核候选 + 审核工作表 + Unknown 预览
python3 scripts/rism002/prepare_candidates.py

# ⑥ 人工逐条审核（示例：批准方向 / 批准 Claim / 记录 Negative）
python3 scripts/rism002/record_review.py --entity direction \
  --id hist_data_verification__data_evidence --decision approved \
  --annotator human_01 --reason "已核对定义与排除条件" --confirm-human-review
python3 scripts/rism002/record_review.py --entity claim \
  --id CLM_037707_01 --decision approved \
  --annotator human_01 --reason "已核对原文与偏移" --confirm-human-review
python3 scripts/rism002/record_review.py --entity direction_annotation \
  --experience-id EXP_00037707 --direction-id hist_data_verification__data_evidence \
  --label-status negative --annotator human_01 --reason "人工确认不适用" --confirm-human-review

# ⑦ 构建正式数据集（--validate 构建后立即校验）
python3 scripts/rism002/build_dataset.py --validate
#   可选：--include-pending-as-unknown 只影响 Unknown 预览，不放松正式集门槛

# ⑧ 独立全量校验
python3 scripts/rism002/validate_dataset.py
#   可选：--samples <path> 指定样本文件；--no-report 只写 JSON
#   注意：当前空集状态会给出 1 条「预期警告」，因此 --strict 会返回 3；
#         正式样本产出后（警告消失）再启用 --strict 做门禁。

# ⑨ 统计与安全合规报告
python3 scripts/rism002/dataset_report.py

# ⑩ 完整单元测试（20 项）
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/rism002 -p 'test_*.py' -v
```

`--entity` 取值：`direction` / `claim` / `gap` / `strategy` / `direction_annotation`；`--decision` 取值：`approved` / `rejected`。

---

## 六、链路有效性验证（为什么空集不是缺陷）

在**完全不触碰正式审核文件**的前提下，用临时目录构造「显式人工审核 fixture」：2 个方向设为 `approved`（`annotation_source=human`）、1 段经历内的 3 条 Claim / 3 条 Gap / 1 条 Strategy 全部人工 approved、写入 1 条人工 `positive` + 1 条人工 `negative` 方向标注。

结果：
- `build_dataset.py` 产出 **1 条合格正式样本**（3 Claim / 3 Gap / 1 Strategy）；
- `validate_dataset.py`：**0 错误 0 警告**；
- `negative_directions_created = 0` —— Negative 全部来自人工记录，未由「未出现」推导；
- 未审核策略被正确拒绝；
- 临时目录验证后已删除，`data/annotations/` 与 `data/processed/` 保持 0 行。

结论：构建链路已验证可用；当前空集**完全由「尚无人工审核记录」这一合规约束造成**。

---

## 七、关键统计

| 指标 | 数值 |
|---|---|
| 源数据 | 100 简历 / 742 经历 / 1035 问题 / 300 追问链 / 471 多标签样本 |
| 原文引用偏移校验 | 1035 / 1035 通过，0 错误 |
| 意图分析 | 28 意图签名、1234 相似问题对、759 同原文异目标对、9 个过宽一级维度 |
| 方向目录 | 28 方向（28 `candidate` / 0 `approved`）、14 多父维度、最多 3 父维度、59 条关联、0 循环依赖 |
| 岗位能力 | 8 岗位族、24 能力、136 条能力-方向关联 |
| 候选数据 | 45 Claim（9 类）/ 39 Gap（9 类）/ 18 Strategy（8 类），全部 `pending` |
| 正式数据集 | **0 样本**，`dataset_status=awaiting_human_review` |
| 校验 | 源审计 0 错误、本体 0 错误 0 警告、数据集 0 错误 1 预期警告（空集提示） |
| 单元测试 | **20 / 20 通过**（15.04s） |
| 只读资产改动 | **0** |
| 训练代码命中（AST） | **0** |
| LLM 调用 | **0**（`llm_used: false`） |

---

## 八、是否修改过 RISM-001

**没有。**

- `RISMv1/`（冻结基线）：`outputs/rism002/rism001_baseline_manifest.json` 记录了全部文件的 SHA-256；多次比对结果 `rism001_baseline_changed = []`，文件数与内容完全一致。
- `RISMv2/` 中的 RISM-001 原有文件（`prepare_data.py`、`audit_dataset.py`、`build_multilabel_dataset.py`、`generate_labels.py`、`generate_embeddings.py`、`split_dataset.py`、`dataset.py`、`models/rism_model.py`、`train.py`、`evaluate.py`、`predict.py`、`data/*.jsonl`、`embeddings/*`、`outputs/best_model.pth` 等）：`readonly_source_changed = []`，**零字节改动**。
- RISM-002 全部为**新增**文件，未对任何旧文件做编辑、重命名或删除；未新增公共模块的修改。
- 未覆盖第一版 Embedding、标签矩阵 `labels.npy`、划分文件 `split_indices.npz`、模型权重 `best_model.pth`、历史输出 `prediction_result.json`。
- 详见 `08_rism001_impact_analysis.md`。

---

## 九、是否产生任何模型训练行为

**没有。**

- RISM-002 全部代码为纯标准库数据工程代码；`dataset_report.py` 的 AST 级检测（真实 `import` 节点与训练调用节点）结果 `training_code_hits = []`。
- 未 import `torch` / `transformers` / `sentence_transformers`，未调用 `model.train()` / `loss.backward()` / `optimizer.step()`。
- 未运行 `train.py` / `evaluate.py` / `predict.py` / `generate_embeddings.py` / `build_multilabel_dataset.py` / `split_dataset.py` / `calculate_pos_weight.py`。
- 未生成任何新 Embedding 或 multi-hot 标签矩阵，未做数据集划分。
- 唯一的「类训练」操作是单元测试与临时 fixture 验证，均为纯 JSON 读写，不涉及张量或梯度。

---

## 十、后续建议（不在本次任务执行）

1. 按 §3 清单完成 28 个方向与 102 条审核工作表的人工审核，再重建正式数据集。
2. 方向定义调整时保持 `direction_id` 稳定；废弃用 `deprecated` 而非删除。
3. 若需扩大候选覆盖，修改 `configs/rism002.json → dataset.sample_experience_limit`，但仍须逐条人工审核，不得批量批准。
4. 之后的版本再考虑：RISM-002 Embedding、方向级 multi-hot 标签矩阵（必须显式区分 positive / negative / unknown 三态，不得把 unknown 折叠成 negative）、数据集划分、模型训练与评估。
5. 若未来启用外部 LLM，须先完成脱敏、明确告知发送数据字段与目标服务、取得用户显式授权，并在报告中留痕。

---

**最终确认：本次交付的是 RISM-002 数据集体系与处理工具，不是模型；未训练、未推理、未修改 RISM-001。**
