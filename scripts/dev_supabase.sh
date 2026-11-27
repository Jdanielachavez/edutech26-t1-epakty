#!/usr/bin/env bash
# Arranca la API contra la base de Supabase (en vez del PostgreSQL local), en el puerto 8011 por defecto.
# Lee DATABASE_URL_LOCAL de env/supabase.env (certificado con ruta de este equipo) sin cargar el archivo en el shell
# (sus URLs llevan «&» sin comillas). No imprime secretos.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env.dev; set +a
URL="$(grep -m1 '^DATABASE_URL_LOCAL=' env/supabase.env | cut -d= -f2- | sed -e "s/^['\"]//" -e "s/['\"]$//")"
[ -n "$URL" ] || { echo "Falta DATABASE_URL_LOCAL en env/supabase.env"; exit 1; }
export DATABASE_URL="$URL"
exec .venv/bin/python -m backend.server --port "${1:-8011}"
