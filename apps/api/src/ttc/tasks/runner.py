import asyncio
import logging

from sqlalchemy import text

from ttc.adapters.realtime import enqueue_hangup, hangup_call
from ttc.api.v1.evidence import fetch_crossref
from ttc.api.v1.voice import create_transcript_report
from ttc.core.db import dispose_engine, get_session
from ttc.domains.resume.service import parse_resume

logger = logging.getLogger(__name__)


async def run_once(*, llm=None, storage=None) -> bool:
    async for session in get_session():
        async with session.begin():
            expired = (await session.execute(text(
                "SELECT v.id, v.provider_call_id, c.tenant_id FROM voice_session v "
                "JOIN candidate c ON c.id = v.candidate_id WHERE v.status = 'live' "
                "AND v.started_at + v.max_seconds * interval '1 second' <= now() "
                "ORDER BY v.started_at FOR UPDATE OF v SKIP LOCKED LIMIT 1"
            ))).mappings().one_or_none()
            if expired is not None:
                await session.execute(text(
                    "UPDATE voice_session SET status = 'ended', ended_at = now(), "
                    "end_reason = 'timeout' WHERE id = :id"
                ), {"id": expired["id"]})
                await create_transcript_report(session, expired["id"])
                if expired["provider_call_id"]:
                    await enqueue_hangup(session, expired["tenant_id"], expired["id"],
                                         expired["provider_call_id"])
                return True
            task = (await session.execute(text(
                "SELECT id, tenant_id, type, resource_id, payload, attempts, "
                "max_attempts FROM task "
                "WHERE status = 'queued' ORDER BY "
                "CASE WHEN type = 'realtime_hangup' THEN 0 ELSE 1 END, created_at "
                "FOR UPDATE SKIP LOCKED LIMIT 1"
            ))).mappings().one_or_none()
            if task is None:
                return False
            await session.execute(text(
                "UPDATE task SET status = 'running', attempts = attempts + 1, "
                "started_at = now() WHERE id = :id"
            ), {"id": task["id"]})
        try:
            if task["type"] == "resume_parse":
                await session.execute(text(
                    "UPDATE resume SET parse_status = 'parsing' WHERE id = :id"
                ), {"id": task["resource_id"]})
                await parse_resume(session, task["resource_id"], llm=llm, storage=storage)
            elif task["type"] == "evidence_search":
                await fetch_crossref(session, task)
            elif task["type"] == "realtime_hangup":
                await hangup_call(task["payload"]["call_id"])
            else:
                raise ValueError(f"Unsupported task type: {task['type']}")
            await session.execute(text(
                "UPDATE task SET status = 'succeeded', finished_at = now(), error = NULL "
                "WHERE id = :id"
            ), {"id": task["id"]})
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.exception("Task %s failed", task["id"])
            retry = task["attempts"] + 1 < task["max_attempts"]
            await session.execute(text(
                "UPDATE task SET status = CAST(:status AS task_status), error = :error, "
                "finished_at = CASE WHEN :retry THEN NULL ELSE now() END "
                "WHERE id = :id"
            ), {"status": "queued" if retry else "failed", "error": str(exc)[:500],
                "retry": retry, "id": task["id"]})
            if not retry and task["type"] == "resume_parse":
                await session.execute(text(
                    "UPDATE resume SET parse_status = 'failed' WHERE id = :id"
                ), {"id": task["resource_id"]})
            await session.commit()
        return True
    return False


async def main() -> None:
    try:
        while True:
            if not await run_once():
                await asyncio.sleep(2)
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
