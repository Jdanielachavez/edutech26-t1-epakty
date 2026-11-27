#!/usr/bin/env bash
# Publica SOLO el webhook del motor (POST /webhook/epakti-alerta-360) por un túnel HTTPS temporal de Cloudflare.
# El editor de n8n y los demás flujos no quedan expuestos. La URL cambia cada vez que se reinicia el túnel: pásala a Wilo.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs
command -v cloudflared >/dev/null || { echo "Instala cloudflared: brew install cloudflared"; exit 1; }
curl -s -m 5 localhost:5678/healthz >/dev/null || { echo "n8n no responde en localhost:5678"; exit 1; }
pkill -f 'scripts/webhook_proxy.py' 2>/dev/null || true
pkill -f 'cloudflared tunnel --no-autoupdate --url http://127.0.0.1:5680' 2>/dev/null || true
nohup python3 scripts/webhook_proxy.py 5680 > logs/proxy.log 2>&1 &
nohup cloudflared tunnel --no-autoupdate --url http://127.0.0.1:5680 > logs/tunel.log 2>&1 &
for i in $(seq 1 30); do U=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' logs/tunel.log | head -1 || true); [ -n "$U" ] && break; sleep 2; done
[ -n "${U:-}" ] || { echo "No se obtuvo la URL; revisa logs/tunel.log"; exit 1; }
echo "Webhook publicado: $U/webhook/epakti-alerta-360"
