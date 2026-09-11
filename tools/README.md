# tools — импорт номенклатуры закупок из файлового архива

Скрипты, которыми база была заполнена реальными данными из папки
`… \ IMPORT HJ \ Import 2022-2026HJ`. Держатся здесь, чтобы импорт можно было
повторить, когда архив пополнится.

Структура архива, на которую они опираются:

```
КАТЕГОРИЯ \ [СТРАНА] \ ПОСТАВЩИК \ ДД.ММ.ГГГГ \ документы
```

Папка с датой = одна поставка. Тип документа определяется по имени файла
(`CI`, `PI`, `PACKING`, `CO`, `CMR`, `ГТД`, …).

## Порядок запуска

**1. Сканирование архива → JSON** (ничего не меняет, только читает):

```powershell
.\tools\scan-procurement.ps1 -Root "<путь к Import 2022-2026HJ>"
```

Путь передаётся параметром намеренно: он содержит идентификатор общей папки
Google Drive, которому не место в репозитории.

**2. Загрузка в базу.** Скрипты выполняются внутри контейнера `ved-api` —
там уже есть Python, SQLAlchemy и модели приложения:

```bash
docker cp tools/procurement.json        ved-api:/tmp/procurement.json
docker cp tools/import_procurement.py   ved-api:/tmp/import_procurement.py
docker compose exec -e PYTHONPATH=/srv api python /tmp/import_procurement.py
```

Без `--apply` это **сухой прогон**: печатает, что будет создано, и выходит.
С `--apply` — **удаляет все сделки и поставщиков** и создаёт их заново.
Сначала снимите дамп:

```bash
docker compose exec -T db pg_dump -U ved ved > backup.sql
```

**3. Категории поставщиков** (по папке верхнего уровня):

```bash
docker cp tools/backfill_categories.py ved-api:/tmp/backfill_categories.py
docker compose exec -e PYTHONPATH=/srv api python /tmp/backfill_categories.py --apply
```

## Что эти скрипты не умеют

Суммы контрактов, ETD/ETA, номера ГТД и УНК лежат **внутри** документов, а не
в их именах. Импорт их не заполняет — эти поля остаются пустыми и вносятся
вручную. Для их извлечения потребуется разбор ~5 500 PDF, часть из которых
сканы и требует OCR.

`/tmp` в контейнере очищается при пересоздании контейнера — после
`docker compose up --build` файлы нужно скопировать заново.
