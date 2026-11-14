# AI 简历深度追问数据集构建系统

> 版本 `0.1.0-pilot`　|　最后更新 2026-11-14　|　当前阶段：**第二阶段已完成，等待第三阶段人工验收**

---

## 1. 项目简介

本项目构建一套**可直接用于后续 AI 简历深度追问模型训练、评估与优化**的结构化数据集。核心不是「给整份简历配几道面试题」，而是把每份简历拆成独立经历单元，再让**每一道问题精准绑定一个具体经历单元、一段可逐字核对的简历原文、一个明确的追问目的**。

本阶段**只构建数据集**，不包含任何模型训练、推理服务或业务系统。

- 全部数据由本地规则模板 + 30 岗位知识库 + 固定种子结构化随机组合生成；
- 全部人物、学校、公司、联系方式均为算法合成的**虚构实体**，不使用真实个人简历或身份信息；
- 不调用任何外部 / 付费 AI 服务（`config/generation_config.yaml` 中 `external_generation.enabled: false`）。

## 2. 项目目标

| 目标 | 状态 |
|---|---|
| 5000 份高质量模拟简历 | 计划已建立，试验阶段已生成 100 份，剩余 4900 份待验收后生成 |
| 覆盖 30 个岗位类别，每岗 ≥100 份 | 全量计划每岗 166~167 份 |
| 每份简历 8~12 道经历级深度问题 | 已实现，试验数据 8~12 道 |
| 每问精准关联具体经历 + 原文引用 | 已实现并设为硬性门槛 |
| 每问含提问依据、追问维度、提问原因 | 已实现 |
| 重要问题生成递进式多轮追问链 | 已实现，每份 ≥3 条 |
| 完整质量校验、统计分析与验收机制 | 已实现并全量跑通 |

## 3. 数据集规模

| 项目 | 目标 | 试验阶段实际 |
|---|---:|---:|
| 模拟简历 | 5000 | 100 |
| 岗位类别 | 30 | 30 |
| 经历单元 | — | 742 |
| 面试问题 | 8~12 道/份 | 1035（8~12 道/份） |
| 追问链 | ≥3 条/份 | 300（3 条/份） |

## 4. 30 个岗位类别

| 编号 | 岗位 | 编号 | 岗位 | 编号 | 岗位 |
|---:|---|---:|---|---:|---|
| 1 | Python开发工程师 | 11 | 软件测试工程师 | 21 | 电子硬件工程师 |
| 2 | Java开发工程师 | 12 | 运维工程师 | 22 | 机械工程师 |
| 3 | 前端开发工程师 | 13 | UI/UX设计师 | 23 | 电气工程师 |
| 4 | 后端开发工程师 | 14 | 财务人员 | 24 | 销售人员 |
| 5 | 算法工程师 | 15 | 人力资源 | 25 | 客户服务人员 |
| 6 | AI工程师 | 16 | 市场运营 | 26 | 供应链管理人员 |
| 7 | 数据分析师 | 17 | 业务运营 | 27 | 法务人员 |
| 8 | 数据工程师 | 18 | 嵌入式开发工程师 | 28 | 教育培训人员 |
| 9 | 产品经理 | 19 | 网络安全工程师 | 29 | 建筑工程人员 |
| 10 | 项目经理 | 20 | 软件架构师 | 30 | 研究开发人员 |

每岗位一份知识库 `knowledge_base/positions/<id>.json`，含核心职责、常见任务、核心技能、工具、业务场景、**4 个结构化项目模板**（含目标/技术要点/典型指标/难点）、成果指标、技术难点、工作风险、维度权重、5 档年限能力阶梯、岗位专属追问话题。共 120 个项目模板，全部岗位专属，禁止跨岗复用。

## 5. 工作年限分布

| 工作年限 | `career_level` | 目标数量 | 占比 |
|---|---|---:|---:|
| 应届毕业生 | `fresh` | 1000 | 20% |
| 1～3年 | `junior` | 1250 | 25% |
| 3～5年 | `mid` | 1250 | 25% |
| 5～10年 | `senior` | 1000 | 20% |
| 10年以上 | `expert` | 500 | 10% |

