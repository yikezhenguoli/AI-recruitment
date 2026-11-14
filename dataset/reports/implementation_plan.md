# AI 简历深度追问数据集构建系统 — 第一阶段实施方案

> 文档版本：v1.0　|　生成日期：2026-11-14　|　阶段：第一阶段（项目检查与方案设计）
> 本文件为**设计基线**，后续实现必须与之保持一致；如实现发生调整，须同步更新本文。

---

## 1. 项目现状检查

| 检查项 | 实际结果 |
|---|---|
| 工作目录 | `/Users/zhengrui/Documents/computer_programme/AI-recruitment/dataset` |
| 检查时目录状态 | **完全空目录**，无任何文件、代码、配置、数据 |
| 是否有既有结构需要保留 | 无，因此按需求第八节建议结构新建，不破坏任何既有资产 |
| Python | 3.13.12（系统自带） |
| 第三方依赖 | `yaml / numpy / pandas / faker / jsonschema / matplotlib / tqdm` **全部缺失** |
| 磁盘可用空间 | 约 44 GiB，远大于本数据集预估占用（< 200 MiB） |
| 版本控制 | 无 `.git` |
| 外部 AI 服务 | 未配置、未授权，**默认不调用** |

### 1.1 环境结论（决定技术路线）

1. **纯标准库实现**：不依赖 pip 安装。YAML 配置由 `scripts/lib/config.py` 内置的极简 YAML 子集解析器读取；若环境后续安装 PyYAML 会自动优先使用。
2. **纯本地生成**：不调用任何付费或外部 API，全部由岗位知识库 + 结构化规则 + 固定种子随机组合生成，满足第 12.5 条与第十五节禁止项。
3. **不使用任何模型训练代码**：本阶段仅含数据工程脚本（生成、拆解、校验、统计、报告），不含 PyTorch / Transformer / 推理服务 / 前后端业务系统。

---

## 2. 总体架构与阶段路线

```
阶段一（本文）  项目检查 → Schema 设计 → 30 岗位知识库 → 流水线设计 → 校验机制设计
阶段二          生成 100 份试验数据（覆盖 30 岗位 / 5 年限 / 4 质量型）+ 全量自动校验
阶段三          人工验收（6 份抽样报告）→ 修正生成规则 → 必要时重生成试验数据
阶段四          保留已验收 100 份，分批生成剩余 4900 份，逐批校验 + 断点续跑
阶段五          全量校验 + 最终统计 + 交付验收
```

**当前仅执行到阶段二结束即停止**，因为阶段三是人工验收环节，未经用户确认不得批量生成剩余 4900 份。

### 2.1 流水线（阶段二～五复用同一套代码）

```
build_position_knowledge.py        30 岗位知识库 JSON + 公共素材库
        ↓
generate_candidate_profiles.py     全量 5000 条确定性分配计划（配额精确）→ generation_plan.json
        ↓  select_pilot_ids() 抽取 100 个 ID（全量计划的子集）
generate_resumes.py                按 item_seed 独立生成简历 + 事实句
        ↓
extract_experiences.py             强制经历拆解，建立 resume_id → experience_id → original_content
        ↓
generate_questions.py              事实句级问题生成（引用精确原文 + 字符偏移）
        ↓
generate_question_chains.py        每份 ≥3 条同经历递进追问链
        ↓
validate_dataset.py                全量内容级校验（含 5 项硬性门槛）
        ↓
deduplicate_dataset.py / generate_statistics.py  去重分析与统计报告
        ↓
run_pipeline.py                    分批编排 / 断点续跑 / 日志与状态
```

---

## 3. 核心设计决策：事实句原子化（最关键）

需求第 3 章要求「一个问题 → 一个具体经历单元 → 一段简历原文 → 一个明确追问目的」，且 `reference.original_text` 必须真实出现在对应经历的 `original_content` 中。若先自由生成整段简历文本再做字符串匹配，无法保证引用可追溯，也容易产生泛化问题。

**解决方案：把每段经历描述结构化为若干「事实句」（fact sentence）。**

