#!/usr/bin/env bash
# Importa y activa en n8n los flujos de E-Pakty (contenedor de compose o de desarrollo). No toca credenciales.
# Uso:  ./scripts/n8n_import_all.sh [contenedor]        (por defecto: el servicio n8n de compose; en desarrollo: epakty-n8n)
# Variables: PAKTAI_API_INTERNAL_URL (por defecto http://api:8000, la API vista desde n8n)
set -euo pipefail
cd "$(dirname "$0")/.."
API_URL="${PAKTAI_API_INTERNAL_URL:-http://api:8000}"
if [ "${1:-}" ]; then RUN=(docker exec "$1"); CP=(docker cp); C="$1"
else C="$(docker compose ps -q n8n)"; RUN=(docker exec "$C"); CP=(docker cp); fi
[ -n "$C" ] || { echo "No encuentro el contenedor de n8n"; exit 1; }
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
# Flujo -> id estable en n8n (para actualizar sin duplicar)
for f in paktai_borrador_bedrock_local epakti_entrega_correo epakti_contacto_lead epakti_errores epakti_alerta_360_firmado; do
  sed "s#http://host.docker.internal:8000#${API_URL}#g" "n8n/workflows/${f}.json" > "$TMP/${f}.json"
  "${CP[@]}" "$TMP/${f}.json" "$C:/tmp/${f}.json"
  "${RUN[@]}" n8n import:workflow --input="/tmp/${f}.json" 2>&1 | grep -v "license" | tail -1 || true
  # En un n8n recién creado la primera importación puede perderse: se repite (es idempotente, cada flujo tiene id fijo).
  "${RUN[@]}" n8n import:workflow --input="/tmp/${f}.json" >/dev/null 2>&1 || true
done
echo
echo "Importados. Pasos manuales en n8n (el editor, por túnel SSH):"
echo "  1) Credenciales: «Header Auth» X-Epakti-Webhook-Token = N8N_WEBHOOK_TOKEN; «Header Auth» Authorization = Bearer <token rol worker>; AWS (Bedrock); SMTP."
echo "  2) Asignarlas a los nodos de cada flujo y activar los flujos (los de entrega/contacto/errores comparten ruta con su versión sandbox: no activar ambas)."
