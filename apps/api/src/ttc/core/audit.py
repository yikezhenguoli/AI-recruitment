from sqlalchemy import text

from ttc.core.request_context import request_id_context


async def record_audit(session, user, action, resource_type, resource_id):
    await session.execute(text(
        "INSERT INTO audit_log (tenant_id, actor_id, action, resource_type, "
        "resource_id, request_id) VALUES (:tenant, :actor, :action, :type, :id, :request)"
    ), {"tenant": user.tenant_id, "actor": user.id, "action": action,
        "type": resource_type, "id": resource_id,
        "request": request_id_context.get() or "worker"})
