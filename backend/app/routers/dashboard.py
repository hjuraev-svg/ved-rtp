from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import Claim, Deal, Payment, Stage, StageEvent, Supplier, User, UserDashboard
from ..reference import DEFAULT_PIPELINE, PIPELINE_BY_CODE
from ..schemas import DashboardOut, LayoutIn, LayoutOut
from ..security import current_user
from ..services import OPEN_STATUSES, build_dashboard

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


@router.get("/finance")
async def finance(
    pipeline: str = "",
    db: AsyncSession = Depends(get_db),
    _: User = Depends(current_user),
):
    """Взаиморасчёты: законтрактовано, оплачено, остаток — и график платежей.

    Считается по валютам раздельно и не приводится к одной: курс на дату есть
    не у каждого платежа, а складывать доллары с юанями без него — выдумывать
    цифру, которой никто не сможет доверять.
    """
    today = date.today()

    deal_filter = [Deal.status.in_(OPEN_STATUSES)]
    if pipeline:
        deal_filter.append(Deal.pipeline == pipeline)

    # --- законтрактовано по валютам ---
    contracted = (
        await db.execute(
            select(Deal.currency, func.sum(Deal.contract_amount))
            .where(*deal_filter, Deal.contract_amount.is_not(None))
            .group_by(Deal.currency)
        )
    ).all()

    # --- оплачено и запланировано по валютам и направлению ---
    paid_rows = (
        await db.execute(
            select(Payment.currency, Payment.direction, Payment.status, func.sum(Payment.amount))
            .join(Deal, Deal.id == Payment.deal_id)
            .where(*deal_filter)
            .group_by(Payment.currency, Payment.direction, Payment.status)
        )
    ).all()

    def bucket(direction: str, status_: str) -> list[dict]:
        return [
            {"currency": c or "USD", "amount": total or Decimal(0)}
            for c, d, s, total in paid_rows
            if d == direction and s == status_ and total
        ]

    # --- долг по сделкам: контракт минус оплаченное ---
    per_deal = (
        await db.execute(
            select(
                Deal.id,
                Deal.code,
                Deal.title,
                Deal.currency,
                Deal.contract_amount,
                Supplier.name,
                func.coalesce(
                    select(func.sum(Payment.amount))
                    .where(Payment.deal_id == Deal.id, Payment.status == "paid", Payment.direction == "out")
                    .correlate(Deal)
                    .scalar_subquery(),
                    0,
                ),
            )
            .outerjoin(Supplier, Supplier.id == Deal.supplier_id)
            .where(*deal_filter, Deal.contract_amount.is_not(None), Deal.contract_amount > 0)
            .order_by(Deal.contract_amount.desc())
        )
    ).all()

    debts = []
    for did, code, title, cur, amount, supplier, paid in per_deal:
        rest = (amount or Decimal(0)) - (paid or Decimal(0))
        if rest <= 0:
            continue
        debts.append(
            {
                "deal_id": did,
                "code": code,
                "title": title,
                "supplier": supplier or "—",
                "currency": cur or "USD",
                "contract_amount": amount,
                "paid": paid or Decimal(0),
                "rest": rest,
            }
        )

    # --- график: плановые платежи, просроченные первыми ---
    upcoming = (
        await db.execute(
            select(Payment, Deal.code, Deal.title, Supplier.name)
            .join(Deal, Deal.id == Payment.deal_id)
            .outerjoin(Supplier, Supplier.id == Deal.supplier_id)
            .where(*deal_filter, Payment.status == "planned")
            .order_by(Payment.due_date.nulls_last())
            .limit(50)
        )
    ).all()

    schedule = [
        {
            "payment_id": p.id,
            "deal_id": p.deal_id,
            "code": code,
            "title": title,
            "supplier": supplier or "—",
            "direction": p.direction,
            "kind": p.kind,
            "amount": p.amount,
            "currency": p.currency,
            "due_date": p.due_date,
            "overdue": bool(p.due_date and p.due_date < today),
        }
        for p, code, title, supplier in upcoming
    ]

    return {
        "generated_at": datetime.now(timezone.utc),
        "pipeline": pipeline or None,
        "contracted": [{"currency": c or "USD", "amount": t or Decimal(0)} for c, t in contracted if t],
        "paid_out": bucket("out", "paid"),
        "planned_out": bucket("out", "planned"),
        "paid_in": bucket("in", "paid"),
        "planned_in": bucket("in", "planned"),
        "debts": debts[:100],
        "debt_count": len(debts),
        "schedule": schedule,
        "overdue_count": sum(1 for s in schedule if s["overdue"]),
    }


