# RISM-001 与 RISM-002 代码影响分析报告

> 分析时间：2026-11-14 17:32 (GMT+8)
> 分析对象：`AI-recruitment/RISMv1/`（冻结基线）与 `AI-recruitment/RISMv2/` 中的 RISM-001 原有资产
> 关联报告：`01_project_audit.md`、`07_final_report.md`、`dataset_report.md`

---

## 1. 结论（先给答案）

| 问题 | 结论 |
|---|---|
| 是否修改过 RISM-001 的任何 Python 脚本？ | **否** |
| 是否覆盖过模型权重 / Embedding / 标签矩阵 / 数据划分文件？ | **否** |
| 是否修改过原始 JSONL 数据？ | **否** |
| 是否运行过任何会原地写入的 RISM-001 脚本？ | **否** |
| 是否发生过模型训练、推理、Embedding 生成、评估、划分？ | **否** |
| 是否新增了会影响 RISM-001 运行时行为的公共模块改动？ | **否** |
| RISM-001 是否仍能按原方式运行？ | **是，理论上完全不受影响**（本次未实际运行以遵守禁令） |

**证据**：`outputs/rism002/rism001_baseline_manifest.json` 记录 `RISMv1/` 全部 35 个文件的 SHA-256 与大小；`data/raw/source_manifest.json` 记录 `RISMv2/` 中 14 个只读资产的指纹。任务结束时复算：

- `dataset_report.safety.rism001_baseline_changed = []`
- `dataset_report.safety.readonly_source_changed = []`
- `dataset_validation.statistics.readonly_assets_changed = []`
- 单元测试 `test_14_build_never_modifies_rism001_files` 通过

即 **RISM-001 零字节改动**。

---

## 2. 环境变化与根目录决策（影响范围前提）

任务书假定 RISM-001 位于「当前项目」。实测：

1. 会话工作区 `AI-recruitment/dataset/` 是此前的**模拟简历数据集构建项目**（纯标准库、无模型），不含 `data/`、`embeddings/`、`models/`、`outputs/`。
2. 真正的 RISM-001 位于上级目录 `AI-recruitment/RISM/`。
3. 审计期间该目录**被外部进程（非本任务）拆分**为 `RISMv1/` 与 `RISMv2/`，二者 `diff -rq` 无差异，各 35 文件、约 7.5 MiB；原 `RISM/` 不再存在。

因此采用：
- **冻结基线** `RISMv1/`：全程零写入，仅用于哈希比对。
- **开发根** `RISMv2/`：RISM-001 原有 35 个文件同样**不修改**；RISM-002 全部为新增文件，放在独立子目录。

> 该拆分是外部环境变化，**不是本任务对 RISM-001 的修改**。本任务没有创建、删除或重命名 `RISM/`、`RISMv1/`、`RISMv2/` 中的任何旧文件。

如需换根目录，只改 `configs/rism002.json → project_root`；所有新脚本基于 `__file__` 与配置定位，不依赖 cwd，也不会因此写向旧资产。

---

## 3. 逐文件影响矩阵

### 3.1 RISM-001 脚本（全部 只读 / 未执行 / 未修改）

