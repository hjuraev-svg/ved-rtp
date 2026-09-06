# -*- coding: utf-8 -*-
"""Сквозная проверка API. Запускать при поднятом стенде:

    python backend/smoke_test.py                  # по умолчанию http://localhost:8090
    python backend/smoke_test.py http://localhost:8000

Учётные данные администратора берутся из .env (ADMIN_EMAIL / ADMIN_PASSWORD)
или из переменных окружения — отдельно править скрипт при смене логина не нужно.

Скрипт идемпотентен: создаёт временную сделку, прогоняет её по этапам и удаляет.

Работает и на чистой базе (SEED_DEMO=false): если демо-учётных записей или
поставщиков нет, соответствующие проверки пропускаются с пометкой SKIP, а
остальные выполняются под администратором.
"""

import io
import json
import os
import sys
import urllib.error
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8090"
ok = fail = skipped = 0


def env(key, default):
    """Переменная окружения, иначе значение из .env рядом с проектом."""
    if key in os.environ:
        return os.environ[key]
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith(f"{key}=") and not line.startswith("#"):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return default


ADMIN_LOGIN = env("ADMIN_EMAIL", "admin@ved.local")
ADMIN_PASSWORD = env("ADMIN_PASSWORD", "admin123")


def skip(reason):
    global skipped
    skipped += 1
    print(f"  [SKIP] {reason}")


def call(method, path, token=None, body=None, expect=200):
    global ok, fail
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json; charset=utf-8")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            code, payload = r.status, r.read()
    except urllib.error.HTTPError as e:
        code, payload = e.code, e.read()
    except urllib.error.URLError as e:
        print(f"  [FAIL] {method:6} {path:50} -> нет связи: {e.reason}")
        fail += 1
        return None
    good = code == expect
    ok, fail = ok + good, fail + (not good)
    print(f"  [{'OK ' if good else 'FAIL'}] {method:6} {path:50} -> {code} (ждали {expect})")
    try:
        return json.loads(payload) if payload else None
    except ValueError:
        return None


def login(email, pwd):
    res = call("POST", "/api/auth/login", body={"email": email, "password": pwd})
    if not res or "access_token" not in res:
        sys.exit(f"Не удалось войти как {email} — стенд поднят? Верны ADMIN_* в .env?")
    return res["access_token"]


def try_login(email, pwd):
    """Демо-учётка: молча возвращает None, если её нет (SEED_DEMO=false)."""
    data = json.dumps({"email": email, "password": pwd}).encode()
    req = urllib.request.Request(BASE + "/api/auth/login", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())["access_token"]
    except Exception:
        return None


print(f"Стенд: {BASE} · администратор: {ADMIN_LOGIN}\n")
print("=== Состояние и авторизация ===")
call("GET", "/api/health")
admin = login(ADMIN_LOGIN, ADMIN_PASSWORD)
ved = try_login("ved@ved.local", "demo123") or admin
viewer = try_login("viewer@ved.local", "demo123")
demo = ved is not admin
if not demo:
    skip("демо-учётные записи отсутствуют — проверки выполняются под администратором")
call("POST", "/api/auth/login",
     body={"email": ADMIN_LOGIN, "password": ADMIN_PASSWORD + "_wrong"}, expect=401)
call("GET", "/api/deals", expect=401)

print("\n=== Справочники ===")
pipes = call("GET", "/api/pipelines", ved)
assert len(pipes) == 3, "ожидались три типа сделки"
for pl in pipes:
    st_ = call("GET", f"/api/stages?pipeline={pl['code']}", ved)
    dc_ = call("GET", f"/api/doc-types?pipeline={pl['code']}", ved)
    print(f"     {pl['name']:<20} этапов {len(st_):<3} документов {len(dc_)}")
# «Импорт» — это исходный лист Excel, его состав зафиксирован.
stages = call("GET", "/api/stages?pipeline=import", ved)
tpl = call("GET", "/api/checklist-template?pipeline=import", ved)
dt = call("GET", "/api/doc-types?pipeline=import", ved)
assert len(stages) == 18 and len(tpl) == 24 and len(dt) == 9, "импорт не совпадает с Excel"
print(f"     этапов {len(stages)}, пунктов чек-листа {len(tpl)}, типов документов {len(dt)}")

print("\n=== Дашборд ===")
dash = call("GET", "/api/dashboard?pipeline=import", ved)
print(f"     плиток {len(dash['tiles'])}, алертов {len(dash['alerts'])}, "
      f"активных сделок {dash['kpi']['active_deals']}")
cyc = call("GET", "/api/dashboard/cycle-times?pipeline=import", ved)
assert all(c["avg_days"] >= 0 for c in cyc), "отрицательное время на этапе"
call("GET", "/api/dashboard/throughput?pipeline=import", ved)
call("GET", "/api/dashboard/by-supplier", ved)
call("GET", "/api/dashboard?pipeline=bogus", ved, expect=422)