@router.get("/supplier-rating")
async def supplier_rating(
    min_deals: int = 2,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(current_user),
):
    """Рейтинг поставщиков на исполненных поставках.

    Считается только по закрытым сделкам: у незавершённой нет ни срока
    исполнения, ни итога, и включать её значит хвалить поставщика авансом.
    Поставщики с одной-двумя поставками показываются, но помечаются — по
    такой выборке делать выводы нельзя.
    """
    rows = (
        await db.execute(
            select(
                Supplier.id,
                Supplier.name,
                Supplier.country,
                Supplier.category,
                Deal.created_at,
                Deal.closed_at,
                Deal.actual_arrival,
                Deal.eta,
                Deal.eta_initial,
                Deal.production_ready_plan,
                Deal.production_ready_fact,
            )
            .join(Deal, Deal.supplier_id == Supplier.id)
            .where(Deal.status == "done")
        )
    ).all()

    claims = dict(
        (
            await db.execute(
                select(Deal.supplier_id, func.count(Claim.id))
                .join(Claim, Claim.deal_id == Deal.id)
                .where(Deal.supplier_id.is_not(None))
                .group_by(Deal.supplier_id)
            )
        ).all()
    )

    agg: dict[int, dict] = {}
    for sid, name, country, category, created, closed, arrival, eta, eta0, plan, fact in rows:
        a = agg.setdefault(
            sid,
            {
                "supplier_id": sid, "supplier": name, "country": country, "category": category,
                "deals": 0, "cycle_days": [], "on_time": 0, "judged": 0, "slips": [],
            },
        )
        a["deals"] += 1

        # У сделок, загруженных из файлового архива, дата создания и закрытия
        # совпадают: в папке была одна дата. Нулевой цикл здесь означает «срок
        # неизвестен», а не «исполнено в тот же день», и в среднее не идёт —
        # иначе рейтинг показывал бы уверенный ноль там, где данных нет.
        if created and closed and (closed - created).days > 0:
            a["cycle_days"].append((closed - created).days)

        # В срок = приехал не позже обещанной ETA. Судим только там, где
        # обе даты есть: иначе «в срок» превратилось бы в «нет данных».
        if arrival and eta:
            a["judged"] += 1
            if arrival <= eta:
                a["on_time"] += 1
        if eta and eta0:
            a["slips"].append((eta - eta0).days)
        if plan and fact:
            a["slips"].append((fact - plan).days)

    out = []
    for sid, a in agg.items():
        cycles = a["cycle_days"]
        slips = a["slips"]
        out.append(
            {
                "supplier_id": sid,
                "supplier": a["supplier"],
                "country": a["country"] or "",
                "category": a["category"] or "",
                "deals": a["deals"],
                "avg_cycle_days": round(sum(cycles) / len(cycles)) if cycles else None,
                "on_time_pct": round(a["on_time"] / a["judged"] * 100) if a["judged"] else None,
                "judged_deliveries": a["judged"],
                "avg_slip_days": round(sum(slips) / len(slips)) if slips else None,
                "claims": int(claims.get(sid, 0)),
                "thin": a["deals"] < min_deals,
            }
        )
    out.sort(key=lambda r: (-r["deals"], r["supplier"]))
    return out


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
