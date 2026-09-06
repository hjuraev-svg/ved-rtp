from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import Deal, Stage, StageEvent, User, UserDashboard
from ..reference import DEFAULT_PIPELINE, PIPELINE_BY_CODE
from ..schemas import DashboardOut, LayoutIn, LayoutOut
from ..security import current_user
from ..services import build_dashboard

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


# --------------------------------------------------------------------------
# Per-user tile layout
# --------------------------------------------------------------------------
async def _valid_stage_ids(db: AsyncSession) -> list[int]:
    return list((await db.execute(select(Stage.id).order_by(Stage.id))).scalars().all())


def _normalise(order: list[int], hidden: list[int], valid: list[int]) -> tuple[list[int], list[int]]:
    """Keep only real stage ids, drop duplicates, append anything missing.

    Guarantees the layout always covers every stage even after new blocks are
    added, so a saved arrangement can never hide part of the process by accident.
    """
    seen: set[int] = set()
    clean: list[int] = []
    for sid in order:
        if sid in valid and sid not in seen:
            seen.add(sid)
            clean.append(sid)
    clean.extend(sid for sid in valid if sid not in seen)
    clean_hidden = [sid for sid in dict.fromkeys(hidden) if sid in valid]
    return clean, clean_hidden


@router.get("/layout", response_model=LayoutOut)
async def get_layout(db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    valid = await _valid_stage_ids(db)
    row = await db.get(UserDashboard, user.id)
    if not row:
        return LayoutOut(tile_order=valid, hidden=[], is_custom=False)
    order, hidden = _normalise(row.tile_order or [], row.hidden or [], valid)
    return LayoutOut(tile_order=order, hidden=hidden, is_custom=True)


@router.put("/layout", response_model=LayoutOut)
async def save_layout(
    payload: LayoutIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    valid = await _valid_stage_ids(db)
    order, hidden = _normalise(payload.tile_order, payload.hidden, valid)

    row = await db.get(UserDashboard, user.id)
    if row is None:
        row = UserDashboard(user_id=user.id)
        db.add(row)
    row.tile_order = order
    row.hidden = hidden
    await db.commit()
    # Deliberately not broadcast: a layout belongs to one account, and pushing
    # it would reshuffle the dashboard under everyone else.
    return LayoutOut(tile_order=order, hidden=hidden, is_custom=True)


@router.delete("/layout", response_model=LayoutOut)
async def reset_layout(db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    row = await db.get(UserDashboard, user.id)
    if row:
        await db.delete(row)
        await db.commit()
    return LayoutOut(tile_order=await _valid_stage_ids(db), hidden=[], is_custom=False)


@router.get("", response_model=DashboardOut)
async def dashboard(
    pipeline: str = DEFAULT_PIPELINE,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(current_user),
):
    if pipeline not in PIPELINE_BY_CODE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Неизвестный тип сделки")
    return await build_dashboard(db, pipeline)


@router.get("/cycle-times")
async def cycle_times(
    days: int = 90,
    pipeline: str = DEFAULT_PIPELINE,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(current_user),
):
    """Average days spent in each stage, from completed transitions."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        await db.execute(
            select(
                StageEvent.from_stage_id,
                func.avg(StageEvent.days_in_from_stage),
                func.count(StageEvent.id),
            )
            .where(
                StageEvent.created_at >= since,
                StageEvent.from_stage_id.is_not(None),
                StageEvent.days_in_from_stage.is_not(None),
            )
            .group_by(StageEvent.from_stage_id)
        )
    ).all()
    stages = {
        s.id: s
        for s in (
            await db.execute(select(Stage).where(Stage.pipeline == pipeline).order_by(Stage.id))
        ).scalars().all()
    }
    by_stage = {r[0]: (float(r[1] or 0), int(r[2])) for r in rows}
    return [
        {
            "stage_id": sid,
            "name": st.name,
            "group_key": st.group_key,
            "avg_days": round(by_stage.get(sid, (0.0, 0))[0], 1),
            "sla_days": st.sla_days,
            "samples": by_stage.get(sid, (0.0, 0))[1],
        }
        for sid, st in stages.items()
    ]


@router.get("/throughput")
async def throughput(
    weeks: int = 12,
    pipeline: str = DEFAULT_PIPELINE,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(current_user),
):
    """Deals entering the final stage per ISO week — completion trend."""
    since = datetime.now(timezone.utc) - timedelta(weeks=weeks)
    final = (
        await db.execute(
            select(func.max(Stage.id)).where(Stage.pipeline == pipeline)
        )
    ).scalar_one_or_none()
    if final is None:
        return []
    # Group in Python rather than using PostgreSQL's date_trunc so the local
    # SQLite development server behaves exactly like production.
    rows = (
        await db.execute(
            select(StageEvent.created_at).where(
                StageEvent.created_at >= since,
                StageEvent.to_stage_id == final,
            )
        )
    ).scalars().all()
    counts: dict[str, int] = {}
    for created_at in rows:
        week = (created_at.date() - timedelta(days=created_at.weekday())).isoformat()
        counts[week] = counts.get(week, 0) + 1
    return [{"week": week, "count": counts[week]} for week in sorted(counts)]


@router.get("/by-supplier")
async def by_supplier(db: AsyncSession = Depends(get_db), _: User = Depends(current_user)):
    """Block 6: разбивка подписанных контрактов по поставщикам / странам."""
    from ..models import Supplier

    rows = (
        await db.execute(
            select(
                Supplier.name,
                Supplier.country,
                Deal.currency,
                func.count(Deal.id),
                func.sum(Deal.contract_amount),
            )
            .join(Deal, Deal.supplier_id == Supplier.id)
            .where(Deal.contract_amount.is_not(None))
            .group_by(Supplier.name, Supplier.country, Deal.currency)
            .order_by(func.sum(Deal.contract_amount).desc())
        )
    ).all()
    return [
        {
            "supplier": r[0],
            "country": r[1],
            "currency": r[2],
            "deals": int(r[3]),
            "amount": float(r[4] or 0),
        }
        for r in rows
    ]
