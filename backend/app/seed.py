# -*- coding: utf-8 -*-
"""Idempotent bootstrap: reference tables always, demo data only when empty."""

import logging
import random
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .models import (
    Claim,
    ChecklistTemplate,
    Deal,
    DealChecklist,
    DealDocument,
    DocType,
    Quote,
    Stage,
    StageEvent,
    Supplier,
    User,
)
from .reference import CHECKLIST, CHECKLIST_PIPELINE, DOC_TYPES, GROUP_BY_KEY, STAGES
from .security import hash_password

log = logging.getLogger("ved.seed")


async def seed_reference(db: AsyncSession) -> None:
    for row in STAGES:
        group = GROUP_BY_KEY[row["group_key"]]
        stage = await db.get(Stage, row["id"])
        is_new = stage is None
        if is_new:
            stage = Stage(id=row["id"])
            db.add(stage)
        # Descriptive text is owned by the sheet and always refreshed.
        stage.pipeline = row["pipeline"]
        stage.code = row["code"]
        stage.name = row["name"]
        stage.group_key = row["group_key"]
        stage.group_name = group["name"]
        stage.description = row["description"]
        stage.how_to_count = row["how_to_count"]
        stage.data_source = row["data_source"]
        # Operational settings are editable in the UI — seed them once, never overwrite.
        if is_new:
            stage.frequency = row["frequency"]
            stage.responsible = row["responsible"]
            stage.sla_days = row["sla_days"]

    for order_no, (code, title, stage_id, section) in enumerate(CHECKLIST, start=1):
        res = await db.execute(select(ChecklistTemplate).where(ChecklistTemplate.code == code))
        tpl = res.scalar_one_or_none()
        if tpl is None:
            tpl = ChecklistTemplate(code=code)
            db.add(tpl)
        tpl.title = title
        tpl.pipeline = CHECKLIST_PIPELINE
        tpl.stage_id = stage_id
        tpl.section = section
        tpl.order_no = order_no

    for code, name, required, order_no, pipeline in DOC_TYPES:
        res = await db.execute(select(DocType).where(DocType.code == code))
        dt = res.scalar_one_or_none()
        if dt is None:
            dt = DocType(code=code)
            db.add(dt)
        dt.name = name
        dt.is_required = required
        dt.order_no = order_no
        dt.pipeline = pipeline

    await db.commit()
    log.info("reference data seeded (%d stages across pipelines, %d checklist, %d doc types)",
             len(STAGES), len(CHECKLIST), len(DOC_TYPES))


async def seed_admin(db: AsyncSession) -> None:
    res = await db.execute(select(func.count(User.id)))
    if res.scalar_one() > 0:
        return
    # ADMIN_EMAIL may be a plain username ("Saamandar") or an email. Show the
    # человеческую часть in the UI rather than a generic label.
    login = settings.admin_email.strip()
    display = login.split("@")[0].capitalize() if "@" in login else login
    db.add(
        User(
            email=login.lower(),
            full_name=display or "Администратор",
            role="admin",
            password_hash=hash_password(settings.admin_password),
        )
    )
    await db.commit()
    log.info("admin created: %s", login)


DEMO_USERS = [
    ("ved@ved.local", "Азиз Каримов", "ved"),
    ("director@ved.local", "Максим Петров", "director"),
    ("logist@ved.local", "Мафтуна Рахимова", "logist"),
    ("sklad@ved.local", "Иван Кладовщиков", "warehouse"),
    ("buh@ved.local", "Ольга Финансова", "accountant"),
    ("viewer@ved.local", "Наблюдатель", "viewer"),
]

DEMO_SUPPLIERS = [
    ("Ningbo Aroma Industrial Co., Ltd", "Китай", "Li Wei", "WeChat: aroma_liwei"),
    ("Guangzhou PackTech Ltd", "Китай", "Chen Ming", "WhatsApp: +86 138 0013 8000"),
    ("Istanbul Kimya A.Ş.", "Турция", "Emre Yılmaz", "WhatsApp: +90 532 000 0000"),
    ("Delhi Essential Oils Pvt", "Индия", "Rahul Sharma", "Telegram: @delhi_eo"),
    ("Almaty Trade Group", "Казахстан", "Дана Сериковна", "Telegram: @atg_dana"),
    ("Hebei Glass Works", "Китай", "Zhang Lei", "GMAIL: zhang.lei@hbglass.cn"),
]

