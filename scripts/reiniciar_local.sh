#!/usr/bin/env bash
# Detiene TODAS las instancias de la API local (puerto 8000) y del worker, y arranca una de cada una con el código y .env.dev actuales.
# Evita el problema de varios workers con código viejo tomando trabajos de la misma cola. Registros en logs/api.log y logs/worker.log.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs
pids="$(pgrep -f 'backend.production.worker' || true)"; [ -n "$pids" ] && kill $pids && echo "Workers detenidos: $pids"
api="$(lsof -tiTCP:8000 -sTCP:LISTEN || true)"; [ -n "$api" ] && kill $api && echo "API del 8000 detenida: $api"
sleep 2
set -a; . ./.env.dev; set +a
nohup .venv/bin/python -m backend.server --port 8000 >> logs/api.log 2>&1 &
nohup .venv/bin/python -m backend.production.worker >> logs/worker.log 2>&1 &
sleep 4
curl -s -m 10 localhost:8000/health && echo
echo "Workers en marcha: $(pgrep -f backend.production.worker | wc -l | tr -d " ")  (debe ser 1)"