- 生成器在构造经历时，先产生带类型的句子列表，例如
  `["负责订单履约服务的后端开发。", "针对缓存与数据库双写一致性进行专项优化，接口平均响应时间从 800ms 降低至 200ms。"]`；
- `original_content` = 这些事实句**原样拼接**的结果，不做任何改写；
- 每句话携带内部属性 `fact_type / skill / tool / metric / topic / difficulty`（仅内存中使用，不写入 JSONL）；
- 每道问题**绑定且只绑定一个事实句**，`reference.original_text` 取该句去掉句末标点的结果，并用 `str.find()` 计算真实的 `start_offset / end_offset`；
- `resume_text` 与各结构化数组中的描述，直接使用同一份 `original_content`，因此校验器可验证
  `experience.original_content ⊆ resume.resume_text`。

由此带来的可验证保证：

| 需求条款 | 实现方式 |
|---|---|
| 3.1 原文必须可追溯 | 事实句拼接，简历正文同源 |
| 3.2 每问绑定具体经历 | 生成时直接从 (experience, fact) 派生，不可能脱离 |
| 9.3 引用必须来自该经历原文 | 引用即事实句本身，天然是精确子串 |
| 10.3 禁止跨经历混合 | 一个问题只取一个事实句；校验器再反查其它经历的原文是否出现在问题中 |
| 10.3 禁止泛泛提问 | 所有问题模板强制嵌入 `「原文引用」`，无引用即判不合格 |
| 9.3 偏移量不得伪造 | 由 `str.find()` 真实计算，找不到则置 null |

---

## 4. 数据 Schema 设计

### 4.1 `resumes.jsonl`（每行一份简历）

| 字段 | 类型 | 说明 |
|---|---|---|
| `resume_id` / `candidate_id` | string | `RES_000001` / `CAN_000001` |
| `target_position` / `position_id` / `family` | string | 30 岗位之一 |
| `career_level` / `career_level_label` | string | `fresh/junior/mid/senior/expert` 与中文标签 |
| `total_work_years` | int | 与经历时间线一致 |
| `resume_quality` / `resume_quality_label` | string | `high/normal/vague/contradictory` |
| `basic_info` | object | 虚构姓名、年龄、城市、脱敏联系方式、`is_fictional: true` |
| `education` / `work_experiences` / `project_experiences` / `internship_experiences` / `research_experiences` / `competitions` | array | 每项含 `title / organization / start_date / end_date / original_content`，与经历表同源 |
| `skills` / `achievements` / `certifications` | array | 岗位相关的技能、成果、证书 |
| `resume_text` | string | 完整中文简历文本 |
| `quality_signals` | object | `vague_sentence_count / metric_count / risk_statement_count / quantified_ratio`，供校验器核对质量标签一致性 |
| `generation` | object | `seed / batch_id / generated_at / generator_version` |

> 所有姓名、学校、公司、联系方式均为算法合成的虚构实体，不对应任何真实个人或机构。

### 4.2 `resume_experiences.jsonl`（每行一个经历单元）

严格采用需求 9.2 的字段：`experience_id / resume_id / experience_type / title / organization / start_date / end_date / original_content / key_points / skills_involved / achievements / potential_risks / missing_information`，另增 `fact_count / position_id / career_level / quality_score`（评分见第十一节）。

8 种 `experience_type`：`education / internship / work_experience / project_experience / achievement / skill_application / research / competition`。

### 4.3 `interview_questions.jsonl`（每行一道问题）

严格采用需求 9.3 字段，其中：

- `reference` = `{original_text, start_offset, end_offset}`，`original_text` 为精确子串，偏移为真实字符位置；
- `dimension` 取自 15 个英文标签，`secondary_dimensions` 可选辅助维度；
- `question_type` 取自 10 种类型；
- `reason` 说明「为什么问 / 想核实什么」；
- `expected_investigation` 为期望获得的关键信息列表；
- `priority ∈ {high, medium, low}`，`difficulty ∈ {easy, medium, hard}`；
- `follow_up_questions` 为同经历的后续追问；
- 附加 `quality_score`（0～100，硬性门槛独立判定）。

### 4.4 `question_chains.jsonl`（每行一条追问链）