分配算法在**保持全局配额精确不变**的前提下，按 `config/position_categories.yaml` 的 `seniority_preference` 做软性资历匹配（如架构师偏资深、客服偏初级），同时保证每个岗位内部仍有 5 个年限档的多样性。应届毕业生不生成任何正式工作经历，只含课程项目、毕业设计、科研、实习与竞赛；资深候选人体现架构决策、团队管理与业务决策能力。

## 6. 简历质量分布

| 类型 | `resume_quality` | 目标数量 | 占比 | 文本策略 |
|---|---|---:|---:|---|
| 优质简历 | `high` | 1500 | 30% | 职责明确、实现链路完整、指标量化并说明测量条件 |
| 普通简历 | `normal` | 2000 | 40% | 基本完整，部分细节与口径缺失 |
| 信息模糊型 | `vague` | 1000 | 20% | 笼统动词、个人/团队边界不清、缺乏量化，问题以澄清为主 |
| 存在矛盾或疑点型 | `contradictory` | 500 | 10% | 注入时间重叠、指标缺基准、职责规模不匹配等**需进一步核实**的信息 |

> 疑点**不等于造假**：数据中不出现「造假 / 虚假」等结论性标签，只记录 `potential_risks`，并生成 `risk_investigation` 类问题验证。

## 7. 15 个统一追问维度

| 标签 | 含义 | 标签 | 含义 |
|---|---|---|---|
| `personal_contribution` | 个人实际贡献 | `innovation` | 创新能力 |
| `technical_implementation` | 技术实现细节 | `project_management` | 项目管理能力 |
| `achievement_verification` | 成果真实性验证 | `learning_ability` | 学习能力 |
| `data_evidence` | 数据及指标依据 | `risk_awareness` | 风险意识 |
| `problem_solving` | 问题解决能力 | `reflection` | 复盘与改进能力 |
| `technical_decision` | 技术决策能力 | `professional_depth` | 专业深度 |
| `teamwork` | 团队协作能力 | `business_understanding` | 业务理解能力 |
| `leadership` | 领导与管理能力 | | |

全部标签定义在 `config/question_dimensions.yaml`，**不得新增**。每问一个主维度 + 可选辅助维度；不同岗位通过知识库的 `interview_dimensions` 权重体现侧重。

问题类型共 10 种，定义在 `config/question_types.yaml`：`clarification / contribution_verification / technical_deep_dive / result_verification / data_verification / scenario_analysis / decision_analysis / problem_investigation / risk_investigation / reflection`。

## 8. 经历级数据关联设计（最核心）

**设计要点：事实句原子化。**

生成器先把每段经历描述拆成若干带类型的**事实句**（`fact_type / skill / tool / metric / difficulty` 等内部元数据），`original_content` 由这些句子**原样拼接**，简历正文 `resume_text` 与各结构化数组引用同一份文本。因此：

```
一个问题 → 一个具体经历单元 → 一句精确原文 → 一个明确追问目的
```

- 每道问题由 `(experience, 单个事实句)` 直接派生，不可能脱离经历；
- `reference.original_text` 取该句去掉句末标点，天然是 `original_content` 的精确子串；
- `start_offset / end_offset` 由事实句在 `original_content` 中的累加位置**真实计算**，不是伪造值；
- 问题文本强制嵌入 `「原文引用」`，因此不存在「请介绍一下你在项目中的主要职责」这类整份简历级泛问；
- 8 类经历各有独立追问策略，见 `config/experience_types.yaml`；
- 追问链全程复用同一个 `experience_id` 与同一句原文，不跨经历、不虚构候选人回答。

## 9. 数据文件结构