| 脚本 | 行数 | 原写入目标 | RISM-002 的影响 |
|---|---:|---|---|
| `prepare_data.py` | — | 不存在 | 无 |
| `audit_dataset.py` | 215 | `data/training_samples.jsonl` | 未执行、未修改；RISM-002 只读其**产物** |
| `build_multilabel_dataset.py` | 198 | `data/multilabel_samples.jsonl` | 未执行、未修改；只读其产物做盘点 |
| `generate_labels.py` | 68 | `embeddings/labels.npy` | 未执行、未修改；**标签矩阵零改动** |
| `generate_embeddings.py` | 113 | `embeddings/*.npy`, `metadata.json` | 未执行、未修改；**未生成任何 Embedding** |
| `split_dataset.py` | 117 | `split_indices.npz`, `split_metadata.json` | 未执行、未修改；**划分文件零改动** |
| `dataset.py` | 24 | 无 | 未修改 |
| `models/rism_model.py` | 25 | 无 | 未修改；MLP `1024→128→15` 结构保持不变 |
| `train.py` | 273 | `outputs/best_model.pth` | **未执行**；权重零改动；pos_weight、early stopping、BCEWithLogitsLoss 全部未调整 |
| `evaluate.py` | 291 | 无 | 未执行、未修改 |
| `predict.py` | 288 | `outputs/prediction_result.json` | 未执行、未修改；历史推理结果保留 |
| `calculate_pos_weight.py` | 46 | 无 | 未执行、未修改 |
| `check_multilabel_data.py` / `inspect_data.py` / `inspect_label_distribution.py` | 26/81/59 | 无 | 未修改 |
| `test_backward.py` / `test_dataloader.py` / `test_dataset.py` / `test_embedding.py` / `test_loss.py` / `models/test_model.py` | 21~77 | 无 | 未执行、未修改 |
| `input_resume.json` | — | — | 未修改 |

**明令禁止运行的 7 个写入型脚本**（`audit_dataset.py`、`build_multilabel_dataset.py`、`generate_embeddings.py`、`generate_labels.py`、`split_dataset.py`、`train.py`、`predict.py`）本次**一个都没有运行**。

### 3.2 原始数据（只读）

| 文件 | 行数 | 影响 |
|---|---:|---|
| `data/resumes.jsonl` | 100 | 只读；仅提取 `resume_id` / `candidate_id` / `target_position` / `position_id` / `family` / `career_level` |
| `data/resume_experiences.jsonl` | 742 | 只读；`original_content` 作为所有 `source_text` 的唯一合法出处 |
| `data/interview_questions.jsonl` | 1035 | 只读；用于意图分析与 `reference.original_text` 锚点 |
| `data/question_chains.jsonl` | 300 | 只读；RISM-001 完全未使用，RISM-002 用于追问深度与 trigger 条件 |
| `data/training_samples.jsonl` | 1035 | 只读盘点 |
| `data/multilabel_samples.jsonl` | 471 | 只读盘点 |

### 3.3 Embedding / 标签 / 划分 / 权重（只读，零改动）

| 文件 | 实测规格 | 影响 |
|---|---|---|
| `embeddings/experience_embeddings.npy` | `(471, 512) float32` | 只读 `.npy` 头，**不加载数组、不需要 numpy** |
| `embeddings/job_embeddings.npy` | `(471, 512) float32` | 同上 |
| `embeddings/labels.npy` | `(471, 15) float32` | 同上；标签矩阵未重建 |
| `embeddings/metadata.json` | `resume_ids` / `experience_ids` / `labels` / `label_names`(15) | 只读；15 维字母序标签作为兼容层的权威来源 |
| `embeddings/split_indices.npz` | `train/val/test_indices` | 只读成员名；未重新划分 |
| `embeddings/split_metadata.json` | 70/15/15 份简历 ID | 只读 |
| `outputs/best_model.pth` | 535035 字节 `state_dict` | 未打开写入、未加载、未覆盖 |
| `outputs/prediction_result.json` | 2740 字节 | 未修改 |

---

## 4. 依赖与运行时影响

| 维度 | RISM-001 | RISM-002 | 影响 |
|---|---|---|---|
| Python | `.venv` 3.12（含 numpy/torch/transformers/sentence-transformers） | 系统 `python3` 3.13，**纯标准库** | 不共享依赖、不激活对方环境、不 import 对方模块 |
| 配置文件 | 无（全部硬编码字面量） | `configs/rism002.json` + `rism002_taxonomy.json` | 新增独立配置，不向旧脚本注入变量 |
| 路径定位 | 相对路径、隐含 cwd = 项目根 | 基于 `__file__` + 配置 | 不依赖也不改变 cwd 语义 |
| 包导入 | `models/`、`dataset.py` 顶层模块 | 独立包 `rism002.*` 与 `scripts.rism002.*` | 无命名冲突，无 `sys.modules` 覆盖；测试只在 `sys.path` 中插入 RISMv2 根 |
| 随机种子 | `42`（划分） | `configs/rism002.json → seed` 独立 | 不改动全局 RNG 状态，不影响 RISM-001 可复现性 |
| 输出路径 | `data/`、`embeddings/`、`outputs/` 根层 | `data/{raw,ontology,intermediate,annotations,processed}/`、`outputs/rism002/` | 目录不重叠；唯一同名父目录是 `data/` 与 `outputs/`，但写入的是新增子目录与新增文件名 |

