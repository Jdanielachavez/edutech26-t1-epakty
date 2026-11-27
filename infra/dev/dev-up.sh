#!/usr/bin/env bash
# Levanta la base de desarrollo, migra el esquema y crea .env.dev con tokens locales.
# Uso:  infra/dev/dev-up.sh        (necesita Docker en marcha: `colima start`)
set -euo pipefail
cd "$(dirname "$0")/../.."
PY="${PY:-.venv/bin/python}"
./infra/dev/make-certs.sh
docker compose -f compose.dev.yaml up -d db
echo "Esperando a la base…"
until [ "$(docker inspect -f '{{.State.Health.Status}}' epakty-dev-db 2>/dev/null)" = "healthy" ]; do sleep 2; done
SQL() { docker exec -i epakty-dev-db psql -U postgres -d paktai_dev -v ON_ERROR_STOP=1 -q "$@"; }
# Dos logins, como en producción: uno que migra (dueño del esquema) y uno que solo ejecuta la API.
SQL <<'EOS'
DO $$ BEGIN
 IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='paktai_owner') THEN CREATE ROLE paktai_owner LOGIN CREATEROLE PASSWORD 'dev-owner-password'; END IF;
 IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='paktai_app')   THEN CREATE ROLE paktai_app LOGIN PASSWORD 'dev-app-password'; END IF;
END $$;
ALTER DATABASE paktai_dev OWNER TO paktai_owner;
EOS
CA="$PWD/certs/dev-ca.crt"
export MIGRATION_DATABASE_URL="postgresql://paktai_owner:dev-owner-password@localhost:5544/paktai_dev?sslmode=verify-full&sslrootcert=$CA"
"$PY" scripts/migrate.py
SQL -c "GRANT paktai_service TO paktai_app;"
if [ ! -f .env.dev ]; then
  "$PY" - "$CA" <<'EOP'
import json,secrets,sys,os
ca=sys.argv[1]
roles={'admin':{'role':'admin'},'dece':{'role':'dece'},'rectoria':{'role':'rectoria'},
       'tutor':{'role':'tutor','course':'8vo EGB','parallel':'A'},'worker':{'role':'worker'},
       'colecturia':{'role':'colecturia'},'inspeccion':{'role':'inspeccion'},'admisiones':{'role':'admisiones'},
       'n8n_callback':{'role':'n8n_callback'},'epakti_ceo':{'role':'epakti_ceo'},'epakti_mlops':{'role':'epakti_mlops'},
       'epakti_ds':{'role':'epakti_ds'},'epakti_cs':{'role':'epakti_cs'}}
tokens={}
lines=[]
for name,ident in roles.items():
    t=secrets.token_urlsafe(36);tokens[t]=ident;lines.append(f'# token {name}: {t}')
env=['ENVIRONMENT=staging','PAKTAI_INSTITUTION_ID=hackathon-colegio',
 f"DATABASE_URL='postgresql://paktai_app:dev-app-password@localhost:5544/paktai_dev?sslmode=verify-full&sslrootcert={ca}'",
 "PAKTAI_AUTH_TOKENS='"+json.dumps(tokens)+"'",
 "EPAKTI_ENGINE_BASE_URL='http://localhost:8090/api/v1'","EPAKTI_ENGINE_API_KEY='dev-stub-key-replace-in-prod'",
 "STAGING_EMAIL='prueba@example.org'","STAGING_ALLOWLIST='prueba@example.org'",
 "CORS_ORIGINS='http://127.0.0.1:8800,http://localhost:8800,http://127.0.0.1:8765,http://localhost:8765'"]
fd=os.open('.env.dev',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as f:f.write('\n'.join(lines+env)+'\n')
print('.env.dev creado (permisos 600). Los tokens están como comentarios dentro del archivo.')
EOP
fi
echo "Listo. Motor (stub): python3 engine_stub/05_KIT_INTEGRACION_SIN_EXPONER_MOTOR/epakti_engine_stub_server.py --port 8090"
echo "API: set -a; . ./.env.dev; set +a; .venv/bin/python -m backend.server   ·   Worker: .venv/bin/python -m backend.production.worker"
