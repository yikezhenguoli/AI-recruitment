"""Offer 管理与候选人决策。

状态机（单向）：
    draft -> sent -> accepted | declined
    draft/sent -> withdrawn
    sent -> expired（到期后惰性判定）

终态不再接受修改；每次状态迁移写一条 `offer_event` 留痕。
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ttc.api.deps import Principal, require_roles
from ttc.core.audit import record_audit
from ttc.core.db import get_session
from ttc.core.errors import TTCError
from ttc.core.notify import notify
from ttc.core.security import uuid7

router = APIRouter(tags=["offers"])
hr = require_roles("hr", "admin")
candidate_role = require_roles("candidate")

TERMINAL = ("accepted", "declined", "withdrawn", "expired")


class OfferCreate(BaseModel):
    application_id: UUID
    position_title: str | None = Field(default=None, min_length=1, max_length=160)
    salary_monthly: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    salary_months: int | None = Field(default=None, ge=1, le=24)
    start_date: date | None = None
    expires_at: datetime | None = None
    note: str | None = Field(default=None, max_length=2000)


class OfferPatch(BaseModel):
    position_title: str | None = Field(default=None, min_length=1, max_length=160)
    salary_monthly: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    salary_months: int | None = Field(default=None, ge=1, le=24)
    start_date: date | None = None
    expires_at: datetime | None = None
    note: str | None = Field(default=None, max_length=2000)


class Decision(BaseModel):
    decision: Literal["accepted", "declined"]
    note: str | None = Field(default=None, max_length=2000)


async def _expire_stale(session: AsyncSession, tenant_id: UUID) -> None:
    """把已过期但仍标记为 sent 的 offer 收口，保证读到的状态是真实的。"""
    await session.execute(text(
        "UPDATE offer SET status = 'expired', decided_at = now(), updated_at = now() "
        "WHERE tenant_id = :tenant AND status = 'sent' AND expires_at IS NOT NULL "
        "AND expires_at <= now()"
    ), {"tenant": tenant_id})


async def require_offer(session: AsyncSession, offer_id: UUID, tenant_id: UUID,
                        *, lock: bool = False) -> dict:
    row = (await session.execute(text(
        "SELECT * FROM offer WHERE id = :id AND tenant_id = :tenant" +
        (" FOR UPDATE" if lock else "")
    ), {"id": offer_id, "tenant": tenant_id})).mappings().one_or_none()
    if row is None:
        raise TTCError("TTC-2001", "Offer 不存在", 404)
    return dict(row)


async def _event(session: AsyncSession, offer_id: UUID, actor_id: UUID | None,
                 from_status: str | None, to_status: str, note: str | None = None) -> None:
    await session.execute(text(
        "INSERT INTO offer_event (id, offer_id, actor_id, from_status, to_status, note) "
        "VALUES (:id, :offer, :actor, :from_status, :to_status, :note)"
    ), {"id": uuid7(), "offer": offer_id, "actor": actor_id,
        "from_status": from_status, "to_status": to_status, "note": note})


def _check_expiry(value: datetime | None) -> None:
    if value is None:
        return
    if value.tzinfo is None:
        raise TTCError("TTC-2002", "有效期必须包含时区", 409)
    if value <= datetime.now(value.tzinfo):
        raise TTCError("TTC-2002", "有效期必须晚于当前时间", 409)


def _guard(offer: dict, allowed: tuple[str, ...]) -> None:
    if offer["status"] not in allowed:
        raise TTCError("TTC-2002",
                       f"Offer 当前状态为 {offer['status']}，不能执行该操作", 409)


@router.post("/offers", status_code=201)
async def create_offer(body: OfferCreate, user: Principal = Depends(hr),
                       session: AsyncSession = Depends(get_session)):
    application = (await session.execute(text(
        "SELECT ap.id, ap.candidate_id, ap.job_id, j.title FROM application ap "
        "JOIN job j ON j.id = ap.job_id "
        "WHERE ap.id = :id AND ap.tenant_id = :tenant"
    ), {"id": body.application_id, "tenant": user.tenant_id})).mappings().one_or_none()
    if application is None:
        raise TTCError("TTC-2001", "投递记录不存在", 404)
    _check_expiry(body.expires_at)
    existing = (await session.execute(text(
        "SELECT id, status FROM offer WHERE application_id = :id"
    ), {"id": body.application_id})).mappings().one_or_none()
    if existing is not None:
        raise TTCError("TTC-2002",
                       f"该投递已存在 Offer（状态 {existing['status']}）", 409)
    offer_id = uuid7()
    row = (await session.execute(text(
        "INSERT INTO offer (id, tenant_id, application_id, candidate_id, job_id, "
        "position_title, salary_monthly, salary_months, start_date, expires_at, note, "
        "created_by) VALUES (:id, :tenant, :application, :candidate, :job, :title, "
        ":salary, :months, :start, :expires, :note, :user) "
        "RETURNING id, status, position_title, created_at"
    ), {"id": offer_id, "tenant": user.tenant_id, "application": body.application_id,
        "candidate": application["candidate_id"], "job": application["job_id"],
        "title": body.position_title or application["title"],
        "salary": body.salary_monthly, "months": body.salary_months,
        "start": body.start_date, "expires": body.expires_at, "note": body.note,
        "user": user.id})).mappings().one()
    await _event(session, offer_id, user.id, None, "draft", "创建 Offer 草稿")
    await record_audit(session, user, "offer.create", "offer", offer_id)
    await session.commit()
    return dict(row)


@router.get("/offers")
async def list_offers(status: Literal["draft", "sent", "accepted", "declined",
                                     "withdrawn", "expired"] | None = None,
                      job_id: UUID | None = None,
                      limit: int = Query(default=50, ge=1, le=200),
                      user: Principal = Depends(hr),
                      session: AsyncSession = Depends(get_session)):
    await _expire_stale(session, user.tenant_id)
    rows = (await session.execute(text(
        "SELECT o.id, o.status, o.position_title, o.salary_monthly, o.salary_months, "
        "o.start_date, o.expires_at, o.sent_at, o.decided_at, o.created_at, o.updated_at, "
        "o.candidate_id, c.display_name AS candidate_name, "
        "o.job_id, j.title AS job_title, o.application_id "
        "FROM offer o JOIN candidate c ON c.id = o.candidate_id "
        "JOIN job j ON j.id = o.job_id "
        "WHERE o.tenant_id = :tenant "
        "AND (CAST(:status AS text) IS NULL OR o.status = CAST(:status AS text)) "
        "AND (CAST(:job AS uuid) IS NULL OR o.job_id = CAST(:job AS uuid)) "
        "ORDER BY o.created_at DESC LIMIT :limit"
    ), {"tenant": user.tenant_id, "status": status, "job": job_id,
        "limit": limit})).mappings().all()
    await session.commit()
    return {"items": [dict(row) for row in rows]}


@router.get("/offers/{offer_id}")
async def get_offer(offer_id: UUID, user: Principal = Depends(hr),
                    session: AsyncSession = Depends(get_session)):
    await _expire_stale(session, user.tenant_id)
    offer = await require_offer(session, offer_id, user.tenant_id)
    events = (await session.execute(text(
        "SELECT id, actor_id, from_status, to_status, note, created_at "
        "FROM offer_event WHERE offer_id = :id ORDER BY created_at, id"
    ), {"id": offer_id})).mappings().all()
    await session.commit()
    return {**offer, "events": [dict(row) for row in events]}


@router.patch("/offers/{offer_id}")
async def patch_offer(offer_id: UUID, body: OfferPatch, user: Principal = Depends(hr),
                      session: AsyncSession = Depends(get_session)):
    offer = await require_offer(session, offer_id, user.tenant_id, lock=True)
    _guard(offer, ("draft", "sent"))
    _check_expiry(body.expires_at)
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        await session.commit()
        return offer
    updated = (await session.execute(text(
        "UPDATE offer SET position_title = :title, salary_monthly = :salary, "
        "salary_months = :months, start_date = :start, expires_at = :expires, note = :note, "
        "updated_at = now() WHERE id = :id AND tenant_id = :tenant "
        "RETURNING id, status, position_title, salary_monthly, salary_months, "
        "start_date, expires_at, note, updated_at"
    ), {"id": offer_id, "tenant": user.tenant_id,
        "title": changes.get("position_title", offer["position_title"]),
        "salary": changes.get("salary_monthly", offer["salary_monthly"]),
        "months": changes.get("salary_months", offer["salary_months"]),
        "start": changes.get("start_date", offer["start_date"]),
        "expires": changes.get("expires_at", offer["expires_at"]),
        "note": changes.get("note", offer["note"])})).mappings().one()
    await record_audit(session, user, "offer.update", "offer", offer_id)
    await session.commit()
    return dict(updated)


@router.post("/offers/{offer_id}/send")
async def send_offer(offer_id: UUID, user: Principal = Depends(hr),
                     session: AsyncSession = Depends(get_session)):
    offer = await require_offer(session, offer_id, user.tenant_id, lock=True)
    _guard(offer, ("draft",))
    updated = (await session.execute(text(
        "UPDATE offer SET status = 'sent', sent_at = now(), updated_at = now() "
        "WHERE id = :id RETURNING id, status, sent_at, expires_at"
    ), {"id": offer_id})).mappings().one()
    await _event(session, offer_id, user.id, "draft", "sent", "发送给候选人")
    await _notify_candidate(session, offer, "offer_sent", "你收到一份 Offer",
                            f"{offer['position_title']} 的 Offer 已发出，请登录查看。",
                            f"/offers/{offer_id}")
    await record_audit(session, user, "offer.send", "offer", offer_id)
    await session.commit()
    return dict(updated)


@router.post("/offers/{offer_id}/withdraw")
async def withdraw_offer(offer_id: UUID, user: Principal = Depends(hr),
                         session: AsyncSession = Depends(get_session)):
    offer = await require_offer(session, offer_id, user.tenant_id, lock=True)
    _guard(offer, ("draft", "sent"))
    updated = (await session.execute(text(
        "UPDATE offer SET status = 'withdrawn', decided_at = now(), updated_at = now() "
        "WHERE id = :id RETURNING id, status, decided_at"
    ), {"id": offer_id})).mappings().one()
    await _event(session, offer_id, user.id, offer["status"], "withdrawn", "招聘方撤回")
    await _notify_candidate(session, offer, "offer_withdrawn", "Offer 已撤回",
                            f"{offer['position_title']} 的 Offer 已被招聘方撤回。",
                            f"/offers/{offer_id}")
    await record_audit(session, user, "offer.withdraw", "offer", offer_id)
    await session.commit()
    return dict(updated)


@router.post("/offers/{offer_id}/decision")
async def record_decision(offer_id: UUID, body: Decision, user: Principal = Depends(hr),
                          session: AsyncSession = Depends(get_session)):
    """招聘方代录候选人决定（电话/邮件沟通后补录）。"""
    return await _decide(session, offer_id, user, body, by_candidate=False)


async def _decide(session: AsyncSession, offer_id: UUID, user: Principal,
                  body: Decision, *, by_candidate: bool) -> dict:
    offer = await require_offer(session, offer_id, user.tenant_id, lock=True)
    _guard(offer, ("sent",))
    updated = (await session.execute(text(
        "UPDATE offer SET status = :status, decided_at = now(), updated_at = now() "
        "WHERE id = :id RETURNING id, status, decided_at"
    ), {"id": offer_id, "status": body.decision})).mappings().one()
    actor = "候选人" if by_candidate else "招聘方代录"
    await _event(session, offer_id, user.id, "sent", body.decision,
                 f"{actor}决定：{body.decision}。{body.note or ''}".strip())
    if by_candidate:
        await record_audit(session, user, "offer.decision", "offer", offer_id)
    await session.commit()
    return dict(updated)


async def _notify_candidate(session: AsyncSession, offer: dict, kind: str, title: str,
                            body: str, link: str) -> None:
    user_id = (await session.execute(text(
        "SELECT user_id FROM candidate WHERE id = :id"
    ), {"id": offer["candidate_id"]})).scalar_one_or_none()
    if user_id is None:
        return
    await notify(session, tenant_id=offer["tenant_id"], user_id=user_id, kind=kind,
                 title=title, body=body, link=link)


# ---------------------------------------------------------------- 候选人门户

@router.get("/portal/offers")
async def my_offers(user: Principal = Depends(candidate_role),
                    session: AsyncSession = Depends(get_session)):
    candidate_id = (await session.execute(text(
        "SELECT id FROM candidate WHERE user_id = :user AND tenant_id = :tenant"
    ), {"user": user.id, "tenant": user.tenant_id})).scalar_one_or_none()
    if candidate_id is None:
        return {"items": []}
    await _expire_stale(session, user.tenant_id)
    rows = (await session.execute(text(
        "SELECT o.id, o.status, o.position_title, o.salary_monthly, o.salary_months, "
        "o.start_date, o.expires_at, o.sent_at, o.decided_at, o.note, o.created_at, "
        "j.id AS job_id, j.title AS job_title "
        "FROM offer o JOIN job j ON j.id = o.job_id "
        "WHERE o.candidate_id = :candidate AND o.status <> 'draft' "
        "ORDER BY o.created_at DESC"
    ), {"candidate": candidate_id})).mappings().all()
    await session.commit()
    return {"items": [dict(row) for row in rows]}


@router.post("/portal/offers/{offer_id}/decision")
async def decide_my_offer(offer_id: UUID, body: Decision,
                          user: Principal = Depends(candidate_role),
                          session: AsyncSession = Depends(get_session)):
    offer = (await session.execute(text(
        "SELECT o.* FROM offer o JOIN candidate c ON c.id = o.candidate_id "
        "WHERE o.id = :id AND c.user_id = :user AND o.tenant_id = :tenant"
    ), {"id": offer_id, "user": user.id, "tenant": user.tenant_id})).mappings().one_or_none()
    if offer is None:
        raise TTCError("TTC-2001", "Offer 不存在", 404)
    return await _decide(session, offer_id, user, body, by_candidate=True)
