#!/usr/bin/env bash
# Migra el esquema a Supabase. Pide los datos por teclado: la contraseña no queda en el historial.
set -euo pipefail
cd "$(dirname "$0")/.."
CERT=certs/supabase-ca.crt
if [ ! -f "$CERT" ]; then
  echo "Falta $CERT. Descárgalo en Supabase: Project Settings → Database → SSL Configuration → Download certificate,"
  echo "y guárdalo como $(pwd)/$CERT"; exit 1
fi
HOST="${SUPABASE_DB_HOST:-aws-0-us-east-2.pooler.supabase.com}"; echo "Host: $HOST"
read -rsp "Contraseña de la base de datos (no se ve al escribir): " PASS; echo
ENC=$(.venv/bin/python -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1],safe=""))' "$PASS")
export MIGRATION_DATABASE_URL="postgresql://postgres.tpbactrhpksrugqggikk:${ENC}@${HOST}:5432/postgres?sslmode=verify-full&sslrootcert=${CERT}"
.venv/bin/python scripts/migrate.py && echo "Migración lista en Supabase."