```
project/
├── README.md
├── config/
│   ├── generation_config.yaml        # 数量/种子/批次/阈值/路径/外部开关
│   ├── position_categories.yaml      # 30 岗位 + 资历偏好
│   ├── experience_types.yaml         # 8 类经历及追问策略
│   ├── question_dimensions.yaml      # 15 维度
│   ├── question_types.yaml           # 10 问题类型
│   ├── quality_distribution.yaml     # 年限/质量配额 + 文本策略权重
│   └── scoring_rules.yaml            # 评分权重与硬性门槛
├── knowledge_base/
│   ├── positions/*.json              # 30 份岗位知识库
│   └── common/                       # 公共素材库、岗位索引
├── dataset/
│   ├── resumes/resumes.jsonl
│   ├── resumes/resume_experiences.jsonl
│   ├── questions/interview_questions.jsonl
│   ├── questions/question_chains.jsonl
│   ├── metadata/                     # 计划、统计、校验、去重、事实句索引
│   └── batches/                      # 每批独立产物（断点续跑）
├── scripts/
│   ├── lib/                          # config / plan / common / resume_builder /
│   │                                 # question_engine / scoring / pipeline
│   ├── build_position_knowledge.py
│   ├── generate_candidate_profiles.py
│   ├── generate_resumes.py
│   ├── extract_experiences.py
│   ├── generate_questions.py
│   ├── generate_question_chains.py
│   ├── validate_dataset.py
│   ├── deduplicate_dataset.py
│   ├── generate_statistics.py
│   └── run_pipeline.py
├── reports/                          # 实施计划 + 4 份阶段报告
└── logs/generation.log, generation_state.json
```

`dataset/metadata/experience_facts.jsonl` 是**内部生成中间产物**（事实句索引），用于问题生成，不属于交付数据集主体。

## 10. JSONL 数据格式

### 10.1 `resumes.jsonl`（每行一份简历）

```json
{
  "resume_id": "RES_000001",
  "candidate_id": "CAN_000001",
  "target_position": "Python开发工程师",
  "position_id": "python_engineer",
  "family": "软件研发",
  "career_level": "mid",
  "career_level_label": "3-5年",
  "total_work_years": 4,
  "resume_quality": "high",
  "resume_quality_label": "优质简历",
  "basic_info": {"name": "虚构姓名", "age": 28, "city": "上海",
                 "phone": "138****0001", "email": "candidate_000001@example.test",
                 "is_fictional": true},
  "education": [{"experience_id": "EXP_00000101", "title": "...", "organization": "...",
                 "start_date": "2018-09", "end_date": "2022-06", "original_content": "..."}],
  "work_experiences": [], "project_experiences": [], "internship_experiences": [],
  "research_experiences": [], "competitions": [],
  "achievement_experiences": [], "skill_application_experiences": [],
  "skills": [], "achievements": [], "certifications": [],
  "resume_text": "完整中文简历文本（包含所有经历的 original_content）",
  "quality_signals": {"vague_sentence_count": 0, "metric_count": 6,
                      "risk_statement_count": 0, "total_fact_count": 28,
                      "quantified_ratio": 0.214},
  "generation": {"seed": 20269033, "batch_id": 0, "as_of_date": "2026-10",
                 "generator_version": "1.0.0", "source": "local_rule_based"},
  "quality_score": 94
}
```

### 10.2 `resume_experiences.jsonl`（每行一个经历单元）

```json
{
  "experience_id": "EXP_00000103",
  "resume_id": "RES_000001",
  "experience_type": "project_experience",
  "title": "订单履约服务重构",
  "organization": "云栖科技有限公司",
  "start_date": "2023-03",
  "end_date": "2023-11",
  "original_content": "本人独立负责Redis缓存模块的设计与实现。……接口平均响应时间从800ms降低至200ms。",
  "key_points": ["本人独立负责Redis缓存模块的设计与实现", "..."],
  "skills_involved": ["Redis", "Python", "MySQL"],
  "achievements": ["接口平均响应时间从800ms降低至200ms"],
  "potential_risks": ["性能指标未说明压测环境与统计口径"],
  "missing_information": ["未说明指标的测量方法、数据来源与对比基准"],
  "fact_count": 6,
  "position_id": "python_engineer",
  "career_level": "mid",
  "quality_score": 88
}
```

`experience_type` 取值：`education / internship / work_experience / project_experience / achievement / skill_application / research / competition`。

### 10.3 `interview_questions.jsonl`（每行一道问题）

