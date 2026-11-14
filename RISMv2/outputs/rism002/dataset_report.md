# RISM-002 数据集统计与质量报告

> 生成时间：2026-11-14T19:36:28+08:00
>
> ontology_version：RISM-002.1
> 生成脚本：scripts/rism002/dataset_report.py
> 隐私：仅含 ID / 计数 / 枚举分布，不含简历正文与个人信息

## 1. 数据规模（RISM-001 只读源数据）

| 指标 | 值 |
|---|---|
| 简历数量 | 100 |
| 候选人数量 | 100 |
| 经历数量 | 742 |
| 历史问题数量 | 1035 |
| 历史追问链数量 | 300 |
| 岗位类别数 | 30 |
| 岗位族数量 | 8 |

## 2. 本体目录

| 指标 | 值 |
|---|---|
| 追问方向总数 | 28 |
| 方向状态分布 | {'candidate': 28} |
| 关联多个一级维度的方向数 | 14 |
| 岗位能力条目数 | 24 |
| 岗位能力族分布 | {'software_development': 3, 'algorithm_and_data': 3, 'product_and_project': 3, 'quality_and_operations': 3, 'design': 3, 'corporate_functions': 3, 'marketing_and_sales': 3, 'hardware_and_manufacturing': 3} |

## 3. 历史追问意图分析

| 指标 | 值 |
|---|---|
| questions_analyzed | 1035 |
| chains_analyzed | 300 |
| distinct_intent_signatures | 28 |
| distinct_question_type_dimension_combinations | 28 |
| similar_question_pairs_total | 1234 |
| cross_dimension_similar_pairs | 759 |
| quotes_with_multiple_intents | 182 |
| broad_primary_dimensions | 9 |
| candidate_directions_generated | 28 |
| candidate_directions_auto_approved | 0 |
| secondary_dimensions_recovered | 1035 |
| llm_used | False |

## 4. 候选数据（全部 pending，非已审核标签）

| 指标 | 值 |
|---|---|
| 候选 Claim | 45 |
| 候选 Evidence Gap | 39 |
| 候选 Strategy | 18 |
| unknown-only 预览样本 | 12 |
| 全部候选均为 pending | True |

## 5. 人工审核记录

| 指标 | 值 |
|---|---|
| claims | 0 |
| evidence_gaps | 0 |
| strategies | 0 |
| direction_annotations | 0 |

## 6. 审核状态与来源分布

| 审核状态 | 数量 |
|---|---|
| direction:pending | 28 |

| 标注来源 | 数量 |
|---|---|

## 7. 正式数据集统计

| 指标 | 值 |
|---|---|
| 样本数 | 0 |
| 简历数 | 0 |
| 候选人数 | 0 |
| 经历数 | 0 |
| 数据集状态 | awaiting_human_review |

## 8. Claim / Evidence Gap 类型分布（正式 + 候选）

| 口径 | 类型 | 数量 |
|---|---|---|
| 候选 | collaboration | 1 |
| 候选 | decision | 7 |
| 候选 | leadership | 2 |
| 候选 | problem_resolution | 2 |
| 候选 | qualitative_achievement | 7 |
| 候选 | quantified_achievement | 5 |
| 候选 | responsibility | 14 |
| 候选 | technical_method | 7 |
| 候选-Gap | missing_attribution | 3 |
| 候选-Gap | missing_measurement_method | 5 |
| 候选-Gap | missing_process | 24 |
| 候选-Gap | missing_risk_handling | 4 |
| 候选-Gap | missing_technical_details | 3 |

## 9. 追问方向 / 一级维度 / 策略类型分布（候选口径）

