# RISM-002 历史追问意图分析报告

> 生成时间：2026-11-14T19:34:50+08:00
>
> 阶段：四
> 分析模式：rule_based_baseline
> 外部 LLM：关闭

## 1. 分析概览

| 指标 | 值 |
|---|---|
| 分析模式 | rule_based_baseline |
| 历史问题数 | 1035 |
| 追问链数 | 300 |
| 不同意图签名数 | 28 |
| 问题类型 × 一级维度组合数 | 28 |
| 语义相似问题对（总数） | 1234 |
| 相似问题但维度不同 | 759 |
| 同一原文对应多种意图 | 182 |
| 一级维度语义过宽数 | 9 |
| 生成的候选二级方向 | 28 |
| 自动批准的方向数 | 0 |
| 回收的 secondary_dimensions 问题数 | 1035 |

## 2. 外部 LLM 调用状态

| 指标 | 值 |
|---|---|
| 是否调用 | 否 |
| 原因 / 说明 | 外部 LLM 默认关闭，本次分析未发送任何数据 |
| 将发送字段 | （无，未启用） |
| 目标服务 | （无，未启用） |

> 本次分析完全由本地规则完成，未向任何第三方服务发送数据。

## 3. 核心考察意图签名（Top 25）

| # | 问题类型 | 主维度 | 问题数 | 主要考察点 |
|---|---|---|---|---|
| 1 | data_verification | data_evidence | 79 | 统计口径与计算公式、数据来源与采集方式、对比基准与观察周期 |
| 2 | clarification | business_understanding | 72 | 业务问题与触发背景、相关方与优先级判断、业务验收标准 |
| 3 | data_verification | achievement_verification | 65 | 归因隔离方法、统计窗口敏感性、可支撑的过程记录 |
| 4 | decision_analysis | project_management | 62 | 排期与依赖关系、里程碑设置、风险预案与资源协调 |
| 5 | contribution_verification | leadership | 58 | 实际决策权限、任务分配方式、结果责任范围 |
| 6 | reflection | reflection | 58 | 识别到的不足、具体改进动作、改进效果的验证方式 |
| 7 | clarification | technical_implementation | 55 | 具体实现步骤、关键工具与参数、完成确认方式 |
| 8 | problem_investigation | problem_solving | 55 | 问题现象与影响面、排查路径与排除依据、根因与验证方式 |
| 9 | technical_deep_dive | professional_depth | 46 | 原理性解释、适用边界与前提、与同类方案的比较 |
| 10 | clarification | personal_contribution | 44 | 个人独立承担的任务、团队其他成员的分工、可核对的交付物与参与程度 |
| 11 | contribution_verification | teamwork | 41 | 协作对象与分工约定、信息同步机制、冲突处理方式 |
| 12 | risk_investigation | risk_awareness | 36 | 关键条件与假设、核对动作、信息同步方式 |
| 13 | problem_investigation | professional_depth | 34 | 机理层面解释、与专业机制的关联、根因与表象的区分 |
| 14 | technical_deep_dive | technical_implementation | 33 | 实现链路与关键步骤、关键参数与边界条件、异常处理与回退机制 |
| 15 | decision_analysis | innovation | 31 | 新设计的具体内容、与常规做法的差异、收益评估方式 |
| 16 | reflection | learning_ability | 29 | 新掌握的知识或技能、学习路径与资源、迁移应用的实例 |
| 17 | scenario_analysis | business_understanding | 28 | 目标变化的影响、优先级重排依据、资源取舍逻辑 |
| 18 | technical_deep_dive | technical_decision | 28 | 备选方案清单、评估维度与约束、最终取舍理由 |
| 19 | scenario_analysis | risk_awareness | 27 | 方案前提条件、潜在失效点、兜底与降级措施 |
| 20 | scenario_analysis | technical_decision | 27 | 可复用部分与需替换部分、约束变化后的权衡、新的方案结论 |
| 21 | risk_investigation | data_evidence | 25 | 计算口径与公式、数据来源与采集方式、与其它口径的差异说明 |
| 22 | problem_investigation | risk_awareness | 19 | 前置征兆、同类风险排查、影响面评估 |
| 23 | reflection | innovation | 19 | 主动提出的改进、尝试过程与结果、受限条件下的设计思路 |
| 24 | decision_analysis | technical_decision | 18 | 候选方案与比较维度、排除理由、妥协项与后续成本 |
| 25 | contribution_verification | personal_contribution | 16 | 个人独立产出、沿用或协作的部分、可举证的个人决策 |

