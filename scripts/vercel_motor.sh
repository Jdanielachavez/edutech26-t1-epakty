#!/usr/bin/env bash
# Pone en Vercel (producción) la URL y la clave del motor de Wilo y despliega.
# La URL del túnel cambia cada vez que Wilo reinicia su PC: pásala como argumento para actualizarla.
#   ./scripts/vercel_motor.sh                      → usa la URL guardada en .env.dev
#   ./scripts/vercel_motor.sh https://nueva.../api/v1
set -euo pipefail
cd "$(dirname "$0")/.."
URL="${1:-$(grep -m1 '^EPAKTI_ENGINE_BASE_URL=' .env.dev | cut -d= -f2-)}"
KEY="$(grep -m1 '^EPAKTI_ENGINE_API_KEY=' .env.dev | cut -d= -f2-)"
SCH="$(grep -m1 '^EPAKTI_SCHOOL_ID=' .env.dev | cut -d= -f2-)"
[ -n "$URL" ] && [ -n "$KEY" ] || { echo "Faltan EPAKTI_ENGINE_BASE_URL o EPAKTI_ENGINE_API_KEY en .env.dev"; exit 1; }
echo "Motor: $URL"; echo "Colegio: $SCH"; echo "Clave: (oculta, ${#KEY} caracteres)"; echo
# El motor tiene que responder ANTES de tocar producción: así una dirección de ejemplo, mal escrita
# o con el túnel caído no deja el portal sin motor.
echo "Comprobando que el motor responda…"
if ! curl -fsS -m 15 "${URL%/api/v1}/health" >/dev/null 2>&1; then
  echo
  echo "X  Ese motor NO responde:  $URL"
  echo "   No se cambió nada en producción: queda como estaba."
  echo "   Revisa que la dirección sea la que te pasó Wilo y que su PC esté encendida."
  exit 1
fi
echo "OK: el motor responde."; echo
for v in EPAKTI_ENGINE_BASE_URL EPAKTI_ENGINE_API_KEY EPAKTI_SCHOOL_ID; do
  vercel env rm "$v" production --yes >/dev/null 2>&1 || true
done
printf '%s' "$URL" | vercel env add EPAKTI_ENGINE_BASE_URL production --sensitive
printf '%s' "$KEY" | vercel env add EPAKTI_ENGINE_API_KEY production --sensitive
printf '%s' "$SCH" | vercel env add EPAKTI_SCHOOL_ID production --sensitive
echo; echo "Variables listas. Desplegando…"; echo
vercel --prod --yes