DEMO_DEALS = [
    # (stage_id, title, days_in_stage, supplier_idx, amount, currency, transport)
    (1, "Ароматизаторы пищевые — партия Q3", 7, None, None, "USD", ""),
    (1, "Эфирные масла (лаванда, мята) 500 кг", 2, None, None, "USD", ""),
    (2, "Стеклофлаконы 100 мл — 40 000 шт", 9, None, None, "USD", ""),
    (2, "Гофрокороб под линию розлива", 3, None, None, "USD", ""),
    (3, "Колпачки алюминиевые с резьбой", 4, None, None, "USD", ""),
    (3, "Красители пищевые — годовой объём", 6, None, None, "USD", ""),
    (4, "Помпы дозирующие 24/410", 2, 1, None, "USD", ""),
    (5, "Спирт-ректификат — контракт 2026", 14, 2, 185000, "USD", ""),
    (5, "Этикетка самоклеящаяся BOPP", 3, 1, 42000, "USD", ""),
    (6, "Отдушки парфюмерные — рамочный контракт", 4, 0, 312000, "USD", ""),
    (7, "Триацетин фарм. — 12 тонн", 11, 3, 96500, "USD", ""),
    (8, "ПЭТ-преформы 28 мм", 5, 5, 78000, "USD", ""),
    (9, "Аромакомпозиции — заказ №AR-118", 8, 0, 154000, "USD", "sea"),
    (9, "Стеклобанка 250 мл — производство", 3, 5, 61000, "USD", "sea"),
    (10, "Пробки-капельницы LDPE", 2, 1, 23400, "USD", "road"),
    (11, "Масло-основа кокосовое — 18 т", 4, 3, 88000, "USD", "sea"),
    (12, "Отдушки — коносамент MSCU7781203", 12, 0, 154000, "USD", "sea"),
    (12, "Флаконы стеклянные — CMR 448120", 6, 5, 61000, "USD", "road"),
    (13, "Красители — комплект документов", 3, 4, 34000, "USD", "road"),
    (14, "Спирт-ректификат — пакет у брокера", 2, 2, 185000, "USD", "rail"),
    (15, "Триацетин — оформление ГТД", 5, 3, 96500, "USD", "road"),
    (16, "Колпачки — прибытие на склад", 1, 1, 23400, "USD", "road"),
    (17, "Гофрокороб — приёмка партии", 2, 1, 19800, "USD", "road"),
    (18, "Этикетка BOPP — акт и претензия", 3, 1, 42000, "USD", "road"),
]