## 4. 语义重复但表达不同的问题（样例）

| 问题 A | 问题 B | 相似度 | 同维度 |
|---|---|---|---|
| Q_00003001 | Q_00009711 | 1.0 | 是 |
| Q_00003001 | Q_00304403 | 1.0 | 是 |
| Q_00003001 | Q_00336906 | 1.0 | 是 |
| Q_00003001 | Q_00347009 | 1.0 | 是 |
| Q_00003001 | Q_00388404 | 1.0 | 是 |
| Q_00003705 | Q_00230501 | 1.0 | 是 |
| Q_00003705 | Q_00275607 | 1.0 | 是 |
| Q_00003705 | Q_00426209 | 1.0 | 是 |
| Q_00003705 | Q_00474404 | 1.0 | 是 |
| Q_00009711 | Q_00304403 | 1.0 | 是 |
| Q_00009711 | Q_00336906 | 1.0 | 是 |
| Q_00009711 | Q_00347009 | 1.0 | 是 |
| Q_00009711 | Q_00388404 | 1.0 | 是 |
| Q_00010105 | Q_00095411 | 1.0 | 是 |
| Q_00019007 | Q_00046206 | 1.0 | 是 |
| Q_00019007 | Q_00157806 | 1.0 | 是 |
| Q_00019007 | Q_00196501 | 1.0 | 是 |
| Q_00024506 | Q_00128508 | 1.0 | 是 |
| Q_00032111 | Q_00435104 | 1.0 | 是 |
| Q_00046206 | Q_00157806 | 1.0 | 是 |

引用同一段经历原文但考察目标不同的问题对共 759 对，样例如下：

| 原文指纹 | 经历 ID | 问题 A | 维度 A | 问题 B | 维度 B | 骨架相似度 |
|---|---|---|---|---|---|---|
| 574c8f91348d | EXP_00003002 | Q_00003001 | risk_awareness | Q_00003004 | achievement_verification | 0.0 |
| e3d2d19db127 | EXP_00003705 | Q_00003701 | technical_implementation | Q_00003708 | business_understanding | 0.0 |
| e3d2d19db127 | EXP_00003705 | Q_00003701 | technical_implementation | Q_00366902 | leadership | 0.0 |
| e3d2d19db127 | EXP_00003705 | Q_00003708 | business_understanding | Q_00366902 | leadership | 0.0 |
| 8e7e5c94014e | EXP_00003704 | Q_00003703 | risk_awareness | Q_00003707 | project_management | 0.0 |
| ab57a214080e | EXP_00003705 | Q_00003705 | data_evidence | Q_00046212 | reflection | 0.0 |
| ab57a214080e | EXP_00003705 | Q_00003705 | data_evidence | Q_00049004 | learning_ability | 0.0 |
| ab57a214080e | EXP_00003705 | Q_00003705 | data_evidence | Q_00056706 | professional_depth | 0.0 |
| ab57a214080e | EXP_00003705 | Q_00003705 | data_evidence | Q_00072307 | achievement_verification | 0.0441 |
| ab57a214080e | EXP_00003705 | Q_00003705 | data_evidence | Q_00086109 | risk_awareness | 0.0 |
| ab57a214080e | EXP_00003705 | Q_00003705 | data_evidence | Q_00215808 | risk_awareness | 0.0 |
| ab57a214080e | EXP_00003705 | Q_00003705 | data_evidence | Q_00257002 | professional_depth | 0.0 |
| ab57a214080e | EXP_00003705 | Q_00003705 | data_evidence | Q_00257006 | learning_ability | 0.0 |
| ab57a214080e | EXP_00003705 | Q_00003705 | data_evidence | Q_00308506 | professional_depth | 0.0 |
| ab57a214080e | EXP_00003705 | Q_00003705 | data_evidence | Q_00374107 | reflection | 0.0 |

## 5. 文本相似但考察目标不同