```json
{
  "question_id": "Q_00000101",
  "resume_id": "RES_000001",
  "experience_id": "EXP_00000103",
  "experience_type": "project_experience",
  "reference": {
    "original_text": "使用Redis优化订单查询接口，使平均响应时间从800ms降低至200ms",
    "start_offset": 128,
    "end_offset": 163
  },
  "dimension": "technical_implementation",
  "secondary_dimensions": ["problem_solving"],
  "question_type": "technical_deep_dive",
  "question": "你在《订单履约服务重构》这段经历中提到「使用Redis优化订单查询接口，使平均响应时间从800ms降低至200ms」。请结合缓存一致性方案，说明具体实现链路、关键参数以及异常情况下的处理方式。",
  "reason": "需要验证候选人是否真正理解并亲自实现过该环节，而不只是参与过相关项目。",
  "expected_investigation": ["实现链路与关键步骤", "关键参数与边界条件", "异常处理与回退机制"],
  "priority": "high",
  "difficulty": "medium",
  "follow_up_questions": ["为什么不用更简单的实现？", "哪些参数是你实际调过的？"],
  "quality_score": 94
}
```

> `reference.original_text` 必须能在对应 `experience_id` 的 `original_content` 中逐字找到；偏移量真实计算，无法定位时才允许为 `null`。所有文件均为严格 JSON，无注释、无尾随逗号。

### 10.4 `question_chains.jsonl`（每行一条追问链）

```json
{
  "chain_id": "CHAIN_00000101",
  "resume_id": "RES_000001",
  "experience_id": "EXP_00000103",
  "root_question_id": "Q_00000101",
  "dimension": "technical_implementation",
  "theme": "technical",
  "chain_depth": 5,
  "stop_condition": "若候选人的回答已完整覆盖……可提前结束追问。",
  "questions": [
    {"sequence": 1, "level": "fact_confirmation", "question": "围绕《订单履约服务重构》中的「…」，请先确认…",
     "purpose": "确认个人实际贡献与事实基础",
     "expected_investigation": ["个人承担的环节", "职责边界"],
     "trigger_condition": "候选人尚未清晰说明个人职责与参与范围"}
  ],
  "quality_score": 100
}
```

层级固定递进：`fact_confirmation → process_detail → principle_decision → verification_challenge → scenario_migration`，深度 4~5 层，按根问题类型分技术 / 证据 / 澄清 / 复盘 4 种主题。

## 11. 数据生成流程

```
① build_position_knowledge.py        30 岗位知识库 + 公共素材库
② generate_candidate_profiles.py     5000 条确定性分配计划 → generation_plan.json
                                     + 分层抽取 100 个试验 ID（全量计划真子集）
③ run_pipeline.py --stage pilot      分批生成简历（每份独立 item_seed）
④ extract_experiences.py             强制经历拆解，剥离内部事实句
⑤ generate_questions.py              事实句级问题生成（8~12 道/份）
⑥ generate_question_chains.py        每份 ≥3 条同经历递进追问链
⑦ validate_dataset.py                全量内容级校验（含硬性门槛）
⑧ deduplicate_dataset.py             重复率 / 模板集中度分析
⑨ generate_statistics.py             统计 JSON + 4 份报告
```

**阶段闸门**：`--stage full` 会检查 `dataset/metadata/acceptance.json`；未确认人工验收时直接报错退出，防止未经审核就批量生成剩余 4900 份。

## 12. 数据质量校验机制

`scripts/validate_dataset.py` 检查 6 大类：

| 类别 | 主要检查 |
|---|---|
| 基础完整性 | 数量、四类 ID 唯一、JSONL 可解析、必填字段、全部外键存在 |
| 简历合理性 | 年限与时间线、教育时间、工作段重叠、应届无正式工作、技能与岗位匹配、年龄、质量标签与 `quality_signals` 一致 |
| 经历关联（最高优先级） | experience_id 存在且归属一致、experience_type 一致、引用为精确子串且偏移量吻合、问题含引用、reason 与引用一致、无跨经历混合、无泛问 |
| 问题质量 | 8~12 道/份、覆盖 ≥3 经历、维度/类型合法、目的与预期信息、重复率、模板集中度、中文自然度、岗位专业词泄漏 |
| 追问链 | ≥3 条/份、根问题存在、同经历、层级递进、目的与触发条件、无重复、无虚构回答、无跨经历跳转 |
| 多样性 | 岗位/年限/质量分布、15 维度覆盖、10 类型集中度、简历与问题重复率、模板签名分布 |

