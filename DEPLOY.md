# Развёртывание на сервере

**Рабочий адрес: https://jnslabsonline.uz/ved/**

Вход: `Samandar` / `<см. .env на сервере>`.

---

## Что и где стоит

Сервер `ubuntu@176.96.241.39` (Ubuntu 24.04). Проект — в `~/ved`.

```
браузер ──HTTPS──► erp_aroma-caddy-1 (:443, Let's Encrypt)
                   маршрут /ved/* → uri strip_prefix /ved → ved-web:80
                            │  сеть erp_aroma_default
                   ┌────────▼─────────┐
                   │ ved-web (nginx)  │  порт наружу НЕ публикуется
                   │  /  → статика SPA│
                   │  /api, /ws → api │
                   └────────┬─────────┘
                            │  сеть ved-rtp_default
                   ┌────────▼─────────┐   ┌──────────────┐
                   │ ved-api :8000    │──►│ ved-db :5432 │
                   │ 127.0.0.1:8095   │   │ 127.0.0.1:   │
                   └──────────────────┘   │        5435  │
                                          └──────────────┘
```

Наружу открыт **только** 443 через Caddy. API и Postgres слушают loopback,
контейнер `ved-web` вообще не публикует порт.

SPA собрана с `base=/ved/` (build-arg `VITE_BASE`), поэтому браузер запрашивает
`/ved/assets/*`, `/ved/api/*`, `/ved/ws`; Caddy срезает префикс.

---

## Обновление

С рабочей машины, из папки проекта:

```bash
./deploy.sh
```

Скрипт синхронизирует код, пересобирает образы, перезапускает контейнеры и
ждёт `/api/health`. **База и `.env` на сервере не трогаются** — обновление не
теряет данные.

Ручной вариант:

```bash
ssh ubuntu@176.96.241.39 "cd ~/ved && docker compose build && docker compose up -d"
```

На сервере в `.env` задано
`COMPOSE_FILE=docker-compose.yml:docker-compose.caddy.yml`,
поэтому обычная команда `docker compose` сама подхватывает серверный оверлей.

---

## Управление

```bash
ssh ubuntu@176.96.241.39 "cd ~/ved && docker compose ps"
ssh ubuntu@176.96.241.39 "cd ~/ved && docker compose logs -f api"
ssh ubuntu@176.96.241.39 "cd ~/ved && docker compose restart api"
```

### Резервная копия базы

```bash
ssh ubuntu@176.96.241.39 "cd ~/ved && docker compose exec -T db pg_dump -U ved ved" > ved_backup.sql
```

Восстановление:

```bash
cat ved_backup.sql | ssh ubuntu@176.96.241.39 "cd ~/ved && docker compose exec -T db psql -U ved ved"
```

### Проверка работоспособности

```bash
python backend/smoke_test.py https://jnslabsonline.uz/ved
```

---

## Маршрут в Caddy

Добавлен в общий `/opt/aroma/erp_Aroma/Caddyfile` — тот же файл обслуживает
`/jns`, `/unf`, `/accounting` и корень `jnslabsonline.uz`. Блок стоит **до**
catch-all, иначе `/ved` ушёл бы в aroma-фронтенд и отвечал 404.

```caddy
@ved_root path /ved
redir @ved_root /ved/ 308

handle /ved/* {
	uri strip_prefix /ved
	reverse_proxy ved-web:80
}
```

Резервная копия перед правкой: `/opt/aroma/erp_Aroma/Caddyfile.bak.20260805-ved`.

Откат:

```bash
ssh ubuntu@176.96.241.39 "cp /opt/aroma/erp_Aroma/Caddyfile.bak.20260805-ved /opt/aroma/erp_Aroma/Caddyfile && docker exec erp_aroma-caddy-1 caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile"
```

**Правило:** после любой правки Caddyfile сначала `caddy validate`, потом
`caddy reload` (не `restart`) — при ошибке Caddy продолжит работать на старой
конфигурации, и соседние сайты не упадут.

---

## Что стоит сделать дальше

| Задача | Почему |
|---|---|
| Сменить пароль `<см. .env на сервере>` | Система в интернете; 4 цифры перебираются за секунды, ограничения попыток нет |
| Ограничение попыток входа | Сейчас пароль можно перебирать без задержек |
| Регулярный `pg_dump` по cron | Резервных копий нет — данные живут только в томе `ved-rtp_db_data` |