| 原文指纹 | 问题数 | 意图数 | 意图组合（维度/问题类型） |
|---|---|---|---|
| ab57a214080e | 23 | 7 | achievement_verification/risk_investigation、data_evidence/risk_investigation、learning_ability/reflection、problem_solving/problem_investigation |
| bbc8ec7efd83 | 14 | 7 | achievement_verification/risk_investigation、data_evidence/risk_investigation、problem_solving/problem_investigation、professional_depth/problem_investigation |
| 113c5d6b186b | 14 | 7 | achievement_verification/risk_investigation、data_evidence/risk_investigation、innovation/reflection、problem_solving/problem_investigation |
| bcf7b275ec98 | 8 | 5 | business_understanding/clarification、leadership/contribution_verification、personal_contribution/clarification、teamwork/contribution_verification |
| d8cae396d488 | 5 | 5 | achievement_verification/data_verification、data_evidence/data_verification、professional_depth/technical_deep_dive、technical_decision/technical_deep_dive |
| 877dbc64613f | 10 | 4 | business_understanding/clarification、personal_contribution/clarification、teamwork/contribution_verification、technical_implementation/clarification |
| 71737ec3d7dd | 9 | 4 | business_understanding/clarification、leadership/contribution_verification、teamwork/contribution_verification、technical_implementation/clarification |
| 842f5dae8060 | 4 | 4 | business_understanding/clarification、personal_contribution/clarification、teamwork/contribution_verification、technical_implementation/clarification |
| 97703a8fceaa | 4 | 4 | business_understanding/clarification、personal_contribution/clarification、problem_solving/problem_investigation、teamwork/contribution_verification |
| 9b6bd8123d6d | 7 | 3 | business_understanding/clarification、personal_contribution/clarification、technical_implementation/clarification |
| 4e1e0b116b08 | 6 | 3 | business_understanding/clarification、personal_contribution/clarification、technical_implementation/clarification |
| 3941cd00458c | 5 | 3 | business_understanding/clarification、personal_contribution/clarification、teamwork/contribution_verification |
| 254b8a515888 | 5 | 3 | business_understanding/clarification、personal_contribution/clarification、technical_implementation/clarification |
| 268cad9b13a6 | 4 | 3 | business_understanding/clarification、leadership/contribution_verification、technical_implementation/clarification |
| 95d8534ba9b1 | 4 | 3 | leadership/contribution_verification、personal_contribution/clarification、technical_implementation/clarification |
| 12f7390c7a35 | 4 | 3 | business_understanding/clarification、leadership/contribution_verification、personal_contribution/clarification |
| f9b0f495901e | 4 | 3 | business_understanding/clarification、personal_contribution/clarification、technical_implementation/clarification |
| efa1ca6e42bc | 4 | 3 | personal_contribution/contribution_verification、problem_solving/problem_investigation、technical_implementation/clarification |
| bbd6fa8011fa | 4 | 3 | business_understanding/clarification、personal_contribution/clarification、technical_implementation/clarification |
| 17a8818f8429 | 4 | 3 | business_understanding/clarification、personal_contribution/clarification、technical_implementation/clarification |

> 原文以 SHA-256 前 12 位指纹代替，报告不输出简历原文内容。

## 6. 现有 15 个一级维度无法准确表达的意图

| 一级维度 | 中文名 | 不同考察目标数 | 问题类型分布 |
|---|---|---|---|
| achievement_verification | 成果真实性验证 | 3 | data_verification:65、result_verification:10、risk_investigation:12 |
| business_understanding | 业务理解能力 | 3 | clarification:72、result_verification:8、scenario_analysis:28 |
| data_evidence | 数据及指标依据 | 2 | data_verification:79、risk_investigation:25 |
| innovation | 创新能力 | 2 | decision_analysis:31、reflection:19 |
| personal_contribution | 个人实际贡献 | 2 | clarification:44、contribution_verification:16 |
| professional_depth | 专业深度 | 2 | problem_investigation:34、technical_deep_dive:46 |
| risk_awareness | 风险意识 | 3 | problem_investigation:19、risk_investigation:36、scenario_analysis:27 |
| technical_decision | 技术决策能力 | 3 | decision_analysis:18、scenario_analysis:27、technical_deep_dive:28 |
| technical_implementation | 技术实现细节 | 2 | clarification:55、technical_deep_dive:33 |

## 7. 候选二级追问方向

