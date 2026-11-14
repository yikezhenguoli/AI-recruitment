"""Seed realistic demo companies and jobs.

Idempotent: tenants are keyed by slug, users by (tenant_id, email),
jobs by (tenant_id, title), versions by (job_id, version_no) and
plans by (job_id, name). Re-running only inserts what is missing.

Run from apps/api:
    .venv/bin/python scripts/seed_demo_companies.py
"""

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from ttc.core.db import dispose_engine, get_engine
from ttc.core.security import hash_password, uuid7

# Single shared password for every seeded HR account. Never printed.
SEED_PASSWORD = os.environ.get("TTC_SEED_PASSWORD") or "SeedDemo#2026"

DEMO_TENANT_SLUG = "demo"
DEMO_OWNER_EMAIL = "web.test.hr@ttc.local"

# ---------------------------------------------------------------- templates

WEIGHT_TEMPLATES = {
    "engineering": [
        ("tech_stack", "技术栈匹配", "核心语言、框架与工具的实际使用深度", 30),
        ("project_depth", "项目复杂度", "承担过的系统规模、并发量与技术难点", 25),
        ("engineering_quality", "工程质量", "代码规范、测试、可观测性与稳定性意识", 15),
        ("collaboration", "协作沟通", "跨团队协作、方案表达与评审经验", 15),
        ("business_understanding", "业务理解", "对业务目标与用户场景的理解程度", 15),
    ],
    "algorithm": [
        ("algorithm_fundamentals", "算法基础", "机器学习、深度学习与数学基础", 30),
        ("project_depth", "项目与论文深度", "真实落地的模型项目或高质量研究成果", 20),
        ("experiment_rigor", "实验与数据能力", "数据构建、评估设计与结果归因能力", 20),
        ("engineering_ability", "工程落地能力", "训练、部署与性能优化的工程经验", 15),
        ("business_understanding", "业务理解", "对业务指标与场景约束的理解", 15),
    ],
    "product": [
        ("insight", "需求洞察", "从客户与数据中发现真实问题的能力", 30),
        ("design", "产品设计", "方案完整度、优先级判断与文档质量", 25),
        ("data", "数据分析", "指标定义、实验设计与复盘能力", 20),
        ("collaboration", "跨团队协作", "推动研发、设计与销售协同落地的能力", 15),
        ("industry", "行业理解", "对所在行业与商业模式的理解", 10),
    ],
    "marketing": [
        ("growth", "增长策略", "渠道组合、预算分配与投放优化能力", 30),
        ("content", "内容与渠道", "内容策划、本地化与渠道运营经验", 25),
        ("analytics", "数据复盘", "归因分析、ROI 评估与实验能力", 20),
        ("brand", "品牌理解", "品牌定位与用户心智的把握", 15),
        ("execution", "执行落地", "项目推进、节奏控制与跨团队协同", 10),
    ],
    "supply_chain": [
        ("planning", "计划与预测", "需求预测、补货与库存计划能力", 30),
        ("supplier", "供应商管理", "寻源、谈判与供应商绩效管理经验", 25),
        ("cost", "成本控制", "成本结构分析与降本落地能力", 20),
        ("risk", "风险管理", "供应中断、交付异常与合规风险应对", 15),
        ("analytics", "数据分析", "使用数据工具支撑决策的能力", 10),
    ],
    "quality": [
        ("system", "质量体系", "质量体系建设、审核与持续改进经验", 30),
        ("compliance", "法规符合性", "相关法规、标准与注册要求的掌握程度", 25),
        ("problem_solving", "问题分析", "根因分析与纠正预防措施的有效性", 20),
        ("influence", "跨部门推动", "推动研发、生产与供应商整改的能力", 15),
        ("documentation", "数据与记录", "记录完整性、可追溯性与文档质量", 10),
    ],
}

INTERVIEW_TEMPLATES = {
    "engineering": (45, [
        ("电话初筛", "动机、基本信息与岗位匹配度", 5),
        ("技术一面", "核心语言、框架与项目细节", 15),
        ("系统设计", "架构取舍、容量与故障处理", 10),
        ("HR 终面", "稳定性、期望与团队匹配", 5),
    ]),
    "algorithm": (60, [
        ("简历核验", "项目贡献与论文真实性", 8),
        ("算法与项目", "模型选型、数据处理与评估设计", 15),
        ("现场建模", "给定场景的分析思路与可行性", 12),
        ("团队匹配", "协作方式、职业规划与期望", 5),
    ]),
    "product": (45, [
        ("需求复盘", "过往产品的真实需求与决策过程", 10),
        ("产品案例", "现场拆解一个业务场景", 15),
        ("跨团队协作", "与研发、销售的协作方式", 8),
        ("HR 面", "动机、期望与稳定性", 5),
    ]),
    "marketing": (40, [
        ("渠道复盘", "过往投放与增长案例", 10),
        ("内容策划", "现场设计一个内容或活动方案", 12),
        ("数据问答", "指标口径与 ROI 分析", 8),
        ("HR 面", "动机、期望与稳定性", 5),
    ]),
    "supply_chain": (40, [
        ("供应链场景", "补货、库存与交付的真实案例", 12),
        ("供应商谈判", "现场模拟议价与异常处理", 10),
        ("数据与风险", "用数据识别与应对供应风险", 8),
        ("HR 面", "动机、期望与稳定性", 5),
    ]),
    "quality": (40, [
        ("质量体系", "体系搭建、审核与改进经验", 10),
        ("法规案例", "法规要求与实际落地案例", 10),
        ("问题分析", "现场给出根因分析思路", 10),
        ("HR 面", "动机、期望与稳定性", 5),
    ]),
}

INTERVIEW_DIMENSIONS = [
    ("professional", "专业能力", 40),
    ("problem_solving", "问题解决", 25),
    ("collaboration", "协作沟通", 20),
    ("motivation", "动机与稳定性", 15),
]

# ---------------------------------------------------------------- job data

