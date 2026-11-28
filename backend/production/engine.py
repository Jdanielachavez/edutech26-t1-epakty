"""Cliente del motor predictivo de E-Pakti (servicio aparte de Wilo; en desarrollo, el stub del contrato).

Solo dos variables lo conectan: EPAKTI_ENGINE_BASE_URL y EPAKTI_ENGINE_API_KEY. Cambiar la URL del stub
(http://localhost:8090/api/v1) por la del motor productivo no requiere tocar código.

Reglas:
- La clave del motor viaja solo de servidor a servidor (cabecera X-Epakti-Engine-Key), nunca al navegador.
- El rol que se reenvía es el que el backend ya verificó; el motor nunca decide quién es el usuario.
- Timeout estricto de 5 s por llamada: si el motor no responde, la API contesta 503 en vez de colgarse.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import ssl
import time
from urllib.parse import urlparse

import httpx

# Roles internos del backend -> roles del contrato v2.1 del motor.
CONTRACT_ROLE = {'admin': 'RECTORADO', 'rectoria': 'RECTORADO', 'tutor': 'DOCENTE_TUTOR', 'dece': 'DECE',
                 'inspeccion': 'INSPECCION', 'colecturia': 'COLECTURIA', 'admisiones': 'ADMISIONES',
                 'worker': 'N8N_ORCHESTRATOR', 'n8n_callback': 'N8N_ORCHESTRATOR',
                 'epakti_ceo': 'EPAKTI_CEO', 'epakti_mlops': 'EPAKTI_MLOPS', 'epakti_ds': 'EPAKTI_DATA_SCIENCE',
                 'epakti_cs': 'EPAKTI_CS'}


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def mint_jwt(secret: str, role: str, school_id: str, ttl_s: int = 60, now: float | None = None) -> str:
    """Token HS256 de vida corta con el rol y el colegio YA verificados por la API (mismo formato que usa el motor con Supabase:
    app_metadata.role y app_metadata.school_id). Lo firma el servidor con un secreto compartido; el navegador nunca lo ve."""
    t = int(now or time.time())
    header = _b64(json.dumps({'alg': 'HS256', 'typ': 'JWT'}, separators=(',', ':')).encode())
    claims = _b64(json.dumps({'iss': 'epakti-bff', 'aud': 'authenticated', 'sub': f'bff:{role}', 'iat': t, 'exp': t + ttl_s, 'role': 'authenticated',
                              'app_metadata': {'role': role, 'school_id': school_id}}, separators=(',', ':')).encode())
    sig = _b64(hmac.new(secret.encode(), f'{header}.{claims}'.encode(), hashlib.sha256).digest())
    return f'{header}.{claims}.{sig}'


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def mint_jwt(secret: str, contract_role: str, school_id: str, *, issuer: str = 'epakti-bff', ttl_s: int = 120, now: float | None = None) -> str:
    """Token HS256 de vida corta con la forma de un JWT de Supabase Auth (el motor lo verifica con SUPABASE_JWT_SECRET).

    El rol y el colegio viajan en app_metadata, como pide el contrato del motor. Los fija el servidor, nunca el navegador.
    """
    issued = int(now or time.time())
    header = {'alg': 'HS256', 'typ': 'JWT'}
    claims = {'iss': issuer, 'aud': 'authenticated', 'sub': f'{issuer}:{contract_role}', 'role': 'authenticated',
              'iat': issued, 'exp': issued + ttl_s, 'app_metadata': {'role': contract_role, 'school_id': school_id}}
    body = _b64(json.dumps(header, separators=(',', ':')).encode()) + '.' + _b64(json.dumps(claims, separators=(',', ':')).encode())
    return body + '.' + _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())


class EngineUnavailable(RuntimeError):
    pass


class EngineClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 5.0, transport=None, school_id: str = '', jwt_secret: str = ''):
        url = urlparse(base_url)
        local = url.hostname in ('localhost', '127.0.0.1', '::1')
        if url.scheme != 'https' and not (url.scheme == 'http' and local):
            raise ValueError('EPAKTI_ENGINE_BASE_URL debe ser HTTPS (http solo para el stub local)')
        if url.username or url.password:
            raise ValueError('EPAKTI_ENGINE_BASE_URL no puede llevar credenciales en la URL')
        self.base = base_url.rstrip('/')
        self.jwt_secret = jwt_secret   # si existe, se envía un JWT firmado en lugar de «ROLE:...» (cuando Wilo apague los roles de prueba)
        self.jwt_secret = jwt_secret   # si existe, la autenticación va con un JWT firmado en vez del rol de prueba
        self.school_id = school_id   # colegio del motor (X-School-Id); lo fija el servidor, nunca el navegador
        self.api_key = api_key
        verify = ssl.create_default_context() if url.scheme == 'https' else True
        self.http = httpx.Client(timeout=timeout, follow_redirects=False, verify=verify, transport=transport)
        self._down_until = 0.0

    # Con el túnel del motor caído, cada llamada esperaba el timeout completo y el portal se trababa.
    # Tras un fallo de conexión se responde al instante durante DOWN_S segundos.
    DOWN_S = 60

    def _check_down(self):
        if time.monotonic() < self._down_until:
            raise EngineUnavailable('El motor no respondió hace poco')

    def _mark_down(self):
        self._down_until = time.monotonic() + self.DOWN_S

    def request(self, method: str, path: str, role: str, *, json=None, params=None, headers=None):
        self._check_down()
        contract_role = CONTRACT_ROLE[role]
        h = {'X-Epakti-Engine-Key': self.api_key, 'X-Epakti-Role': contract_role,
             # El stub de Wilo lee el rol de esta cabecera; el motor productivo usa la clave + X-Epakti-Role.
             'Authorization': self._bearer(contract_role), **({'X-School-Id': self.school_id} if self.school_id else {}), **(headers or {})}
        try:
            response = self.http.request(method, self.base + path, json=json, params=params, headers=h)
        except httpx.HTTPError as error:
            self._mark_down()
            raise EngineUnavailable(type(error).__name__) from None
        if response.status_code in (502, 503, 504, 530):   # túnel o motor apagado
            self._mark_down()
        if 300 <= response.status_code < 400 or response.status_code >= 500:
            raise EngineUnavailable(f'HTTP {response.status_code}')
        try:
            body = response.json()
        except ValueError:
            raise EngineUnavailable('Respuesta no JSON') from None
        return response.status_code, body

    def _bearer(self, contract_role: str) -> str:
        if self.jwt_secret:
            return 'Bearer ' + mint_jwt(self.jwt_secret, contract_role, self.school_id)
        return f'Bearer ROLE:{contract_role}'

    def is_live(self) -> bool:
        """¿Es el motor PyTorch de Wilo (sube CSV) o el stub del contrato (recibe JSON)? Se pregunta una vez a /health."""
        if getattr(self, '_live', None) is None:
            self._check_down()
            try:
                r = self.http.get(self.base.rsplit('/api/', 1)[0] + '/health', timeout=5)
                self._live = 'LIVE' in str(r.json().get('mode', '')).upper()
            except (httpx.HTTPError, ValueError):
                self._mark_down()
                raise EngineUnavailable('No se pudo consultar /health del motor') from None
        return self._live

    def upload_csv(self, role: str, files: dict, data: dict, idempotency_key: str):
        """EP-02C: sube los CSV del colegio al motor (multipart). Devuelve (status, cuerpo)."""
        contract_role = CONTRACT_ROLE[role]
        h = {'X-Epakti-Engine-Key': self.api_key, 'X-Epakti-Role': contract_role, 'Authorization': self._bearer(contract_role),
             'Idempotency-Key': idempotency_key, **({'X-School-Id': self.school_id} if self.school_id else {})}
        multipart = {name: (f'{name}.csv', content, 'text/csv') for name, content in files.items()}
        try:
            response = self.http.post(self.base + '/ingestion/upload-csv', data=data, files=multipart, headers=h, timeout=60)
        except httpx.HTTPError as error:
            raise EngineUnavailable(type(error).__name__) from None
        if 300 <= response.status_code < 400 or response.status_code >= 500:
            raise EngineUnavailable(f'HTTP {response.status_code}')
        try:
            return response.status_code, response.json()
        except ValueError:
            raise EngineUnavailable('Respuesta no JSON') from None

    def close(self):
        self.http.close()
