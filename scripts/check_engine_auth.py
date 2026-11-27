"""Comprueba cómo autentica el motor de Wilo. Solo lecturas (GET del triage). No imprime secretos.

Uso: set -a; . ./.env.dev; set +a; EPAKTI_ENGINE_JWT_SECRET=<clave compartida> python -m scripts.check_engine_auth

Resultado esperado cuando Wilo ya configuró SUPABASE_JWT_SECRET con la clave compartida y apagó los roles de prueba:
  clave + rol de prueba  -> 401/403   (rechazado)
  clave + JWT válido     -> 200       (aceptado)
  clave + JWT firma falsa-> 401/403
  JWT sin clave del motor-> 401
"""
import os
import sys

import httpx

from backend.production.config import Settings
from backend.production.engine import mint_jwt

PATH = '/dashboard/docente-tutor/triage'


def main():
    s = Settings()
    if not s.engine_base_url:
        sys.exit('Falta EPAKTI_ENGINE_BASE_URL')
    secret = os.getenv('EPAKTI_ENGINE_JWT_SECRET', '')
    school = s.engine_school_id or 'SCH-DEMO-240'
    base = s.engine_base_url.rstrip('/')

    def call(label, auth, key=True):
        headers = {'Authorization': auth, 'X-School-Id': school}
        if key:
            headers['X-Epakti-Engine-Key'] = s.engine_api_key
        r = httpx.get(base + PATH, headers=headers, timeout=20)
        detail = ''
        try:
            body = r.json(); detail = str(body.get('code') or body.get('detail') or '')[:70]
        except ValueError:
            pass
        print(f'{label:<34} -> HTTP {r.status_code}  {detail}')
        return r.status_code

    print(f'Motor: {base.split("/api")[0]} · colegio {school}')
    role_token = call('clave + rol de prueba (ROLE:)', 'Bearer ROLE:DOCENTE_TUTOR')
    if not secret:
        print('Define EPAKTI_ENGINE_JWT_SECRET para probar también los tokens firmados.')
        return
    good = call('clave + JWT firmado (válido)', 'Bearer ' + mint_jwt(secret, 'DOCENTE_TUTOR', school))
    call('clave + JWT con firma falsa', 'Bearer ' + mint_jwt('f' * 40, 'DOCENTE_TUTOR', school))
    call('JWT válido pero SIN clave del motor', 'Bearer ' + mint_jwt(secret, 'DOCENTE_TUTOR', school), key=False)
    if good == 200 and role_token in (401, 403):
        print('\nLISTO: el motor exige el token firmado y rechaza los roles de prueba. Activa EPAKTI_ENGINE_JWT_SECRET en .env.dev.')
    elif good == 200:
        print('\nEl motor acepta el JWT, pero TODAVÍA acepta roles de prueba: pídele a Wilo EPAKTI_ALLOW_DEV_ROLE_TOKENS=false.')
    else:
        print('\nTodavía no: el motor no acepta el JWT firmado. Wilo debe poner la clave compartida en SUPABASE_JWT_SECRET y reiniciar.')


if __name__ == '__main__':
    main()
