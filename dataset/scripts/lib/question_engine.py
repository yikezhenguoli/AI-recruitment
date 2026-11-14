"""经历级问题生成 + 递进式追问链生成。

核心不变式：
  * 每道问题由 (experience, 单个事实句) 直接派生，天然绑定一个 experience_id；
  * reference.original_text 是 original_content 的精确子串，偏移由事实句累加位置真实计算；
  * 问题文本强制嵌入「原文引用」，因此不可能出现整份简历级泛问；
  * 追问链全程复用同一个 experience_id 与同一句原文，不跨经历、不虚构候选人回答。
"""
from __future__ import annotations

import random
from collections import Counter
from typing import Any

from . import config
from .common import load_position_kb, strip_tail_punct
from .scoring import score_chain, score_question

# ---------------------------------------------------------------- 事实类型 → 允许的问题类型
FACT_TYPE_QTYPE: dict[str, list[str]] = {
    "education_background": ["clarification", "technical_deep_dive", "reflection"],
    "course_project": ["technical_deep_dive", "clarification", "decision_analysis"],
    "research_method": ["technical_deep_dive", "decision_analysis", "data_verification"],
    "research_result": ["result_verification", "data_verification", "reflection"],
    "responsibility": ["contribution_verification", "clarification", "problem_investigation"],
    "tech_stack": ["technical_deep_dive", "decision_analysis", "scenario_analysis"],
    "tech_implementation": ["technical_deep_dive", "problem_investigation", "decision_analysis"],
    "optimization": ["technical_deep_dive", "data_verification", "problem_investigation"],
    "metric": ["data_verification", "result_verification", "risk_investigation"],
    "problem_solved": ["problem_investigation", "technical_deep_dive", "reflection"],
    "decision": ["decision_analysis", "scenario_analysis", "reflection"],
    "collaboration": ["contribution_verification", "problem_investigation", "reflection"],
    "leadership": ["contribution_verification", "decision_analysis", "reflection"],
    "delivery": ["risk_investigation", "problem_investigation", "reflection"],
    "achievement": ["result_verification", "data_verification", "reflection"],
    "skill_application": ["technical_deep_dive", "scenario_analysis", "risk_investigation"],
    "project_background": ["clarification", "decision_analysis", "reflection"],
    "competition_role": ["contribution_verification", "technical_deep_dive", "reflection"],
    "competition_result": ["result_verification", "data_verification", "reflection"],
    "learning": ["reflection", "clarification", "scenario_analysis"],
    "vague_statement": ["clarification", "contribution_verification", "problem_investigation"],
    "risk_statement": ["risk_investigation", "data_verification", "result_verification"],
    "reflection": ["reflection", "decision_analysis", "scenario_analysis"],
}
DEFAULT_QTYPE = ["clarification", "technical_deep_dive", "reflection"]

# ---------------------------------------------------------------- 开场白（组合使用，降低模板感）
OPENERS = [
    "你在《{title}》这段经历中提到",
    "简历中《{title}》部分写到",
    "关于《{title}》，你的描述是",
    "针对《{title}》里的这句表述",
    "你提到自己在《{title}》中",
    "《{title}》里有这样一句描述",
]

