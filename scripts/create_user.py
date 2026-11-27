"""Crea o actualiza un usuario con contraseña en un archivo .env (PAKTAI_USERS + SESSION_SECRET).

Uso:  python -m scripts.create_user .env.dev admin.pakty admin --nombre "Administración E-Pakty"
      python -m scripts.create_user .env.dev colegio.rector rectoria --nombre "Rectoría"
Genera una contraseña aleatoria, guarda solo su hash scrypt y deja la contraseña como comentario `# clave <usuario>: ...`
en el mismo archivo (solo para desarrollo; en producción se entrega por un canal seguro y no se guarda en claro).
"""
import argparse
import json
import re
import secrets
from pathlib import Path

from backend.production.accounts import hash_password, LOGIN_ROLES


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('envfile'); ap.add_argument('usuario'); ap.add_argument('rol', choices=LOGIN_ROLES)
    ap.add_argument('--nombre'); ap.add_argument('--curso'); ap.add_argument('--paralelo')
    ap.add_argument('--clave', help='Si se omite, se genera una aleatoria')
    ap.add_argument('--sin-comentario', action='store_true', help='No dejar la contraseña como comentario en el archivo')
    a = ap.parse_args()
    path = Path(a.envfile)
    text = path.read_text(encoding='utf-8') if path.exists() else ''
    match = re.search(r'^PAKTAI_USERS=(.*)$', text, re.M)
    users = json.loads(match.group(1).strip().strip("'")) if match else {}
    name = a.usuario.strip().lower()
    password = a.clave or secrets.token_urlsafe(12)
    users[name] = {k: v for k, v in {'hash': hash_password(password), 'role': a.rol, 'name': a.nombre or a.usuario,
                                     'course': a.curso, 'parallel': a.paralelo}.items() if v}
    # Entre comillas simples: el hash lleva `$` y el shell lo expandiría al hacer `. ./.env.dev`.
    line = "PAKTAI_USERS='" + json.dumps(users, ensure_ascii=False, separators=(',', ':')) + "'"
    text = re.sub(r'^PAKTAI_USERS=.*$', lambda _: line, text, flags=re.M) if match else text.rstrip('\n') + '\n' + line + '\n'
    if not re.search(r'^SESSION_SECRET=', text, re.M):
        text = text.rstrip('\n') + '\nSESSION_SECRET=' + secrets.token_urlsafe(48) + '\n'
    text = re.sub(rf'^# clave {re.escape(name)}:.*\n', '', text, flags=re.M)
    if not a.sin_comentario:
        text = f'# clave {name}: {password}\n' + text
    path.write_text(text, encoding='utf-8')
    print(f'Usuario {name} ({a.rol}) guardado en {path}.' + ('' if a.sin_comentario else ' La contraseña quedó como comentario en el archivo.'))


if __name__ == '__main__':
    main()
