"""Cuentas con usuario y contraseña, y sesiones firmadas.

- Las contraseñas nunca se guardan: solo su hash scrypt (formato `scrypt$N$r$p$sal$hash`, todo en hexadecimal).
- Una sesión es `payload.firma`: el payload lleva usuario, rol y vencimiento; la firma es HMAC-SHA256 con
  SESSION_SECRET. Sin ese secreto el inicio de sesión queda desactivado (los tokens Bearer siguen sirviendo
  para n8n y el worker).
- Los usuarios viven en la variable PAKTAI_USERS (JSON). Generar uno: `python -m scripts.create_user`.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1
# Roles que una persona puede tener al entrar con contraseña (n8n y el worker usan tokens, no contraseña).
LOGIN_ROLES = ('admin', 'rectoria', 'dece', 'tutor', 'inspeccion', 'colecturia', 'admisiones',
               'epakti_ceo', 'epakti_mlops', 'epakti_ds', 'epakti_cs')
# Quién puede subir datos y operar modelos (administrador) frente a quién solo consulta resultados (consumidor).
OPERATOR_ROLES = ('admin', 'epakti_ceo', 'epakti_mlops', 'epakti_ds', 'epakti_cs')


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return f'scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}'


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split('$')
        if scheme != 'scrypt':
            return False
        candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=len(bytes.fromhex(digest)))
        return hmac.compare_digest(candidate, bytes.fromhex(digest))
    except (ValueError, TypeError):
        return False


# Hash de relleno: si el usuario no existe, igual se gasta el mismo tiempo (no se puede averiguar qué usuarios existen).
_DUMMY = hash_password('relleno-no-valido', salt=b'0' * 16)


def authenticate_user(users: dict, username: str, password: str):
    record = users.get((username or '').strip().lower())
    ok = verify_password(password or '', record['hash'] if record else _DUMMY)
    if not record or not ok:
        return None
    return {'user': username.strip().lower(), 'role': record['role'], 'name': record.get('name') or username,
            'course': record.get('course'), 'parallel': record.get('parallel')}


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def issue_session(secret: str, identity: dict, ttl_s: int, now: float | None = None) -> tuple[str, int]:
    expires = int((now or time.time()) + ttl_s)
    payload = _b64(json.dumps({**identity, 'exp': expires}, separators=(',', ':'), ensure_ascii=False).encode())
    signature = _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
    return f'{payload}.{signature}', expires


def read_session(secret: str, token: str, now: float | None = None):
    if not secret or token.count('.') != 1:
        return None
    payload, signature = token.split('.')
    expected = _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(signature.encode(), expected.encode()):
        return None
    try:
        data = json.loads(_unb64(payload))
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict) or data.get('exp', 0) < (now or time.time()) or data.get('role') not in LOGIN_ROLES:
        return None
    return {k: data.get(k) for k in ('user', 'role', 'name', 'course', 'parallel')}
