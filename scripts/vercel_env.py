"""Pone en Vercel las variables que necesita la API publicada (proyecto «epakti», entorno production).

Lo ejecutas TÚ en tu terminal: los secretos van de tus archivos locales a Vercel sin imprimirse. Crea un administrador NUEVO
para el sitio público (no reutiliza las claves de desarrollo) y te muestra su contraseña una sola vez, al final.

Uso:  .venv/bin/python scripts/vercel_env.py                 (todas las variables; después: vercel --prod)
      .venv/bin/python scripts/vercel_env.py --solo-admin    (rota SOLO el administrador y SESSION_SECRET; después: vercel --prod)

--solo-admin sirve para revocar una contraseña expuesta: el administrador anterior deja de existir y, al cambiar SESSION_SECRET,
también se invalidan todas las sesiones abiertas. El cambio se aplica al redesplegar.
"""
import json
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.production.accounts import hash_password  # noqa: E402


def read_env(name: str, path: str) -> str:
    for line in (ROOT / path).read_text(encoding='utf-8').splitlines():
        if line.startswith(name + '='):
            return line.split('=', 1)[1].strip().strip('\'"')
    sys.exit(f'Falta {name} en {path}')


def add(name: str, value: str) -> bool:
    r = subprocess.run(['vercel', 'env', 'add', name, 'production', '--force', '--sensitive'], input=value, text=True,
                       capture_output=True, cwd=ROOT)
    print(('  ✓ ' if r.returncode == 0 else '  ✗ ') + name + ('' if r.returncode == 0 else '  (falló: ' + (r.stderr or r.stdout).strip().splitlines()[-1][:120] + ')'))
    return r.returncode == 0


def main():
    if not shutil.which('vercel'):
        sys.exit('Falta el CLI de Vercel (npm i -g vercel)')
    if subprocess.run(['vercel', 'whoami'], capture_output=True, cwd=ROOT).returncode != 0:
        sys.exit('Inicia sesión primero: vercel login')
    # Base: Supabase por el pooler en modo transacción (6543), sin archivo de certificado (Vercel no lo tiene): sslmode=require.
    u = urlsplit(read_env('DATABASE_URL', 'env/supabase.env'))
    db = urlunsplit((u.scheme, u.netloc.rsplit('@', 1)[0] + '@' + u.hostname + ':6543', u.path, 'sslmode=require', ''))
    password = secrets.token_urlsafe(14)
    users = {'admin.vercel': {'hash': hash_password(password), 'role': 'admin', 'name': 'Administración E-Pakty'}}
    values = [('ENVIRONMENT', 'staging'), ('PAKTAI_INSTITUTION_ID', 'hackathon-colegio'), ('DATABASE_URL', db),
              ('PAKTAI_USERS', json.dumps(users, separators=(',', ':'))), ('SESSION_SECRET', secrets.token_urlsafe(48)),
              ('EPAKTI_ENGINE_BASE_URL', read_env('EPAKTI_ENGINE_BASE_URL', '.env.dev')),
              ('EPAKTI_ENGINE_API_KEY', read_env('EPAKTI_ENGINE_API_KEY', '.env.dev')),
              ('EPAKTI_SCHOOL_ID', read_env('EPAKTI_SCHOOL_ID', '.env.dev')),
              ('CORS_ORIGINS', 'https://epakti.vercel.app'), ('TRUST_PROXY_HEADERS', '1')]
    if '--solo-admin' in sys.argv:
        values = [(n, v) for n, v in values if n in ('PAKTAI_USERS', 'SESSION_SECRET')]
        print('Rotando SOLO el administrador y la clave de sesiones…')
    print('Escribiendo variables en Vercel (production)…')
    ok = all([add(n, v) for n, v in values])
    if not ok:
        sys.exit('\nAlgunas variables fallaron; no se mostró ninguna contraseña. Revisa el mensaje y vuelve a correr el script.')
    # La contraseña NUNCA se imprime (la salida puede terminar en un chat o en un registro): va al portapapeles y a un archivo privado.
    vault = Path.home() / '.epakti' / 'admin_vercel.txt'
    vault.parent.mkdir(mode=0o700, exist_ok=True)
    vault.write_text(f'usuario: admin.vercel\nclave: {password}\n', encoding='utf-8')
    vault.chmod(0o600)
    copied = shutil.which('pbcopy') and subprocess.run(['pbcopy'], input=password, text=True).returncode == 0
    print('\nListo. Administrador del sitio público: usuario admin.vercel')
    print('  La contraseña NO se muestra aquí.' + (' Está copiada en tu portapapeles (pégala en tu gestor de contraseñas).' if copied else ''))
    print(f'  También quedó en {vault} (solo tú puedes leerlo). Bórralo cuando la guardes.')
    print('\nSiguiente: avísame y corro  vercel --prod  (hasta entonces sigue activa la configuración anterior).')


if __name__ == '__main__':
    main()
