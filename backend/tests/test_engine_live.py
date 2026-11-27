"""El worker entrega la carga al motor en vivo de Wilo (multipart) sin nombres personales y espera su trabajo."""
import csv
import io
import httpx
from backend.production.config import Settings
from backend.production.engine import EngineClient
from backend.production.worker import push_to_engine, _strip_names
from scripts.build_dashboard_data import SOURCE

SEEN = {}


def _handler(request: httpx.Request):
    if request.url.path == '/health':
        return httpx.Response(200, json={'status': 'ok', 'mode': 'EPAKTI_LIVE_PYTORCH_ENGINE'})
    if request.url.path.endswith('/ingestion/upload-csv'):
        SEEN['headers'] = dict(request.headers); SEEN['body'] = request.content
        return httpx.Response(202, json={'job_id': 'DEMO-1', 'poll_url': '/api/v1/ingestion/jobs/DEMO-1'})
    if request.url.path.endswith('/ingestion/jobs/DEMO-1'):
        return httpx.Response(200, json={'status': 'COMPLETED', 'estudiantes_procesados': 240, 'estudiantes_rechazados': 0})
    return httpx.Response(404, json={'detail': 'no'})


def test_live_engine_receives_csv_without_names_and_job_is_awaited():
    engine = EngineClient('https://motor.example.org/api/v1', 'k' * 20, transport=httpx.MockTransport(_handler), school_id='SCH-DEMO-240')
    files = {p.stem: p.read_bytes() for p in SOURCE.glob('*.csv')}
    out = push_to_engine(engine, Settings(), files, 'JOB-X', silver={'students': []}, poll_s=0)
    assert out == {'job_id': 'DEMO-1', 'status': 'COMPLETED', 'estudiantes_procesados': 240, 'estudiantes_rechazados': 0}
    assert SEEN['headers']['x-school-id'] == 'SCH-DEMO-240' and SEEN['headers']['idempotency-key'] == 'JOB-X'
    part = next(x for x in SEEN['body'].split(b'--') if b'name="estudiantes"' in x)
    assert b'codigo' in part and b'nombre_ficticio' not in part   # sin nombres de estudiantes


def test_strip_names_keeps_other_columns():
    cleaned = _strip_names(b'codigo,nombre_ficticio,curso\nEST-1,Ana Perez,8vo\n')
    row = next(csv.DictReader(io.StringIO(cleaned.decode())))
    assert row == {'codigo': 'EST-1', 'curso': '8vo'}


def test_signed_token_carries_verified_role_and_school_and_expires():
    import base64, hashlib, hmac, json
    from backend.production.engine import mint_jwt
    secret = 'x' * 40
    token = mint_jwt(secret, 'RECTORADO', 'SCH-DEMO-240', ttl_s=60, now=1000)
    head, body, sig = token.split('.')
    pad = lambda v: v + '=' * (-len(v) % 4)
    claims = json.loads(base64.urlsafe_b64decode(pad(body)))
    assert claims['app_metadata'] == {'role': 'RECTORADO', 'school_id': 'SCH-DEMO-240'} and claims['exp'] == 1060 and claims['aud'] == 'authenticated'
    expected = base64.urlsafe_b64encode(hmac.new(secret.encode(), f'{head}.{body}'.encode(), hashlib.sha256).digest()).rstrip(b'=').decode()
    assert sig == expected


def test_engine_sends_signed_token_only_when_secret_is_configured():
    seen = []
    handler = lambda req: (seen.append(req.headers['authorization']), httpx.Response(200, json={}))[1]
    plain = EngineClient('https://motor.example.org/api/v1', 'k' * 20, transport=httpx.MockTransport(handler), school_id='SCH-1')
    plain.request('GET', '/x', 'admin')
    signed = EngineClient('https://motor.example.org/api/v1', 'k' * 20, transport=httpx.MockTransport(handler), school_id='SCH-1', jwt_secret='s' * 40)
    signed.request('GET', '/x', 'admin')
    assert seen[0] == 'Bearer ROLE:RECTORADO' and seen[1].count('.') == 2 and 'ROLE:' not in seen[1]


# ================= Token firmado hacia el motor (HS256) =================
import base64
import hashlib
import hmac
import json
import time
from backend.production.engine import mint_jwt

SECRET = 'j' * 40


def _decode(token):
    head, body, sig = token.split('.')
    pad = lambda x: x + '=' * (-len(x) % 4)
    return json.loads(base64.urlsafe_b64decode(pad(head))), json.loads(base64.urlsafe_b64decode(pad(body))), sig, head + '.' + body


def test_minted_token_has_supabase_shape_and_valid_signature():
    token = mint_jwt(SECRET, 'RECTORADO', 'SCH-DEMO-240', now=1_000_000)
    header, claims, sig, signed = _decode(token)
    assert header == {'alg': 'HS256', 'typ': 'JWT'}
    assert claims['app_metadata'] == {'role': 'RECTORADO', 'school_id': 'SCH-DEMO-240'}
    assert claims['aud'] == 'authenticated' and claims['exp'] - claims['iat'] == 120
    expected = base64.urlsafe_b64encode(hmac.new(SECRET.encode(), signed.encode(), hashlib.sha256).digest()).rstrip(b'=').decode()
    assert sig == expected
    other = mint_jwt('x' * 40, 'RECTORADO', 'SCH-DEMO-240', now=1_000_000)
    assert other.split('.')[2] != sig   # otra clave, otra firma


def test_client_sends_jwt_only_when_secret_is_configured():
    seen = []

    def handler(request):
        seen.append(request.headers['authorization']); return httpx.Response(200, json={'ok': True})
    plain = EngineClient('https://motor.example.org/api/v1', 'k' * 20, transport=httpx.MockTransport(handler), school_id='SCH-X')
    plain.request('GET', '/dashboard/docente-tutor/triage', 'tutor')
    signed = EngineClient('https://motor.example.org/api/v1', 'k' * 20, transport=httpx.MockTransport(handler), school_id='SCH-X', jwt_secret=SECRET)
    signed.request('GET', '/dashboard/docente-tutor/triage', 'tutor')
    assert seen[0] == 'Bearer ROLE:DOCENTE_TUTOR'                 # sin secreto: rol de prueba (comportamiento actual)
    _, claims, _, _ = _decode(seen[1].removeprefix('Bearer '))
    assert claims['app_metadata'] == {'role': 'DOCENTE_TUTOR', 'school_id': 'SCH-X'} and claims['exp'] > time.time()


def test_short_jwt_secret_is_rejected_by_config():
    import pytest
    with pytest.raises(ValueError):
        Settings(engine_jwt_secret='corto').validate('api')