`chain_id / resume_id / experience_id / root_question_id / dimension / chain_depth / questions[]`，另增 `theme / stop_condition`。
每个 `questions[]` 元素含 `sequence / level / question / purpose / expected_investigation / trigger_condition`；`level` 取自
`fact_confirmation → process_detail → principle_decision → verification_challenge → scenario_migration` 的递进序列。

### 4.5 辅助文件

- `dataset/metadata/generation_plan.json`：5000 条确定性分配计划（**只是计划，不是数据**），保证试验 100 份是最终 5000 份的真子集；
- `logs/generation_state.json`：批次状态、已完成 ID、失败队列，支撑断点续跑；
- `dataset/batches/*.jsonl`：每批独立产物，校验通过后才合并进正式数据文件；
- `logs/generation.log`：生成过程日志。

---

## 5. 30 个岗位知识库设计

每岗位一份 `knowledge_base/positions/<id>.json`，字段：

`position_id / index / position_name / family / core_responsibilities / common_tasks / core_skills / tools / business_scenarios / project_types[] / achievement_metrics / technical_difficulties / work_risks / interview_dimensions / career_level_requirements / probe_topics`。

`project_types[]` 每项含 `name / goal / tech_focus[] / typical_metrics[] / difficulties[]`。当前已生成 **30 岗位 × 4 项目类型 = 120 个结构化项目模板**，每个岗位另含 5～6 条专属成果指标、5～6 条技术难点、4 条工作风险、5 档年限能力阶梯、4 个岗位专属追问话题。

**差异化保证**：

1. 岗位专属项目名、技术栈、指标、难点全部来自各自知识库，禁止跨岗位复用；
2. `interview_dimensions` 为每岗位配置不同的维度权重（如算法工程师偏 `data_evidence / innovation`，软件架构师偏 `technical_decision / leadership`，客户服务偏 `data_evidence / teamwork`）；
3. `probe_topics` 注入问题与追问链，例如 Python 岗的「缓存一致性方案」、财务岗的「月结截止性」、建筑工程岗的「隐蔽工程验收」；
4. 校验器检查「岗位专业词泄漏」：非本岗位的技术词不得出现在该岗位简历的问题中。

---

## 6. 分配计划算法（精确配额）

```
levels    = 按 career_levels.count 展开并洗牌   (1000/1250/1250/1000/500)
qualities = 按 resume_qualities.count 展开并洗牌 (1500/2000/1000/500)
positions = 30 岗位轮转 5000 次后整体洗牌        (每岗位 166~167 份，均 ≥100)
for i in 0..4999:
    slot[i] = (RES_%06d, level[i], quality[i], position[i], item_seed = seed + i*7919)
```

- 洗牌是**排列**操作，不改变各维度计数，因此最终分布与验收表**逐项精确相等**；
- 每份简历使用独立 `item_seed`，单份重生成不影响其它简历，是可复现 + 断点续跑 + 失败单点的前提；
- 试验 100 份采用**分层抽样**：按岗位分层抽取，并贪心补齐 5 个年限档与 4 种质量型，之后按 ID 排序。其 ID 直接来自全量计划，因此第四阶段只需补生成剩余 4900 个 ID。

---

## 7. 简历生成设计

### 7.1 时间线

以 `as_of_date = 2026-10` 为基准月，所有日期格式 `YYYY-MM`：

- 应届：本科 2022-09～2026-06（或硕士 2023-09～2026-06，本科 2019-09～2023-06），**不生成任何正式工作经历**；允许课程项目、毕业设计、科研训练、实习、竞赛；
- 有经验者：`grad_year = 2026 - total_work_years`，教育止于毕业年 6 月，工作经历从毕业年 7 月连续排至 2026-10，按年限切分为 1～3 段，段间不重叠（`contradictory` 类型除外，见 7.2）；
- 年龄由毕业年份推算，与年限档匹配。

### 7.2 四种质量型（不是简单删减，而是不同的文本策略）