# ---------------------------------------------------------------- 问题类型 → 维度变体
QTYPE_VARIANTS: dict[str, list[dict[str, Any]]] = {
    "clarification": [
        {
            "dim": "personal_contribution",
            "probes": [
                "。请具体说明这段描述里你本人独立完成了哪些工作，哪些部分由团队其他成员承担？",
                "。这里的职责边界比较概括，请拆开说明你实际经手的任务、交付物以及参与程度。",
                "。请澄清这句话对应的「{topic}」相关工作具体包含哪些内容，当时的分工方式是什么？",
            ],
            "reason": "该表述未区分个人与团队职责，需要确认候选人实际参与深度，避免把团队成果直接等同于个人贡献。",
            "expected": ["个人独立承担的任务", "团队其他成员的分工", "可核对的交付物与参与程度"],
            "followups": ["你在这个环节中独立做出过哪些判断？", "如果去掉你负责的部分，结果会有什么不同？", "当时是否留有可查的交付记录？"],
        },
        {
            "dim": "business_understanding",
            "probes": [
                "。请说明这项工作当时要解决的业务问题是什么，为什么优先级被排在当前位置？",
                "。请结合{scene}的业务背景，解释这句话对应的工作对业务指标的意义。",
                "。请讲清楚这项工作的触发原因、涉及方以及你理解的验收标准。",
            ],
            "reason": "简历只描述了动作没有交代业务背景，需要判断候选人是否理解工作背后的业务目标，而非仅执行指令。",
            "expected": ["业务问题与触发背景", "相关方与优先级判断", "业务验收标准"],
            "followups": ["当时有没有被否掉的替代做法？", "业务方最关注哪个指标？", "如果目标变化，做法会怎么调整？"],
        },
        {
            "dim": "technical_implementation",
            "probes": [
                "。这句描述没有展开实现细节，请说明具体是怎么做的、分哪几步完成？",
                "。请补充「{topic}」相关的实现方式，包括输入输出、关键步骤与使用的工具。",
                "。请把这句话拆成可执行的步骤，说明每一步由谁完成、如何确认完成。",
            ],
            "reason": "描述停留在概括层面，需要通过实现细节判断候选人是否真正动手做过该工作。",
            "expected": ["具体实现步骤", "关键工具与参数", "完成确认方式"],
            "followups": ["哪一步最容易出错？", "有没有现成方案可以直接用？", "你是如何验证每一步结果的？"],
        },
    ],
    "contribution_verification": [
        {
            "dim": "personal_contribution",
            "probes": [
                "。请指出其中由你个人设计或决策的部分，并举一个能体现你判断的具体例子。",
                "。这项工作中哪些内容是你的原创产出，哪些沿用团队既有方案？",
                "。请按「你独立负责 / 你参与配合 / 他人负责」把这句子里的工作重新划分一次。",
            ],
            "reason": "需要把个人贡献从团队成果中剥离出来，判断简历中的成绩与本人实际工作的对应关系。",
            "expected": ["个人独立产出", "沿用或协作的部分", "可举证的个人决策"],
            "followups": ["你的方案被采纳前有过哪些争议？", "如果换一个人负责，结果会不同吗？", "哪部分成果可以明确归因于你？"],
        },
        {
            "dim": "teamwork",
            "probes": [
                "。请说明与{team}协作时接口或分工是怎么约定的，出现过哪些不一致？",
                "。这项工作中需要向谁同步进展？信息不同步时你是怎么处理的？",
                "。请描述一次因为协作方式调整而改动方案的经过。",
            ],
            "reason": "简历提及协作但未说明协作机制，需要了解候选人在真实组织环境中的配合方式。",
            "expected": ["协作对象与分工约定", "信息同步机制", "冲突处理方式"],
            "followups": ["谁对最终结果负责？", "有没有跨部门升级的情况？", "协作流程后来有没有改进？"],
        },
        {
            "dim": "leadership",
            "probes": [
                "。请说明你在其中承担的管理职责，包括排期、决策与结果负责的范围。",
                "。团队意见不一致时，你依据什么做出最终决定？",
                "。请描述你如何分配任务并确认成员交付质量。",
            ],
            "reason": "需要核实候选人是否具备与描述相称的组织与决策权限，而非仅参与执行。",
            "expected": ["实际决策权限", "任务分配方式", "结果责任范围"],
            "followups": ["你如何处理进度偏差？", "有没有你否掉的成员方案？", "团队规模与汇报关系是怎样的？"],
        },
    ],
    "technical_deep_dive": [
        {
            "dim": "technical_implementation",
            "probes": [
                "。请结合{topic}，说明具体实现链路、关键参数以及异常情况下的处理方式。",
                "。请展开讲讲这一步的实现细节：数据或请求怎么流转、在哪里做校验、失败如何回退？",
                "。请说明「{tool}」在该环节中承担什么职责，边界条件是如何设定的？",
            ],
            "reason": "需要验证候选人是否真正理解并亲自实现过该环节，而不只是参与过相关项目。",
            "expected": ["实现链路与关键步骤", "关键参数与边界条件", "异常处理与回退机制"],
            "followups": ["为什么不用更简单的实现？", "哪些参数是你实际调过的？", "出现边界情况时最先暴露什么问题？"],
        },
        {
            "dim": "professional_depth",
            "probes": [
                "。请解释「{topic}」背后的原理，以及在这个场景下它的适用边界在哪里？",
                "。如果让你评估这套做法的专业性，你会从哪些维度给出判断？",
                "。请说明该做法与你了解的其他同类方案在原理层面的差别。",
            ],
            "reason": "希望判断候选人是否具备超出操作流程本身的专业理解，能否解释为什么这样做。",
            "expected": ["原理性解释", "适用边界与前提", "与同类方案的比较"],
            "followups": ["哪个前提最容易被忽略？", "有没有反例说明该做法不适用？", "你会如何向新人解释这个原理？"],
        },
        {
            "dim": "technical_decision",
            "probes": [
                "。请说明当时为什么采用这个技术路径，评估过哪些替代方案？",
                "。这项实现里哪一处是关键取舍？如果换成「{tool}」会有什么代价？",
                "。请还原当时做技术判断时的约束条件与比较依据。",
            ],
            "reason": "技术描述本身不能反映判断力，需要追问决策过程以区分执行者与方案设计者。",
            "expected": ["备选方案清单", "评估维度与约束", "最终取舍理由"],
            "followups": ["有没有事后证明选错了的部分？", "谁参与了最终拍板？", "现在回头看会改哪一项？"],
        },
    ],
    "result_verification": [
        {
            "dim": "achievement_verification",
            "probes": [
                "。请描述这个成果从开始到被确认的完整过程，谁参与验收、依据是什么？",
                "。这项成果中哪一部分可以直接归因于你的工作？有无可复核的记录？",
                "。请说明成果被采纳后是否持续生效，后续有没有出现反复。",
            ],
            "reason": "成果描述需要核实取得过程与可复现性，避免把团队或阶段性结果当作个人稳定产出。",
            "expected": ["成果形成过程", "验收方与验收依据", "成果的持续性"],
            "followups": ["过程中有没有被推翻重来？", "如果重做一次还能达到同样结果吗？", "谁可以佐证你的贡献？"],
        },
        {
            "dim": "business_understanding",
            "probes": [
                "。请说明这个成果对{scene}业务的实际价值，以及用什么业务指标体现？",
                "。成果与业务目标之间是怎么建立联系的？中间有哪些假设？",
                "。请解释为什么这个结果对当时的业务是重要的。",
            ],
            "reason": "需要确认候选人理解成果的业务含义，而不只是报出一个结果数字。",
            "expected": ["业务价值链路", "对应业务指标", "关键假设"],
            "followups": ["业务方如何使用这个结果？", "有没有与预期不一致的地方？", "价值能持续多久？"],
        },
    ],
    "data_verification": [
        {
            "dim": "data_evidence",
            "probes": [
                "。请说明这些数字的统计口径、数据来源与对比基准，以及当时的测量方法。",
                "。这个指标是在什么条件下测得的？样本量、观察周期和排除项分别是什么？",
                "。请把指标拆到可核对的粒度：原始值、改进后数值、计算方式与复核人。",
            ],
            "reason": "量化指标缺少口径与基准时无法判断可信度，需要候选人提供可核对的测量依据。",
            "expected": ["统计口径与计算公式", "数据来源与采集方式", "对比基准与观察周期"],
            "followups": ["同期还有哪些因素会影响该指标？", "有没有做过显著性或稳定性检验？", "指标由谁复核确认？"],
        },
        {
            "dim": "achievement_verification",
            "probes": [
                "。请说明这个数字是否扣除了同期其它改动或外部因素的影响，如何隔离？",
                "。如果换一个统计窗口，这个结论还成立吗？",
                "。请提供能支撑该数值的过程记录或对照数据。",
            ],
            "reason": "指标提升可能来自并行改动或口径变化，需要核实归因是否成立。",
            "expected": ["归因隔离方法", "统计窗口敏感性", "可支撑的过程记录"],
            "followups": ["有没有对照组？", "口径中途调整过吗？", "最大不确定性来自哪里？"],
        },
    ],
    "scenario_analysis": [
        {
            "dim": "risk_awareness",
            "probes": [
                "。如果{scene}的规模或约束明显变化，这套做法最先暴露的风险是什么？",
                "。请指出「{topic}」在极端情况下的失效点，以及你当时预留的兜底措施。",
                "。哪些条件一旦不成立，这句话里的做法就不再适用？",
            ],
            "reason": "考察候选人是否了解方案的适用前提与风险边界，能否把经验迁移到新约束下。",
            "expected": ["方案前提条件", "潜在失效点", "兜底与降级措施"],
            "followups": ["最早出现的预警信号是什么？", "有没有做过压力或边界验证？", "你会先加固哪一部分？"],
        },
        {
            "dim": "technical_decision",
            "probes": [
                "。若把同样的做法迁移到另一个业务场景，你会保留什么、替换什么？",
                "。请比较在规模扩大后「{tool}」与其它方案的取舍变化。",
                "。请重新做一次方案选择，说明约束变化后结论是否改变。",
            ],
            "reason": "通过场景迁移判断候选人的技术判断是否具备可迁移性，而非记住了单一项目的固定做法。",
            "expected": ["可复用部分与需替换部分", "约束变化后的权衡", "新的方案结论"],
            "followups": ["迁移成本主要在哪？", "哪些经验不能直接照搬？", "有没有现成案例可参考？"],
        },
        {
            "dim": "business_understanding",
            "probes": [
                "。如果业务目标从效率改为质量或合规，你的做法要怎么调整？",
                "。请从业务优先级角度说明「{topic}」的投入是否值得，依据是什么？",
                "。当资源减半时，你会保留这项工作的哪一部分？",
            ],
            "reason": "希望了解候选人能否在业务目标变化时重新排序工作，而不是固守原方案。",
            "expected": ["目标变化的影响", "优先级重排依据", "资源取舍逻辑"],
            "followups": ["谁来决定优先级？", "有没有被砍掉的替代项？", "调整后如何衡量效果？"],
        },
    ],
    "decision_analysis": [
        {
            "dim": "technical_decision",
            "probes": [
                "。请还原当时的决策过程：有哪些候选方案、比较维度分别是什么、谁最终拍板？",
                "。为什么最后排除了其它做法？请给出可比较的代价或风险说明。",
                "。这个选择里有没有妥协项？后续是否为此付过成本？",
            ],
            "reason": "方案描述只给了结论，需要考察候选人是否真正参与权衡并能说明取舍依据。",
            "expected": ["候选方案与比较维度", "排除理由", "妥协项与后续成本"],
            "followups": ["决策信息当时是否充分？", "有没有事后推翻的判断？", "如果由你重新决定会改吗？"],
        },
        {
            "dim": "innovation",
            "probes": [
                "。这个方案里哪些地方是区别于常规做法的新设计？你如何评估它的收益？",
                "。请说明「{topic}」上的改进是来自既有实践还是你提出的调整。",
                "。如果去掉这个新设计，结果会差多少？",
            ],
            "reason": "需要区分沿用成熟做法与真正的改进，判断候选人的创新贡献是否可核实。",
            "expected": ["新设计的具体内容", "与常规做法的差异", "收益评估方式"],
            "followups": ["有没有失败过的尝试？", "这个改进被复用了吗？", "别人如何评价这个做法？"],
        },
        {
            "dim": "project_management",
            "probes": [
                "。请说明该决策对应的排期、依赖与风险预案是如何安排的。",
                "。方案落地时关键里程碑怎么设？出现偏差你如何处理？",
                "。请描述你在推进过程中协调过哪些资源。",
            ],
            "reason": "希望了解决策之外的落地管理能力，判断候选人能否把方案推进到交付。",
            "expected": ["排期与依赖关系", "里程碑设置", "风险预案与资源协调"],
            "followups": ["最大的依赖风险是什么？", "延期时如何沟通？", "有没有变更过范围？"],
        },
    ],
    "problem_investigation": [
        {
            "dim": "problem_solving",
            "probes": [
                "。请按时间顺序说明问题现象、排查路径、定位到的根因以及修复动作。",
                "。当时有哪些可能的解释？你是如何逐一排除并确认根因的？",
                "。请说明「{topic}」相关的排查依据，以及修复后如何验证不再复现。",
            ],
            "reason": "问题解决类描述容易只写结论，需要通过排查过程判断候选人的实际分析能力。",
            "expected": ["问题现象与影响面", "排查路径与排除依据", "根因与验证方式"],
            "followups": ["最先看的指标或记录是什么？", "有没有走过弯路？", "后来加了什么防复发措施？"],
        },
        {
            "dim": "risk_awareness",
            "probes": [
                "。这个问题在发生前有没有可观测的征兆？后续如何建立预警？",
                "。请说明同类问题在其它环节是否也可能出现，你做过哪些排查？",
                "。如果当时没有及时发现，最坏影响是什么？",
            ],
            "reason": "考察候选人是否具备风险前置意识，而不只是事后修复。",
            "expected": ["前置征兆", "同类风险排查", "影响面评估"],
            "followups": ["预警阈值怎么定？", "有没有遗漏的场景？", "谁来跟进闭环？"],
        },
        {
            "dim": "professional_depth",
            "probes": [
                "。请从原理层面解释为什么会出现这个问题，而不只是描述修复动作。",
                "。这个现象与「{topic}」的哪些机制有关？",
                "。请说明你的修复是否触及根因，还是只缓解了表象。",
            ],
            "reason": "需要判断候选人对问题机理的理解深度，区分经验性试错与原理性定位。",
            "expected": ["机理层面解释", "与专业机制的关联", "根因与表象的区分"],
            "followups": ["有没有更彻底但成本更高的解法？", "修复引入了新风险吗？", "如何向他人解释这个原因？"],
        },
    ],
    "risk_investigation": [
        {
            "dim": "achievement_verification",
            "probes": [
                "。这段描述里有些信息需要进一步核实，请说明当时的实际安排与可对照的记录。",
                "。请按时间顺序把该阶段的工作与同期其它任务对齐说明，便于确认投入情况。",
                "。请补充能说明这项成果形成过程的材料或可核对的细节。",
            ],
            "reason": "该处存在时间线、职责或口径上需要进一步核实的信息；提问目的是澄清事实，不预设任何结论。",
            "expected": ["实际时间安排", "可核对的过程记录", "成果形成的具体经过"],
            "followups": ["哪些记录可以提供佐证？", "当时的汇报关系是怎样的？", "还有谁了解这段经过？"],
        },
        {
            "dim": "data_evidence",
            "probes": [
                "。请说明这里的数据是怎么算出来的，口径、基准和观察周期分别是什么？",
                "。这个数值与同期其它统计口径是否一致？如果不一致，差异来自哪里？",
                "。请补充该指标的采集方式与复核过程。",
            ],
            "reason": "部分指标缺少解释，需要通过口径与来源的澄清来判断数据是否可比，而非直接质疑数据本身。",
            "expected": ["计算口径与公式", "数据来源与采集方式", "与其它口径的差异说明"],
            "followups": ["口径由谁定义？", "中途是否调整过统计方式？", "能否给出原始记录？"],
        },
        {
            "dim": "risk_awareness",
            "probes": [
                "。请说明这段经历中有哪些条件如果变化，结论就需要重新评估？",
                "。你当时如何识别并跟进这类需要确认的信息？",
                "。请描述你为避免信息误解做过的核对动作。",
            ],
            "reason": "希望了解候选人对信息准确性与口径一致性的敏感程度，以及主动澄清的习惯。",
            "expected": ["关键条件与假设", "核对动作", "信息同步方式"],
            "followups": ["谁负责最终确认？", "有没有形成书面记录？", "后续如何避免同类问题？"],
        },
    ],
    "reflection": [
        {
            "dim": "reflection",
            "probes": [
                "。回看这段经历，如果重新做一次，你会优先改进哪一环？依据是什么？",
                "。请说明事后复盘发现了什么问题，后续是否真的落地了改进。",
                "。这项工作中最不满意的部分是什么？改进效果如何验证？",
            ],
            "reason": "通过复盘考察候选人能否识别不足并给出可验证的改进，而不是只描述成功结果。",
            "expected": ["识别到的不足", "具体改进动作", "改进效果的验证方式"],
            "followups": ["改进有没有遇到阻力？", "同样的经验复用过吗？", "现在会怎么调整目标？"],
        },
        {
            "dim": "learning_ability",
            "probes": [
                "。这段经历里哪些知识或技能是你新学的？请说明学习路径与首次应用场景。",
                "。请描述从「不会」到「能独立交付」的过程中，你依赖了哪些资料或帮助。",
                "。请举一个把「{topic}」的经验迁移到后续工作的例子。",
            ],
            "reason": "需要了解候选人的学习方式与经验迁移能力，判断成长是否可延续。",
            "expected": ["新掌握的知识或技能", "学习路径与资源", "迁移应用的实例"],
            "followups": ["哪个概念最难理解？", "有没有做过刻意练习？", "后来教过别人吗？"],
        },
        {
            "dim": "innovation",
            "probes": [
                "。复盘之后你提出过哪些不同于原做法的改进？效果如何？",
                "。请说明「{topic}」上你做过的一次主动尝试，即使结果不理想。",
                "。如果不受当时的资源限制，你会如何重新设计这一部分？",
            ],
            "reason": "考察候选人是否具备主动改进的意识，以及能否提出有依据的新方案。",
            "expected": ["主动提出的改进", "尝试过程与结果", "受限条件下的设计思路"],
            "followups": ["尝试失败的原因是什么？", "改进被采纳了吗？", "收益如何衡量？"],
        },
    ],
}


