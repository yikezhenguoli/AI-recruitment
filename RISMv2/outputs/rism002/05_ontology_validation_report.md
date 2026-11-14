# RISM-002 方向目录校验报告

> 生成时间：2026-11-14T19:34:51+08:00
>
> 阶段：五
> 只读：是

## 1. 校验概览

| 指标 | 值 |
|---|---|
| 校验结论 | 通过 |
| 错误数 | 0 |
| 警告数 | 0 |
| 方向总数 | 28 |
| 已批准方向数 | 0 |
| 岗位能力数 | 24 |
| 岗位族数 | 8 |

## 2. 校验项结果

| 检查项 | 结果 |
|---|---|
| direction_id 唯一 / 格式 | 通过 |
| parent_dimensions ⊆ 15 个一级维度 | 通过 |
| related_directions 引用存在 | 通过 |
| depends_on 循环依赖 | 0 个环 |
| status 合法 | 通过 |
| 定义字段完整性 | 通过 |
| approved 必须人工审核 | 通过 |
| 岗位能力方向引用 | 通过 |
| 本体版本一致 | 通过 |

## 3. 方向状态分布

| 状态 | 数量 |
|---|---|
| candidate | 28 |

## 4. 一级维度被引用分布（多对多）

| 一级维度 | 关联方向数 |
|---|---|
| achievement_verification | 4 |
| business_understanding | 5 |
| data_evidence | 7 |
| innovation | 2 |
| leadership | 1 |
| learning_ability | 1 |
| personal_contribution | 2 |
| problem_solving | 5 |
| professional_depth | 2 |
| project_management | 1 |
| reflection | 7 |
| risk_awareness | 3 |
| teamwork | 1 |
| technical_decision | 3 |
| technical_implementation | 2 |

关联多个一级维度的方向数：**14**；单方向最多关联 **3** 个一级维度。

## 5. 关联与依赖统计

| 指标 | 值 |
|---|---|
| 方向间语义关联边 | 59 |
| 依赖边 | 0 |
| 依赖环 | 0 |
| 能力→方向关联边 | 136 |
| 已绑定岗位族的方向数 | 28 |

## 6. 错误明细

- （无）

## 7. 警告明细

- （无）

## 8. 审核状态说明

初始目录全部为 `candidate` 且 `annotation_status=pending`、`annotation_source=historical_question`。校验器强制要求 `approved` 方向必须带 `human` 来源与 `reviewed=true`；candidate 方向不得携带 approved 审核状态。方向 ID 稳定唯一，语义相似但考察目标不同的方向不合并。

## 9. 数据安全声明

报告仅输出 ID、计数与枚举分布，未输出任何简历正文或个人信息；校验过程只读。