COMPANIES = [
    {
        "slug": "yunshu-cloud",
        "name": "云枢科技",
        "industry": "云计算 / 企业 SaaS",
        "jobs": [
            {
                "title": "高级后端工程师",
                "department": "研发部",
                "headcount": 3,
                "template": "engineering",
                "status": "published",
                "responsibilities": [
                    "负责协同平台核心服务的架构设计与开发",
                    "参与服务拆分、API 治理与稳定性建设",
                    "推动日志、指标与链路追踪等可观测性建设",
                    "参与代码评审与技术方案评审",
                ],
                "jd_text": (
                    "岗位职责：\n"
                    "1. 负责云枢协同平台核心服务的架构设计与开发，"
                    "覆盖文档协作、权限与消息通知等模块；\n"
                    "2. 参与服务拆分与 API 治理，保障接口在高峰期稳定可用；\n"
                    "3. 推动可观测性建设，完善日志、指标与链路追踪；\n"
                    "4. 参与代码评审与技术方案评审，沉淀团队工程规范。\n\n"
                    "任职要求：\n"
                    "1. 本科及以上学历，计算机相关专业，5 年以上后端开发经验；\n"
                    "2. 精通 Go 或 Java，熟悉 PostgreSQL、Redis、Kafka 等中间件；\n"
                    "3. 有高并发、多租户 SaaS 系统设计经验；\n"
                    "4. 熟悉 Kubernetes 与 CI/CD 流程，具备良好的问题定位能力。\n\n"
                    "技术栈：Go、Java、PostgreSQL、Redis、Kafka、Kubernetes。"
                ),
            },
            {
                "title": "云平台 SRE 工程师",
                "department": "基础设施部",
                "headcount": 2,
                "template": "engineering",
                "status": "published",
                "responsibilities": [
                    "负责多云环境的稳定性建设与容量规划",
                    "维护 Kubernetes 集群与发布流水线",
                    "建设监控告警与故障演练体系",
                    "参与重大故障复盘并推动改进",
                ],
                "jd_text": (
                    "岗位职责：\n"
                    "1. 负责公司多云环境的稳定性建设，制定容量规划与应急预案；\n"
                    "2. 维护 Kubernetes 集群、镜像仓库与发布流水线，降低变更风险；\n"
                    "3. 建设监控告警与故障演练体系，推动 SLO 落地；\n"
                    "4. 参与重大故障复盘，输出可执行的改进项。\n\n"
                    "任职要求：\n"
                    "1. 3 年以上运维或 SRE 经验，熟悉 Linux 与网络基础；\n"
                    "2. 熟练使用 Terraform、Ansible、Prometheus、Grafana；\n"
                    "3. 具备脚本开发能力，熟悉 Python 或 Go；\n"
                    "4. 有大规模集群或云原生平台实践经验者优先。\n\n"
                    "技术栈：Kubernetes、Terraform、Prometheus、Grafana、Python。"
                ),
            },
            {
                "title": "数据平台工程师",
                "department": "数据部",
                "headcount": 2,
                "template": "algorithm",
                "status": "published",
                "responsibilities": [
                    "负责数据仓库与实时数据链路建设",
                    "维护离线与实时任务，保障数据质量",
                    "与分析师协作梳理指标口径",
                    "参与数据治理与权限管理",
                ],
                "jd_text": (
                    "岗位职责：\n"
                    "1. 负责数据仓库与实时数据链路的建设，支撑经营分析与产品埋点；\n"
                    "2. 设计并维护离线与实时任务，保障数据质量与时效；\n"
                    "3. 与分析师、产品经理协作，梳理指标口径并沉淀数据资产；\n"
                    "4. 参与数据治理，完善元数据、血缘与权限管理。\n\n"
                    "任职要求：\n"
                    "1. 3 年以上数据平台或数仓开发经验；\n"
                    "2. 熟悉 Flink、Spark、Kafka，熟练使用 SQL 与 Python；\n"
                    "3. 理解维度建模与湖仓一体架构；\n"
                    "4. 有 SaaS 业务指标体系建设经验者优先。\n\n"
                    "技术栈：Flink、Spark、Kafka、ClickHouse、Python。"
                ),
            },
            {
                "title": "产品经理（企业协同）",
                "department": "产品部",
                "headcount": 1,
                "template": "product",
                "status": "published",
                "responsibilities": [
                    "负责企业协同产品线的需求调研与版本规划",
                    "深入客户现场提炼高频场景",
                    "推动研发、设计与售前协同交付",
                    "基于数据持续优化产品体验",
                ],
                "jd_text": (
                    "岗位职责：\n"
                    "1. 负责企业协同产品线的需求调研、方案设计与版本规划；\n"
                    "2. 深入客户现场，提炼高频场景并输出可落地的产品方案；\n"
                    "3. 与研发、设计、售前紧密协作，推动版本按期交付；\n"
                    "4. 跟踪核心指标，基于数据持续优化产品体验。\n\n"
                    "任职要求：\n"
                    "1. 3 年以上 B 端产品经验，有协同办公或项目管理产品背景；\n"
                    "2. 具备较强的需求分析与文档能力，能独立完成 PRD；\n"
                    "3. 熟悉 SaaS 商业模式与客户成功体系；\n"
                    "4. 有大型企业客户交付经验者优先。"
                ),
            },
        ],
    },
    {
        "slug": "zhizao-future",
        "name": "智造未来",
        "industry": "智能制造 / 工业视觉",
        "jobs": [
            {
                "title": "工业视觉算法工程师",
                "department": "算法部",
                "headcount": 2,
                "template": "algorithm",
                "status": "published",
                "responsibilities": [
                    "研发工业缺陷检测算法",
                    "设计小样本与半监督训练方案",
                    "完成模型评估与部署优化",
                    "参与现场调试与误检分析",
                ],
                "jd_text": (
                    "岗位职责：\n"
                    "1. 负责工业缺陷检测算法的研发与落地，覆盖分类、检测与分割任务；\n"
                    "2. 针对产线数据特点设计数据增强与半监督方案，提升小样本场景效果；\n"
                    "3. 完成模型训练、评估与部署，配合工程团队优化推理性能；\n"
                    "4. 参与现场调试，分析误检漏检原因并持续迭代。\n\n"
                    "任职要求：\n"
                    "1. 硕士及以上学历，计算机、自动化或相关专业；\n"
                    "2. 熟悉 PyTorch，掌握 YOLO、ResNet、SAM 等主流模型；\n"
                    "3. 有工业质检、表面缺陷检测项目经验；\n"
                    "4. 熟悉 TensorRT 或 ONNX Runtime 部署流程者优先。\n\n"
                    "技术栈：Python、PyTorch、OpenCV、TensorRT。"
                ),
            },
            {
                "title": "嵌入式软件工程师",
                "department": "研发部",
                "headcount": 2,
                "template": "engineering",
                "status": "published",
                "responsibilities": [
                    "开发工业控制器嵌入式软件",
                    "参与软硬件联调与现场问题定位",
                    "编写设计文档与测试用例",
                    "支持样机验证与小批量试产",
                ],
                "jd_text": (
                    "岗位职责：\n"
                    "1. 负责工业控制器嵌入式软件的开发与维护，完成驱动与通信模块设计；\n"
                    "2. 参与软硬件联调，定位并解决现场问题；\n"
                    "3. 编写设计文档与测试用例，保障版本质量；\n"
                    "4. 配合产线完成样机验证与小批量试产。\n\n"
                    "任职要求：\n"
                    "1. 本科及以上学历，电子、自动化或计算机相关专业；\n"
                    "2. 精通 C/C++，熟悉 STM32 或同类 MCU 开发；\n"
                    "3. 熟悉 EtherCAT、CAN、Modbus 等工业总线；\n"
                    "4. 有运动控制或 PLC 相关经验者优先。\n\n"
                    "技术栈：C/C++、STM32、FreeRTOS、EtherCAT。"
                ),
            },
            {
                "title": "制造运营经理",
                "department": "生产部",
                "headcount": 1,
                "template": "supply_chain",
                "status": "published",
                "responsibilities": [
                    "负责生产计划、排产与交付管理",
                    "推动精益生产与现场改善",
                    "协调采购、质量与工艺处理异常",
                    "建立生产数据看板并复盘",
                ],
                "jd_text": (
                    "岗位职责：\n"
                    "1. 负责工厂生产计划、排产与交付管理，保障订单按期完成；\n"
                    "2. 推动精益生产与现场改善，提升设备综合效率；\n"
                    "3. 协调采购、质量与工艺团队，处理生产异常；\n"
                    "4. 建立生产数据看板，定期复盘产能与成本。\n\n"
                    "任职要求：\n"
                    "1. 5 年以上制造业生产管理经验，有自动化产线背景；\n"
                    "2. 熟悉 MES、ERP 系统与生产计划逻辑；\n"
                    "3. 具备较强的跨部门协调与现场管理能力；\n"
                    "4. 有精益六西格玛项目经验者优先。\n\n"
                    "技术栈：MES、ERP、精益生产、数据分析。"
                ),
            },
            {
                "title": "质量管理工程师",
                "department": "质量部",
                "headcount": 1,
                "template": "quality",
                "status": "published",
                "responsibilities": [
                    "负责来料、过程与出货质量控制",
                    "组织质量问题分析并推动闭环",
                    "参与新产品质量策划与首件确认",
                    "维护质量体系并配合审核",
                ],
                "jd_text": (
                    "岗位职责：\n"
                    "1. 负责来料、过程与出货质量控制，维护检验标准与作业指导书；\n"
                    "2. 组织质量问题分析，推动 8D 报告闭环；\n"
                    "3. 参与新产品质量策划，完成 PPAP 与首件确认；\n"
                    "4. 维护 ISO 9001 体系文件并配合内外部审核。\n\n"
                    "任职要求：\n"
                    "1. 本科及以上学历，机械、电子或质量管理相关专业；\n"
                    "2. 3 年以上制造业质量工作经验；\n"
                    "3. 熟悉 SPC、MSA、FMEA 等质量工具；\n"
                    "4. 具备良好的沟通推动能力与文档功底。\n\n"
                    "技术栈：ISO 9001、SPC、FMEA、8D。"
                ),
            },
        ],
    },
    {
        "slug": "kangtai-med",
        "name": "康泰医疗器械",
        "industry": "医疗器械",
        "jobs": [
            {
                "title": "医疗器械注册专员",
                "department": "注册部",
                "headcount": 1,
                "template": "quality",
                "status": "published",
                "responsibilities": [
                    "编写并递交医疗器械注册资料",
                    "跟踪审评进度并响应发补",
                    "审核产品技术要求与说明书合规性",
                    "维护注册档案并配合体系考核",
                ],
                "jd_text": (
                    "岗位职责：\n"
                    "1. 负责二类、三类医疗器械注册资料的编写、整理与递交；\n"
                    "2. 跟踪注册审评进度，及时响应发补意见；\n"
                    "3. 参与产品技术要求、说明书与标签的合规审核；\n"
                    "4. 维护注册档案，配合体系考核与飞行检查。\n\n"
                    "任职要求：\n"
                    "1. 本科及以上学历，生物医学工程、药学或相关专业；\n"
                    "2. 3 年以上医疗器械注册经验，熟悉 NMPA 法规；\n"
                    "3. 有源器械或无源植入类产品注册经验者优先；\n"
                    "4. 工作细致，具备较强的文字与沟通能力。\n\n"
                    "技术栈：NMPA、ISO 13485、注册申报、法规检索。"
                ),
            },
            {
                "title": "临床数据经理",
                "department": "临床部",
                "headcount": 1,
                "template": "algorithm",
                "status": "published",
                "responsibilities": [
                    "负责临床试验数据采集、清洗与统计",
                    "设计病例报告表与数据管理计划",
                    "协同监查、统计与注册保障数据质量",
                    "参与数据库锁定与报告审核",
                ],
                "jd_text": (
                    "岗位职责：\n"
                    "1. 负责临床试验数据的采集、清洗与统计分析；\n"
                    "2. 设计病例报告表，编写数据管理计划与核查计划；\n"
                    "3. 与临床监查、统计与注册团队协作，保障数据质量；\n"
                    "4. 参与数据库锁定与统计分析报告审核。\n\n"
                    "任职要求：\n"
                    "1. 本科及以上学历，流行病学、统计学或医学相关专业；\n"
                    "2. 3 年以上临床数据管理经验；\n"
                    "3. 熟悉 GCP 与 CDISC 标准，能使用 SAS 或 R；\n"
                    "4. 有医疗器械临床试验项目经验者优先。\n\n"
                    "技术栈：GCP、CDISC、SAS、R、EDC 系统。"
                ),
            },
            {
                "title": "硬件工程师（医疗电子）",
                "department": "研发部",
                "headcount": 1,
                "template": "engineering",
                "status": "draft",
                "responsibilities": [
                    "设计医疗监测设备硬件方案",
                    "完成器件选型、PCB 评审与调试",
                    "参与 EMC 与安规测试整改",
                    "编写设计文档并支持转产",
                ],
                "jd_text": (
                    "岗位职责：\n"
                    "1. 负责医疗监测设备的硬件方案设计与原理图绘制；\n"
                    "2. 完成器件选型、PCB 评审与样机调试；\n"
                    "3. 参与 EMC 与安规测试，整改测试问题；\n"
                    "4. 编写硬件设计文档并支持转产。\n\n"
                    "任职要求：\n"
                    "1. 本科及以上学历，电子、通信或自动化相关专业；\n"
                    "2. 3 年以上硬件开发经验，熟悉模拟与数字电路；\n"
                    "3. 熟练使用 Altium Designer 或 Cadence；\n"
                    "4. 有医疗电子或小信号采集经验者优先。\n\n"
                    "技术栈：Altium Designer、EMC、模拟电路、STM32。"
                ),
            },
        ],
    },
    {
        "slug": "hanhai-global",
        "name": "瀚海跨境",
        "industry": "跨境电商",
        "jobs": [
            {
                "title": "海外市场增长经理",
                "department": "市场部",
                "headcount": 1,
                "template": "marketing",
                "status": "published",
                "responsibilities": [
                    "制定欧美与东南亚市场增长策略",
                    "管理广告渠道并优化投放 ROI",
                    "策划本地化内容与促销活动",
                    "搭建增长看板并复盘渠道表现",
                ],
                "jd_text": (
                    "岗位职责：\n"
                    "1. 负责欧美与东南亚市场的增长策略制定与执行；\n"
                    "2. 管理 Google、Meta、TikTok 等广告渠道，优化投放 ROI；\n"
                    "3. 策划本地化内容与促销活动，提升品牌认知与转化；\n"
                    "4. 搭建增长数据看板，定期复盘渠道表现。\n\n"
                    "任职要求：\n"
                    "1. 本科及以上学历，市场营销、国际贸易或相关专业；\n"
                    "2. 3 年以上跨境电商或海外投放经验；\n"
                    "3. 熟悉独立站与平台站运营逻辑；\n"
                    "4. 英语可作为工作语言，具备跨文化沟通能力。\n\n"
                    "技术栈：Google Ads、Meta Ads、GA4、独立站、SEO。"
                ),
            },
            {
                "title": "供应链计划专员",
                "department": "供应链部",
                "headcount": 2,
                "template": "supply_chain",
                "status": "published",
                "responsibilities": [
                    "负责海外仓与国内仓补货计划",
                    "跟踪库存与在途数据识别风险",
                    "协同采购、物流与销售优化备货",
                    "输出供应链分析报告",
                ],
                "jd_text": (
                    "岗位职责：\n"
                    "1. 负责海外仓与国内仓的补货计划，平衡库存与交付时效；\n"
                    "2. 跟踪在途与库存数据，识别断货与滞销风险；\n"
                    "3. 与采购、物流与销售团队协作，优化备货模型；\n"
                    "4. 输出周度与月度供应链分析报告。\n\n"
                    "任职要求：\n"
                    "1. 本科及以上学历，供应链、物流或统计相关专业；\n"
                    "2. 2 年以上跨境电商供应链计划经验；\n"
                    "3. 熟练使用 Excel 与 ERP，具备 SQL 能力者优先；\n"
                    "4. 数据敏感，逻辑清晰，能承受一定工作节奏。\n\n"
                    "技术栈：ERP、Excel、SQL、库存计划、海外仓。"
                ),
            },
            {
                "title": "跨境店铺运营",
                "department": "运营部",
                "headcount": 2,
                "template": "marketing",
                "status": "published",
                "responsibilities": [
                    "负责平台店铺日常运营与商品上架",
                    "优化 Listing 与关键词提升自然流量",
                    "策划站内活动并跟踪效果",
                    "维护店铺健康度与客户评价",
                ],
                "jd_text": (
                    "岗位职责：\n"
                    "1. 负责 Amazon、Shopee 等平台店铺的日常运营与商品上架；\n"
                    "2. 优化 Listing 标题、图片与关键词，提升自然流量；\n"
                    "3. 策划站内活动与优惠券，跟踪活动效果；\n"
                    "4. 处理客户评价与售后问题，维护店铺健康度。\n\n"
                    "任职要求：\n"
                    "1. 本科及以上学历，英语读写熟练；\n"
                    "2. 2 年以上跨境电商平台运营经验；\n"
                    "3. 熟悉平台规则与广告工具；\n"
                    "4. 有家居或消费电子类目经验者优先。\n\n"
                    "技术栈：Amazon Seller Central、Shopee、Listing 优化、站内广告。"
                ),
            },
            {
                "title": "数据分析师（电商）",
                "department": "数据部",
                "headcount": 1,
                "template": "algorithm",
                "status": "draft",
                "responsibilities": [
                    "搭建业务指标体系与数据看板",
                    "分析用户行为与销售数据",
                    "建设自动化报表与异常监控",
                    "支持增长与供应链专项分析",
                ],
                "jd_text": (
                    "岗位职责：\n"
                    "1. 负责业务数据的采集、清洗与指标体系搭建；\n"
                    "2. 通过用户行为与销售数据分析，输出可执行的运营建议；\n"
                    "3. 搭建自动化报表与异常监控，提升决策效率；\n"
                    "4. 配合增长与供应链团队完成专项分析。\n\n"
                    "任职要求：\n"
                    "1. 本科及以上学历，统计、数学或计算机相关专业；\n"
                    "2. 2 年以上数据分析经验，熟练使用 SQL 与 Python；\n"
                    "3. 熟悉 Tableau、Power BI 或 Metabase；\n"
                    "4. 有电商或零售行业经验者优先。\n\n"
                    "技术栈：SQL、Python、Tableau、GA4、A/B 测试。"
                ),
            },
        ],
    },
    {
        "slug": "lvyuan-energy",
        "name": "绿源新能源",
        "industry": "新能源 / 储能",
        "jobs": [
            {
                "title": "储能系统工程师",
                "department": "研发部",
                "headcount": 2,
                "template": "engineering",
                "status": "published",
                "responsibilities": [
                    "负责工商业储能系统方案设计",
                    "完成系统匹配计算与仿真",
                    "支持项目交付与并网调试",
                    "参与产品标准与测试规范编写",
                ],
                "jd_text": (
                    "岗位职责：\n"
                    "1. 负责工商业储能系统的方案设计与技术选型；\n"
                    "2. 完成电池簇、PCS、EMS 的匹配计算与系统仿真；\n"
                    "3. 支持项目交付，解决现场调试与并网问题；\n"
                    "4. 参与产品标准与测试规范编写。\n\n"
                    "任职要求：\n"
                    "1. 本科及以上学历，电气工程、自动化或新能源相关专业；\n"
                    "2. 3 年以上储能或电力系统工作经验；\n"
                    "3. 熟悉锂电池特性、BMS 与 PCS 工作原理；\n"
                    "4. 有工商业储能项目交付经验者优先。\n\n"
                    "技术栈：BMS、PCS、EMS、MATLAB/Simulink、储能系统设计。"
                ),
            },
            {
                "title": "电力电子硬件工程师",
                "department": "硬件部",
                "headcount": 2,
                "template": "engineering",
                "status": "published",
                "responsibilities": [
                    "设计储能变流器与充电模块硬件",
                    "完成器件选型、磁性与热设计",
                    "参与样机调试与 EMC 整改",
                    "编写设计文档并支持量产",
                ],
                "jd_text": (
                    "岗位职责：\n"
                    "1. 负责储能变流器与充电模块的硬件设计；\n"
                    "2. 完成功率器件选型、磁性元件设计与热设计；\n"
                    "3. 参与样机调试、EMC 整改与可靠性测试；\n"
                    "4. 编写硬件设计文档并支持量产导入。\n\n"
                    "任职要求：\n"
                    "1. 本科及以上学历，电力电子、电气工程相关专业；\n"
                    "2. 3 年以上电力电子硬件开发经验；\n"
                    "3. 熟悉 LLC、DAB、三相逆变等拓扑；\n"
                    "4. 熟练使用示波器、功率分析仪等调试工具。\n\n"
                    "技术栈：电力电子、LLC、DAB、Altium Designer、EMC。"
                ),
            },
            {
                "title": "项目交付经理",
                "department": "交付部",
                "headcount": 1,
                "template": "product",
                "status": "published",
                "responsibilities": [
                    "负责储能项目整体交付计划",
                    "协调设计、采购、施工与调试",
                    "管理客户沟通与验收风险",
                    "复盘项目成本与质量问题",
                ],
                "jd_text": (
                    "岗位职责：\n"
                    "1. 负责储能项目的整体交付计划与进度管理；\n"
                    "2. 协调设计、采购、施工与调试团队，保障项目按期并网；\n"
                    "3. 管理客户沟通与验收，处理现场变更与风险；\n"
                    "4. 复盘项目成本与质量问题，沉淀交付标准。\n\n"
                    "任职要求：\n"
                    "1. 本科及以上学历，电气、工程管理或相关专业；\n"
                    "2. 3 年以上新能源项目管理经验；\n"
                    "3. 熟悉储能或光伏电站建设流程；\n"
                    "4. 具备较强的沟通协调与风险控制能力。\n\n"
                    "技术栈：项目管理、储能电站、并网验收、进度控制。"
                ),
            },
            {
                "title": "采购工程师",
                "department": "采购部",
                "headcount": 2,
                "template": "supply_chain",
                "status": "published",
                "responsibilities": [
                    "负责电芯与电气物料采购",
                    "制定采购计划并跟踪交期",
                    "开展比价议价与合同谈判",
                    "参与供应商审核与绩效评估",
                ],
                "jd_text": (
                    "岗位职责：\n"
                    "1. 负责电芯、结构件与电气物料的采购与供应商管理；\n"
                    "2. 制定采购计划，跟踪交期并处理供应异常；\n"
                    "3. 开展比价、议价与合同谈判，控制采购成本；\n"
                    "4. 参与供应商审核与绩效评估。\n\n"
                    "任职要求：\n"
                    "1. 本科及以上学历，供应链、电气或材料相关专业；\n"
                    "2. 3 年以上制造业采购经验，有新能源行业背景；\n"
                    "3. 熟悉采购流程与供应商管理体系；\n"
                    "4. 具备较强的谈判能力与成本意识。\n\n"
                    "技术栈：ERP、供应商管理、成本分析、合同谈判。"
                ),
            },
        ],
    },
]