**5 项硬性门槛**（任一不过即该问题不合格，不参与加权评分）：
`experience_link_valid` / `reference_exact_match` / `no_generic_question` / `no_cross_experience_mix` / `chain_experience_consistent`。

评分采用 0~100 制，权重与扣分全部在 `config/scoring_rules.yaml` 统一管理；评分写入各记录的 `quality_score`，汇总到 `reports/quality_report.md`。

## 13. 运行环境

- macOS / Linux / Windows 均可；实测 macOS + Python **3.13.12**
- **零第三方依赖**：仅使用 Python 标准库（`json / random / re / math / glob / argparse / datetime / collections`）
- YAML 配置由 `scripts/lib/config.py` 内置的极简 YAML 子集解析器读取；若环境安装了 PyYAML 会自动优先使用
- 不使用网络、不使用数据库、不调用任何模型或 API
- 全量 5000 份预估占用 < 200 MiB

## 14. 安装方法

```bash
cd /Users/zhengrui/Documents/computer_programme/AI-recruitment/dataset
python3 --version                      # 需 >= 3.8
# 无需 pip install；可选：pip install pyyaml（并非必须）
python3 -m compileall -q scripts       # 语法自检
python3 scripts/build_position_knowledge.py   # 生成 30 份岗位知识库
```

## 15. 运行方法

```bash
# 第二阶段：生成 100 份试验数据 + 全量校验 + 4 份报告
python3 scripts/run_pipeline.py --stage pilot --strict

# 第三阶段：人工审阅 reports/ 下的报告，确认后解除阶段闸门
python3 scripts/run_pipeline.py --accept --note "人工验收通过"

# 第四阶段：保留已验收 100 份，分批生成剩余 4900 份
python3 scripts/run_pipeline.py --stage full --strict

# 第五阶段：全量重新校验（自动输出 final_acceptance_report.md）
python3 scripts/run_pipeline.py --validate-only --strict
```

也可逐步单独运行：

```bash
python3 scripts/generate_candidate_profiles.py --stage pilot
python3 scripts/generate_resumes.py --stage pilot
python3 scripts/extract_experiences.py
python3 scripts/generate_questions.py --stage pilot
python3 scripts/generate_question_chains.py
python3 scripts/validate_dataset.py --stage pilot --strict
python3 scripts/deduplicate_dataset.py
python3 scripts/generate_statistics.py --stage pilot
```

## 16. 断点续跑方法

- `dataset/metadata/generation_plan.json`：5000 条确定性计划，每份简历有独立 `item_seed`，重生成单份不影响其它简历；
- `logs/generation_state.json`：记录 `completed_resume_ids / completed_batches / failed_resume_ids / batches`；
- `dataset/batches/<stage>_<批次>_raw.json` 与 `_qa.json`：每批独立产物，**已完成且校验通过的批次默认跳过**；
- 失败数据进入 `failed_resume_ids`，可用 `--force` 重跑指定批次；`--force` 会重生成已完成批次；
- `logs/generation.log` 记录每批数量、校验结果与异常；
- 合并阶段按 `resume_id / experience_id / question_id / chain_id` 去重并排序，保证幂等。

复现性：固定 `random_seed = 20261114`，相同配置与生成环境下结果一致。可自行验证：

```bash
python3 -c "import sys;sys.path.insert(0,'scripts');from lib import plan;print(plan.validate_plan(plan.build_plan()))"
```

## 17. 数据统计方法

```bash
python3 scripts/generate_statistics.py --stage pilot   # 或 full / auto
```

输出 `dataset/metadata/` 下 `dataset_metadata.json / position_statistics.json / quality_statistics.json / dimension_statistics.json / validation_result.json / deduplication_report.json`，以及 `reports/` 下：