| 类型 | 职责边界 | 技术/业务过程 | 量化指标 | 特殊处理 |
|---|---|---|---|---|
| `high` | 明确个人独立负责部分 | 完整实现链路 + 关键决策 + 异常处理 | 95% 事实句带指标并说明测量条件 | 增加决策与复盘句 |
| `normal` | 基本清晰 | 有过程但缺部分细节 | 约 55% | 部分指标无口径说明 |
| `vague` | 使用「参与/协助/相关工作」等笼统表述，个人与团队边界不清 | 20% 有细节 | 8% | `missing_information` 显著增多，问题以 `clarification` 为主 |
| `contradictory` | 存在需核实点 | 中等 | 约 55% | 注入 **1 条** 核实型事实句，类型包括时间重叠、指标缺基准、职责规模不匹配、技术描述与成果不匹配、成果缺解释；并在 `potential_risks` 中标注 |

> 疑点**不等于造假**：数据中不出现「造假/虚假」等结论性标签，只记录「需要进一步核实」，并生成 `risk_investigation` 类问题验证。

### 7.3 多样性

- 每岗位 4 个项目模板 + 事实句模板（每种事实类型 3～6 个句式）+ 数字扰动（对指标中的数值做 ±25% 内扰动，保持语义方向）+ 随机机构名/人名/城市/学校组合；
- 句序、可选从句、技术栈组合随机；
- 校验器统计 `resume_text` 完全重复率与问题模板集中度，超阈值即判不合格。

---

## 8. 经历拆解设计（阶段四，强制前置）

`extract_experiences.py` 读取生成器输出的「事实句级中间结构」，逐条转成经历单元：

- `experience_id = EXP_%06d`，全局唯一，按 `(resume_id, sort_order)` 稳定编号；
- 每段经历独立成单元，不合并不同经历、不把同一经历无意义切碎；
- `key_points` 取自该经历事实句；`skills_involved` 取事实句携带技能 + 岗位技能；`achievements` 取含指标的事实句；
- `potential_risks` 来自知识库 `work_risks` 与注入的核实点；`missing_information` 由事实类型推导（如含指标句但无测量方法 → 「未说明指标测量方法与对比基准」）；
- 输出前断言 `original_content in resume_text`。

---

## 9. 问题生成设计

### 9.1 事实类型 → 问题类型 → 维度

定义 20 种 `fact_type`（`responsibility / tech_stack / tech_implementation / optimization / metric / problem_solved / decision / collaboration / leadership / delivery / achievement / research_method / research_result / competition_role / competition_result / course_project / learning / vague_statement / risk_statement / skill_application`）。

每种事实类型映射到允许的问题类型（如 `metric → data_verification / result_verification / risk_investigation`），每种问题类型再提供 2～3 个主维度变体，每个变体 3 个句式模板。问题由「开场白 × 原文引用 × 追问子句」组合，并注入岗位 `probe_topics`，从而避免模板化且保证专业性。

### 9.2 每份简历的选题约束

- 数量 8～12（配置化）；
- 覆盖 ≥3 个不同 `experience_id`；
- 主维度 ≥4 种，且按岗位 `interview_dimensions` 加权、按年限加权（资深加 `leadership / project_management`，应届加 `learning_ability`）；
- 同一 `(experience_id, 引用, 维度)` 不重复；同一引用最多承载 2 道不同维度的问题；
- 优先顺序：`project_experience > work_experience > internship > achievement > skill_application > research > competition > education`；
- `vague` 简历保证澄清类问题占比，`contradictory` 简历保证核实类问题占比，`high` 简历保证技术深挖与数据核实；
- 问题文本强制包含 `「准确原文」`，`reason` 必须与该引用一致，不引入无原文依据的事实假设。

### 9.3 不同经历的追问策略

由 `config/experience_types.yaml` 的 `focus / preferred_dimensions / preferred_question_types` 驱动，8 类经历各不相同：教育重专业深度与理论应用，实习重个人贡献与成长，正式工作重成果真实性与协作，项目重方案决策与指标依据，成果重口径与可复现性，技能应用重原理与边界，科研重实验设计与局限，竞赛重分工与评价依据。

---

## 10. 追问链设计