DEMO_JOBS = [
    {
        "title": "高级前端工程师",
        "department": "研发部",
        "headcount": 2,
        "template": "engineering",
        "status": "published",
        "responsibilities": [
            "负责招聘平台 Web 端架构设计与核心功能开发",
            "实现复杂交互与数据可视化页面",
            "优化前端性能与构建流程",
            "参与组件库与前端工程规范建设",
        ],
        "jd_text": (
            "岗位职责：\n"
            "1. 负责招聘平台 Web 端的架构设计与核心功能开发；\n"
            "2. 与产品、设计协作，完成复杂交互与数据可视化页面；\n"
            "3. 优化前端性能与构建流程，提升页面加载与渲染效率；\n"
            "4. 参与组件库建设与前端工程规范落地。\n\n"
            "任职要求：\n"
            "1. 本科及以上学历，4 年以上前端开发经验；\n"
            "2. 精通 TypeScript、React 与状态管理方案；\n"
            "3. 熟悉 Vite、Webpack 与前端监控体系；\n"
            "4. 有中后台或数据产品经验者优先。\n\n"
            "技术栈：TypeScript、React、Vite、Tailwind CSS、ECharts。"
        ),
    },
    {
        "title": "机器学习平台工程师",
        "department": "算法部",
        "headcount": 2,
        "template": "algorithm",
        "status": "published",
        "responsibilities": [
            "负责简历解析与岗位匹配模型训练上线",
            "建设特征工程与离线评估流水线",
            "优化模型推理服务性能",
            "推动模型在业务中落地",
        ],
        "jd_text": (
            "岗位职责：\n"
            "1. 负责简历解析与岗位匹配模型的训练、评估与上线；\n"
            "2. 建设特征工程与离线评估流水线，保障迭代效率；\n"
            "3. 优化模型推理服务，控制延迟与资源成本；\n"
            "4. 与算法、后端团队协作，推动模型在业务中落地。\n\n"
            "任职要求：\n"
            "1. 硕士及以上学历，计算机、人工智能相关专业；\n"
            "2. 熟悉 Python 与 PyTorch，掌握 Transformer 类模型；\n"
            "3. 有 NLP、信息抽取或推荐系统项目经验；\n"
            "4. 熟悉 Docker、Kubernetes 与模型服务化者优先。\n\n"
            "技术栈：Python、PyTorch、Transformers、FastAPI、Docker。"
        ),
    },
    {
        "title": "数据分析师（招聘业务）",
        "department": "数据部",
        "headcount": 1,
        "template": "algorithm",
        "status": "published",
        "responsibilities": [
            "定义并监控招聘业务核心指标",
            "搭建自动化报表与数据看板",
            "开展候选人转化专题分析",
            "设计并评估产品实验",
        ],
        "jd_text": (
            "岗位职责：\n"
            "1. 负责招聘业务核心指标的定义、监控与归因分析；\n"
            "2. 搭建自动化报表与数据看板，支持运营与管理决策；\n"
            "3. 开展候选人转化、岗位效果等专题分析；\n"
            "4. 与产品、算法团队协作，设计并评估实验。\n\n"
            "任职要求：\n"
            "1. 本科及以上学历，统计、数学或计算机相关专业；\n"
            "2. 2 年以上数据分析经验，精通 SQL；\n"
            "3. 熟练使用 Python 进行数据处理与可视化；\n"
            "4. 有 A/B 测试或增长分析经验者优先。\n\n"
            "技术栈：SQL、Python、Pandas、Metabase、A/B 测试。"
        ),
    },
    {
        "title": "产品经理（AI 应用）",
        "department": "产品部",
        "headcount": 1,
        "template": "product",
        "status": "published",
        "responsibilities": [
            "负责人岗匹配与智能评估产品设计",
            "定义模型能力边界与评估指标",
            "跟踪反馈持续迭代产品",
            "输出 PRD 与验收标准",
        ],
        "jd_text": (
            "岗位职责：\n"
            "1. 负责人岗匹配与智能评估产品的需求分析与方案设计；\n"
            "2. 与算法团队协作，定义模型能力边界与评估指标；\n"
            "3. 跟踪用户反馈与业务数据，持续迭代产品体验；\n"
            "4. 输出 PRD、原型与验收标准，推动版本落地。\n\n"
            "任职要求：\n"
            "1. 3 年以上 B 端产品经验，有 AI 产品落地案例；\n"
            "2. 理解大模型能力与常见应用形态；\n"
            "3. 具备较强的逻辑分析与跨团队沟通能力；\n"
            "4. 有招聘或人力资源行业背景者优先。\n\n"
            "技术栈：PRD、原型设计、数据分析、大模型应用。"
        ),
    },
    {
        "title": "测试开发工程师",
        "department": "质量部",
        "headcount": 2,
        "template": "engineering",
        "status": "published",
        "responsibilities": [
            "设计并执行核心链路测试方案",
            "建设接口自动化与回归体系",
            "参与性能测试与稳定性演练",
            "推动质量门禁落地",
        ],
        "jd_text": (
            "岗位职责：\n"
            "1. 负责平台核心链路的测试方案设计与执行；\n"
            "2. 建设接口自动化与回归测试体系，提升交付质量；\n"
            "3. 参与性能测试与稳定性演练，定位瓶颈问题；\n"
            "4. 推动研发流程中的质量门禁落地。\n\n"
            "任职要求：\n"
            "1. 本科及以上学历，3 年以上测试开发经验；\n"
            "2. 熟练使用 Python 与 pytest，熟悉接口测试；\n"
            "3. 了解 Docker、CI/CD 与常见监控工具；\n"
            "4. 有 Web 或 AI 应用测试经验者优先。\n\n"
            "技术栈：Python、pytest、Postman、Docker、GitLab CI。"
        ),
    },
    {
        "title": "技术招聘专员",
        "department": "人力资源部",
        "headcount": 2,
        "template": "marketing",
        "status": "published",
        "responsibilities": [
            "负责研发与算法岗位全流程招聘",
            "维护候选人库并提升触达效率",
            "分析招聘漏斗优化渠道流程",
            "参与雇主品牌与校招项目",
        ],
        "jd_text": (
            "岗位职责：\n"
            "1. 负责研发与算法岗位的全流程招聘，包括需求沟通、寻访与面试安排；\n"
            "2. 维护候选人库，提升人才复用与触达效率；\n"
            "3. 分析招聘漏斗数据，优化渠道与流程；\n"
            "4. 参与雇主品牌内容建设与校园招聘项目。\n\n"
            "任职要求：\n"
            "1. 本科及以上学历，2 年以上技术招聘经验；\n"
            "2. 熟悉互联网或 AI 行业人才市场；\n"
            "3. 具备较强的沟通能力与候选人运营意识；\n"
            "4. 有招聘系统使用经验者优先。\n\n"
            "技术栈：ATS、人才 mapping、面试协调、招聘数据分析。"
        ),
    },
    {
        "title": "内容营销经理",
        "department": "市场部",
        "headcount": 1,
        "template": "marketing",
        "status": "published",
        "responsibilities": [
            "制定并执行品牌内容策略",
            "策划案例、白皮书与线上活动",
            "管理内容生产流程与合规",
            "跟踪效果优化选题分发",
        ],
        "jd_text": (
            "岗位职责：\n"
            "1. 负责品牌内容策略制定与执行，覆盖公众号、视频号与行业媒体；\n"
            "2. 策划产品案例、行业白皮书与线上活动；\n"
            "3. 管理内容生产流程，把控质量与合规；\n"
            "4. 跟踪内容效果，优化选题与分发策略。\n\n"
            "任职要求：\n"
            "1. 本科及以上学历，3 年以上 B 端内容营销经验；\n"
            "2. 具备优秀的文案与策划能力；\n"
            "3. 熟悉新媒体运营与 SEO；\n"
            "4. 有 AI 或 SaaS 行业经验者优先。\n\n"
            "技术栈：内容策划、SEO、公众号运营、数据分析。"
        ),
    },
    {
        "title": "供应链运营专员",
        "department": "供应链部",
        "headcount": 1,
        "template": "supply_chain",
        "status": "published",
        "responsibilities": [
            "负责服务采购与供应商日常管理",
            "跟踪合同、付款与交付进度",
            "维护采购数据与供应商档案",
            "配合财务完成对账与成本分析",
        ],
        "jd_text": (
            "岗位职责：\n"
            "1. 负责平台服务采购与供应商日常管理；\n"
            "2. 跟踪合同、付款与交付进度，处理异常事项；\n"
            "3. 维护采购数据与供应商档案，输出运营报表；\n"
            "4. 配合财务完成对账与成本分析。\n\n"
            "任职要求：\n"
            "1. 本科及以上学历，1 年以上采购或供应链经验；\n"
            "2. 熟练使用 Excel 与 ERP 系统；\n"
            "3. 工作细致，具备良好的沟通与执行能力；\n"
            "4. 有互联网公司采购经验者优先。\n\n"
            "技术栈：ERP、Excel、合同管理、供应商管理。"
        ),
    },
    {
        "title": "客户成功经理",
        "department": "客户成功部",
        "headcount": 1,
        "template": "product",
        "status": "draft",
        "responsibilities": [
            "负责重点企业客户上线与运营支持",
            "跟踪使用数据识别续约机会",
            "收集反馈推动产品改进",
            "输出客户健康度报告",
        ],
        "jd_text": (
            "岗位职责：\n"
            "1. 负责重点企业客户的上线、培训与日常运营支持；\n"
            "2. 跟踪客户使用数据，识别续约与增购机会；\n"
            "3. 收集客户反馈，推动产品与流程改进；\n"
            "4. 输出客户健康度报告与季度复盘。\n\n"
            "任职要求：\n"
            "1. 本科及以上学历，3 年以上客户成功或客户运营经验；\n"
            "2. 熟悉 SaaS 客户成功体系；\n"
            "3. 具备较强的沟通与问题解决能力；\n"
            "4. 有 HR SaaS 行业经验者优先。\n\n"
            "技术栈：CRM、客户健康度、续约管理、数据分析。"
        ),
    },
    {
        "title": "信息安全工程师",
        "department": "安全部",
        "headcount": 1,
        "template": "engineering",
        "status": "draft",
        "responsibilities": [
            "建设平台安全基线与漏洞管理",
            "开展应用安全评估与渗透测试",
            "建设日志审计与入侵检测",
            "参与安全事件响应与合规检查",
        ],
        "jd_text": (
            "岗位职责：\n"
            "1. 负责平台安全基线建设与漏洞管理；\n"
            "2. 开展应用安全评估、渗透测试与代码审计；\n"
            "3. 建设日志审计与入侵检测能力；\n"
            "4. 参与安全事件响应与合规检查。\n\n"
            "任职要求：\n"
            "1. 本科及以上学历，3 年以上安全工作经验；\n"
            "2. 熟悉 OWASP Top 10 与常见攻防技术；\n"
            "3. 熟悉 Linux、容器安全与云安全配置；\n"
            "4. 持有 CISSP、CISP 等证书者优先。\n\n"
            "技术栈：OWASP、渗透测试、容器安全、日志审计。"
        ),
    },
]


