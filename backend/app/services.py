"""Derived values: red zones, cycle times, dashboard aggregation.

Everything here is computed from stored facts — nothing is denormalised, so the
numbers can never drift from the underlying deals.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    ChecklistTemplate,
    Claim,
    Deal,
    DealChecklist,
    DealDocument,
    DocType,
    Stage,
    StageEvent,
)
from .reference import DEFAULT_PIPELINE, GROUP_BY_KEY, PIPELINE_BY_CODE

OPEN_STATUSES = ("active", "on_hold")


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def days_since(dt: datetime) -> float:
    return round((datetime.now(timezone.utc) - _aware(dt)).total_seconds() / 86400, 2)


def working_days(start: date, end: date) -> int:
    """Mon-Fri day count — «свыше 3 рабочих дней» for ГТД is a working-day rule."""
    if not start or not end or end < start:
        return 0
    total, cur = 0, start
    while cur < end:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            total += 1
    return total


def eta_slip_days(deal: Deal) -> int | None:
    """Positive = arriving later than first promised."""
    if deal.eta and deal.eta_initial:
        return (deal.eta - deal.eta_initial).days
    return None


def production_slip_days(deal: Deal) -> int | None:
    if not deal.production_ready_plan:
        return None
    reference = deal.production_ready_fact or date.today()
    return (reference - deal.production_ready_plan).days


def is_overdue(deal: Deal, sla_days: int | None) -> bool:
    """Red zone.

    The special rules below come from «Описание блоков» and only describe the
    import pipeline; «Местный поставщик» and «Услуга» fall back to plain
    time-in-stage against their own sla_days.
    """
    if deal.status not in OPEN_STATUSES:
        return False

    if deal.pipeline != "import":
        return sla_days is not None and days_since(deal.stage_entered_at) > sla_days

    if deal.stage_id == 15 and deal.gtd_submitted_at and not deal.gtd_released_at:
        return working_days(deal.gtd_submitted_at, date.today()) > (sla_days or 3)

    if deal.stage_id == 12:  # in transit: judged by ETA, not time-in-stage
        if deal.eta and not deal.actual_arrival and date.today() > deal.eta:
            return True
        slip = eta_slip_days(deal)
        return slip is not None and slip > 0

    if deal.stage_id == 9:  # production: «отклонение от плана более 5 дней»
        slip = production_slip_days(deal)
        if slip is not None and slip > (sla_days or 5):
            return True

    if sla_days is None:
        return False
    return days_since(deal.stage_entered_at) > sla_days


async def docs_ready_pct(db: AsyncSession, deal_id: int) -> int:
    """Block 13: % готовности комплекта = получено / требуется × 100."""
    res = await db.execute(
        select(
            func.count(DealDocument.id).filter(DocType.is_required.is_(True)),
            func.count(DealDocument.id).filter(
                DocType.is_required.is_(True), DealDocument.is_received.is_(True)
            ),
        )
        .select_from(DealDocument)
        .join(DocType, DocType.id == DealDocument.doc_type_id)
        .join(Deal, Deal.id == DealDocument.deal_id)
        .where(DealDocument.deal_id == deal_id, DocType.pipeline == Deal.pipeline)
    )
    required, received = res.one()
    return int(round(received / required * 100)) if required else 0


async def checklist_pct(db: AsyncSession, deal_id: int) -> int:
    res = await db.execute(
        select(
            func.count(DealChecklist.id),
            func.count(DealChecklist.id).filter(DealChecklist.is_done.is_(True)),
        )
        .select_from(DealChecklist)
        .join(ChecklistTemplate, ChecklistTemplate.id == DealChecklist.template_id)
        .join(Deal, Deal.id == DealChecklist.deal_id)
        .where(DealChecklist.deal_id == deal_id, ChecklistTemplate.pipeline == Deal.pipeline)
    )
    total, done = res.one()
    return int(round(done / total * 100)) if total else 0


async def bulk_progress(db: AsyncSession, deal_ids: list[int]) -> dict[int, tuple[int, int]]:
    """(docs_pct, checklist_pct) for many deals in two queries."""
    if not deal_ids:
        return {}

    docs = await db.execute(
        select(
            DealDocument.deal_id,
            func.count(DealDocument.id).filter(DocType.is_required.is_(True)),
            func.count(DealDocument.id).filter(
                DocType.is_required.is_(True), DealDocument.is_received.is_(True)
            ),
        )
        .select_from(DealDocument)
        .join(DocType, DocType.id == DealDocument.doc_type_id)
        .join(Deal, Deal.id == DealDocument.deal_id)
        .where(DealDocument.deal_id.in_(deal_ids), DocType.pipeline == Deal.pipeline)
        .group_by(DealDocument.deal_id)
    )
    doc_map = {
        row[0]: int(round(row[2] / row[1] * 100)) if row[1] else 0 for row in docs.all()
    }

    chk = await db.execute(
        select(
            DealChecklist.deal_id,
            func.count(DealChecklist.id),
            func.count(DealChecklist.id).filter(DealChecklist.is_done.is_(True)),
        )
        .select_from(DealChecklist)
        .join(ChecklistTemplate, ChecklistTemplate.id == DealChecklist.template_id)
        .join(Deal, Deal.id == DealChecklist.deal_id)
        .where(
            DealChecklist.deal_id.in_(deal_ids),
            ChecklistTemplate.pipeline == Deal.pipeline,
        )
        .group_by(DealChecklist.deal_id)
    )
    chk_map = {
        row[0]: int(round(row[2] / row[1] * 100)) if row[1] else 0 for row in chk.all()
    }

    return {did: (doc_map.get(did, 0), chk_map.get(did, 0)) for did in deal_ids}


def serialize_deal(deal: Deal, docs_pct: int = 0, chk_pct: int = 0) -> dict:
    stage = deal.stage
    sla = stage.sla_days if stage else None
    data = {
        c.name: getattr(deal, c.name) for c in Deal.__table__.columns
    }
    data.update(
        stage_name=stage.name if stage else "",
        stage_group=stage.group_name if stage else "",
        stage_group_key=stage.group_key if stage else "",
        supplier=deal.supplier,
        assignee=deal.assignee,
        days_in_stage=days_since(deal.stage_entered_at),
        sla_days=sla,
        is_overdue=is_overdue(deal, sla),
        eta_slip_days=eta_slip_days(deal),
        docs_ready_pct=docs_pct,
        checklist_done_pct=chk_pct,
    )
    return data


async def build_dashboard(db: AsyncSession, pipeline: str = DEFAULT_PIPELINE) -> dict:
    now = datetime.now(timezone.utc)
    today = date.today()
    week_ago = now - timedelta(days=7)
    week_ahead = today + timedelta(days=7)
    month_start = today.replace(day=1)

    stages = (
        await db.execute(select(Stage).where(Stage.pipeline == pipeline).order_by(Stage.id))
    ).scalars().all()
    stage_by_id = {s.id: s for s in stages}
    final_stage_id = stages[-1].id if stages else None

    open_deals = (
        (
            await db.execute(
                select(Deal)
                .where(Deal.status.in_(OPEN_STATUSES), Deal.pipeline == pipeline)
                .order_by(Deal.stage_id)
            )
        )
        .unique()
        .scalars()
        .all()
    )

    # ---- tiles ----
    per_stage: dict[int, list[Deal]] = defaultdict(list)
    for d in open_deals:
        per_stage[d.stage_id].append(d)

    entered_week = dict(
        (
            await db.execute(
                select(StageEvent.to_stage_id, func.count(StageEvent.id))
                .where(StageEvent.created_at >= week_ago)
                .group_by(StageEvent.to_stage_id)
            )
        ).all()
    )

    tiles = []
    alerts: list[dict] = []
    for stage in stages:
        deals = per_stage.get(stage.id, [])
        overdue = 0
        for d in deals:
            if is_overdue(d, stage.sla_days):
                overdue += 1
                alerts.append(_alert_for(d, stage))
        avg_days = round(sum(days_since(d.stage_entered_at) for d in deals) / len(deals), 1) if deals else 0.0
        group = GROUP_BY_KEY.get(stage.group_key, {"name": stage.group_name})
        tiles.append(
            {
                "stage_id": stage.id,
                "code": stage.code,
                "name": stage.name,
                "group_key": stage.group_key,
                "group_name": group.get("name", stage.group_name),
                "count": len(deals),
                "overdue": overdue,
                "sla_days": stage.sla_days,
                "entered_this_week": int(entered_week.get(stage.id, 0)),
                "avg_days_in_stage": avg_days,
            }
        )

    # ---- KPI ----
    signed_rows = (
        await db.execute(
            select(Deal.currency, func.count(Deal.id), func.sum(Deal.contract_amount))
            .where(
                Deal.pipeline == pipeline,
                Deal.contract_date >= month_start,
                Deal.contract_date <= today,
            )
            .group_by(Deal.currency)
        )
    ).all()
    contracts_signed_month = sum(int(r[1]) for r in signed_rows)
    contracts_amount_month = [
        {"currency": r[0] or "USD", "amount": r[2] or Decimal(0)} for r in signed_rows if r[2]
    ]

    in_transit = len(per_stage.get(12, [])) if pipeline == "import" else 0
    arriving_week = sum(
        1
        for d in open_deals
        if d.eta and not d.actual_arrival and today <= d.eta <= week_ahead
    )

    cleared = (
        await db.execute(
            select(Deal.gtd_submitted_at, Deal.gtd_released_at).where(
                Deal.pipeline == pipeline,
                Deal.gtd_submitted_at.is_not(None),
                Deal.gtd_released_at.is_not(None),
            )
        )
    ).all()
    avg_customs = (
        round(sum(working_days(a, b) for a, b in cleared) / len(cleared), 1) if cleared else None
    )

    doc_totals = (
        await db.execute(
            select(
                func.count(DealDocument.id).filter(DocType.is_required.is_(True)),
                func.count(DealDocument.id).filter(
                    DocType.is_required.is_(True), DealDocument.is_received.is_(True)
                ),
            )
            .select_from(DealDocument)
            .join(DocType, DocType.id == DealDocument.doc_type_id)
            .join(Deal, Deal.id == DealDocument.deal_id)
            .where(Deal.status.in_(OPEN_STATUSES), Deal.pipeline == pipeline)
        )
    ).one()
    docs_pct = int(round(doc_totals[1] / doc_totals[0] * 100)) if doc_totals[0] else 0

    claim_rows = (
        await db.execute(
            select(Claim.currency, func.count(Claim.id), func.sum(Claim.amount))
            .join(Deal, Deal.id == Claim.deal_id)
            .where(Claim.status.in_(("open", "in_progress")), Deal.pipeline == pipeline)
            .group_by(Claim.currency)
        )
    ).all()
    open_claims = sum(int(r[1]) for r in claim_rows)
    claims_amount = [{"currency": r[0] or "USD", "amount": r[2] or Decimal(0)} for r in claim_rows if r[2]]

    # УНК control: deals that already have a signed contract (stage >= 6)
    needs_unk = (
        [d for d in open_deals if d.stage_id >= 6 and d.contract_number]
        if pipeline == "import"
        else []
    )
    unk_registered = sum(1 for d in needs_unk if d.unk_number)
    unk_missing = len(needs_unk) - unk_registered
    for d in needs_unk:
        if not d.unk_number and d.stage_id >= 7:
            alerts.append(
                {
                    "deal_id": d.id,
                    "code": d.code,
                    "title": d.title,
                    "stage_id": d.stage_id,
                    "stage_name": stage_by_id[d.stage_id].name,
                    "days_in_stage": days_since(d.stage_entered_at),
                    "sla_days": stage_by_id[d.stage_id].sla_days,
                    "kind": "unk_missing",
                    "detail": "Контракт подписан, но УНК в банке не зарегистрирован",
                }
            )

    alerts.sort(key=lambda a: (-a["days_in_stage"],))

    return {
        "generated_at": now,
        "tiles": tiles,
        "kpi": {
            "active_deals": len(open_deals),
            "overdue_deals": len({a["deal_id"] for a in alerts}),
            "contracts_signed_month": contracts_signed_month,
            "contracts_amount_month": contracts_amount_month,
            "in_transit": in_transit,
            "arriving_this_week": arriving_week,
            "avg_customs_days": avg_customs,
            "docs_ready_pct": docs_pct,
            "open_claims": open_claims,
            "claims_amount": claims_amount,
            "unk_registered": unk_registered,
            "unk_missing": unk_missing,
        },
        "alerts": alerts[:50],
        "pipeline": pipeline,
        "groups": [
            {"key": k, "name": GROUP_BY_KEY[k]["name"], "color": GROUP_BY_KEY[k]["color"]}
            for k in dict.fromkeys(st.group_key for st in stages)
            if k in GROUP_BY_KEY
        ],
    }


def _alert_for(deal: Deal, stage: Stage) -> dict:
    kind, detail = "sla", f"Без движения {days_since(deal.stage_entered_at):.0f} дн. при норме {stage.sla_days} дн."

    if stage.id == 12:
        slip = eta_slip_days(deal)
        if deal.eta and not deal.actual_arrival and date.today() > deal.eta:
            kind = "eta_overdue"
            detail = f"ETA {deal.eta:%d.%m.%Y} прошла, прибытие не отмечено"
        elif slip:
            kind = "eta_slip"
            detail = f"ETA сдвинута на {slip} дн. ({deal.eta_initial:%d.%m} → {deal.eta:%d.%m})"
    elif stage.id == 9:
        slip = production_slip_days(deal)
        if slip is not None and slip > 0:
            kind = "production_slip"
            detail = f"Отставание от плана готовности на {slip} дн."
    elif stage.id == 15 and deal.gtd_submitted_at and not deal.gtd_released_at:
        kind = "customs_slow"
        detail = (
            f"На оформлении {working_days(deal.gtd_submitted_at, date.today())} раб. дн. "
            f"при норме {stage.sla_days}"
        )

    return {
        "deal_id": deal.id,
        "code": deal.code,
        "title": deal.title,
        "stage_id": stage.id,
        "stage_name": stage.name,
        "days_in_stage": days_since(deal.stage_entered_at),
        "sla_days": stage.sla_days,
        "kind": kind,
        "detail": detail,
    }


async def next_deal_code(db: AsyncSession, pipeline: str = DEFAULT_PIPELINE) -> str:
    """ВЭД-2026-001 / МП-2026-001 / УСЛ-2026-001.

    Numbering is per type and uses the highest existing suffix, so deleting a
    deal never makes the next one collide with an existing code.
    """
    year = date.today().year
    tag = PIPELINE_BY_CODE.get(pipeline, PIPELINE_BY_CODE[DEFAULT_PIPELINE])["prefix"]
    prefix = f"{tag}-{year}-"
    res = await db.execute(
        select(func.max(func.cast(func.substr(Deal.code, len(prefix) + 1), Integer))).where(
            Deal.code.like(f"{prefix}%")
        )
    )
    return f"{prefix}{(res.scalar_one() or 0) + 1:03d}"
