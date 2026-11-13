import argparse
import asyncio
import getpass
import os

from sqlalchemy import text

from ttc.core.config import get_settings
from ttc.core.db import dispose_engine, get_engine
from ttc.core.security import hash_password, uuid7


async def bootstrap(args, password: str) -> None:
    engine = get_engine()
    if engine is None:
        raise RuntimeError("DATABASE_URL is required")
    async with engine.begin() as connection:
        tenant = (await connection.execute(
            text("SELECT id FROM tenant WHERE slug = :slug"), {"slug": args.tenant_slug}
        )).scalar_one_or_none()
        if tenant is None:
            tenant = uuid7()
            await connection.execute(
                text("INSERT INTO tenant (id, slug, name, is_demo) "
                     "VALUES (:id, :slug, :name, :demo)"),
                {"id": tenant, "slug": args.tenant_slug, "name": args.tenant_name,
                 "demo": get_settings().demo_mode},
            )
        existing = (await connection.execute(
            text("SELECT id FROM app_user WHERE tenant_id = :tenant AND email = :email"),
            {"tenant": tenant, "email": args.email},
        )).scalar_one_or_none()
        if existing is not None:
            raise ValueError("User already exists; bootstrap will not change credentials")
        user_id = uuid7()
        await connection.execute(
            text("INSERT INTO app_user (id, tenant_id, email, display_name, password_hash, role) "
                 "VALUES (:id, :tenant, :email, :name, :password_hash, :role)"),
            {"id": user_id, "tenant": tenant, "email": args.email,
             "name": args.name, "password_hash": hash_password(password), "role": args.role},
        )
        if args.role == "candidate":
            await connection.execute(
                text("INSERT INTO candidate (id, tenant_id, user_id, display_name, "
                     "source, is_synthetic) VALUES (:id, :tenant, :user, :name, 'demo', true)"),
                {"id": uuid7(), "tenant": tenant, "user": user_id, "name": args.name},
            )
    await dispose_engine()
    print(f"Created {args.role} user {user_id} in tenant {args.tenant_slug}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a local tenant or user")
    parser.add_argument("--tenant-slug", required=True)
    parser.add_argument("--tenant-name", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--role", choices=("admin", "hr", "candidate"), default="admin")
    args = parser.parse_args()
    password = os.environ.get("TTC_BOOTSTRAP_PASSWORD") or getpass.getpass("Password: ")
    if len(password) < 12:
        parser.error("Password must be at least 12 characters")
    asyncio.run(bootstrap(args, password))


if __name__ == "__main__":
    main()