| 类别 | 取值 | 数量 |
|---|---|---|
| 方向 | hist_clarification__business_understanding | 1 |
| 方向 | hist_clarification__personal_contribution | 1 |
| 方向 | hist_data_verification__achievement_verification | 1 |
| 方向 | hist_data_verification__data_evidence | 3 |
| 方向 | hist_decision_analysis__innovation | 2 |
| 方向 | hist_problem_investigation__professional_depth | 1 |
| 方向 | hist_reflection__innovation | 1 |
| 方向 | hist_reflection__reflection | 1 |
| 方向 | hist_result_verification__achievement_verification | 1 |
| 方向 | hist_risk_investigation__achievement_verification | 1 |
| 方向 | hist_risk_investigation__risk_awareness | 3 |
| 方向 | hist_scenario_analysis__technical_decision | 1 |
| 方向 | hist_technical_deep_dive__professional_depth | 1 |
| 一级维度 | achievement_verification | 3 |
| 一级维度 | business_understanding | 1 |
| 一级维度 | data_evidence | 3 |
| 一级维度 | innovation | 3 |
| 一级维度 | personal_contribution | 1 |
| 一级维度 | professional_depth | 2 |
| 一级维度 | reflection | 1 |
| 一级维度 | risk_awareness | 3 |
| 一级维度 | technical_decision | 1 |
| 策略类型 | counterfactual_analysis | 4 |
| 策略类型 | decision_verification | 2 |
| 策略类型 | evidence_verification | 5 |
| 策略类型 | principle_verification | 1 |
| 策略类型 | process_reconstruction | 3 |
| 策略类型 | reflection_analysis | 2 |
| 策略类型 | scenario_extension | 1 |

## 10. Positive / Negative / Unknown 分布

| label_status | 正式样本计数 |
|---|---|
| （暂无记录） | — |

## 11. 各方向标注来源分布

| annotation_source | 数量 |
|---|---|
| （暂无记录） | — |

## 12. 不同岗位族的方向分布（候选口径，非已审核标签）

| 岗位族 | 方向 ID | 候选策略计数 |
|---|---|---|
| algorithm_and_data | hist_data_verification__data_evidence | 2 |
| algorithm_and_data | hist_reflection__innovation | 1 |
| algorithm_and_data | hist_technical_deep_dive__professional_depth | 1 |
| algorithm_and_data | hist_scenario_analysis__technical_decision | 1 |
| algorithm_and_data | hist_risk_investigation__risk_awareness | 1 |
| algorithm_and_data | hist_risk_investigation__achievement_verification | 1 |
| corporate_functions | hist_decision_analysis__innovation | 2 |
| corporate_functions | hist_risk_investigation__risk_awareness | 2 |
| corporate_functions | hist_data_verification__data_evidence | 1 |
| corporate_functions | hist_result_verification__achievement_verification | 1 |
| corporate_functions | hist_clarification__business_understanding | 1 |
| corporate_functions | hist_clarification__personal_contribution | 1 |
| corporate_functions | hist_reflection__reflection | 1 |
| corporate_functions | hist_data_verification__achievement_verification | 1 |
| corporate_functions | hist_problem_investigation__professional_depth | 1 |

## 13. 优先级与难度（正式样本）

| 类别 | 取值 | 数量 |
|---|---|---|
| （暂无记录） | — | — |

## 14. 重复与异常

| 指标 | 值 |
|---|---|
| 校验结论 | True |
| 错误数 | 0 |
| 警告数 | 1 |
| 重复策略数 | 0 |
| 出现在多个样本的经历文本数 | 0 |
| 正式样本重复 sample_id | 由 validate_dataset.py 逐条检测 |

## 15. 安全与合规

| 指标 | 值 |
|---|---|
| RISM-001 基线被改动文件 | 0（无） |
| 只读源资产被改动 | 0（无） |
| RISM-002 代码中的训练调用命中 | 0（无） |
| 外部 LLM 启用 | False |
| 外部 LLM 服务 | None |
| 报告输出简历正文/个人信息 | 否（配置 privacy.id_only_in_reports=true） |

## 16. 状态解读

正式数据集当前为空是预期状态：所有候选 Claim / Evidence Gap / Strategy 与追问方向均为 pending，需人工逐条审核后由 record_review.py 记录，再由 build_dataset.py 生成正式样本。未出现的方向一律保持 unknown，不会被自动转换为 negative；规则/历史问题来源的输出不会被标记为 reviewed 或高可信度标签。
