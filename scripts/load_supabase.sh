#!/usr/bin/env bash
# Carga el dataset ficticio en Supabase. Lee DATABASE_URL_LOCAL de env/supabase.env sin cargarlo en el shell.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env.dev; set +a
URL="$(grep -m1 '^DATABASE_URL_LOCAL=' env/supabase.env | cut -d= -f2- | sed -e "s/^['\"]//" -e "s/['\"]$//")"
[ -n "$URL" ] || { echo "Falta DATABASE_URL_LOCAL en env/supabase.env"; exit 1; }
DATABASE_URL="$URL" .venv/bin/python -m scripts.load_supabase "$@" 2>&1 | grep -v "couldn't stop thread\|hint: you can try"