async def seed_demo(db: AsyncSession) -> None:
    res = await db.execute(select(func.count(Deal.id)))
    if res.scalar_one() > 0:
        return

    rnd = random.Random(20260804)
    now = datetime.now(timezone.utc)
    today = date.today()

    users = []
    for email, name, role in DEMO_USERS:
        existing = await db.execute(select(User).where(User.email == email))
        u = existing.scalar_one_or_none()
        if u is None:
            u = User(email=email, full_name=name, role=role, password_hash=hash_password("demo123"))
            db.add(u)
        users.append(u)
    await db.flush()

    suppliers = []
    for name, country, contact, messenger in DEMO_SUPPLIERS:
        s = Supplier(
            name=name,
            country=country,
            contact_person=contact,
            messenger=messenger,
            email=f"sales@{name.split()[0].lower()}.com",
        )
        db.add(s)
        suppliers.append(s)
    await db.flush()

    templates = (
        await db.execute(
            select(ChecklistTemplate)
            .where(ChecklistTemplate.pipeline == "import")
            .order_by(ChecklistTemplate.order_no)
        )
    ).scalars().all()
    doc_types = (
        await db.execute(
            select(DocType).where(DocType.pipeline == "import").order_by(DocType.order_no)
        )
    ).scalars().all()
    ved_user = next(u for u in users if u.role == "ved")

    for idx, (stage_id, title, age, sup_idx, amount, currency, transport) in enumerate(DEMO_DEALS, start=1):
        entered = now - timedelta(days=age, hours=rnd.randint(0, 20))
        # Give every already-passed stage a plausible duration, then derive the
        # creation date by walking backwards. Building the history this way keeps
        # it arithmetically consistent — durations can never come out negative.
        durations = [rnd.uniform(0.6, 5.5) for _ in range(stage_id - 1)]
        created = entered - timedelta(days=sum(durations))
        supplier = suppliers[sup_idx] if sup_idx is not None else None

        deal = Deal(
            code=f"ВЭД-{today.year}-{idx:03d}",
            pipeline="import",
            title=title,
            description="",
            stage_id=stage_id,
            status="active",
            priority=rnd.choice(["normal", "normal", "normal", "high", "low"]),
            requester="Директор производства",
            assignee_id=ved_user.id,
            supplier_id=supplier.id if supplier else None,
            country=supplier.country if supplier else "",
            incoterms=rnd.choice(["FOB", "CIF", "EXW", "DAP"]) if supplier else "",
            currency=currency,
            transport_mode=transport,
            stage_entered_at=entered,
            created_at=created,
            updated_at=entered,
        )

        if stage_id >= 5 and amount:
            deal.contract_amount = amount
            deal.contract_number = f"CT-{today.year}-{100 + idx}"
        if stage_id >= 6 and amount:
            # Spread signings across the last ~7 weeks, but keep roughly a third
            # inside the current month so the monthly KPI is not empty on day 1.
            back = rnd.randint(0, today.day - 1) if idx % 3 == 0 else rnd.randint(4, 50)
            deal.contract_date = today - timedelta(days=back)
        if stage_id >= 7:
            # one deal deliberately left without УНК to exercise the alert
            if idx != 11:
                deal.unk_number = f"{rnd.randint(10000000, 99999999)}/0001/0/1"
                deal.unk_date = (deal.contract_date or today) + timedelta(days=rnd.randint(2, 12))
        if stage_id >= 8:
            deal.payment_confirmed_at = today - timedelta(days=rnd.randint(5, 40))
            deal.payment_amount = amount
            deal.order_confirmation_at = today - timedelta(days=rnd.randint(3, 35))
        if stage_id >= 9:
            deal.production_ready_plan = today - timedelta(days=rnd.randint(-20, 15))
            if stage_id >= 11:
                deal.production_ready_fact = deal.production_ready_plan + timedelta(days=rnd.randint(0, 6))
        if stage_id >= 10:
            deal.packing_status = "confirmed" if stage_id > 10 else "requirements_sent"
        if stage_id >= 11:
            deal.freight_cost_plan = rnd.randint(1800, 9000)
            if stage_id >= 13:
                deal.freight_cost_fact = float(deal.freight_cost_plan) * rnd.uniform(0.95, 1.18)
        if stage_id >= 12:
            deal.etd = today - timedelta(days=rnd.randint(5, 35))
            deal.eta_initial = deal.etd + timedelta(days=rnd.randint(14, 40))
            slip = rnd.choice([0, 0, 0, 3, 7])
            deal.eta = deal.eta_initial + timedelta(days=slip)
        if stage_id >= 14:
            deal.broker_docs_sent_at = today - timedelta(days=rnd.randint(2, 12))
        if stage_id >= 15:
            deal.gtd_submitted_at = today - timedelta(days=rnd.randint(1, 9))
            if stage_id >= 16:
                deal.gtd_released_at = deal.gtd_submitted_at + timedelta(days=rnd.randint(1, 5))
                deal.gtd_number = f"26{rnd.randint(100000, 999999)}/{rnd.randint(100000,999999)}/000{rnd.randint(1,9)}"
        if stage_id >= 16:
            deal.warehouse_notified_at = today - timedelta(days=rnd.randint(1, 6))
        if stage_id >= 17:
            deal.actual_arrival = today - timedelta(days=rnd.randint(0, 4))
            deal.places_plan = rnd.randint(20, 400)
            deal.places_fact = deal.places_plan - rnd.choice([0, 0, 0, 1, 2])
            deal.packaging_ok = rnd.choice([True, True, True, False])
            deal.marking_ok = rnd.choice([True, True, True, False])
        if stage_id >= 18:
            deal.act_number = f"АВК-{today.year}-{idx:03d}"
            deal.act_date = today - timedelta(days=rnd.randint(0, 3))

        db.add(deal)
        await db.flush()

        # checklist: everything belonging to an earlier stage is already done
        for tpl in templates:
            done = tpl.stage_id < stage_id or (tpl.stage_id == stage_id and rnd.random() < 0.4)
            db.add(
                DealChecklist(
                    deal_id=deal.id,
                    template_id=tpl.id,
                    is_done=done,
                    done_at=created + (entered - created) * rnd.random() if done else None,
                    done_by_id=ved_user.id if done else None,
                )
            )

        # documents follow the same progression
        for dt in doc_types:
            received = False
            if dt.code in ("contract",) and stage_id >= 6:
                received = True
            elif dt.code == "order_confirmation" and stage_id >= 8:
                received = True
            elif dt.code in ("invoice", "packing_list", "cmr_bl") and stage_id >= 13:
                received = rnd.random() < 0.9
            elif dt.code == "cert_origin" and stage_id >= 13:
                received = rnd.random() < 0.7
            elif dt.code == "cert_quality" and stage_id >= 13:
                received = rnd.random() < 0.5
            elif dt.code == "gtd" and stage_id >= 16:
                received = True
            elif dt.code == "act_qc" and stage_id >= 18:
                received = True
            db.add(
                DealDocument(
                    deal_id=deal.id,
                    doc_type_id=dt.id,
                    is_received=received,
                    received_at=today - timedelta(days=rnd.randint(1, 20)) if received else None,
                    number=f"{dt.code.upper()}-{rnd.randint(1000, 9999)}" if received else "",
                )
            )

        # quotes for deals that reached the comparison stage
        if stage_id >= 3:
            pool = rnd.sample(suppliers, k=rnd.randint(2, 4))
            base = rnd.randint(20000, 120000)
            for qi, sup in enumerate(pool):
                db.add(
                    Quote(
                        deal_id=deal.id,
                        supplier_id=sup.id,
                        price=round(base * rnd.uniform(0.88, 1.22), 2),
                        currency="USD",
                        lead_time_days=rnd.choice([21, 30, 35, 45, 60]),
                        payment_terms=rnd.choice(["30% предоплата / 70% против копий", "100% предоплата", "50/50", "аккредитив"]),
                        incoterms=rnd.choice(["FOB", "CIF", "EXW"]),
                        received_at=today - timedelta(days=rnd.randint(5, 45)),
                        is_selected=bool(supplier and sup.id == supplier.id and qi == 0),
                        select_reason="price" if (supplier and sup.id == supplier.id and qi == 0) else "",
                    )
                )

        # stage history so cycle-time charts have something to show
        prev_entered = created
        for s in range(1, stage_id + 1):
            # entry[1] = created, entry[stage_id] = entered, the rest accumulate
            # durations[s-2] — the time spent in the stage being left.
            if s == 1:
                step = created
            elif s == stage_id:
                step = entered
            else:
                step = prev_entered + timedelta(days=durations[s - 2])
            db.add(
                StageEvent(
                    deal_id=deal.id,
                    from_stage_id=s - 1 if s > 1 else None,
                    to_stage_id=s,
                    days_in_from_stage=round((step - prev_entered).total_seconds() / 86400, 2)
                    if s > 1
                    else None,
                    user_id=ved_user.id,
                    created_at=step,
                )
            )
            prev_entered = step

        if stage_id == 18 and rnd.random() < 0.8:
            db.add(
                Claim(
                    deal_id=deal.id,
                    kind="supplier",
                    amount=rnd.randint(300, 4200),
                    currency="USD",
                    description="Повреждение упаковки при транспортировке, недостача 2 места.",
                    status="open",
                )
            )

    await db.commit()
    log.info("demo data seeded: %d deals", len(DEMO_DEALS))


async def run_seed(db: AsyncSession) -> None:
    await seed_reference(db)
    await seed_admin(db)
    if settings.seed_demo:
        await seed_demo(db)
