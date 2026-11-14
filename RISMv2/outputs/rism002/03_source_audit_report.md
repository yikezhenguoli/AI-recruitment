# RISM-002 原始数据审计报告

> 生成时间：2026-11-14T19:34:50+08:00
>
> 阶段：三
> 只读：是

## 1. 审计概览

| 指标 | 值 |
|---|---|
| 审计结论 | 通过 |
| 错误数 | 0 |
| 警告数 | 0 |
| 本体版本 | RISM-002.1 |
| 简历 / 经历 / 问题 / 追问链 | 100 / 742 / 1035 / 300 |

## 2. JSONL 格式与 ID 唯一性

| 数据集 | 有效行数 | KiB | 解析错误 | 唯一 ID 数 |
|---|---|---|---|---|
| resumes | 100 | 1135.1 | 0 | 100 |
| experiences | 742 | 1077.2 | 0 | 742 |
| questions | 1035 | 1073.7 | 0 | 1035 |
| chains | 300 | 749.5 | 0 | 300 |

## 3. 必需字段覆盖

| 数据集 | 字段 | 出现次数 | 总行数 | 状态 |
|---|---|---|---|---|
| resumes | resume_id | 100 | 100 | 完整 |
| resumes | candidate_id | 100 | 100 | 完整 |
| resumes | target_position | 100 | 100 | 完整 |
| resumes | position_id | 100 | 100 | 完整 |
| resumes | family | 100 | 100 | 完整 |
| resumes | career_level | 100 | 100 | 完整 |
| resumes | resume_text | 100 | 100 | 完整 |
| experiences | experience_id | 742 | 742 | 完整 |
| experiences | resume_id | 742 | 742 | 完整 |
| experiences | experience_type | 742 | 742 | 完整 |
| experiences | title | 742 | 742 | 完整 |
| experiences | original_content | 742 | 742 | 完整 |
| questions | question_id | 1035 | 1035 | 完整 |
| questions | resume_id | 1035 | 1035 | 完整 |
| questions | experience_id | 1035 | 1035 | 完整 |
| questions | experience_type | 1035 | 1035 | 完整 |
| questions | reference | 1035 | 1035 | 完整 |
| questions | dimension | 1035 | 1035 | 完整 |
| questions | question_type | 1035 | 1035 | 完整 |
| questions | question | 1035 | 1035 | 完整 |
| questions | reason | 1035 | 1035 | 完整 |
| questions | expected_investigation | 1035 | 1035 | 完整 |
| questions | priority | 1035 | 1035 | 完整 |
| questions | difficulty | 1035 | 1035 | 完整 |
| questions | follow_up_questions | 1035 | 1035 | 完整 |
| chains | chain_id | 300 | 300 | 完整 |
| chains | resume_id | 300 | 300 | 完整 |
| chains | experience_id | 300 | 300 | 完整 |
| chains | root_question_id | 300 | 300 | 完整 |
| chains | dimension | 300 | 300 | 完整 |
| chains | questions | 300 | 300 | 完整 |

## 4. 关联与原文引用校验

| 检查项 | 数量 |
|---|---|
| 经历引用无效简历 | 0 |
| 问题引用无效经历 | 0 |
| 问题简历归属不一致 | 0 |
| 问题经历类型不一致 | 0 |
| 原文引用非经历子串 | 0 |
| 引用字符偏移错误 | 0 |
| 已校验引用条数 | 1035 |
| 追问链引用无效经历 | 0 |
| 追问链根问题异常 | 0 |
| 追问层级非法 | 0 |
| 追问序号不连续 | 0 |

## 5. 经历类型分布

| 取值 | 数量 |
|---|---|
| achievement | 30 |
| competition | 35 |
| education | 121 |
| internship | 68 |
| project_experience | 250 |
| research | 41 |
| skill_application | 56 |
| work_experience | 141 |

## 6. 一级追问维度分布

| 取值 | 数量 |
|---|---|
| achievement_verification | 87 |
| business_understanding | 108 |
| data_evidence | 104 |
| innovation | 50 |
| leadership | 58 |
| learning_ability | 29 |
| personal_contribution | 60 |
| problem_solving | 55 |
| professional_depth | 80 |
| project_management | 62 |
| reflection | 58 |
| risk_awareness | 82 |
| teamwork | 41 |
| technical_decision | 73 |
| technical_implementation | 88 |

## 7. 历史问题类型分布

| 取值 | 数量 |
|---|---|
| clarification | 171 |
| contribution_verification | 115 |
| data_verification | 144 |
| decision_analysis | 111 |
| problem_investigation | 108 |
| reflection | 106 |
| result_verification | 18 |
| risk_investigation | 73 |
| scenario_analysis | 82 |
| technical_deep_dive | 107 |

## 8. 追问链深度分布

| 取值 | 数量 |
|---|---|
| 4 | 142 |
| 5 | 158 |

## 9. 追问层级分布

| 取值 | 数量 |
|---|---|
| fact_confirmation | 300 |
| principle_decision | 300 |
| process_detail | 300 |
| scenario_migration | 158 |
| verification_challenge | 300 |

## 10. 岗位族分布

| 取值 | 数量 |
|---|---|
| 产品与项目 | 7 |
| 市场与销售 | 13 |
| 硬件与制造 | 16 |
| 算法与数据 | 18 |
| 职能支持 | 17 |
| 设计 | 3 |
| 质量与运维 | 10 |
| 软件研发 | 16 |

## 11. 历史数据覆盖

| 指标 | 值 |
|---|---|
| 有历史问题的经历 | 471 |
| 无历史问题的经历（不得据此判 Negative） | 271 |
| RISM-001 embedding 样本数 | 471 |

## 12. 只读资产指纹

| 指标 | 值 |
|---|---|
| 已比对文件数 | 14 |
| 发生变化 | 0 |
| 缺失 | 0 |

## 13. Embedding 资产只读盘点

| 资产 | shape | dtype | bytes |
|---|---|---|---|
| experience_embeddings | [471, 512] | <f4 | 964736 |
| job_embeddings | [471, 512] | <f4 | 964736 |
| labels | [471, 15] | <f4 | 28388 |
| split_indices_members | - | - | - |

## 14. 错误明细

- （无）

## 15. 警告明细

- （无）

## 16. 数据安全声明

本报告仅输出 ID、计数与枚举分布；未输出简历正文、姓名、电话、邮箱等个人信息。审计全程以只读方式打开源文件，未执行任何写入、训练或 Embedding 生成。