| direction_id | 名称 | 关联一级维度数 | 支撑问题数 | 方向状态 | 审核状态 |
|---|---|---|---|---|---|
| hist_data_verification__data_evidence | 数据核实·数据及指标依据 | 2 | 79 | candidate | pending |
| hist_clarification__business_understanding | 信息澄清·业务理解能力 | 1 | 72 | candidate | pending |
| hist_data_verification__achievement_verification | 数据核实·成果真实性验证 | 2 | 65 | candidate | pending |
| hist_decision_analysis__project_management | 决策分析·项目管理能力 | 1 | 62 | candidate | pending |
| hist_contribution_verification__leadership | 贡献核实·领导与管理能力 | 1 | 58 | candidate | pending |
| hist_reflection__reflection | 复盘反思·复盘与改进能力 | 1 | 58 | candidate | pending |
| hist_problem_investigation__problem_solving | 问题排查·问题解决能力 | 2 | 55 | candidate | pending |
| hist_clarification__technical_implementation | 信息澄清·技术实现细节 | 1 | 55 | candidate | pending |
| hist_technical_deep_dive__professional_depth | 技术深挖·专业深度 | 1 | 46 | candidate | pending |
| hist_clarification__personal_contribution | 信息澄清·个人实际贡献 | 1 | 44 | candidate | pending |
| hist_contribution_verification__teamwork | 贡献核实·团队协作能力 | 1 | 41 | candidate | pending |
| hist_risk_investigation__risk_awareness | 风险核实·风险意识 | 2 | 36 | candidate | pending |
| hist_problem_investigation__professional_depth | 问题排查·专业深度 | 1 | 34 | candidate | pending |
| hist_technical_deep_dive__technical_implementation | 技术深挖·技术实现细节 | 1 | 33 | candidate | pending |
| hist_decision_analysis__innovation | 决策分析·创新能力 | 2 | 31 | candidate | pending |
| hist_reflection__learning_ability | 复盘反思·学习能力 | 1 | 29 | candidate | pending |
| hist_technical_deep_dive__technical_decision | 技术深挖·技术决策能力 | 1 | 28 | candidate | pending |
| hist_scenario_analysis__business_understanding | 场景分析·业务理解能力 | 2 | 28 | candidate | pending |
| hist_scenario_analysis__risk_awareness | 场景分析·风险意识 | 1 | 27 | candidate | pending |
| hist_scenario_analysis__technical_decision | 场景分析·技术决策能力 | 1 | 27 | candidate | pending |
| hist_risk_investigation__data_evidence | 风险核实·数据及指标依据 | 2 | 25 | candidate | pending |
| hist_reflection__innovation | 复盘反思·创新能力 | 2 | 19 | candidate | pending |
| hist_problem_investigation__risk_awareness | 问题排查·风险意识 | 3 | 19 | candidate | pending |
| hist_decision_analysis__technical_decision | 决策分析·技术决策能力 | 3 | 18 | candidate | pending |
| hist_contribution_verification__personal_contribution | 贡献核实·个人实际贡献 | 2 | 16 | candidate | pending |
| hist_risk_investigation__achievement_verification | 风险核实·成果真实性验证 | 3 | 12 | candidate | pending |
| hist_result_verification__achievement_verification | 成果核实·成果真实性验证 | 3 | 10 | candidate | pending |
| hist_result_verification__business_understanding | 成果核实·业务理解能力 | 2 | 8 | candidate | pending |

## 8. 追问链递进关系分析

| 指标 | 值 |
|---|---|
| 追问链总数 | 300 |
| 不同触发条件数 | 20 |
| 不同追问目的数 | 20 |
| 层级分布 | fact_confirmation:300、process_detail:300、principle_decision:300、verification_challenge:300、scenario_migration:158 |

| 递进序列 | 链数 |
|---|---|
| fact_confirmation → process_detail → principle_decision → verification_challenge → scenario_migration | 158 |
| fact_confirmation → process_detail → principle_decision → verification_challenge | 142 |

难度映射（供 Strategy.difficulty 使用）：

| 追问层级 | 难度 |
|---|---|
| fact_confirmation | L1 |
| process_detail | L2 |
| principle_decision | L3 |
| verification_challenge | L3 |
| scenario_migration | L4 |

## 9. 候选结果使用限制（硬性）

- 所有候选方向 `status = candidate`、`annotation_status = pending`、`annotation_source = historical_question`，**未自动批准任何方向**。
- 历史问题中出现某方向仅可作为 Positive **候选**；某段经历未出现某方向**不得**据此判定为 Negative。
- 未审核的候选结果不得进入 `data/processed/rism002_samples.jsonl`。
- 方向 ID 稳定唯一，不因中文名称调整而变更；语义相似但考察目标不同的方向不自动合并。

## 10. 数据安全声明

报告仅输出问题 ID、计数、枚举与脱敏指纹；未输出简历正文、姓名、电话、邮箱等个人信息。全部输入以只读方式打开，未发生任何网络请求、模型训练或 Embedding 生成。
