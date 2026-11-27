"""Crea el usuario de la API en Supabase (paktai_app, solo con paktai_service, sin BYPASSRLS).

Pide la contraseña de administrador (postgres) por teclado, genera una contraseña aleatoria para paktai_app
y escribe env/supabase.env (permisos 600, ignorado por git) con DATABASE_URL para la API y el worker.
Ninguna contraseña se imprime.
"""
import getpass
import os
import secrets
import urllib.parse
from pathlib import Path

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
REF = 'tpbactrhpksrugqggikk'
HOST = os.getenv('SUPABASE_DB_HOST', 'aws-0-us-east-2.pooler.supabase.com')
CA = ROOT / 'certs' / 'supabase-ca.crt'


def url(user, password, ca):
    return (f"postgresql://{user}.{REF}:{urllib.parse.quote(password, safe='')}@{HOST}:5432/postgres"
            f"?sslmode=verify-full&sslrootcert={ca}")


def main():
    admin = getpass.getpass('Contraseña de postgres (no se ve al escribir): ')
    app_password = secrets.token_urlsafe(32)
    with psycopg.connect(url('postgres', admin, CA), autocommit=True) as c:
        exists = c.execute("SELECT 1 FROM pg_roles WHERE rolname='paktai_app'").fetchone()
        verb = 'ALTER' if exists else 'CREATE'
        c.execute(sql.SQL(verb + ' ROLE paktai_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD {}')
                  .format(sql.Literal(app_password)))
        c.execute('GRANT paktai_service TO paktai_app')
    # Comprobación: el usuario nuevo entra y puede asumir paktai_service.
    with psycopg.connect(url('paktai_app', app_password, CA)) as c:
        c.execute('SET LOCAL ROLE paktai_service')
        c.execute('SELECT count(*) FROM paktai_edu.ingestion_jobs').fetchone()
    out = ROOT / 'env' / 'supabase.env'
    out.write_text('# Generado por scripts/supabase_runtime_user.py. NO SUBIR. Para API y worker.\n'
                   f"DATABASE_URL={url('paktai_app', app_password, '/certs/supabase-ca.crt')}\n"
                   f"DATABASE_URL_LOCAL={url('paktai_app', app_password, CA)}\n", encoding='utf-8')
    os.chmod(out, 0o600)
    print(f'Usuario paktai_app listo y probado. Conexión guardada en {out.relative_to(ROOT)} (permisos 600).')


if __name__ == '__main__':
    main()
