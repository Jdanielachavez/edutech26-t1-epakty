#!/usr/bin/env bash
# Deja ed.paktai-ec.com funcionando completo desde esta Mac: n8n (correo, IA, avisos) y el worker
# que procesa las cargas de archivos y la cola de avisos. Úsalo antes de cada demostración.
#
#   ./scripts/encender_produccion.sh
#
# Qué hace:
#   1. Publica n8n con un túnel temporal de Cloudflare, solo con las rutas de los flujos (no el editor).
#   2. Pone en Vercel N8N_WEBHOOK_BASE_URL, N8N_WEBHOOK_HMAC_SECRET y N8N_WEBHOOK_TOKEN y vuelve a publicar.
#   3. Enciende el worker contra la base de producción (Supabase).
# La dirección del túnel cambia cada vez: si reinicias la Mac, vuelve a correr este script.
# Deja la Mac encendida y conectada mientras dure la demostración.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs
DOMINIO=ed.paktai-ec.com
val(){ grep -m1 "^$1=" "$2" | cut -d= -f2- | sed -e "s/^['\"]//" -e "s/['\"]$//"; }

command -v cloudflared >/dev/null || { echo "Falta cloudflared: brew install cloudflared"; exit 1; }
curl -fsS -m 5 http://127.0.0.1:5678/healthz >/dev/null || { echo "n8n no responde en tu Mac (localhost:5678). Abre Docker y el contenedor epakty-n8n."; exit 1; }
SECRET="$(val N8N_WEBHOOK_HMAC_SECRET .env.dev)"; TOKEN="$(val N8N_WEBHOOK_TOKEN .env.dev)"
DB="$(val DATABASE_URL_LOCAL env/supabase.env)"
[ ${#SECRET} -ge 32 ] && [ -n "$TOKEN" ] && [ -n "$DB" ] || { echo "Faltan N8N_WEBHOOK_HMAC_SECRET / N8N_WEBHOOK_TOKEN en .env.dev o DATABASE_URL_LOCAL en env/supabase.env"; exit 1; }

echo "1/3 · Publicando n8n…"
# n8n responde 401/403 sin token: eso confirma que el túnel llega hasta los flujos.
llega(){ code=$(curl -s -o /dev/null -w '%{http_code}' -m 10 -X POST -H 'Content-Type: application/json' -d '{}' "$1/webhook/epakti-errores" || true); [ "$code" = 401 ] || [ "$code" = 403 ]; }
U=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' logs/tunel.log 2>/dev/null | head -1 || true)
if [ -n "$U" ] && pgrep -f 'cloudflared tunnel --no-autoupdate --url http://127.0.0.1:5680' >/dev/null && pgrep -f 'scripts/webhook_proxy.py' >/dev/null && llega "$U"; then
  echo "    El túnel ya estaba funcionando; se reutiliza."
else
  pkill -f 'scripts/webhook_proxy.py' 2>/dev/null || true
  pkill -f 'cloudflared tunnel --no-autoupdate --url http://127.0.0.1:5680' 2>/dev/null || true
  sleep 1
  nohup python3 scripts/webhook_proxy.py 5680 > logs/proxy.log 2>&1 &
  : > logs/tunel.log
  nohup cloudflared tunnel --no-autoupdate --url http://127.0.0.1:5680 > logs/tunel.log 2>&1 &
  U=""; for _ in $(seq 1 30); do U=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' logs/tunel.log | head -1 || true); [ -n "$U" ] && break; sleep 2; done
  [ -n "$U" ] || { echo "No se obtuvo la dirección del túnel; revisa logs/tunel.log"; exit 1; }
  # Una dirección nueva de Cloudflare tarda uno o dos minutos en existir en internet.
  echo "    Esperando a que la dirección nueva esté disponible (hasta 4 minutos)…"
  ok=0; for _ in $(seq 1 48); do llega "$U" && { ok=1; break; }; sleep 5; done
  [ "$ok" = 1 ] || { echo "El túnel no llega a n8n (respuesta $code). Vuelve a correr el script en un minuto; revisa logs/tunel.log"; exit 1; }
fi
echo "    n8n publicado en $U (solo los flujos)"

echo "2/3 · Configurando producción y publicando…"
for v in N8N_WEBHOOK_BASE_URL N8N_WEBHOOK_HMAC_SECRET N8N_WEBHOOK_TOKEN; do vercel env rm "$v" production --yes >/dev/null 2>&1 || true; done
printf '%s' "$U/webhook" | vercel env add N8N_WEBHOOK_BASE_URL production --sensitive >/dev/null
printf '%s' "$SECRET" | vercel env add N8N_WEBHOOK_HMAC_SECRET production --sensitive >/dev/null
printf '%s' "$TOKEN" | vercel env add N8N_WEBHOOK_TOKEN production --sensitive >/dev/null
DEP=$(vercel --prod --yes 2>&1 | grep -oE 'https://epakti-[a-z0-9]+-[a-z0-9-]+\.vercel\.app' | head -1)
[ -n "$DEP" ] || { echo "No se pudo publicar en Vercel"; exit 1; }
vercel alias set "$DEP" "$DOMINIO" >/dev/null
echo "    Publicado en https://$DOMINIO"

echo "3/3 · Encendiendo el worker contra la base de producción…"
# Solo se reinicia el worker de producción (su PID queda en logs/); el de desarrollo local no se toca.
PIDF=logs/worker_produccion.pid
[ -f "$PIDF" ] && kill "$(cat "$PIDF")" 2>/dev/null || true
sleep 1
( set -a; . ./.env.dev; set +a; export DATABASE_URL="$DB" N8N_WEBHOOK_BASE_URL="http://127.0.0.1:5678/webhook"
  nohup .venv/bin/python -m backend.production.worker >> logs/worker_produccion.log 2>&1 &
  echo $! > "$PIDF" )
sleep 3
kill -0 "$(cat "$PIDF")" 2>/dev/null || { echo "El worker no arrancó; revisa logs/worker_produccion.log"; exit 1; }
echo "    Worker en marcha (registro: logs/worker_produccion.log)"

echo
echo "Listo. Correo, IA, avisos y cargas funcionan en https://$DOMINIO mientras esta Mac siga encendida."
echo "Para que el motor de Wilo mande sus alertas a n8n, pásale esta dirección:"
echo "    $U/webhook/epakti-alerta-360"
