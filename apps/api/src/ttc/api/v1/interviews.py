"""面试排期：人工约定的时间窗，与 AI 实时语音面试（voice_session）是两条独立链路。

冲突规则：同一个面试官、或同一个候选人，在 `scheduled`/`confirmed` 状态下的
时间窗不允许重叠。`canceled`/`no_show`/`completed` 不占时间。
"""

import json
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ttc.api.deps import Principal, require_roles
from ttc.core.audit import record_audit
from ttc.core.db import get_session
from ttc.core.errors import TTCError
from ttc.core.notify import notify, notify_roles
from ttc.core.security import uuid7

router = APIRouter(tags=["interviews"])
hr = require_roles("hr", "admin")
candidate_role = require_roles("candidate")

ACTIVE = ("scheduled", "confirmed")


class ScheduleCreate(BaseModel):
    candidate_id: UUID
    job_id: UUID
    application_id: UUID | None = None
    plan_id: UUID | None = None
    interviewer_id: UUID | None = None
    scheduled_at: datetime
    duration_min: int = Field(default=45, ge=15, le=240)
    mode: Literal["onsite", "video", "phone"] = "video"
    location: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=2000)


class SchedulePatch(BaseModel):
    scheduled_at: datetime | None = None
    duration_min: int | None = Field(default=None, ge=15, le=240)
    mode: Literal["onsite", "video", "phone"] | None = None
    location: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=2000)
    interviewer_id: UUID | None = None


class StatusInput(BaseModel):
    status: Literal["confirmed", "completed", "canceled", "no_show"]
    note: str | None = Field(default=None, max_length=2000)


class PlanCreate(BaseModel):
    job_id: UUID | None = None
    name: str = Field(min_length=1, max_length=80)
    duration_min: int = Field(default=45, ge=5, le=120)
    rounds: list[dict] = Field(default_factory=list)
    dimensions: list[dict] = Field(default_factory=list)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise TTCError("TTC-2002", "时间必须包含时区", 409)
    return value


def _slot_end(row: dict) -> datetime:
    return row["scheduled_at"] + timedelta(minutes=row["duration_min"])


async def _conflicts(session: AsyncSession, *, tenant_id: UUID, start: datetime,
                     duration_min: int, interviewer_id: UUID | None,
                     candidate_id: UUID, exclude: UUID | None = None) -> dict:
    end = start + timedelta(minutes=duration_min)
    overlap = ("scheduled_at < :end AND "
               "scheduled_at + make_interval(mins => duration_min) > :start")
    base = {"tenant": tenant_id, "start": start, "end": end, "exclude": exclude}
    result: dict = {"interviewer": [], "candidate": []}
    if interviewer_id is not None:
        rows = (await session.execute(text(
            "SELECT id, scheduled_at, duration_min FROM interview_slot "
            "WHERE tenant_id = :tenant AND interviewer_id = :iv "
            "AND status IN ('scheduled','confirmed') "
            f"AND {overlap} AND (CAST(:exclude AS uuid) IS NULL OR id <> CAST(:exclude AS uuid))"
        ), {**base, "iv": interviewer_id})).mappings().all()
        result["interviewer"] = [dict(row) for row in rows]
    rows = (await session.execute(text(
        "SELECT id, scheduled_at, duration_min FROM interview_slot "
        "WHERE tenant_id = :tenant AND candidate_id = :candidate "
        "AND status IN ('scheduled','confirmed') "
        f"AND {overlap} AND (CAST(:exclude AS uuid) IS NULL OR id <> CAST(:exclude AS uuid))"
    ), {**base, "candidate": candidate_id})).mappings().all()
    result["candidate"] = [dict(row) for row in rows]
    return result


async def _assert_free(session: AsyncSession, **kwargs) -> None:
    clashes = await _conflicts(session, **kwargs)
    if clashes["interviewer"] or clashes["candidate"]:
        parts = []
        if clashes["interviewer"]:
            parts.append("面试官该时段已有安排")
        if clashes["candidate"]:
            parts.append("候选人该时段已有安排")
        raise TTCError("TTC-2002", "；".join(parts), 409, {"conflicts": clashes})