- 每份简历选 ≥3 个重要问题作为 `root_question_id`，优先选核心项目、关键成果、模糊或存疑经历；
- 一条链**只取该问题的 `experience_id` 与同一句原文**，5 个层级递进：事实确认 → 过程细节 → 原理/决策 → 验证与挑战 → 场景迁移与反思；
- 每层都带 `purpose / expected_investigation / trigger_condition`，`trigger_condition` 描述「在什么回答情况下适合继续问」，**不生成任何候选人回答**，也不假设回答内容；
- 链级附 `stop_condition`：若候选人已充分说明，可提前结束追问；
- 按根问题类型分 4 种主题（技术、证据、澄清、复盘）使用不同层级句式，避免所有链相同；
- 校验器检查层级顺序、同经历一致性、无重复、无跨经历跳转。

---

## 11. 质量校验机制（独立脚本 `validate_dataset.py`）

### 11.1 五项硬性门槛（任一不过即该问题不合格，不参与加权）

`experience_link_valid` / `reference_exact_match` / `no_generic_question` / `no_cross_experience_mix` / `chain_experience_consistent`，定义见 `config/scoring_rules.yaml`。

### 11.2 检查清单

| 类别 | 主要检查 |
|---|---|
| 基础完整性 | 5000 份（试验阶段 100 份）、四类 ID 唯一、JSONL 可解析、必填字段、全部外键存在 |
| 简历合理性 | 年限与时间线一致、教育时间合理、工作段不重叠（`contradictory` 的标注重叠除外）、应届无正式工作、技能与岗位匹配、成果与级别匹配、质量标签与 `quality_signals` 一致 |
| 经历关联（最高优先级） | experience_id 存在、resume_id 一致、experience_type 一致、`reference.original_text` 为精确子串且偏移量匹配、问题围绕该经历、reason 与引用一致、无原文外事实假设、无跨经历混合、无整份简历级泛问 |
| 问题质量 | 每份 8～12 道、覆盖 ≥3 经历、维度/类型合法、有目的与预期信息、重复率、模板集中度、岗位专业性、中文自然度（无占位符/英文残留/过短） |
| 追问链 | 每份 ≥3 条、关联真实问题、同经历、层级递进、目的明确、无重复、无虚构回答、无跨经历跳转 |
| 多样性 | 岗位/年限/质量分布、15 维度覆盖、10 类型不过度集中、简历与问题重复率、跨岗位专业词泄漏 |

### 11.3 评分

`config/scoring_rules.yaml` 统一管理简历 / 经历 / 问题 / 追问链四类权重（合计 100），硬性门槛独立判定：「即使其它评分较高，只要没有正确关联具体经历，也不能判定为合格」。评分结果写入各记录的 `quality_score`，汇总进入 `quality_report.md`。

---

## 12. 工程机制

- **可配置**：数量、岗位、年限、质量、问题数、链数、维度、难度、种子、批次、阈值全部在 `config/*.yaml`，脚本不硬编码；
- **可复现**：固定 `random_seed = 20261114`，每份简历独立派生种子，同配置同环境结果一致；
- **可断点续跑**：`generation_plan.json` + `generation_state.json` + 每批独立文件；已完成且校验通过的批次跳过；失败 ID 进入 `failed_ids` 可单独重生成；
- **批量**：默认 100 份/批，逐批校验，通过后才合并；
- **日志**：`logs/generation.log` 记录批次开始/结束、数量、校验结果、异常。

---

## 13. 需要新增的文件清单

```
README.md
config/   generation_config.yaml / position_categories.yaml / experience_types.yaml /
          question_dimensions.yaml / question_types.yaml / quality_distribution.yaml /
          scoring_rules.yaml
knowledge_base/positions/*.json (30)   knowledge_base/common/*.json (2)
scripts/lib/  config.py / plan.py / common.py / resume_builder.py / question_engine.py /
              io_utils.py
scripts/      build_position_knowledge.py / generate_candidate_profiles.py /
              generate_resumes.py / extract_experiences.py / generate_questions.py /
              generate_question_chains.py / validate_dataset.py / deduplicate_dataset.py /
              generate_statistics.py / run_pipeline.py
dataset/      resumes/*.jsonl  questions/*.jsonl  metadata/*.json  batches/*.jsonl
reports/      implementation_plan.md / generation_report.md / quality_report.md /
              coverage_report.md / sample_review_report.md / final_acceptance_report.md
logs/         generation.log / generation_state.json
```

