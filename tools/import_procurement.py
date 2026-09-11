"""Load real procurement records derived from the G: archive into ВЭД RTP.

Runs inside the ved-api container. Reads /tmp/procurement.json (produced by the
host-side folder scan), rebuilds suppliers and deals, and wires up the document
set for each deal.

Pass --apply to write. Without it the script only reports what it would do.
"""

import asyncio
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import delete, select

from app.db import SessionLocal
from app.models import (
    ChecklistTemplate,
    Claim,
    Comment,
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

APPLY = "--apply" in sys.argv
SRC = "/tmp/procurement.json"

DATE_SEG = re.compile(r"^\d{2}[.\-]\d{2}[.\-]\d{4}")
YEAR_SEG = re.compile(r"^_?\d{4}([-–_]\d{2,4})*$")
NOISE = {"_archive", "draft", "rev", "final docs", "new", "old", "архив"}

# Only mappings that are unambiguous from the path or the company name itself.
# Anything uncertain is left blank rather than guessed.
PATH_COUNTRY = {
    "CHINA": "Китай", "TURKEY": "Турция", "INDIA": "Индия", "EUROPE": "Европа",
    "RUS": "Россия", "Mexico": "Мексика", "UZBEKISTAN": "Узбекистан",
    "BELARUS": "Беларусь", "GERMANY": "Германия",
}
NAME_COUNTRY = [
    (re.compile(r"guangzhou|shenzhen|ningbo|foshan|wenzhou|jiangxi|xi.an|dongguan|"
                r"shanghai|suzhou|henan|shaanxi|china|\(hk\)|ailusi|danq", re.I), "Китай"),
    (re.compile(r"sarebekir|saribekir|kale kimya|7m valf|turkey|gulcicek|gulchechak", re.I), "Турция"),
    (re.compile(r"novaphene|saujanya|india", re.I), "Индия"),
    (re.compile(r"givaudan|expressions|technico|basf|angus|imcd", re.I), "Европа"),
]

# stage inference for still-open (2026) import deals, most advanced first
IMPORT_STAGE_RULES = [
    ({"act_qc"}, 18),
    ({"gtd"}, 15),
    ({"cmr_bl", "cert_origin", "invoice", "packing_list"}, 14),
    ({"invoice", "packing_list"}, 13),
    ({"cmr_bl"}, 12),
    ({"contract", "order_confirmation"}, 9),
    ({"contract"}, 6),
    ({"order_confirmation"}, 5),
]
SERVICE_STAGE_RULES = [
    ({"svc_act"}, 206),
    ({"svc_invoice"}, 205),
    ({"svc_waybill"}, 204),
    ({"svc_request"}, 202),
]
FINAL_STAGE = {"import": 19, "service": 207}
OPEN_YEAR = 2026


def clean_supplier(rel_path: str) -> str | None:
    """Nearest ancestor of the date folder that is a real supplier name."""
    parts = [p for p in rel_path.split("\\") if p]
    i = len(parts) - 2
    while i >= 1:
        seg = parts[i].strip()
        low = seg.lower()
        if low in NOISE or YEAR_SEG.match(seg) or DATE_SEG.match(seg):
            i -= 1
            continue
        return re.sub(r"\s+", " ", seg).strip(" .,-«»\"'")
    return None


def norm_key(name: str) -> str:
    return re.sub(r"[^a-z0-9а-яё]", "", name.lower())


def country_for(rel_path: str, supplier: str) -> str:
    for seg in rel_path.split("\\"):
        if seg in PATH_COUNTRY:
            return PATH_COUNTRY[seg]
    for rx, c in NAME_COUNTRY:
        if rx.search(supplier):
            return c
    return ""


def infer_stage(pipeline: str, docs: set[str]) -> int:
    rules = IMPORT_STAGE_RULES if pipeline == "import" else SERVICE_STAGE_RULES
    for needed, stage_id in rules:
        if needed <= docs:
            return stage_id
    return 1 if pipeline == "import" else 201


async def main():
    raw = json.load(open(SRC, encoding="utf-8-sig"))
    records = raw["deals"]

    # ---- normalise suppliers -------------------------------------------------
    suppliers: dict[str, dict] = {}
    cleaned = []
    for r in records:
        name = clean_supplier(r["rel_path"])
        if not name:
            continue
        key = norm_key(name)
        if not key:
            continue
        info = suppliers.setdefault(key, {"name": name, "country": "", "deals": 0})
        # keep the longest spelling as canonical (usually the fullest legal name)
        if len(name) > len(info["name"]):
            info["name"] = name
        c = country_for(r["rel_path"], name)
        if c and not info["country"]:
            info["country"] = c
        info["deals"] += 1
        r = dict(r)
        r["supplier_key"] = key
        cleaned.append(r)

    print(f"records          : {len(cleaned)}")
    print(f"suppliers        : {len(suppliers)}  "
          f"({sum(1 for s in suppliers.values() if s['country'])} with country)")
    by_year = defaultdict(int)
    for r in cleaned:
        by_year[r["year"]] += 1
    print("by year          :", dict(sorted(by_year.items())))
    open_n = sum(1 for r in cleaned if r["year"] >= OPEN_YEAR)
    print(f"will be active   : {open_n}")
    print(f"will be done     : {len(cleaned) - open_n}")

    if not APPLY:
        print("\nDRY RUN — nothing written. Re-run with --apply.")
        return

    async with SessionLocal() as db:
        # ---- clear demo content ---------------------------------------------
        for model in (Comment, Claim, Quote, StageEvent, DealChecklist, DealDocument, Deal):
            await db.execute(delete(model))
        await db.execute(delete(Supplier))
        await db.execute(
            delete(User).where(User.email.like("%@ved.local"), User.role != "admin")
        )
        await db.commit()
        print("demo content removed")

        # ---- suppliers -------------------------------------------------------
        sup_ids: dict[str, int] = {}
        for key, info in sorted(suppliers.items(), key=lambda kv: kv[1]["name"].lower()):
            s = Supplier(
                name=info["name"],
                country=info["country"],
                notes=f"Импортировано из архива закупок · сделок: {info['deals']}",
                is_active=True,
            )
            db.add(s)
            await db.flush()
            sup_ids[key] = s.id
        await db.commit()
        print(f"suppliers created: {len(sup_ids)}")

        # ---- reference lookups ----------------------------------------------
        doctypes = (await db.execute(select(DocType))).scalars().all()
        dt_by_code = {d.code: d for d in doctypes}
        dt_by_pipeline = defaultdict(list)
        for d in doctypes:
            dt_by_pipeline[d.pipeline].append(d)
        templates = defaultdict(list)
        for t in (await db.execute(select(ChecklistTemplate))).scalars().all():
            templates[t.pipeline].append(t)
        stage_ids = {s.id for s in (await db.execute(select(Stage))).scalars().all()}

        # ---- deals -----------------------------------------------------------
        counters: dict[tuple[str, int], int] = defaultdict(int)
        prefix = {"import": "ВЭД", "service": "УСЛ"}
        made = 0
        for r in sorted(cleaned, key=lambda x: (x["deal_date"], x["rel_path"])):
            pipeline = r["pipeline"]
            year = r["year"]
            counters[(pipeline, year)] += 1
            code = f"{prefix[pipeline]}-{year}-{counters[(pipeline, year)]:03d}"

            docs = set(r["doc_types"])
            is_open = year >= OPEN_YEAR
            stage_id = infer_stage(pipeline, docs) if is_open else FINAL_STAGE[pipeline]
            if stage_id not in stage_ids:
                stage_id = FINAL_STAGE[pipeline]

            when = datetime.strptime(r["deal_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            ref = (r.get("refs") or [None])[0]
            sup_id = sup_ids[r["supplier_key"]]
            sup_name = suppliers[r["supplier_key"]]["name"]

            title = f"{r['category']} · {sup_name}"
            if ref:
                title += f" · {ref}"

            deal = Deal(
                code=code,
                title=title[:300],
                description=f"Источник: {r['rel_path']}\nФайлов в папке: {r['file_count']}",
                pipeline=pipeline,
                stage_id=stage_id,
                status="active" if is_open else "done",
                priority="normal",
                supplier_id=sup_id,
                country=suppliers[r["supplier_key"]]["country"],
                contract_number=ref or "",
                currency="USD",
                stage_entered_at=when,
                created_at=when,
                updated_at=when,
                closed_at=None if is_open else when,
            )
            db.add(deal)
            await db.flush()

            # document set: detected ones marked received, the rest left open
            for dt in dt_by_pipeline[pipeline]:
                got = dt.code in docs
                db.add(DealDocument(
                    deal_id=deal.id,
                    doc_type_id=dt.id,
                    is_received=got,
                    received_at=when.date() if got else None,
                    file_name=(r["doc_samples"].get(dt.code) or "")[:300] if got else "",
                    note="из архива" if got else "",
                ))
            for t in templates[pipeline]:
                db.add(DealChecklist(deal_id=deal.id, template_id=t.id))

            db.add(StageEvent(
                deal_id=deal.id,
                from_stage_id=None,
                to_stage_id=stage_id,
                comment=f"Импорт из архива закупок ({r['deal_date']})",
                created_at=when,
            ))
            made += 1
            if made % 50 == 0:
                await db.commit()
                print(f"  ... {made} deals")
        await db.commit()
        print(f"deals created    : {made}")


asyncio.run(main())
