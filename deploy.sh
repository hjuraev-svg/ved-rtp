#!/usr/bin/env bash
# Deploy / update ВЭД RTP on the remote server.
#
#   ./deploy.sh                 # sync code, rebuild, restart
#   ./deploy.sh --logs          # follow API logs afterwards
#
# Safe to re-run: the server .env is never overwritten and the database volume
# is never touched, so deploying does not lose data.

set -euo pipefail

HOST="${VED_HOST:-ubuntu@176.96.241.39}"
DIR="${VED_DIR:-~/ved}"
# Served through the shared Caddy on the server (docker-compose.caddy.yml);
# the container publishes no host port of its own.
URL="${VED_URL:-https://jnslabsonline.uz/ved}"

echo "→ Deploying to ${HOST}:${DIR}"

ssh -o BatchMode=yes "$HOST" "mkdir -p $DIR"

# .env stays on the server — it holds server-specific secrets.
tar --exclude='.env' \
    --exclude='node_modules' \
    --exclude='__pycache__' \
    --exclude='dist' \
    --exclude='.git' \
    -czf - . | ssh -o BatchMode=yes "$HOST" "tar -xzf - -C $DIR"
echo "→ Code synced"

ssh -o BatchMode=yes "$HOST" "cd $DIR && docker compose build 2>&1 | tail -3 && docker compose up -d 2>&1 | tail -5"

echo "→ Waiting for health…"
for i in $(seq 1 30); do
  if curl -fsS -m 5 "${URL}/api/health" >/dev/null 2>&1; then
    echo "→ Healthy"
    curl -s "${URL}/api/health"; echo
    break
  fi
  [ "$i" = 30 ] && { echo "✗ Did not become healthy in time"; ssh "$HOST" "cd $DIR && docker compose logs --tail 40 api"; exit 1; }
  sleep 2
done

ssh -o BatchMode=yes "$HOST" "cd $DIR && docker compose ps --format 'table {{.Service}}\t{{.Status}}\t{{.Ports}}'"
echo
echo "✓ ${URL}/"
echo
echo "Note: the Caddyfile route (/opt/aroma/erp_Aroma/Caddyfile) is separate"
echo "infrastructure — deploying does not touch it."

if [ "${1:-}" = "--logs" ]; then
  ssh -t "$HOST" "cd $DIR && docker compose logs -f api"
fi