> 唯一的「共享」是 RISM-002 会**读取** RISM-001 的 4 份源 JSONL 作为历史数据来源（需求 §6 明确要求「优先利用现有数据」）。这是只读引用，不构成修改。

---

## 5. 语义与标签体系影响（兼容性分析）

### 5.1 保留兼容层，不改动预测目标

RISM-002 完整保留 15 个一级维度，且顺序与 `embeddings/metadata.json["label_names"]` 的**字母序完全一致**：

```
achievement_verification, business_understanding, data_evidence, innovation,
leadership, learning_ability, personal_contribution, problem_solving,
professional_depth, project_management, reflection, risk_awareness,
teamwork, technical_decision, technical_implementation
```

因此 `labels.npy` 的列语义、`best_model.pth` 的 15 个输出单元、RISM-001 的评估代码**全部保持有效**。RISM-002 没有新增、删除、重排或改名任何一级维度。

### 5.2 RISM-002 主动规避的 10 个 RISM-001 已知问题

| # | RISM-001 现状 | RISM-002 的处理 | 是否影响 RISM-001 |
|---|---|---|---|
| 1 | `generate_labels.py` 全零初始化，未出现方向 = Negative | 引入 `unknown` 三态，未出现方向**绝不**转 negative | 否（新体系独立） |
| 2 | `audit_dataset.py` 丢弃 `secondary_dimensions` | 回收为意图分析补充信号 | 否 |
| 3 | `question_chains.jsonl` 完全未用 | 用于追问深度 / 递进 / `follow_up_triggers` | 否 |
| 4 | 15 维过宽 | 建立二级方向，与一级多对多（14/28 方向含 ≥2 父维度） | 否 |
| 5 | 训练侧 `normalize_embeddings=True`，`predict.py` 未设置 | 仅记录，**不在本任务修复** | 否 |
| 6 | 脚本隐含 cwd | RISM-002 一律基于 `__file__` + 配置 | 否 |
| 7 | `split_dataset.py` 硬断言 471/100/512/15 | 新数据集不复用旧划分、不重算 | 否 |
| 8 | 无 requirements / 配置 / README | RISM-002 补齐独立配置与 `README_RISM002.md` | 否 |
| 9 | `test_indices` 存在但 `evaluate.py` 只评估 val | 仅记录，未处理 | 否 |
| 10 | `metadata.json` 缺模型名 / 归一化标志 / 种子 | RISM-002 产物带 `ontology_version` 与生成元信息 | 否 |

> 第 5、9 项是 RISM-001 的既有缺陷，**本任务按禁令未修改**；若未来要修复，应作为独立的 RISM-001 维护任务处理，并与本数据集体系解耦。

### 5.3 特别说明：742 段经历中 271 段从未被提问

这是「不得把未出现方向自动认定为 Negative」的现实依据。RISM-001 的 multi-hot 把 471 个经历中未命中的维度全置 0；RISM-002 则把「没有判断」显式记为 `unknown`，且 `negative` 只能由人工在 `direction_annotations` 中给出。**两套标签语义不同，不能混用、不能互相覆盖**。

---

## 6. 本次执行的写入清单（全部为新增路径）

