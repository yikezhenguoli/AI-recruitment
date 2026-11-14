"""Reset the configured TTC database to the complete demo baseline.

The reset keeps the schema and Alembic version, removes every business row,
then recreates:

* tenant ``demo`` / 演示企业
* admin ``web.test.hr@ttc.local``
* HR ``hr.demo@ttc.local`` and legacy ``hr.reset@ttc.local``
* candidate ``demo.candidate@ttc.local`` and ``candidate1@ttc.local`` ... ``candidate5@ttc.local``
* five published jobs with JD versions, weight plans and interview plans

Run from ``apps/api``:

    uv run python scripts/reset_demo_database.py --dry-run
    uv run python scripts/reset_demo_database.py --yes

The destructive mode requires ``--yes`` or an exact interactive confirmation.
Demo login passwords default to ``SeedDemo#2026`` and can be overridden with
``TTC_RESET_DEMO_PASSWORD``. Legacy reset passwords remain configurable with
``TTC_RESET_HR_PASSWORD`` and ``TTC_RESET_CANDIDATE_PASSWORD``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ttc.core.db import dispose_engine, get_engine
from ttc.core.security import hash_password, uuid7

EXPECTED_MIGRATION = "0011_interview_markdown_report"
DEMO_TENANT_SLUG = "demo"
DEMO_TENANT_NAME = "演示企业"
HR_EMAIL = "hr.reset@ttc.local"
HR_NAME = "新 HR"
HR_PASSWORD = os.environ.get("TTC_RESET_HR_PASSWORD", "HR#Reset2026!")
DEMO_ADMIN_EMAIL = "web.test.hr@ttc.local"
DEMO_ADMIN_NAME = "演示管理员"
DEMO_HR_EMAIL = "hr.demo@ttc.local"
DEMO_HR_NAME = "演示招聘专员"
DEMO_CANDIDATE_EMAIL = "demo.candidate@ttc.local"
DEMO_CANDIDATE_NAME = "演示候选人"
DEMO_PASSWORD = os.environ.get("TTC_RESET_DEMO_PASSWORD", "SeedDemo#2026")
CANDIDATE_PASSWORD = os.environ.get(
    "TTC_RESET_CANDIDATE_PASSWORD",
    "Candidate#2026!",
)
CANDIDATES = tuple(
    (f"candidate{index}@ttc.local", f"新候选人 {index}")
    for index in range(1, 6)
)
DEMO_JOB_PRESETS = (
    {
        "title": "高级后端工程师",
        "department": "研发部",
        "headcount": 2,
        "template": "engineering",
        "responsibilities": [
            "负责招聘平台核心服务和 API 的架构设计与开发",
            "建设异步任务、权限和租户隔离能力",
            "优化数据库查询、接口性能与稳定性",
            "参与技术评审、测试和可观测性建设",
        ],
        "requirements": [
            "本科及以上学历，5 年以上后端开发经验",
            "熟练使用 Python、FastAPI 与 PostgreSQL",
            "有异步任务、消息队列和多租户系统经验",
            "重视工程质量、安全边界和可追溯性",
        ],
        "skills": ["Python", "FastAPI", "PostgreSQL", "Redis", "WebSocket", "Docker"],
    },
    {
        "title": "机器学习工程师",
        "department": "算法部",
        "headcount": 2,
        "template": "algorithm",
        "responsibilities": [
            "负责简历解析、岗位匹配和面试评估模型的训练与上线",
            "建设数据清洗、特征工程和离线评测流水线",
            "优化模型服务的准确率、延迟和资源成本",
            "建立模型版本、评测集和回归验证机制",
        ],
        "requirements": [
            "硕士及以上学历，计算机、人工智能或相关专业",
            "熟练使用 Python、PyTorch 和常见 NLP 工具",
            "有信息抽取、分类或推荐系统落地经验",
            "理解模型评测、数据偏差与线上监控",
        ],
        "skills": ["Python", "PyTorch", "Transformers", "NLP", "Docker", "MLOps"],
    },
    {
        "title": "AI 产品经理",
        "department": "产品部",
        "headcount": 1,
        "template": "product",
        "responsibilities": [
            "负责 AI 招聘产品的需求分析、方案设计和版本规划",
            "定义模型能力边界、人工接管规则和验收指标",
            "与算法、研发和 HR 协作推动产品落地",
            "跟踪用户行为与招聘数据，持续优化体验",
        ],
        "requirements": [
            "3 年以上 B 端产品经验，有 AI 产品落地案例",
            "能够将业务问题拆解为可验证的产品假设",
            "理解大模型、语音交互和 Agent 的常见边界",
            "具备跨团队沟通、PRD 和数据分析能力",
        ],
        "skills": ["AI 产品", "PRD", "用户研究", "数据分析", "原型设计", "Agent"],
    },
    {
        "title": "内容营销经理",
        "department": "市场部",
        "headcount": 1,
        "template": "marketing",
        "responsibilities": [
            "制定企业 AI 招聘产品的品牌与内容策略",
            "策划案例、白皮书、直播和行业活动",
            "管理内容生产流程、渠道分发与合规审核",
            "基于获客和转化数据优化内容组合",
        ],
        "requirements": [
            "本科及以上学历，3 年以上 B 端内容营销经验",
            "具备优秀的中文写作、选题和活动策划能力",
            "熟悉公众号、视频号、SEO 和线索运营",
            "有 AI、SaaS 或人力资源行业经验者优先",
        ],
        "skills": ["内容策略", "B2B 营销", "SEO", "活动策划", "线索运营", "数据分析"],
    },
    {
        "title": "供应链运营专员",
        "department": "供应链部",
        "headcount": 1,
        "template": "supply_chain",
        "responsibilities": [
            "负责软件服务、云资源和外包采购执行",
            "跟踪合同、付款、交付和续费节点",
            "维护供应商档案、采购数据与运营报表",
            "配合财务完成对账、预算和成本分析",
        ],
        "requirements": [
            "本科及以上学历，1 年以上采购或供应链经验",
            "熟练使用 Excel、ERP 和合同管理系统",
            "具备良好的沟通、执行和风险意识",
            "有互联网或 SaaS 公司采购经验者优先",
        ],
        "skills": ["采购管理", "供应商管理", "合同管理", "Excel", "ERP", "成本分析"],
    },
)
DEMO_WEIGHT_TEMPLATES = {
    "engineering": (
        ("tech_stack", "技术栈匹配", "核心语言、框架与工具的实际使用深度", 30),
        ("project_depth", "项目复杂度", "系统规模、并发量与技术难点", 25),
        ("engineering_quality", "工程质量", "测试、稳定性、安全与可观测性意识", 15),
        ("collaboration", "协作沟通", "跨团队协作与方案表达能力", 15),
        ("business_understanding", "业务理解", "对业务目标与用户场景的理解", 15),
    ),
    "algorithm": (
        ("algorithm_fundamentals", "算法基础", "机器学习与数学基础", 30),
        ("project_depth", "项目深度", "真实模型项目和高质量成果", 20),
        ("experiment_rigor", "实验与数据能力", "数据构建、评估设计与结果归因", 20),
        ("engineering_ability", "工程落地能力", "训练、部署与性能优化经验", 15),
        ("business_understanding", "业务理解", "对业务指标和场景约束的理解", 15),
    ),
    "product": (
        ("insight", "需求洞察", "发现问题与理解用户的能力", 30),
        ("design", "产品设计", "方案完整度、优先级和文档质量", 25),
        ("data", "数据分析", "指标定义、实验设计与复盘", 20),
        ("collaboration", "跨团队协作", "推动研发、设计和业务协同落地", 15),
        ("industry", "行业理解", "对行业和商业模式的理解", 10),
    ),
    "marketing": (
        ("growth", "增长策略", "渠道组合、预算和转化优化", 30),
        ("content", "内容与渠道", "选题、内容生产与渠道运营", 25),
        ("analytics", "数据复盘", "归因分析、ROI 与实验能力", 20),
        ("brand", "品牌理解", "品牌定位与用户心智", 15),
        ("execution", "执行落地", "项目推进、节奏控制和协同", 10),
    ),
    "supply_chain": (
        ("planning", "计划与预测", "需求、采购计划和交付管理", 30),
        ("supplier", "供应商管理", "寻源、谈判和绩效管理", 25),
        ("cost", "成本控制", "成本结构分析和降本落地", 20),
        ("risk", "风险管理", "供应异常、合同和合规风险", 15),
        ("analytics", "数据分析", "使用数据工具支持决策", 10),
    ),
}
DEMO_INTERVIEW_DIMENSIONS = [
    {"key": "professional", "label": "专业能力", "weight_pct": 40},
    {"key": "problem_solving", "label": "问题解决", "weight_pct": 25},
    {"key": "collaboration", "label": "协作沟通", "weight_pct": 20},
    {"key": "motivation", "label": "动机与稳定性", "weight_pct": 15},
]
DEMO_INTERVIEW_ROUNDS = {
    "engineering": (45, [
        ("技术初筛", "核心技术与项目贡献", 8),
        ("技术深面", "架构、性能和故障处理", 15),
        ("协作评估", "跨团队协作和工程质量", 8),
        ("HR 终面", "动机、期望和稳定性", 5),
    ]),
    "algorithm": (60, [
        ("简历核验", "项目贡献、论文和成果真实性", 8),
        ("算法深面", "模型选型、数据和评估设计", 15),
        ("场景建模", "给定业务场景的分析与方案", 12),
        ("团队匹配", "协作方式、规划和稳定性", 5),
    ]),
    "product": (45, [
        ("需求复盘", "真实问题和决策过程", 10),
        ("产品案例", "现场拆解业务场景", 15),
        ("协作评估", "跨团队推动和验收", 8),
        ("HR 面", "动机、期望和稳定性", 5),
    ]),
    "marketing": (40, [
        ("内容案例", "过往内容和渠道成果", 10),
        ("活动策划", "现场设计行业活动", 12),
        ("数据复盘", "获客、转化和 ROI", 8),
        ("HR 面", "动机、期望和稳定性", 5),
    ]),
    "supply_chain": (40, [
        ("采购案例", "采购和供应商管理经历", 12),
        ("谈判模拟", "价格、交付和异常处理", 10),
        ("数据与风险", "对账、预算和风险识别", 8),
        ("HR 面", "动机、期望和稳定性", 5),
    ]),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="恢复 TTC 演示数据库初始状态（删除全部业务记录）",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="跳过交互确认，直接执行重置",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只检查迁移版本和待清理表，不修改数据库",
    )
    return parser.parse_args()


async def current_version(connection: AsyncConnection) -> str | None:
    return await connection.scalar(text("SELECT version_num FROM alembic_version"))


async def public_tables(connection: AsyncConnection) -> list[str]:
    rows = await connection.execute(text(
        "SELECT tablename FROM pg_tables "
        "WHERE schemaname = 'public' AND tablename <> 'alembic_version' "
        "ORDER BY tablename"
    ))
    return list(rows.scalars())


async def truncate_business_tables(connection: AsyncConnection) -> None:
    tables = await public_tables(connection)
    if not tables:
        raise RuntimeError("未找到可重置的 public 业务表")
    quoted = ", ".join(f'"{name.replace(chr(34), chr(34) * 2)}"' for name in tables)
    await connection.execute(text(
        f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"
    ))


def job_jd_text(spec: dict) -> str:
    responsibilities = "\n".join(
        f"{index}. {item}；"
        for index, item in enumerate(spec["responsibilities"], start=1)
    )
    requirements = "\n".join(
        f"{index}. {item}；"
        for index, item in enumerate(spec["requirements"], start=1)
    )
    skills = "、".join(spec["skills"])
    return (
        f"岗位名称：{spec['title']}\n\n"
        f"岗位职责：\n{responsibilities}\n\n"
        f"任职要求：\n{requirements}\n\n"
        f"技术栈：{skills}。"
    )


def weight_dimensions(template: str) -> list[dict]:
    return [
        {"key": key, "label": label, "description": description, "weight_pct": pct}
        for key, label, description, pct in DEMO_WEIGHT_TEMPLATES[template]
    ]


async def insert_demo_jobs(
    connection: AsyncConnection,
    tenant_id,
    owner_id,
    *,
    created_at: datetime | None = None,
) -> tuple[int, int]:
    """Ensure the five preset jobs exist; existing titles are never overwritten."""
    created = 0
    skipped = 0
    base_time = created_at or datetime.now(UTC)
    for index, spec in enumerate(DEMO_JOB_PRESETS):
        existing = (await connection.execute(
            text("SELECT id FROM job WHERE tenant_id = :tenant AND title = :title"),
            {"tenant": tenant_id, "title": spec["title"]},
        )).scalar_one_or_none()
        if existing is not None:
            skipped += 1
            continue

        job_id = uuid7()
        version_id = uuid7()
        job_time = base_time - timedelta(days=index)
        await connection.execute(text(
            "INSERT INTO job (id, tenant_id, owner_id, title, department, headcount, "
            "status, created_at, updated_at) VALUES (:id, :tenant, :owner, :title, "
            ":department, :headcount, 'draft', :created_at, :created_at)"
        ), {
            "id": job_id,
            "tenant": tenant_id,
            "owner": owner_id,
            "title": spec["title"],
            "department": spec["department"],
            "headcount": spec["headcount"],
            "created_at": job_time,
        })
        structured = {
            "role_title": spec["title"],
            "department": spec["department"],
            "responsibilities": spec["responsibilities"],
            "requirements": spec["requirements"],
            "required_skills": spec["skills"],
        }
        await connection.execute(text(
            "INSERT INTO job_version (id, job_id, version_no, jd_text, structured, "
            "source, is_saved, created_by, created_at) VALUES "
            "(:id, :job, 1, :jd_text, CAST(:structured AS jsonb), "
            "'manual', true, :owner, :created_at)"
        ), {
            "id": version_id,
            "job": job_id,
            "jd_text": job_jd_text(spec),
            "structured": json.dumps(structured, ensure_ascii=False),
            "owner": owner_id,
            "created_at": job_time,
        })
        await connection.execute(text(
            "UPDATE job SET status = 'published', current_version_id = :version, "
            "published_at = :published_at, updated_at = :published_at WHERE id = :id"
        ), {
            "id": job_id,
            "version": version_id,
            "published_at": job_time,
        })
        await connection.execute(text(
            "INSERT INTO weight_plan (id, tenant_id, job_id, name, mode, dimensions, "
            "total_pct) VALUES (:id, :tenant, :job, :name, 'custom', "
            "CAST(:dimensions AS jsonb), 100)"
        ), {
            "id": uuid7(),
            "tenant": tenant_id,
            "job": job_id,
            "name": f"{spec['title']} 评估权重",
            "dimensions": json.dumps(
                weight_dimensions(spec["template"]),
                ensure_ascii=False,
            ),
        })
        duration, rounds = DEMO_INTERVIEW_ROUNDS[spec["template"]]
        await connection.execute(text(
            "INSERT INTO interview_plan (id, tenant_id, job_id, name, duration_min, "
            "rounds, dimensions) VALUES (:id, :tenant, :job, :name, :duration, "
            "CAST(:rounds AS jsonb), CAST(:dimensions AS jsonb))"
        ), {
            "id": uuid7(),
            "tenant": tenant_id,
            "job": job_id,
            "name": f"{spec['title']} 面试方案",
            "duration": duration,
            "rounds": json.dumps(
                [
                    {"name": name, "focus": focus, "question_budget": budget}
                    for name, focus, budget in rounds
                ],
                ensure_ascii=False,
            ),
            "dimensions": json.dumps(DEMO_INTERVIEW_DIMENSIONS, ensure_ascii=False),
        })
        created += 1
    return created, skipped


async def insert_staff_user(
    connection: AsyncConnection,
    tenant_id,
    email: str,
    display_name: str,
    password: str,
    role: str,
) -> None:
    await connection.execute(
        text(
            "INSERT INTO app_user "
            "(id, tenant_id, email, display_name, password_hash, role, status) "
            "VALUES (:id, :tenant, :email, :name, :password_hash, "
            "CAST(:role AS user_role), 'active')"
        ),
        {
            "id": uuid7(),
            "tenant": tenant_id,
            "email": email,
            "name": display_name,
            "password_hash": hash_password(password),
            "role": role,
        },
    )


async def insert_login_candidate(
    connection: AsyncConnection,
    tenant_id,
    email: str,
    display_name: str,
    password: str,
    *,
    synthetic: bool,
) -> None:
    user_id = uuid7()
    await connection.execute(
        text(
            "INSERT INTO app_user "
            "(id, tenant_id, email, display_name, password_hash, role, status) "
            "VALUES (:id, :tenant, :email, :name, :password_hash, "
            "CAST('candidate' AS user_role), 'active')"
        ),
        {
            "id": user_id,
            "tenant": tenant_id,
            "email": email,
            "name": display_name,
            "password_hash": hash_password(password),
        },
    )
    await connection.execute(
        text(
            "INSERT INTO candidate "
            "(id, tenant_id, user_id, display_name, source, is_synthetic) "
            "VALUES (:id, :tenant, :user, :name, 'upload', :synthetic)"
        ),
        {
            "id": uuid7(),
            "tenant": tenant_id,
            "user": user_id,
            "name": display_name,
            "synthetic": synthetic,
        },
    )


async def insert_baseline(connection: AsyncConnection) -> None:
    tenant_id = uuid7()
    await connection.execute(
        text(
            "INSERT INTO tenant (id, slug, name, is_demo) "
            "VALUES (:id, :slug, :name, true)"
        ),
        {"id": tenant_id, "slug": DEMO_TENANT_SLUG, "name": DEMO_TENANT_NAME},
    )

    await insert_staff_user(
        connection,
        tenant_id,
        DEMO_ADMIN_EMAIL,
        DEMO_ADMIN_NAME,
        DEMO_PASSWORD,
        "admin",
    )
    await insert_staff_user(
        connection,
        tenant_id,
        DEMO_HR_EMAIL,
        DEMO_HR_NAME,
        DEMO_PASSWORD,
        "hr",
    )
    await insert_staff_user(
        connection,
        tenant_id,
        HR_EMAIL,
        HR_NAME,
        HR_PASSWORD,
        "hr",
    )

    await insert_login_candidate(
        connection,
        tenant_id,
        DEMO_CANDIDATE_EMAIL,
        DEMO_CANDIDATE_NAME,
        DEMO_PASSWORD,
        synthetic=True,
    )
    for email, display_name in CANDIDATES:
        await insert_login_candidate(
            connection,
            tenant_id,
            email,
            display_name,
            CANDIDATE_PASSWORD,
            synthetic=False,
        )
    admin_id = (await connection.execute(
        text("SELECT id FROM app_user WHERE tenant_id = :tenant AND email = :email"),
        {"tenant": tenant_id, "email": DEMO_ADMIN_EMAIL},
    )).scalar_one()
    created, skipped = await insert_demo_jobs(
        connection,
        tenant_id,
        admin_id,
    )
    print(f"预置岗位: created={created} skipped={skipped}")


async def reset(*, dry_run: bool) -> None:
    engine = get_engine()
    if engine is None:
        raise RuntimeError("DATABASE_URL is not configured")
    try:
        async with engine.connect() as connection:
            version = await current_version(connection)
            if version != EXPECTED_MIGRATION:
                raise RuntimeError(
                    f"数据库迁移版本为 {version!r}，期望 {EXPECTED_MIGRATION!r}；"
                    "请先执行 alembic upgrade head"
                )
            tables = await public_tables(connection)
            print(f"迁移版本: {version}")
            print(f"待清理业务表: {len(tables)} 张")
            print(f"重置后预置岗位: {len(DEMO_JOB_PRESETS)} 个（均为已发布状态）")
            if dry_run:
                print("dry-run：未修改数据库")
                return

        async with engine.begin() as connection:
            await truncate_business_tables(connection)
            await insert_baseline(connection)
    finally:
        await dispose_engine()

    async with get_engine().connect() as connection:
        counts = {
            "tenant": await connection.scalar(text("SELECT count(*) FROM tenant")),
            "app_user": await connection.scalar(text("SELECT count(*) FROM app_user")),
            "candidate": await connection.scalar(text("SELECT count(*) FROM candidate")),
            "auth_session": await connection.scalar(text("SELECT count(*) FROM auth_session")),
            "job": await connection.scalar(text("SELECT count(*) FROM job")),
            "published_job": await connection.scalar(
                text("SELECT count(*) FROM job WHERE status = 'published'")
            ),
            "weight_plan": await connection.scalar(text("SELECT count(*) FROM weight_plan")),
            "interview_plan": await connection.scalar(
                text("SELECT count(*) FROM interview_plan")
            ),
        }
    await dispose_engine()
    print(
        "恢复完成: "
        f"tenant={counts['tenant']} app_user={counts['app_user']} "
        f"candidate={counts['candidate']} auth_session={counts['auth_session']} "
        f"job={counts['job']} published_job={counts['published_job']} "
        f"weight_plan={counts['weight_plan']} "
        f"interview_plan={counts['interview_plan']}"
    )


def confirm() -> bool:
    print("警告：该操作会删除当前 TTC 数据库中的全部业务记录，且不可恢复。")
    if not sys.stdin.isatty():
        print("非交互环境必须显式传入 --yes。", file=sys.stderr)
        return False
    return input("输入 RESET 继续：").strip() == "RESET"


def main() -> int:
    args = parse_args()
    if not args.dry_run and not args.yes and not confirm():
        print("已取消")
        return 1
    try:
        asyncio.run(reset(dry_run=args.dry_run))
    except Exception as exc:
        print(f"恢复失败: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