async def require_slot(session: AsyncSession, slot_id: UUID, tenant_id: UUID,
                       *, lock: bool = False) -> dict:
    row = (await session.execute(text(
        "SELECT * FROM interview_slot WHERE id = :id AND tenant_id = :tenant" +
        (" FOR UPDATE" if lock else "")
    ), {"id": slot_id, "tenant": tenant_id})).mappings().one_or_none()
    if row is None:
        raise TTCError("TTC-2001", "面试安排不存在", 404)
    return dict(row)


async def _candidate_user(session: AsyncSession, candidate_id: UUID) -> UUID | None:
    return (await session.execute(text(
        "SELECT user_id FROM candidate WHERE id = :id"), {"id": candidate_id}
    )).scalar_one_or_none()


@router.post("/interviews", status_code=201)
async def create_schedule(body: ScheduleCreate, user: Principal = Depends(hr),
                          session: AsyncSession = Depends(get_session)):
    start = _aware(body.scheduled_at)
    candidate = (await session.execute(text(
        "SELECT id, display_name FROM candidate WHERE id = :id AND tenant_id = :tenant"
    ), {"id": body.candidate_id, "tenant": user.tenant_id})).mappings().one_or_none()
    if candidate is None:
        raise TTCError("TTC-2001", "候选人不存在", 404)
    job = (await session.execute(text(
        "SELECT id, title FROM job WHERE id = :id AND tenant_id = :tenant"
    ), {"id": body.job_id, "tenant": user.tenant_id})).mappings().one_or_none()
    if job is None:
        raise TTCError("TTC-2001", "岗位不存在", 404)
    if body.interviewer_id is not None:
        exists = (await session.execute(text(
            "SELECT 1 FROM app_user WHERE id = :id AND tenant_id = :tenant AND status = 'active'"
        ), {"id": body.interviewer_id, "tenant": user.tenant_id})).scalar_one_or_none()
        if exists is None:
            raise TTCError("TTC-2001", "面试官不存在", 404)
    await _assert_free(session, tenant_id=user.tenant_id, start=start,
                       duration_min=body.duration_min,
                       interviewer_id=body.interviewer_id,
                       candidate_id=body.candidate_id)
    slot_id = uuid7()
    row = (await session.execute(text(
        "INSERT INTO interview_slot (id, tenant_id, application_id, candidate_id, job_id, "
        "plan_id, interviewer_id, scheduled_at, duration_min, mode, location, note, created_by) "
        "VALUES (:id, :tenant, :application, :candidate, :job, :plan, :iv, :at, :duration, "
        ":mode, :location, :note, :user) "
        "RETURNING id, status, scheduled_at, duration_min, mode, location, created_at"
    ), {"id": slot_id, "tenant": user.tenant_id, "application": body.application_id,
        "candidate": body.candidate_id, "job": body.job_id, "plan": body.plan_id,
        "iv": body.interviewer_id, "at": start, "duration": body.duration_min,
        "mode": body.mode, "location": body.location, "note": body.note,
        "user": user.id})).mappings().one()
    candidate_user = await _candidate_user(session, body.candidate_id)
    if candidate_user is not None:
        await notify(session, tenant_id=user.tenant_id, user_id=candidate_user,
                     kind="interview_scheduled", title="面试安排已确认",
                     body=f"{job['title']} 的面试安排在 "
                          f"{start.astimezone(UTC).isoformat()}（UTC）。",
                     link=f"/interviews/{slot_id}")
    if body.interviewer_id is not None:
        await notify(session, tenant_id=user.tenant_id, user_id=body.interviewer_id,
                     kind="interview_assigned", title="你有一场面试",
                     body=f"{candidate['display_name']} · {job['title']}，"
                          f"{start.astimezone(UTC).isoformat()}（UTC）。",
                     link=f"/schedules/{slot_id}")
    await record_audit(session, user, "interview.schedule", "interview_slot", slot_id)
    await session.commit()
    return dict(row)