```
新增（RISMv2 内）：
  README_RISM002.md
  configs/rism002.json, configs/rism002_taxonomy.json
  rism002/**（6 子包，17 个 .py：10 个功能模块 + 7 个 __init__.py；另 1 个 definitions.json）
  scripts/rism002/**（9 个 .py + __init__.py）
  tests/rism002/**（1 个测试文件 + __init__.py）
  data/raw/source_manifest.json
  data/ontology/*.json（2）
  data/intermediate/*.jsonl / *.json（6）
  data/annotations/*.jsonl（5，其中 4 个为空文件）
  data/processed/rism002_samples.jsonl（空文件）
  outputs/rism002/**（报告与结果 JSON，共 16 个）

未写入（明确禁止）：
  RISMv1/**（35 文件）
  RISMv2/data/*.jsonl（6 个源数据）
  RISMv2/embeddings/**（6 个资产）
  RISMv2/outputs/best_model.pth、prediction_result.json
  RISMv2/*.py（所有 RISM-001 脚本）
  RISMv2/models/**
```

> `data/annotations/` 与 `data/processed/` 下创建了**空的占位文件**（0 行），用于明确「尚未审核」状态；它们不与任何 RISM-001 文件同名，也不会被 RISM-001 脚本读取。

---

## 7. 风险与残留事项

| 风险 | 等级 | 说明 / 缓解 |
|---|---|---|
| RISM-002 与 RISM-001 共用 `data/`、`outputs/` 父目录 | 低 | 实际写入均为新增子目录 / 新文件名；配置中 `readonly_assets` 显式列禁写，脚本按哈希复核 |
| 未来若把 `project_root` 指到 `RISMv1/` | 中 | 配置允许改根，可能误写基线；建议保持 `RISMv1` 只读权限，或在配置中增加根路径黑名单 |
| 人工审核阶段需要写入 `data/annotations/` | 低 | 审核工具一次一条、强制人工确认，且有 `human` 来源校验；不会反写源数据 |
| `question_chains.jsonl` 被 RISM-002 使用而 RISM-001 未使用 | 低 | 只读，不改变 RISM-001 行为 |
| 外部曾把 `RISM/` 拆分为 v1/v2 | 提示 | 属环境变化，非本任务操作；如用户合并目录，需重新核对 `project_root` 与基线指纹 |
| RISM-001 既有缺陷（训练/推理归一化不一致、只评估 val）未修复 | 提示 | 按本次禁令刻意保留，建议另立维护任务 |

---

## 8. 复核方法（可重复执行）

```bash
cd /Users/zhengrui/Documents/computer_programme/AI-recruitment/RISMv2

# 1) 统计报告内含安全扫描：基线改动 / 只读源改动 / AST 级训练代码命中 / LLM 状态
python3 scripts/rism002/dataset_report.py
python3 -c "import json; d=json.load(open('outputs/rism002/dataset_report.json')); print(json.dumps(d['safety'],ensure_ascii=False,indent=2))"

# 2) 单元测试第 14 / 15 项
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/rism002 -p 'test_*.py' -v

# 3) 直接比对 RISMv1 基线哈希
python3 -c "
import json,hashlib,os
m=json.load(open('outputs/rism002/rism001_baseline_manifest.json'))
bad=[f for f,r in m['files'].items()
     if not os.path.exists(os.path.join(m['baseline_root'],f))
     or hashlib.sha256(open(os.path.join(m['baseline_root'],f),'rb').read()).hexdigest()!=r['sha256']]
print('changed:', bad or 'NONE')
"
```

三项均应输出「NONE / [] / 测试通过」。

---

## 9. 最终判定

**RISM-001 与 RISM-002 在代码、配置、数据、输出四个层面完全隔离；本次开发对 RISM-001 的影响为零。** 未修改任何旧文件、未覆盖任何模型权重或 Embedding / 标签 / 划分资产、未运行任何训练或推理脚本、未发生任何模型训练行为。RISM-001 的 15 维标签顺序与语义被原样保留为兼容层，其现有模型与评估结果继续有效。