def weight_dimensions(template: str) -> list[dict]:
    return [
        {"key": key, "label": label, "description": description, "weight_pct": pct}
        for key, label, description, pct in WEIGHT_TEMPLATES[template]
    ]


def interview_rounds(template: str) -> tuple[int, list[dict]]:
    duration, rounds = INTERVIEW_TEMPLATES[template]
    return duration, [
        {"name": name, "focus": focus, "question_budget": budget}
        for name, focus, budget in rounds
    ]


def interview_dimensions() -> list[dict]:
    return [
        {"key": key, "label": label, "weight_pct": pct}
        for key, label, pct in INTERVIEW_DIMENSIONS
    ]


async def ensure_tenant(connection, slug: str, name: str, plan: str) -> tuple:
    row = (await connection.execute(
        text("SELECT id FROM tenant WHERE slug = :slug"), {"slug": slug}
    )).scalar_one_or_none()
    if row is not None:
        return row, False
    tenant_id = uuid7()
    await connection.execute(
        text("INSERT INTO tenant (id, name, slug, plan, is_demo) "
             "VALUES (:id, :name, :slug, :plan, false)"),
        {"id": tenant_id, "name": name, "slug": slug, "plan": plan},
    )
    return tenant_id, True


async def ensure_user(connection, tenant_id, email: str, display_name: str,
                      password_hash: str) -> tuple:
    row = (await connection.execute(
        text("SELECT id FROM app_user WHERE tenant_id = :tenant AND email = :email"),
        {"tenant": tenant_id, "email": email},
    )).scalar_one_or_none()
    if row is not None:
        return row, False
    user_id = uuid7()
    await connection.execute(
        text("INSERT INTO app_user (id, tenant_id, email, display_name, password_hash, role) "
             "VALUES (:id, :tenant, :email, :name, :hash, 'admin')"),
        {"id": user_id, "tenant": tenant_id, "email": email, "name": display_name,
         "hash": password_hash},
    )
    return user_id, True