# ---------------------------------------------------------------- 追问链层级模板
CHAIN_LEVELS: dict[str, dict[str, dict[str, Any]]] = {
    "technical": {
        "fact_confirmation": {
            "templates": ["围绕《{title}》中的「{quote}」，请先确认你亲自参与的具体环节，以及「{topic}」相关工作中由他人承担的部分。",
                          "关于《{title}》里的「{quote}」，请先说明你的职责范围与当时可用的资源条件。"],
            "purpose": "确认个人实际贡献与事实基础",
            "expected": ["个人承担的环节", "职责边界", "资源与约束条件"],
            "trigger": "候选人尚未清晰说明个人职责与参与范围",
        },
        "process_detail": {
            "templates": ["针对「{quote}」，请按执行顺序说明实现步骤、关键参数与交付物。",
                          "请结合「{topic}」，把「{quote}」对应的过程拆成可核对的步骤。"],
            "purpose": "还原实际执行过程",
            "expected": ["执行步骤", "关键参数", "中间交付物"],
            "trigger": "候选人已确认本人参与该环节，但尚未展开做法",
        },
        "principle_decision": {
            "templates": ["在「{quote}」对应的工作中，当时为什么选择这条技术路径？请说明考虑过的替代方案与取舍依据。",
                          "请从原理层面解释「{quote}」中做法成立的依据，以及「{topic}」的适用边界。"],
            "purpose": "考察原理理解与技术决策能力",
            "expected": ["原理性依据", "备选方案", "取舍与边界条件"],
            "trigger": "候选人能够说清具体做法，但尚未解释为什么这样做",
        },
        "verification_challenge": {
            "templates": ["如果「{quote}」对应的环节出现边界条件或异常输入，你如何验证方案仍然有效？请给出当时的验证方式。",
                          "关于「{quote}」，请说明结果或指标的测量方式、数据来源与对比基准。"],
            "purpose": "通过证据与异常情况验证真实能力",
            "expected": ["验证与测量方法", "数据口径与基准", "异常场景表现"],
            "trigger": "候选人已说明方案与依据，需要进一步检验可信度",
        },
        "scenario_migration": {
            "templates": ["如果{scene}的规模或约束明显变化，「{quote}」对应的做法最先暴露什么问题？你会如何调整？",
                          "回看「{quote}」，若把同一方案迁移到新场景，你会保留什么、替换什么，依据是什么？"],
            "purpose": "考察经验迁移、风险预判与复盘能力",
            "expected": ["最先出现的瓶颈", "调整方案", "经验的可复用边界"],
            "trigger": "候选人已经理解现有方案及其技术边界",
        },
    },
    "evidence": {
        "fact_confirmation": {
            "templates": ["围绕《{title}》中的「{quote}」，请先说明这项结果是在什么时间范围内、由哪些人共同参与形成的。",
                          "关于《{title}》里的「{quote}」，请先确认你本人负责的是结果的哪一部分。"],
            "purpose": "确认结果形成的事实基础与个人贡献",
            "expected": ["结果形成时间", "参与人员", "个人贡献范围"],
            "trigger": "候选人尚未说明结果产生的背景与个人分工",
        },
        "process_detail": {
            "templates": ["针对「{quote}」，请描述从原始记录到最终结果的处理过程，中间有哪些核对环节。",
                          "请说明「{quote}」对应的数据或成果是如何一步步产出的。"],
            "purpose": "还原成果产出过程与核对环节",
            "expected": ["原始记录来源", "处理步骤", "核对环节"],
            "trigger": "候选人已确认参与，但尚未说明过程",
        },
        "principle_decision": {
            "templates": ["「{quote}」中的结论是基于哪些前提与口径得出的？当时为什么采用这个口径？",
                          "请说明「{quote}」对应的对比基准是如何选定的，有没有考虑过其它基准。"],
            "purpose": "考察口径与基准的选择依据",
            "expected": ["统计前提", "口径选择理由", "候选基准"],
            "trigger": "候选人能够说明产出过程，需要进一步了解决策依据",
        },
        "verification_challenge": {
            "templates": ["关于「{quote}」中的结果，请说明测量方式、样本范围与对比基准；同期还有哪些因素可能影响该结论？",
                          "请提供可支撑「{quote}」的核对方式：如果换一个统计窗口，结论还成立吗？"],
            "purpose": "验证数据可信度与归因是否成立",
            "expected": ["测量与采样方式", "对比基准", "混杂因素与隔离方法"],
            "trigger": "候选人已说明口径与基准，需要检验结论稳健性",
        },
        "scenario_migration": {
            "templates": ["如果{scene}的业务条件变化，「{quote}」对应的口径或结论需要如何重新评估？",
                          "回看「{quote}」，如果重新做一次，你会怎样改进数据的采集与复核流程？"],
            "purpose": "考察结论迁移条件与流程改进能力",
            "expected": ["条件变化的影响", "口径调整", "采集与复核改进"],
            "trigger": "候选人已经理解现有结论及其限制",
        },
    },
    "clarification": {
        "fact_confirmation": {
            "templates": ["围绕《{title}》中的「{quote}」，请先说明你本人具体做了哪几件事，分别交付给谁。",
                          "关于《{title}》里的「{quote}」，请先确认这段工作的时间范围与参与人。"],
            "purpose": "补齐被省略的事实信息",
            "expected": ["具体任务清单", "交付对象", "时间与参与人"],
            "trigger": "候选人尚未清晰说明个人职责",
        },
        "process_detail": {
            "templates": ["针对「{quote}」，请按时间顺序描述当时的推进过程与关键节点。",
                          "请把「{quote}」拆成具体动作，说明每一步的输入、输出与确认方式。"],
            "purpose": "把笼统描述还原为可执行过程",
            "expected": ["推进步骤", "关键节点", "输入输出与确认方式"],
            "trigger": "候选人已说明职责，但描述仍停留在概括层面",
        },
        "principle_decision": {
            "templates": ["「{quote}」里的工作是按什么规则分工的？谁负责确认完成标准？",
                          "请说明「{quote}」对应的「{topic}」相关判断依据，以及当时的约束条件。"],
            "purpose": "明确职责划分规则与判断依据",
            "expected": ["分工规则", "确认标准", "约束条件"],
            "trigger": "候选人已给出过程，需要澄清规则与依据",
        },
        "verification_challenge": {
            "templates": ["关于「{quote}」，其中哪些内容你可以提供记录或佐证？哪些部分只能凭回忆说明？",
                          "请说明「{quote}」对应的成果在当时是如何被验收或确认的。"],
            "purpose": "核实澄清内容的可验证性",
            "expected": ["可佐证的内容", "验收或确认方", "信息不确定之处"],
            "trigger": "候选人已给出较具体的说明，需要确认可核对性",
        },
        "scenario_migration": {
            "templates": ["如果重新参与同类工作，「{quote}」对应的部分你会怎样描述或改进，使其更清晰可核对？",
                          "回看「{quote}」，若{scene}的条件变化，哪些信息仍然必须事先明确？"],
            "purpose": "考察信息表达与事前澄清意识",
            "expected": ["表达或记录改进", "需事先明确的信息", "条件变化的影响"],
            "trigger": "候选人已充分说明该经历，可结束或转入反思",
        },
    },
    "reflection": {
        "fact_confirmation": {
            "templates": ["围绕《{title}》中的「{quote}」，请先确认当时的目标、你的角色以及最终的实际结果。",
                          "关于《{title}》里的「{quote}」，请先说明复盘针对的是哪一次具体实践。"],
            "purpose": "锚定复盘对象与事实基础",
            "expected": ["原始目标", "本人角色", "实际结果"],
            "trigger": "候选人尚未说明复盘对应的具体事件",
        },
        "process_detail": {
            "templates": ["针对「{quote}」，请说明事后是通过哪些信息或反馈发现问题的。",
                          "请描述「{quote}」对应的复盘过程：谁参与、依据什么材料、得出什么结论。"],
            "purpose": "还原复盘信息来源与过程",
            "expected": ["反馈与信息来源", "参与人", "复盘结论"],
            "trigger": "候选人已说明事件，但尚未交代复盘过程",
        },
        "principle_decision": {
            "templates": ["「{quote}」对应的改进为什么优先选这一项？当时还考虑过哪些调整？",
                          "请说明「{quote}」中「{topic}」相关判断在复盘中是如何被重新评估的。"],
            "purpose": "考察改进优先级的判断依据",
            "expected": ["改进优先级依据", "候选调整项", "重新评估的判断标准"],
            "trigger": "候选人已给出复盘结论，需要了解决策依据",
        },
        "verification_challenge": {
            "templates": ["关于「{quote}」对应的改进，请说明后续是否真正落地，以及用什么证据确认有效。",
                          "如果「{quote}」中的改进没有产生预期效果，你如何判断原因？"],
            "purpose": "验证改进是否落地与效果可核查",
            "expected": ["落地情况", "效果证据", "未达预期的排查思路"],
            "trigger": "候选人已说明改进方案，需要检验执行与效果",
        },
        "scenario_migration": {
            "templates": ["如果{scene}换成另一个场景，「{quote}」对应的经验哪些可以复用、哪些需要重新验证？",
                          "回看「{quote}」，这段经验对你后续处理同类问题产生了什么具体改变？"],
            "purpose": "考察经验迁移与持续改进能力",
            "expected": ["可复用经验", "需重新验证的部分", "后续行为改变"],
            "trigger": "候选人已充分复盘，可结束追问",
        },
    },
}

