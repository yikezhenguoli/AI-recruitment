"""角色权限矩阵。

默认矩阵写在代码里；租户一旦通过 `PUT /admin/permissions` 改过，就以
`role_permission` 表为准。`admin` 角色始终拥有全部权限，避免把自己锁在门外。
"""

from sqlalchemy import text

PERMISSIONS = (
    "job:manage",
    "candidate:read",
    "offer:manage",
    "interview:manage",
    "talent:search",
    "member:manage",
    "audit:view",
    "backup:manage",
)

DEFAULT_MATRIX: dict[str, tuple[str, ...]] = {
    "admin": PERMISSIONS,
    "hr": ("job:manage", "candidate:read", "offer:manage", "interview:manage",
           "talent:search"),
    "candidate": (),
    "guest": (),
}


async def matrix(session, tenant_id) -> dict[str, list[str]]:
    rows = (await session.execute(text(
        "SELECT role::text, permission FROM role_permission WHERE tenant_id = :tenant"
    ), {"tenant": tenant_id})).all()
    if not rows:
        return {role: list(values) for role, values in DEFAULT_MATRIX.items()}
    result = {role: [] for role in DEFAULT_MATRIX}
    for role, permission in rows:
        result.setdefault(role, []).append(permission)
    return result


async def has_permission(session, tenant_id, role: str, permission: str) -> bool:
    if role == "admin":
        return True
    rows = (await session.execute(text(
        "SELECT permission FROM role_permission WHERE tenant_id = :tenant AND role = "
        "CAST(:role AS user_role)"
    ), {"tenant": tenant_id, "role": role})).scalars().all()
    if not rows:
        return permission in DEFAULT_MATRIX.get(role, ())
    return permission in rows


async def replace_role(session, tenant_id, role: str, permissions: list[str]) -> list[str]:
    unknown = sorted(set(permissions) - set(PERMISSIONS))
    if unknown:
        raise ValueError(f"Unknown permissions: {', '.join(unknown)}")
    if role == "admin":
        raise ValueError("admin 角色权限不可修改")
    await session.execute(text(
        "DELETE FROM role_permission WHERE tenant_id = :tenant AND role = CAST(:role AS user_role)"
    ), {"tenant": tenant_id, "role": role})
    for permission in dict.fromkeys(permissions):
        await session.execute(text(
            "INSERT INTO role_permission (tenant_id, role, permission) "
            "VALUES (:tenant, CAST(:role AS user_role), :permission)"
        ), {"tenant": tenant_id, "role": role, "permission": permission})
    return list(dict.fromkeys(permissions))