async def insert_job(connection, tenant_id, owner_id, spec: dict,
                     created_at: datetime) -> bool:
    existing = (await connection.execute(
        text("SELECT id FROM job WHERE tenant_id = :tenant AND title = :title"),
        {"tenant": tenant_id, "title": spec["title"]},
    )).scalar_one_or_none()
    if existing is not None:
        return False

    job_id = uuid7()
    version_id = uuid7()
    published_at = created_at if spec["status"] == "published" else None
    await connection.execute(
        text("INSERT INTO job (id, tenant_id, owner_id, title, department, headcount, "
             "status, created_at, updated_at) VALUES (:id, :tenant, :owner, :title, "
             ":department, :headcount, 'draft', :created, :created)"),
        {"id": job_id, "tenant": tenant_id, "owner": owner_id, "title": spec["title"],
         "department": spec["department"], "headcount": spec["headcount"],
         "created": created_at},
    )
    structured = {
        "role_title": spec["title"],
        "responsibilities": spec["responsibilities"],
        "department": spec["department"],
    }
    await connection.execute(
        text("INSERT INTO job_version (id, job_id, version_no, jd_text, structured, "
             "source, created_by, created_at) VALUES (:id, :job, 1, :jd, "
             "CAST(:structured AS jsonb), 'manual', :user, :created)"),
        {"id": version_id, "job": job_id, "jd": spec["jd_text"],
         "structured": json.dumps(structured, ensure_ascii=False),
         "user": owner_id, "created": created_at},
    )
    await connection.execute(
        text("UPDATE job SET status = CAST(:status AS job_status), "
             "current_version_id = :version, published_at = :published, "
             "updated_at = :created WHERE id = :id AND tenant_id = :tenant"),
        {"id": job_id, "tenant": tenant_id, "status": spec["status"],
         "version": version_id, "published": published_at, "created": created_at},
    )

    dimensions = weight_dimensions(spec["template"])
    await connection.execute(
        text("INSERT INTO weight_plan (id, tenant_id, job_id, name, mode, dimensions, "
             "total_pct) VALUES (:id, :tenant, :job, :name, 'custom', "
             "CAST(:dims AS jsonb), 100)"),
        {"id": uuid7(), "tenant": tenant_id, "job": job_id,
         "name": f"{spec['title']} 评估权重",
         "dims": json.dumps(dimensions, ensure_ascii=False)},
    )

    duration, rounds = interview_rounds(spec["template"])
    await connection.execute(
        text("INSERT INTO interview_plan (id, tenant_id, job_id, name, duration_min, "
             "rounds, dimensions) VALUES (:id, :tenant, :job, :name, :duration, "
             "CAST(:rounds AS jsonb), CAST(:dims AS jsonb))"),
        {"id": uuid7(), "tenant": tenant_id, "job": job_id,
         "name": f"{spec['title']} 面试方案", "duration": duration,
         "rounds": json.dumps(rounds, ensure_ascii=False),
         "dims": json.dumps(interview_dimensions(), ensure_ascii=False)},
    )
    return True


