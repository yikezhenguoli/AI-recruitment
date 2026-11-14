"""Reset the configured TTC database to the current empty-demo baseline.

The reset keeps the schema and Alembic version, removes every business row,
then recreates:

* tenant ``demo`` / 演示企业
* HR ``hr.reset@ttc.local``
* candidates ``candidate1@ttc.local`` ... ``candidate5@ttc.local``

Run from ``apps/api``:

    uv run python scripts/reset_demo_database.py --dry-run
    uv run python scripts/reset_demo_database.py --yes

The destructive mode requires ``--yes`` or an exact interactive confirmation.
Passwords can be overridden with ``TTC_RESET_HR_PASSWORD`` and
``TTC_RESET_CANDIDATE_PASSWORD``.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ttc.core.db import dispose_engine, get_engine
from ttc.core.security import hash_password, uuid7

EXPECTED_MIGRATION = "0010_interview_pause_state"
DEMO_TENANT_SLUG = "demo"
DEMO_TENANT_NAME = "演示企业"
HR_EMAIL = "hr.reset@ttc.local"
HR_NAME = "新 HR"
HR_PASSWORD = os.environ.get("TTC_RESET_HR_PASSWORD", "HR#Reset2026!")
CANDIDATE_PASSWORD = os.environ.get(
    "TTC_RESET_CANDIDATE_PASSWORD",
    "Candidate#2026!",
)
CANDIDATES = tuple(
    (f"candidate{index}@ttc.local", f"新候选人 {index}")
    for index in range(1, 6)
)


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


async def insert_baseline(connection: AsyncConnection) -> None:
    tenant_id = uuid7()
    await connection.execute(
        text(
            "INSERT INTO tenant (id, slug, name, is_demo) "
            "VALUES (:id, :slug, :name, true)"
        ),
        {"id": tenant_id, "slug": DEMO_TENANT_SLUG, "name": DEMO_TENANT_NAME},
    )

    hr_user_id = uuid7()
    await connection.execute(
        text(
            "INSERT INTO app_user "
            "(id, tenant_id, email, display_name, password_hash, role, status) "
            "VALUES (:id, :tenant, :email, :name, :password_hash, "
            "CAST('hr' AS user_role), 'active')"
        ),
        {
            "id": hr_user_id,
            "tenant": tenant_id,
            "email": HR_EMAIL,
            "name": HR_NAME,
            "password_hash": hash_password(HR_PASSWORD),
        },
    )

    candidate_password_hash = hash_password(CANDIDATE_PASSWORD)
    for email, display_name in CANDIDATES:
        user_id = uuid7()
        candidate_id = uuid7()
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
                "password_hash": candidate_password_hash,
            },
        )
        await connection.execute(
            text(
                "INSERT INTO candidate "
                "(id, tenant_id, user_id, display_name, source, is_synthetic) "
                "VALUES (:id, :tenant, :user, :name, 'upload', false)"
            ),
            {
                "id": candidate_id,
                "tenant": tenant_id,
                "user": user_id,
                "name": display_name,
            },
        )


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
        }
    await dispose_engine()
    print(
        "恢复完成: "
        f"tenant={counts['tenant']} app_user={counts['app_user']} "
        f"candidate={counts['candidate']} auth_session={counts['auth_session']}"
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