@router.get("/interviews")
async def list_schedules(date_from: datetime | None = Query(default=None, alias="from"),
                         date_to: datetime | None = Query(default=None, alias="to"),
                         status: Literal["scheduled", "confirmed", "completed",
                                         "canceled", "no_show"] | None = None,
                         interviewer_id: UUID | None = None,
                         candidate_id: UUID | None = None,
                         job_id: UUID | None = None,
                         limit: int = Query(default=200, ge=1, le=500),
                         user: Principal = Depends(hr),
                         session: AsyncSession = Depends(get_session)):
    if date_from is not None:
        _aware(date_from)
    if date_to is not None:
        _aware(date_to)
    rows = (await session.execute(text(
        "SELECT s.id, s.status, s.scheduled_at, s.duration_min, s.mode, s.location, s.note, "
        "s.candidate_id, c.display_name AS candidate_name, "
        "s.job_id, j.title AS job_title, s.interviewer_id, u.display_name AS interviewer_name, "
        "s.application_id, s.created_at, s.updated_at "
        "FROM interview_slot s JOIN candidate c ON c.id = s.candidate_id "
        "JOIN job j ON j.id = s.job_id LEFT JOIN app_user u ON u.id = s.interviewer_id "
        "WHERE s.tenant_id = :tenant "
        "AND (CAST(:status AS text) IS NULL OR s.status = CAST(:status AS text)) "
        "AND (CAST(:from AS timestamptz) IS NULL OR s.scheduled_at >= CAST(:from AS timestamptz)) "
        "AND (CAST(:to AS timestamptz) IS NULL OR s.scheduled_at < CAST(:to AS timestamptz)) "
        "AND (CAST(:iv AS uuid) IS NULL OR s.interviewer_id = CAST(:iv AS uuid)) "
        "AND (CAST(:candidate AS uuid) IS NULL OR s.candidate_id = CAST(:candidate AS uuid)) "
        "AND (CAST(:job AS uuid) IS NULL OR s.job_id = CAST(:job AS uuid)) "
        "ORDER BY s.scheduled_at, s.id LIMIT :limit"
    ), {"tenant": user.tenant_id, "status": status, "from": date_from, "to": date_to,
        "iv": interviewer_id, "candidate": candidate_id, "job": job_id,
        "limit": limit})).mappings().all()
    return {"items": [dict(row) for row in rows]}


@router.get("/interviewers")
async def list_interviewers(user: Principal = Depends(hr),
                            session: AsyncSession = Depends(get_session)):
    """可选面试官：本租户在职的 hr / admin 账号（不含候选人）。"""
    rows = (await session.execute(text(
        "SELECT id, email, display_name, role::text AS role FROM app_user "
        "WHERE tenant_id = :tenant AND status = 'active' "
        "AND role IN ('hr', 'admin') ORDER BY display_name"
    ), {"tenant": user.tenant_id})).mappings().all()
    return {"items": [dict(row) for row in rows]}


@router.get("/interviews/{slot_id:uuid}")
async def get_schedule(slot_id: UUID, user: Principal = Depends(hr),
                       session: AsyncSession = Depends(get_session)):
    slot = await require_slot(session, slot_id, user.tenant_id)
    return slot


@router.patch("/interviews/{slot_id}")
async def reschedule(slot_id: UUID, body: SchedulePatch, user: Principal = Depends(hr),
                     session: AsyncSession = Depends(get_session)):
    slot = await require_slot(session, slot_id, user.tenant_id, lock=True)
    if slot["status"] not in ACTIVE:
        raise TTCError("TTC-2002", "只有待进行或已确认的面试可以改期", 409)
    start = _aware(body.scheduled_at) if body.scheduled_at else slot["scheduled_at"]
    duration = body.duration_min or slot["duration_min"]
    interviewer = body.interviewer_id if "interviewer_id" in body.model_fields_set \
        else slot["interviewer_id"]
    if body.interviewer_id is not None:
        exists = (await session.execute(text(
            "SELECT 1 FROM app_user WHERE id = :id AND tenant_id = :tenant AND status = 'active'"
        ), {"id": body.interviewer_id, "tenant": user.tenant_id})).scalar_one_or_none()
        if exists is None:
            raise TTCError("TTC-2001", "面试官不存在", 404)
    await _assert_free(session, tenant_id=user.tenant_id, start=start,
                       duration_min=duration, interviewer_id=interviewer,
                       candidate_id=slot["candidate_id"], exclude=slot_id)
    changes = body.model_dump(exclude_unset=True)
    updated = (await session.execute(text(
        "UPDATE interview_slot SET scheduled_at = :at, duration_min = :duration, "
        "mode = :mode, location = :location, note = :note, interviewer_id = :iv, "
        "updated_at = now() WHERE id = :id "
        "RETURNING id, status, scheduled_at, duration_min, mode, location, updated_at"
    ), {"id": slot_id, "at": start, "duration": duration,
        "mode": changes.get("mode", slot["mode"]),
        "location": changes.get("location", slot["location"]),
        "note": changes.get("note", slot["note"]), "iv": interviewer})).mappings().one()
    candidate_user = await _candidate_user(session, slot["candidate_id"])
    if candidate_user is not None and (start != slot["scheduled_at"] or
                                       duration != slot["duration_min"]):
        await notify(session, tenant_id=user.tenant_id, user_id=candidate_user,
                     kind="interview_rescheduled", title="面试时间已调整",
                     body=f"新的时间为 {start.astimezone(UTC).isoformat()}（UTC）。",
                     link=f"/interviews/{slot_id}")
    await record_audit(session, user, "interview.reschedule", "interview_slot", slot_id)
    await session.commit()
    return dict(updated)