def timeline(count: int, *, start_days_ago: int) -> list[datetime]:
    now = datetime.now(UTC)
    return [now - timedelta(days=start_days_ago + index * 2, hours=index * 3)
            for index in range(count)]


async def seed() -> None:
    engine = get_engine()
    if engine is None:
        raise RuntimeError("DATABASE_URL is required")
    password_hash = hash_password(SEED_PASSWORD)
    created_tenants = []
    reused_tenants = []
    created_users = 0
    inserted_jobs = 0
    skipped_jobs = 0

    async with engine.begin() as connection:
        for company in COMPANIES:
            tenant_id, created = await ensure_tenant(
                connection, company["slug"], company["name"], "pro"
            )
            (created_tenants if created else reused_tenants).append(
                (company["name"], company["slug"])
            )
            email = f"hr@{company['slug']}.example.com"
            owner_id, user_created = await ensure_user(
                connection, tenant_id, email, f"{company['name']}招聘管理员",
                password_hash,
            )
            created_users += int(user_created)

            times = timeline(len(company["jobs"]), start_days_ago=18)
            for spec, created_at in zip(company["jobs"], times):
                if await insert_job(connection, tenant_id, owner_id, spec, created_at):
                    inserted_jobs += 1
                else:
                    skipped_jobs += 1

        demo_tenant = (await connection.execute(
            text("SELECT id FROM tenant WHERE slug = :slug"), {"slug": DEMO_TENANT_SLUG}
        )).scalar_one_or_none()
        if demo_tenant is None:
            raise RuntimeError(f"Demo tenant '{DEMO_TENANT_SLUG}' not found")
        demo_owner = (await connection.execute(
            text("SELECT id FROM app_user WHERE tenant_id = :tenant AND email = :email"),
            {"tenant": demo_tenant, "email": DEMO_OWNER_EMAIL},
        )).scalar_one_or_none()
        if demo_owner is None:
            raise RuntimeError(f"Demo owner {DEMO_OWNER_EMAIL} not found")

        demo_created = 0
        demo_skipped = 0
        times = timeline(len(DEMO_JOBS), start_days_ago=9)
        for spec, created_at in zip(DEMO_JOBS, times):
            if await insert_job(connection, demo_tenant, demo_owner, spec, created_at):
                demo_created += 1
            else:
                demo_skipped += 1

    await dispose_engine()
    print("Created tenants:", created_tenants or "none")
    print("Reused tenants:", reused_tenants or "none")
    print(f"Created HR users: {created_users}")
    print(f"Company jobs inserted: {inserted_jobs}, skipped (already present): {skipped_jobs}")
    print(f"Demo tenant jobs inserted: {demo_created}, skipped: {demo_skipped}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo companies and jobs")
    parser.parse_args()
    asyncio.run(seed())


if __name__ == "__main__":
    main()