| 报告 | 内容 |
|---|---|
| `implementation_plan.md` | 第一阶段实施方案与设计基线 |
| `generation_report.md` | 生成方式、规模、岗位/年限/质量分布 |
| `quality_report.md` | 硬性门槛、关键指标、评分、错误与警告明细 |
| `coverage_report.md` | 岗位、15 维度、10 类型、8 经历类型、难度与优先级覆盖 |
| `sample_review_report.md` | 12 份分层抽样样本 + 人工验收检查清单 |
| `final_acceptance_report.md` | 仅全量阶段生成，逐项对照最终验收表 |

## 18. 当前完成情况

| 阶段 | 状态 |
|---|---|
| 第一阶段 项目检查、Schema 设计、30 岗位知识库、流程与校验方案 | ✅ 完成 |
| 第二阶段 100 份试验数据 + 全量自动校验 | ✅ 完成（100 简历 / 742 经历 / 1035 问题 / 300 追问链） |
| 第三阶段 人工验收 | ⏸ **等待用户确认**，样本与检查清单见 `reports/sample_review_report.md` |
| 第四阶段 剩余 4900 份 | ⏸ 未执行（受阶段闸门保护） |
| 第五阶段 最终质量验收 | ⏸ 未执行 |

试验阶段自动校验结果：**通过，0 错误 0 警告**；硬性门槛未过问题 0 道，问题重复率 0.0，模板集中度 0.0077，441 种不同问题模板签名。配额计划已按验收表精确建立（应届 1000 / 1-3年 1250 / 3-5年 1250 / 5-10年 1000 / 10年+ 500；优质 1500 / 普通 2000 / 模糊 1000 / 疑点 500；每岗 166~167 份）。

## 19. 已知问题

1. **规则生成的表达上限**：数据由结构化规则与岗位知识库合成，自然度高于模板替换，但仍不等同于人类撰写的真实简历；第三阶段人工验收需重点评估表达自然度与问题专业性。
2. **疑点型简历的时间重叠**：`contradictory` 中刻意设计的重叠区间属于「需进一步核实」信息，校验器会豁免，不应误读为数据错误。
3. **试验样本的分布不等于全量分布**：100 份样本采用分层轮转抽样，只保证覆盖 30 岗位 / 5 年限 / 4 质量型，不代表最终占比；最终占比由全量计划保证。
4. **无第三方依赖的取舍**：YAML 使用极简子集（无锚点、无行尾注释、无多行字符串）；若手工编辑配置请遵守该子集。报告为 Markdown 表格，不含图表图片。
5. **未做语义级人工标注**：问题质量评分是规则化评分（关联准确性、引用准确性、针对性、深度等可计算项），不替代人工语义判断。
6. **阶段闸门尚未解除**：当前直接运行 `--stage full` 会报错退出，这是刻意设计，不是缺陷。

## 20. 后续扩展方向

- 第三阶段发现问题后，调整 `config/quality_distribution.yaml` 的文本策略权重或 `question_engine.py` 的模板，再 `--force` 重生成试验数据；
- 扩充 `knowledge_base/positions/*.json` 的项目模板与指标库，进一步提升岗位专业差异；
- 增加更多事实句类型与问题策略，扩展 `config/question_types.yaml`（维度标签仍严格固定为 15 个）；
- 引入可选的人工标注字段（如 `human_review_score`），把抽样验收结论回流到数据集；
- 在后续独立阶段（本项目之外）接入模型训练、评估与推理系统 —— **本阶段明确不做**。

---

## 附：本阶段禁止事项自查

| 禁止项 | 自查结果 |
|---|---|
| PyTorch / 模型训练 / 预训练模型下载 | 无 |
| 推理 API / 前后端业务系统 | 无 |
| 真实个人简历 / 真实身份信息 | 无，全部合成虚构实体 |
| 无经历依据的泛化问题 / 无法追溯原文的问题 | 无，已设为硬性门槛 |
| 跨经历混合追问链 / 虚构候选人回答 | 无 |
| 未经授权调用付费 API | 无，`external_generation.enabled: false` |
| 为凑数量牺牲质量 | 无，未通过验收不得进入第四阶段 |

允许且仅包含：数据生成、拆解、清洗、校验、统计与报告类 Python 数据工程脚本。