@router.post("/interviews/{slot_id}/status")
async def set_status(slot_id: UUID, body: StatusInput, user: Principal = Depends(hr),
                     session: AsyncSession = Depends(get_session)):
    slot = await require_slot(session, slot_id, user.tenant_id, lock=True)
    if slot["status"] in ("canceled", "completed", "no_show"):
        raise TTCError("TTC-2002", "该面试已结束，状态不可再变", 409)
    if body.status == "confirmed" and slot["status"] != "scheduled":
        raise TTCError("TTC-2002", "只有待进行的面试可以确认", 409)
    updated = (await session.execute(text(
        "UPDATE interview_slot SET status = :status, note = COALESCE(:note, note), "
        "updated_at = now() WHERE id = :id RETURNING id, status, updated_at"
    ), {"id": slot_id, "status": body.status, "note": body.note})).mappings().one()
    candidate_user = await _candidate_user(session, slot["candidate_id"])
    if candidate_user is not None and body.status in ("canceled", "confirmed"):
        await notify(
            session, tenant_id=user.tenant_id, user_id=candidate_user,
            kind=f"interview_{body.status}",
            title="面试已取消" if body.status == "canceled" else "面试已确认",
            body=body.note or None, link=f"/interviews/{slot_id}")
    await record_audit(session, user, f"interview.{body.status}", "interview_slot", slot_id)
    await session.commit()
    return dict(updated)


@router.get("/interviews/availability")
async def availability(interviewer_id: UUID, day: date,
                       timezone: str = Query(default="Asia/Shanghai"),
                       duration_min: int = Query(default=45, ge=15, le=240),
                       user: Principal = Depends(hr),
                       session: AsyncSession = Depends(get_session)):
    """按 30 分钟栅格返回面试官当天可用的开始时间。

    只排除已有安排，不感知工作日历、节假日或工作时间外的约定；
    时间窗固定为 09:00–18:00（`timezone` 指定时区）。
    """
    try:
        tz = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise TTCError("TTC-2002", "时区无效", 409) from exc
    window_start = datetime.combine(day, time(9, 0), tzinfo=tz)
    window_end = datetime.combine(day, time(18, 0), tzinfo=tz)
    busy = (await session.execute(text(
        "SELECT scheduled_at, duration_min FROM interview_slot "
        "WHERE tenant_id = :tenant AND interviewer_id = :iv "
        "AND status IN ('scheduled','confirmed') "
        "AND scheduled_at >= :start AND scheduled_at < :end"
    ), {"tenant": user.tenant_id, "iv": interviewer_id,
        "start": window_start, "end": window_end})).mappings().all()
    busy_windows = [(row["scheduled_at"], _slot_end(dict(row))) for row in busy]
    free = []
    cursor = window_start
    step = timedelta(minutes=30)
    while cursor + timedelta(minutes=duration_min) <= window_end:
        end = cursor + timedelta(minutes=duration_min)
        if not any(busy_start < end and busy_end > cursor
                   for busy_start, busy_end in busy_windows):
            free.append({"start": cursor, "end": end})
        cursor += step
    return {"interviewer_id": interviewer_id, "date": day, "timezone": timezone,
            "duration_min": duration_min, "slots": free,
            "note": "仅按已有安排计算，未考虑节假日与个人日历"}


# ---------------------------------------------------------------- 面试计划