print("\n=== Жизненный цикл сделки ===")
deal = call("POST", "/api/deals", ved,
            {"title": "Проверка: клапаны дозирующие 24/410", "requester": "Директор производства",
             "priority": "high", "pipeline": "import", "stage_id": 1}, expect=201)
did = deal["id"]
print(f"     создана {deal['code']}")

chk = call("GET", f"/api/deals/{did}/checklist", ved)
docs = call("GET", f"/api/deals/{did}/documents", ved)
assert len(chk) == 24 and len(docs) == 9, "чек-лист/документы не материализовались"

call("PATCH", f"/api/deals/{did}/checklist/{chk[0]['id']}", ved, {"is_done": True})
call("PATCH", f"/api/deals/{did}/documents/{docs[0]['id']}", ved,
     {"is_received": True, "number": "КТ-2026-001"})

local_deal = call("PATCH", f"/api/deals/{did}/pipeline", ved, {"pipeline": "local"})
assert local_deal["pipeline"] == "local" and local_deal["stage_id"] == 101
assert local_deal["code"].startswith("МП-")
assert call("GET", f"/api/deals/{did}/checklist", ved) == []
assert len(call("GET", f"/api/deals/{did}/documents", ved)) == 6

import_deal = call("PATCH", f"/api/deals/{did}/pipeline", ved, {"pipeline": "import"})
assert import_deal["pipeline"] == "import" and import_deal["stage_id"] == 1
restored_chk = call("GET", f"/api/deals/{did}/checklist", ved)
restored_docs = call("GET", f"/api/deals/{did}/documents", ved)
assert restored_chk[0]["is_done"] is True, "прогресс чек-листа потерян после смены типа"
assert restored_docs[0]["number"] == "КТ-2026-001", "данные документа потеряны после смены типа"

call("POST", f"/api/deals/{did}/move", ved, {"stage_id": 2, "comment": "RFQ разослан"})
call("POST", f"/api/deals/{did}/move", ved, {"stage_id": 3, "comment": "Получены КП"})
hist = call("GET", f"/api/deals/{did}/history", ved)
print(f"     событий в истории: {len(hist)}")

sups = call("GET", "/api/suppliers", ved)
if sups:
    q = call("POST", f"/api/deals/{did}/quotes", ved,
             {"supplier_id": sups[0]["id"], "price": 41000, "lead_time_days": 30,
              "payment_terms": "30% предоплата / 70% против копий", "incoterms": "FOB"}, expect=201)
    call("POST", f"/api/deals/{did}/quotes/{q['id']}/select", ved, {"select_reason": "lead_time"})
else:
    skip("поставщиков нет — проверка КП и выбора поставщика пропущена")
call("POST", f"/api/deals/{did}/claims", ved,
     {"kind": "carrier", "amount": 1250, "description": "Повреждение 3 мест"}, expect=201)
call("POST", f"/api/deals/{did}/comments", ved, {"body": "Согласовано с директором."}, expect=201)

print("\n=== Права доступа ===")
if viewer:
    call("GET", "/api/dashboard", viewer)
    call("PATCH", f"/api/deals/{did}", viewer, {"title": "нельзя"}, expect=403)
    call("PATCH", f"/api/deals/{did}/pipeline", viewer, {"pipeline": "local"}, expect=403)
    call("POST", f"/api/deals/{did}/move", viewer, {"stage_id": 5}, expect=403)
else:
    skip("учётной записи viewer нет — проверка режима «только просмотр» пропущена")
if demo:
    # Эти проверки осмысленны только под не-администратором: admin проходит везде.
    call("POST", "/api/auth/users", ved,
         {"email": "x@ved.local", "full_name": "X", "role": "viewer", "password": "x123456"}, expect=403)
    call("PATCH", "/api/stages/1", ved, {"sla_days": 9}, expect=403)
else:
    skip("нет не-административной учётной записи — проверка ограничений роли пропущена")
call("PATCH", "/api/stages/1", admin, {"sla_days": 5})

print("\n=== Валидация ===")
call("POST", f"/api/deals/{did}/move", ved, {"stage_id": 99}, expect=422)
call("PATCH", f"/api/deals/{did}/pipeline", ved, {"pipeline": "bogus"}, expect=422)
call("PATCH", f"/api/deals/{did}", ved, {"status": "неизвестно"}, expect=422)
call("PATCH", f"/api/deals/{did}", ved, {"нет_такого_поля": 1}, expect=422)
call("GET", "/api/deals/999999", ved, expect=404)

print("\n=== Выгрузка ===")
call("GET", "/api/export/deals.csv", ved)

print("\n=== Очистка ===")
call("DELETE", f"/api/deals/{did}", ved, expect=204)
call("GET", f"/api/deals/{did}", ved, expect=404)

summary = f"Пройдено: {ok} · Провалено: {fail}"
if skipped:
    summary += f" · Пропущено: {skipped}"
print(f"\n{'=' * 68}\n{summary}")
sys.exit(1 if fail else 0)
