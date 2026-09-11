"""Assign a product category to each supplier, taken from the archive folder it
lives under. Run inside ved-api with PYTHONPATH=/srv. --apply to write.
"""

import asyncio
import json
import re
import sys
from collections import Counter, defaultdict

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Supplier

APPLY = "--apply" in sys.argv
SRC = "/tmp/procurement.json"

DATE_SEG = re.compile(r"^\d{2}[.\-]\d{2}[.\-]\d{4}")
YEAR_SEG = re.compile(r"^_?\d{4}([-–_]\d{2,4})*$")
NOISE = {"_archive", "draft", "rev", "final docs", "new", "old", "архив"}

# Top-level archive folder -> label shown in the UI. Russian, to match every
# other value in that table (Страна: Китай, Турция …).
LABELS = {
    "PERFUMES": "Парфюмерия",
    "MACHINERY": "Оборудование",
    "INGREDIENTS": "Ингредиенты",
    "TARES AND ACCESSORIES, VALVES": "Тара и комплектующие",
    "Condoms": "Презервативы",
    "GAS": "Газ",
    "Transportation": "Транспорт",
    "Drones": "Дроны",
    "Air purifier": "Очистители воздуха",
    "Massage chair": "Массажные кресла",
    "Aquarium": "Аквариумы",
    "SIlicone": "Силикон",
    "Exhibitions": "Выставки",
}


def clean_supplier(rel_path: str) -> str | None:
    parts = [p for p in rel_path.split("\\") if p]
    i = len(parts) - 2
    while i >= 1:
        seg = parts[i].strip()
        if seg.lower() in NOISE or YEAR_SEG.match(seg) or DATE_SEG.match(seg):
            i -= 1
            continue
        return re.sub(r"\s+", " ", seg).strip(" .,-«»\"'")
    return None


def norm_key(name: str) -> str:
    return re.sub(r"[^a-z0-9а-яё]", "", name.lower())


async def main():
    raw = json.load(open(SRC, encoding="utf-8-sig"))

    # A supplier's category is the archive folder most of its deals sit under.
    votes: dict[str, Counter] = defaultdict(Counter)
    for r in raw["deals"]:
        name = clean_supplier(r["rel_path"])
        if not name:
            continue
        votes[norm_key(name)][r["category"]] += 1

    unmapped = {c for v in votes.values() for c in v if c not in LABELS}
    if unmapped:
        print("WARNING: no label for:", ", ".join(sorted(unmapped)))

    async with SessionLocal() as db:
        suppliers = (await db.execute(select(Supplier))).scalars().all()
        hits, misses, summary = 0, [], Counter()
        for s in suppliers:
            v = votes.get(norm_key(s.name))
            if not v:
                misses.append(s.name)
                continue
            top, _ = v.most_common(1)[0]
            label = LABELS.get(top, top)
            if APPLY:
                s.category = label
            summary[label] += 1
            hits += 1
        if APPLY:
            await db.commit()

        print(f"suppliers matched : {hits} / {len(suppliers)}")
        if misses:
            print("unmatched         :", ", ".join(misses))
        print("\ncategory distribution:")
        for label, n in summary.most_common():
            print(f"  {label:<24} {n}")
        if not APPLY:
            print("\nDRY RUN — nothing written. Re-run with --apply.")


asyncio.run(main())