@router.post("/interview-plans", status_code=201)
async def create_plan(body: PlanCreate, user: Principal = Depends(hr),
                      session: AsyncSession = Depends(get_session)):
    if body.job_id is not None:
        exists = (await session.execute(text(
            "SELECT 1 FROM job WHERE id = :id AND tenant_id = :tenant"
        ), {"id": body.job_id, "tenant": user.tenant_id})).scalar_one_or_none()
        if exists is None:
            raise TTCError("TTC-2001", "岗位不存在", 404)
    plan_id = uuid7()
    row = (await session.execute(text(
        "INSERT INTO interview_plan (id, tenant_id, job_id, name, duration_min, rounds, "
        "dimensions) VALUES (:id, :tenant, :job, :name, :duration, "
        "CAST(:rounds AS jsonb), CAST(:dimensions AS jsonb)) "
        "RETURNING id, name, duration_min, rounds, dimensions, created_at"
    ), {"id": plan_id, "tenant": user.tenant_id, "job": body.job_id, "name": body.name,
        "duration": body.duration_min,
        "rounds": json.dumps(body.rounds, ensure_ascii=False),
        "dimensions": json.dumps(body.dimensions, ensure_ascii=False)
        })).mappings().one()
    await record_audit(session, user, "interview_plan.create", "interview_plan", plan_id)
    await session.commit()
    return dict(row)


@router.delete("/interview-plans/{plan_id}")
async def archive_plan(plan_id: UUID, user: Principal = Depends(hr),
                       session: AsyncSession = Depends(get_session)):
    result = await session.execute(text(
        "UPDATE interview_plan SET is_active = false WHERE id = :id AND tenant_id = :tenant "
        "RETURNING id"
    ), {"id": plan_id, "tenant": user.tenant_id})
    if result.scalar_one_or_none() is None:
        raise TTCError("TTC-2001", "面试计划不存在", 404)
    await session.commit()
    return {"id": plan_id, "is_active": False}


# ---------------------------------------------------------------- 候选人门户

@router.get("/portal/schedules")
async def my_schedules(user: Principal = Depends(candidate_role),
                       session: AsyncSession = Depends(get_session)):
    candidate_id = (await session.execute(text(
        "SELECT id FROM candidate WHERE user_id = :user AND tenant_id = :tenant"
    ), {"user": user.id, "tenant": user.tenant_id})).scalar_one_or_none()
    if candidate_id is None:
        return {"items": []}
    rows = (await session.execute(text(
        "SELECT s.id, s.status, s.scheduled_at, s.duration_min, s.mode, s.location, s.note, "
        "j.id AS job_id, j.title AS job_title, u.display_name AS interviewer_name "
        "FROM interview_slot s JOIN job j ON j.id = s.job_id "
        "LEFT JOIN app_user u ON u.id = s.interviewer_id "
        "WHERE s.candidate_id = :candidate ORDER BY s.scheduled_at DESC"
    ), {"candidate": candidate_id})).mappings().all()
    return {"items": [dict(row) for row in rows]}


@router.post("/portal/schedules/{slot_id}/confirm")
async def confirm_my_schedule(slot_id: UUID, user: Principal = Depends(candidate_role),
                              session: AsyncSession = Depends(get_session)):
    slot = (await session.execute(text(
        "SELECT s.* FROM interview_slot s JOIN candidate c ON c.id = s.candidate_id "
        "WHERE s.id = :id AND c.user_id = :user AND s.tenant_id = :tenant"
    ), {"id": slot_id, "user": user.id, "tenant": user.tenant_id})).mappings().one_or_none()
    if slot is None:
        raise TTCError("TTC-2001", "面试安排不存在", 404)
    if slot["status"] != "scheduled":
        raise TTCError("TTC-2002", "当前状态不可确认", 409)
    await session.execute(text(
        "UPDATE interview_slot SET status = 'confirmed', updated_at = now() WHERE id = :id"
    ), {"id": slot_id})
    await notify_roles(session, tenant_id=user.tenant_id, roles=("hr", "admin"),
                       kind="interview_confirmed", title="候选人已确认面试",
                       body=f"面试 {slot_id} 已被候选人确认。", link=f"/schedules/{slot_id}")
    await session.commit()
    return {"id": slot_id, "status": "confirmed"}