---

## 14. 潜在风险与缓解

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| 无第三方依赖 | YAML / 统计 / 图表不可用 | 纯标准库实现；内置 YAML 子集解析器；报告用 Markdown 表格而非图片 |
| 规则生成易模板化 | 训练价值下降 | 120 个岗位项目模板 + 组合式句式 + 数值扰动 + 岗位专属 probe_topics；校验器统计模板集中度并设阈值 |
| 规则生成难以达到「人类撰写」的自然度 | 表达生硬 | 中文简历惯用句式库；校验器检查占位符、残留英文、长度与标点；阶段三人工抽样验收后再批量生成 |
| 引用可追溯性被破坏 | 数据集失效 | 事实句原子化 + 真实字符偏移 + 5 项硬性门槛 |
| 精确配额与岗位 ≥100 冲突 | 验收失败 | 洗牌保持计数不变；轮转保证每岗位 166～167 份 |
| 试验 100 份与最终 5000 份不一致 | 需重做试验 | 试验 ID 从全量计划中分层抽取，是最终真子集 |
| 疑点被误读为造假 | 数据偏倚 | 只标注「需进一步核实」，不出现结论性负面标签 |
| 批次中断 | 数据丢失 | 每批独立文件 + 状态文件 + 幂等合并 |
| 未经人工验收即全量生成 | 违反分阶段要求 | 流水线默认 `--stage pilot`，`--stage full` 需显式指定；本文与 README 明确阶段闸门 |

---

## 15. 阶段状态（更新于 2026-11-14 13:38）

- [x] **第一阶段**：项目检查、Schema 设计、30 岗位知识库（30 份 JSON / 120 个项目模板）、
      流程与校验方案、7 份 YAML 配置、本实施方案。
- [x] **第二阶段**：100 份试验数据已生成并完成全量自动校验。
      - 覆盖 30 岗位 / 5 年限档 / 4 种质量型；
      - 简历 100 份、经历单元 742 个、面试问题 1035 道、追问链 300 条；
      - 每份 8~12 道问题、覆盖 ≥3 个经历单元、每份 3 条追问链；
      - `validate_dataset.py --stage pilot --strict`：**通过，0 错误 0 警告**；
      - 5 项硬性门槛失败 0 条；问题重复率 0.0；模板集中度 0.0077；441 种问题模板签名；
      - 已输出 `generation_report.md / quality_report.md / coverage_report.md / sample_review_report.md`。
- [ ] **第三阶段：人工验收（需用户确认，暂不越过）**
      - 抽样样本与检查清单见 `reports/sample_review_report.md`；
      - 确认后执行 `python3 scripts/run_pipeline.py --accept --note "人工验收通过"`。
- [ ] **第四阶段**：剩余 4900 份（受阶段闸门保护，未确认验收时 `--stage full` 会直接报错退出）。
- [ ] **第五阶段**：全量重新校验与 `final_acceptance_report.md`。

### 实现过程中修正的问题（可追溯）

| 发现 | 修正 |
|---|---|
| 无 PyYAML | 内置 YAML 子集解析器，零第三方依赖 |
| 工具名重复、竞赛名称与正文不一致、实习单位不一致 | 去重抽样、把标题/单位作为参数传入事实句构造 |
| 专业与课程不匹配 | 新增 `majors_by_family` 公共素材 |
| 非技术岗位出现「联调 / 回滚预案」等技术措辞 | 按 `family` 切换通用句式 |
| 资历匹配过硬 / 过软 | 改为按岗位偏好加权抽样 + 严格消耗全局配额 |
| `achievement` / `skill_application` 经历未进入简历正文 | 补齐渲染分组，恢复原文可追溯 |
| 场景词与其它经历标题撞名 | 修改知识库场景词；校验器只检查引用之外的新增文字 |
| 科研经历使用跨岗位固定句式、标题与正文课题不一致 | 改为岗位专属表述并统一传参 |
| 一条追问链模板漏掉原文引用 | 补上并加入「生成期自检」断言 |