# 生成期自检：任何追问链模板都必须携带同一句原文，否则会破坏「同经历」不变式
for _theme, _levels in CHAIN_LEVELS.items():
    for _level, _spec in _levels.items():
        for _t in _spec["templates"]:
            if "{quote}" not in _t:
                raise ValueError(f"追问链模板缺少原文引用: {_theme}/{_level}: {_t}")

THEME_BY_QTYPE = {
    "technical_deep_dive": "technical", "decision_analysis": "technical",
    "scenario_analysis": "technical", "problem_investigation": "technical",
    "data_verification": "evidence", "result_verification": "evidence", "risk_investigation": "evidence",
    "clarification": "clarification", "contribution_verification": "clarification",
    "reflection": "reflection",
}


class QuestionBuilder:
    def __init__(self, resume: dict[str, Any], experiences: list[dict[str, Any]],
                 facts_map: dict[str, list[dict[str, Any]]]):
        self.resume = resume
        self.exps = experiences
        self.facts_map = facts_map
        self.gc = config.get_config("generation_config")
        self.xcfg = config.get_config("experience_types")
        self.dcfg = config.get_config("question_dimensions")
        self.qtcfg = config.get_config("question_types")
        self.kb = load_position_kb(resume["position_id"])
        self.rng = random.Random(resume["generation"]["seed"] ^ 0xC0FFEE)
        self.ridx = int(resume["resume_id"].split("_")[1])
        self.valid_dims = {d["key"] for d in self.dcfg["dimensions"]}
        self.valid_qtypes = {d["key"] for d in self.qtcfg["question_types"]}
        self.priority_rank = {k: i for i, k in enumerate(self.xcfg["generation_priority"])}

    # ------------------------------------------------------------ 上下文
    def ctx(self, exp: dict[str, Any], fact: dict[str, Any]) -> dict[str, str]:
        return {
            "title": exp["title"],
            "org": exp["organization"],
            "topic": fact.get("difficulty") or self.rng.choice(self.kb["probe_topics"]),
            "tool": fact.get("tool") or self.rng.choice(self.kb["tools"]),
            "skill": fact.get("skill") or self.rng.choice(self.kb["core_skills"]),
            "scene": self.rng.choice(self.kb["business_scenarios"]),
            "team": self.rng.choice(["产品团队", "业务团队", "测试团队", "数据团队", "外部合作方"]),
        }

    def quote_and_offset(self, exp: dict[str, Any], fact: dict[str, Any]) -> tuple[str, int, int]:
        facts = self.facts_map[exp["experience_id"]]
        pos = 0
        for f in facts:
            if f["text"] == fact["text"]:
                q = strip_tail_punct(f["text"])
                return q, pos, pos + len(q)
            pos += len(f["text"])
        # 兜底：仍必须是精确子串，找不到则返回 null 偏移（由校验器判定）
        q = strip_tail_punct(fact["text"])
        start = exp["original_content"].find(q)
        return q, start if start >= 0 else -1, (start + len(q)) if start >= 0 else -1

    # ------------------------------------------------------------ 候选打分
    def base_score(self, exp: dict[str, Any], fact: dict[str, Any], qt: str,
                   variant: dict[str, Any]) -> float:
        s = 10.0
        rank = self.priority_rank.get(exp["experience_type"], 9)
        s += max(0, (8 - rank)) * 1.6
        s += 0.8 * self.kb["interview_dimensions"].get(variant["dim"], 1)
        q = self.resume["resume_quality"]
        if q == "vague":
            s += 9 if qt == "clarification" else (4 if qt == "contribution_verification" else 0)
        elif q == "contradictory":
            s += 11 if qt == "risk_investigation" else (5 if qt == "data_verification" else 0)
        elif q == "high":
            s += 5 if qt in ("technical_deep_dive", "data_verification") else (3 if qt == "decision_analysis" else 0)
        ft = fact["fact_type"]
        if ft == "vague_statement" and qt == "clarification":
            s += 8
        if ft == "risk_statement" and qt == "risk_investigation":
            s += 10
        if ft in ("metric", "optimization") and qt == "data_verification":
            s += 5
        lvl = self.resume["career_level"]
        if lvl in ("senior", "expert") and variant["dim"] in ("leadership", "project_management", "business_understanding"):
            s += 5
        if lvl == "fresh" and variant["dim"] in ("learning_ability", "professional_depth"):
            s += 4
        if exp["experience_type"] in ("project_experience", "work_experience"):
            s += 3
        return s

    # ------------------------------------------------------------ 问题生成
    def build_questions(self) -> list[dict[str, Any]]:
        rng = self.rng
        lo = self.gc["questions_per_resume_min"]
        hi = self.gc["questions_per_resume_max"]
        target_n = rng.randint(lo, hi)
        candidates: list[dict[str, Any]] = []
        for exp in self.exps:
            facts = self.facts_map.get(exp["experience_id"], [])
            for fact in facts:
                for qt in FACT_TYPE_QTYPE.get(fact["fact_type"], DEFAULT_QTYPE):
                    for variant in QTYPE_VARIANTS.get(qt, []):
                        if variant["dim"] not in self.valid_dims or qt not in self.valid_qtypes:
                            continue
                        candidates.append({
                            "exp": exp, "fact": fact, "qt": qt, "variant": variant,
                            "score": self.base_score(exp, fact, qt, variant),
                        })

        chosen: list[dict[str, Any]] = []
        used_keys: set[tuple[str, str, str]] = set()
        quote_count: Counter[str] = Counter()
        dim_count: Counter[str] = Counter()
        qtype_count: Counter[str] = Counter()
        exp_count: Counter[str] = Counter()
        used_indices: set[int] = set()
        need_exp = min(self.gc["min_distinct_experiences_per_resume"], len(self.exps))

        def pick_one(force_new_exp: bool) -> tuple | None:
            best, best_s = None, -1e18
            for idx, c in enumerate(candidates):
                if idx in used_indices:
                    continue
                exp, fact, dim, qt = c["exp"], c["fact"], c["variant"]["dim"], c["qt"]
                if force_new_exp and exp_count[exp["experience_id"]] > 0:
                    continue
                quote = strip_tail_punct(fact["text"])
                key = (exp["experience_id"], quote, dim)
                if key in used_keys or quote_count[quote] >= 2 or dim_count[dim] >= 3:
                    continue
                if exp_count[exp["experience_id"]] >= 4 or qtype_count[qt] >= 3:
                    continue
                s = (c["score"] - 7.0 * dim_count[dim] - 5.0 * qtype_count[qt]
                     - 3.5 * exp_count[exp["experience_id"]])
                if len(dim_count) < 4 and dim not in dim_count:
                    s += 7
                if len(qtype_count) < 3 and qt not in qtype_count:
                    s += 6
                s += rng.random() * 5
                if s > best_s:
                    best_s, best = s, (idx, c, key, quote)
            return best

        for _ in range(target_n):
            # 前若干轮强制从尚未覆盖的经历中选题，保证 >=3 个经历单元
            best = pick_one(len(exp_count) < need_exp)
            if best is None:
                best = pick_one(False)
            if best is None:
                break
            idx, c, key, quote = best
            used_indices.add(idx)
            used_keys.add(key)
            quote_count[quote] += 1
            dim_count[c["variant"]["dim"]] += 1
            qtype_count[c["qt"]] += 1
            exp_count[c["exp"]["experience_id"]] += 1
            chosen.append(c)

        questions: list[dict[str, Any]] = []
        for i, c in enumerate(chosen[:hi], 1):
            exp, fact, qt, var = c["exp"], c["fact"], c["qt"], c["variant"]
            ctx = self.ctx(exp, fact)
            quote, s_off, e_off = self.quote_and_offset(exp, fact)
            opener = rng.choice(OPENERS).format(**ctx)
            probe = rng.choice(var["probes"]).format(**ctx)
            question_text = f"{opener}「{quote}」{probe}"
            reason = var["reason"]
            expected = list(var["expected"])
            followups = list(rng.sample(var["followups"], min(3, len(var["followups"]))))
            secondary = [d for d in sorted(self.valid_dims)
                         if d != var["dim"] and d in self.kb["interview_dimensions"]]
            secondary = rng.sample(secondary, min(1, len(secondary)))
            if qt in ("risk_investigation", "data_verification", "technical_deep_dive"):
                priority = "high"
            elif qt in ("clarification", "contribution_verification", "result_verification", "decision_analysis"):
                priority = "high" if self.rng.random() < 0.55 else "medium"
            else:
                priority = "medium" if self.rng.random() < 0.7 else "low"
            lvl = self.resume["career_level"]
            difficulty = "hard" if (lvl == "expert" and qt in ("technical_deep_dive", "decision_analysis", "scenario_analysis")) else (
                "easy" if (lvl == "fresh" and qt in ("clarification", "reflection")) else "medium")
            q = {
                "question_id": f"Q_{self.ridx:06d}{i:02d}",
                "resume_id": exp["resume_id"],
                "experience_id": exp["experience_id"],
                "experience_type": exp["experience_type"],
                "reference": {
                    "original_text": quote,
                    "start_offset": s_off if s_off >= 0 else None,
                    "end_offset": e_off if e_off >= 0 else None,
                },
                "dimension": var["dim"],
                "secondary_dimensions": secondary,
                "question_type": qt,
                "question": question_text,
                "reason": reason,
                "expected_investigation": expected,
                "priority": priority,
                "difficulty": difficulty,
                "follow_up_questions": followups,
                "quality_score": 0,
            }
            q["quality_score"] = score_question(q)
            questions.append(q)
        return questions

    # ------------------------------------------------------------ 追问链
    def build_chains(self, questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rng = self.rng
        exp_by_id = {e["experience_id"]: e for e in self.exps}
        n_chain = self.gc["chains_per_resume_min"]
        ranked = sorted(questions, key=lambda q: (
            0 if q["priority"] == "high" else (1 if q["priority"] == "medium" else 2),
            -len(q["question"]), q["question_id"]))
        roots: list[dict[str, Any]] = []
        used_exp: set[str] = set()
        for q in ranked:
            if q["experience_id"] not in used_exp:
                roots.append(q)
                used_exp.add(q["experience_id"])
            if len(roots) >= n_chain:
                break
        for q in ranked:
            if len(roots) >= n_chain:
                break
            if q["question_id"] not in {x["question_id"] for x in roots}:
                roots.append(q)
        if len(roots) < n_chain:
            return []

        chains = []
        levels = self.gc["question_levels"]
        for i, root in enumerate(roots[:n_chain], 1):
            exp = exp_by_id[root["experience_id"]]
            quote = root["reference"]["original_text"]
            theme = THEME_BY_QTYPE.get(root["question_type"], "technical")
            depth = rng.randint(self.gc["chain_depth_min"], min(self.gc["chain_depth_max"], len(levels)))
            ctx = {
                "title": exp["title"], "quote": quote,
                "topic": rng.choice(self.kb["probe_topics"]),
                "scene": rng.choice(self.kb["business_scenarios"]),
            }
            items = []
            for seq, level in enumerate(levels[:depth], 1):
                spec = CHAIN_LEVELS[theme][level]
                items.append({
                    "sequence": seq,
                    "level": level,
                    "question": rng.choice(spec["templates"]).format(**ctx),
                    "purpose": spec["purpose"],
                    "expected_investigation": list(spec["expected"]),
                    "trigger_condition": spec["trigger"],
                })
            chain = {
                "chain_id": f"CHAIN_{self.ridx:06d}{i:02d}",
                "resume_id": root["resume_id"],
                "experience_id": root["experience_id"],
                "root_question_id": root["question_id"],
                "dimension": root["dimension"],
                "theme": theme,
                "chain_depth": depth,
                "stop_condition": "若候选人的回答已完整覆盖个人职责、执行过程、决策依据、指标口径与场景边界，可提前结束追问，不必走完全部层级。",
                "questions": items,
            }
            chain["quality_score"] = score_chain(chain)
            chains.append(chain)
        return chains


def build_for_resume(resume: dict[str, Any], experiences: list[dict[str, Any]],
                     facts_map: dict[str, list[dict[str, Any]]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    b = QuestionBuilder(resume, experiences, facts_map)
    questions = b.build_questions()
    chains = b.build_chains(questions)
    return questions, chains


def build_chains_for_resume(resume: dict[str, Any], experiences: list[dict[str, Any]],
                            questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """供独立脚本 generate_question_chains.py 使用：只重建追问链。"""
    b = QuestionBuilder(resume, experiences, {})
    return b.build_chains(questions)
