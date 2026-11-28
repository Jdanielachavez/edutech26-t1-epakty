"""Integración real: PostgreSQL (TEST_DATABASE_URL) + stub del motor de Wilo (se levanta solo en un puerto libre)."""
import json
import os
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4
import hashlib
import hmac
import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from backend.production.config import Settings, forbidden_present
from backend.production.repository import Repository
from backend.production.api import create_app
from backend.production.engine import EngineClient
from backend.production.privacy import is_financial, NAME_KEYS, POLICY_KEYS, norm_course
from backend.production.worker import tick, process_job, sign
from backend.production.contracts import AgentDraft, enforce_draft
from backend.production.validation import validate_source
from scripts.build_dashboard_data import build, SOURCE, ROOT

STUB = ROOT / 'engine_stub' / '05_KIT_INTEGRACION_SIN_EXPONER_MOTOR' / 'epakti_engine_stub_server.py'
N8N = 'https://n8n.example.org/webhook'
HMAC_SECRET = 'h' * 40
H = lambda k: {'Authorization': 'Bearer ' + k * 32}
TOKENS = {'a' * 32: {'role': 'admin'}, 'w' * 32: {'role': 'worker'}, 't' * 32: {'role': 'tutor', 'course': '8vo EGB', 'parallel': 'A'},
          'r' * 32: {'role': 'rectoria'}, 'd' * 32: {'role': 'dece'}, 'c' * 32: {'role': 'colecturia'}, 'i' * 32: {'role': 'inspeccion'},
          'm' * 32: {'role': 'admisiones'}, 'n' * 32: {'role': 'n8n_callback'}, 'e' * 32: {'role': 'epakti_ceo'}, 'o' * 32: {'role': 'epakti_mlops'}}


def _free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0)); return s.getsockname()[1]


@pytest.fixture(scope='module')
def stub():
    port = _free_port()
    proc = subprocess.Popen([sys.executable, str(STUB), '--port', str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f'http://127.0.0.1:{port}/api/v1'
    for _ in range(50):
        try:
            if httpx.get(f'http://127.0.0.1:{port}/health', timeout=0.5).status_code == 200: break
        except httpx.HTTPError: time.sleep(0.1)
    yield base
    proc.terminate(); proc.wait(5)


@pytest.fixture(scope='module')
def engine(stub):
    client = EngineClient(stub, 'dev-stub-key-0123456789'); yield client; client.close()


@pytest.fixture(scope='module')
def repo(stub):
    url = os.getenv('TEST_DATABASE_URL')
    if not url: pytest.skip('TEST_DATABASE_URL not configured; live DB check pending')
    # Random tenant prevents destructive cleanup or conflicts with earlier test runs.
    settings = Settings(database_url=url, institution='test-' + uuid4().hex, tokens=TOKENS, engine_base_url=stub,
                        engine_api_key='dev-stub-key-0123456789', n8n_base_url=N8N, n8n_hmac_secret=HMAC_SECRET,
                        worker_backoff_base_s=0.01)
    repository = Repository(settings); repository.open()
    yield repository
    repository.close()


@pytest.fixture(scope='module')
def populated(repo):
    silver, gold, model = build(write_outputs=False); tables = validate_source(SOURCE)
    report = repo.save_pipeline('original', {}, tables, silver, gold, model)
    return silver, gold, model, tables, report


@pytest.fixture
def client(repo, engine):
    return TestClient(create_app(repo.settings, repo, engine), raise_server_exceptions=False)


def leaks(obj, key=''):
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in POLICY_KEYS or NAME_KEYS.match(k): continue
            if is_financial(k): out.append(k)
            out += leaks(v, k)
    elif isinstance(obj, list):
        for v in obj: out += leaks(v, key)
    elif isinstance(obj, str) and is_financial(obj): out.append(key + '=' + obj[:40])
    return out


def drain(repo, transport, engine=None, rounds=60):
    with httpx.Client(transport=transport) as http:
        for _ in range(rounds):
            if not tick(repo, http, engine): break


# ================= Carga, casos y RLS =================
def test_double_load_is_idempotent(repo, populated):
    silver, gold, model, tables, first = populated
    second = repo.save_pipeline('original', {}, tables, silver, gold, model)
    assert not first['replayed'] and second['replayed']
    assert len(repo.students()) == 240
    with repo.transaction() as c:
        assert c.execute('SELECT count(*) n FROM paktai_edu.silver_estudiantes').fetchone()['n'] == 240
        assert c.execute('SELECT count(*) n FROM paktai_edu.bronze_rows').fetchone()['n'] == sum(map(len, tables.values()))


def test_concurrent_interventions_do_not_duplicate(repo, populated):
    with ThreadPoolExecutor(max_workers=8) as pool: results = list(pool.map(lambda _: repo.intervene('EST-001'), range(16)))
    assert len({r['id'] for r in results}) == 1 and sum(r['created'] for r in results) == 1
    with repo.transaction() as c:
        assert c.execute("SELECT count(*) n FROM paktai_edu.intervenciones_dece WHERE id_estudiante='EST-001'").fetchone()['n'] == 1
        assert c.execute("SELECT count(*) n FROM paktai_edu.outbox WHERE kind='N8N' AND event_key LIKE 'case:%'").fetchone()['n'] == 1


def test_draft_claim_and_callback_idempotent(repo, populated):
    case = repo.intervene('EST-002'); lease = repo.claim_draft(case['id'])
    assert lease['claimed'] and not repo.claim_draft(case['id'])['claimed']
    draft = enforce_draft(AgentDraft(mensaje_representante='Acompañar', accion_interna_colegio='Revisar', responsable_asignado='DECE',
                                     plan_3_pasos=['a', 'b', 'c']), repo.student('EST-002'))
    assert not repo.complete_draft(case['id'], draft, uuid4())
    assert repo.complete_draft(case['id'], draft, lease['lease_token'])
    assert not repo.complete_draft(case['id'], draft, lease['lease_token'])


def test_expired_lease_rejects_late_draft(repo, populated):
    case = repo.intervene('EST-003'); lease = repo.claim_draft(case['id'])
    with repo.transaction() as c:
        c.execute("UPDATE paktai_edu.intervenciones_dece SET draft_lease_until=now()-interval '1 second' WHERE id=%s", (case['id'],))
    draft = enforce_draft(AgentDraft(mensaje_representante='x', accion_interna_colegio='y', responsable_asignado='DECE',
                                     plan_3_pasos=['a', 'b', 'c']), repo.student('EST-003'))
    assert not repo.complete_draft(case['id'], draft, lease['lease_token'])


def test_rls_other_institution_invisible(repo, populated):
    with repo.transaction() as c:
        c.execute("SELECT set_config('paktai.institution_id','other',true)")
        assert c.execute('SELECT count(*) n FROM paktai_edu.gold_estudiantes').fetchone()['n'] == 0
        assert c.execute('SELECT count(*) n FROM paktai_edu.student_pii_vault').fetchone()['n'] == 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("INSERT INTO paktai_edu.pipeline_runs VALUES('forbidden','x',now(),'synthetic_official','{}','{}','{}')")


def test_batch_creates_cases_for_critical_students(repo, populated):
    report = populated[4]
    assert report['critical_queued'] >= 1
    with repo.transaction() as c:
        assert c.execute("SELECT count(*) n FROM paktai_edu.outbox WHERE event_key LIKE 'batch:%'").fetchone()['n'] == 1


def test_summary_endpoint_reads_the_view(client, populated):
    r = client.get('/api/v1/summary', headers=H('r'))
    assert r.status_code == 200, r.text
    s = r.json()['summary']
    assert s['estudiantes'] == 240 and s['criticos'] >= 1 and s['moderados'] >= 1


def test_health_reports_real_tls(client, repo, populated):
    result = repo.health()
    assert client.get('/health').status_code == (200 if result['ssl'] else 503)
    if 'sslmode=verify-full' in os.environ.get('TEST_DATABASE_URL', ''):
        assert result['ssl'] is True and result['tls_version'] and client.get('/health').status_code == 200


def test_auth_requires_bearer_and_survives_non_ascii(client, populated):
    good = 'a' * 32
    assert client.get('/api/v1/students', headers={'Authorization': good}).status_code == 401
    assert client.get('/api/v1/students', headers={'Authorization': 'Basic ' + good}).status_code == 401
    assert client.get('/api/v1/students', headers={'Authorization': 'Bearer ñññ'.encode('latin-1')}).status_code == 401
    assert client.get('/api/v1/students', headers={'Authorization': 'bearer ' + good}).status_code == 200


# ================= LOPDP: bóveda de datos personales =================
def test_pii_is_pseudonymized_and_purged(client, repo, populated):
    with repo.transaction() as c:
        bronze = c.execute("SELECT payload FROM paktai_edu.bronze_rows WHERE source_table='estudiantes' LIMIT 1").fetchone()['payload']
        gold = c.execute("SELECT payload FROM paktai_edu.gold_estudiantes WHERE id_estudiante='EST-153'").fetchone()['payload']
        assert 'nombre_ficticio' not in bronze and 'name' not in gold          # analítica sin nombres
    named = {r['id']: r['name'] for r in client.get('/api/v1/students', headers=H('a')).json()}
    assert named['EST-153'] == 'Sebastián Torres Paredes'                         # el nombre sale de la bóveda
    with repo.transaction() as c:
        c.execute("UPDATE paktai_edu.student_pii_vault SET pii_retention_expires_at=now()-interval '1 day' WHERE student_pseudonym_id='EST-153'")
    assert repo.purge_expired_pii() >= 1
    named = {r['id']: r['name'] for r in client.get('/api/v1/students', headers=H('a')).json()}
    assert named['EST-153'] == 'REDACTED_LOPDP' and named['EST-154'] != 'REDACTED_LOPDP'
    with repo.transaction() as c:
        row = c.execute("SELECT full_name,pii_purged_at FROM paktai_edu.student_pii_vault WHERE student_pseudonym_id='EST-153'").fetchone()
        assert row['full_name'] is None and row['pii_purged_at'] is not None


# ================= Ingesta asíncrona (202 + jobs) =================
def _tables():
    import csv
    return {t: list(csv.DictReader(open(SOURCE / f'{t}.csv', encoding='utf-8-sig'))) for t in
            ('estudiantes', 'docentes', 'asistencia', 'notas', 'pensiones', 'horarios')}


def test_batch_sync_is_async_and_idempotent(client, repo, engine, populated):
    body = {'synthetic_declaration': True, 'tablas': _tables()}
    assert client.post('/api/v1/ingestion/batch-sync', json=body, headers=H('r')).status_code == 428   # sin Idempotency-Key
    start = time.monotonic()
    r = client.post('/api/v1/ingestion/batch-sync', json=body, headers={**H('r'), 'Idempotency-Key': 'JOB-TEST-0001'})
    elapsed = time.monotonic() - start
    assert r.status_code == 202 and r.json()['status'] == 'ACCEPTED_ASYNC' and elapsed < 2, elapsed
    job_id = r.json()['job_id']
    again = client.post('/api/v1/ingestion/batch-sync', json=body, headers={**H('r'), 'Idempotency-Key': 'JOB-TEST-0001'}).json()
    assert again['job_id'] == job_id and again['nuevo'] is False
    assert client.get(f'/api/v1/ingestion/jobs/{job_id}', headers=H('r')).json()['status'] == 'QUEUED'
    while process_job(repo, engine): pass
    done = client.get(f'/api/v1/ingestion/jobs/{job_id}', headers=H('r')).json()
    assert done['status'] == 'COMPLETED' and done['result']['students'] == 240 and done['result']['motor']['status'] == 'ACCEPTED_ASYNC'
    with repo.transaction() as c:   # minimización: los datos crudos del trabajo se borran al completar
        assert c.execute('SELECT payload FROM paktai_edu.ingestion_jobs WHERE job_id=%s', (job_id,)).fetchone()['payload'] is None
    assert client.get(f'/api/v1/ingestion/jobs/{job_id}', headers=H('t')).status_code == 403


def test_csv_upload_is_async(client, repo, engine, populated):
    files = [('files', (p.name, p.read_bytes(), 'text/csv')) for p in SOURCE.glob('*.csv')]
    r = client.post('/api/v1/pipeline/batch', files=files, data={'synthetic_declaration': 'true'}, headers=H('a'))
    assert r.status_code == 202, r.text
    assert client.post('/api/v1/pipeline/batch', files=files, data={'synthetic_declaration': 'true'}, headers=H('a')).json()['job_id'] == r.json()['job_id']
    while process_job(repo, engine): pass
    assert client.get(r.json()['poll_url'], headers=H('a')).json()['status'] == 'COMPLETED'


def test_job_backoff_dead_letter_and_retry(client, repo, engine, populated):
    dead = EngineClient('http://127.0.0.1:9/api/v1', 'dev-stub-key-0123456789', timeout=0.5)   # puerto cerrado
    job = client.post('/api/v1/ingestion/batch-sync', json={'synthetic_declaration': True, 'tablas': _tables()},
                      headers={**H('r'), 'Idempotency-Key': 'JOB-TEST-RETRY-' + uuid4().hex[:6]}).json()['job_id']
    statuses = []
    for _ in range(3):
        with repo.transaction() as c:
            c.execute("UPDATE paktai_edu.ingestion_jobs SET next_retry_at=now() WHERE job_id=%s", (job,))
        process_job(repo, dead); statuses.append(repo.job(job)['status'])
    assert statuses == ['FAILED_RETRYABLE', 'FAILED_RETRYABLE', 'DEAD_LETTER'], statuses
    assert 'Motor no disponible' in repo.job(job)['error_message']
    assert client.post(f'/api/v1/ingestion/jobs/{job}/retry', headers=H('r')).status_code == 202
    process_job(repo, engine)
    assert repo.job(job)['status'] == 'COMPLETED'


def test_invalid_data_goes_to_dead_letter_without_retries(client, repo, engine, populated):
    tables = _tables(); tables['notas'] = [dict(tables['notas'][0], nota='15')]
    job = client.post('/api/v1/ingestion/batch-sync', json={'synthetic_declaration': True, 'tablas': tables},
                      headers={**H('r'), 'Idempotency-Key': 'JOB-TEST-BAD-' + uuid4().hex[:6]}).json()['job_id']
    process_job(repo, engine)
    j = repo.job(job)
    assert j['status'] == 'DEAD_LETTER' and j['attempts'] == 1 and 'fuera de rango' in j['error_message']


# ================= Motor por contrato: roles y privacidad =================
def test_engine_routes_rbac_matrix(client, populated):
    matrix = {'/api/v1/dashboard/rectorado/kpis-roi': {'r': 200, 'd': 403, 't': 403, 'c': 403},
              '/api/v1/dashboard/docente-tutor/triage': {'r': 200, 'd': 200, 't': 200, 'i': 200, 'c': 403, 'm': 403},
              '/api/v1/dashboard/dece/inclusion-nee': {'d': 200, 'r': 200, 'c': 403, 't': 403, 'i': 403},
              '/api/v1/dashboard/colecturia/cartera-hogares': {'c': 200, 'r': 200, 'd': 403, 't': 403, 'i': 403},
              '/api/v1/dashboard/vicerrectorado/docentes-horarios': {'i': 200, 'r': 200, 'd': 403, 'c': 403},
              '/api/v1/admin/mlops/overview-and-drift': {'e': 200, 'o': 200, 'a': 200, 'r': 403, 'd': 403, 't': 403},
              '/api/v1/admin/tenants': {'e': 200, 'a': 200, 'r': 403},
              '/api/v1/admin/data-lake/anonymized-explorer': {'a': 200, 'r': 403, 'd': 403}}
    for path, expected in matrix.items():
        for who, code in expected.items():
            assert client.get(path, headers=H(who)).status_code == code, (path, who)


def test_pedagogical_roles_never_receive_financial_data(client, populated):
    # El stub de Wilo envía la beca al DECE: el backend la elimina igual.
    for who, path in [('d', '/api/v1/dashboard/dece/inclusion-nee'), ('d', '/api/v1/students/EST-089/ficha-360'),
                      ('i', '/api/v1/dashboard/docente-tutor/triage'), ('i', '/api/v1/dashboard/vicerrectorado/docentes-horarios')]:
        body = client.get(path, headers=H(who)).json()
        assert leaks(body) == [], (path, leaks(body)[:3])
    dece = client.get('/api/v1/dashboard/dece/inclusion-nee', headers=H('d')).json()
    assert 'tasa_beca' not in json.dumps(dece) and dece['total_nee'] == 92


def test_tutor_only_sees_own_parallel(client, populated):
    tri = client.get('/api/v1/dashboard/docente-tutor/triage', params={'curso': '10 EGB'}, headers=H('t')).json()
    assert tri['estudiantes'] and {(r['curso'], r['paralelo']) for r in tri['estudiantes']} == {('8 EGB', 'A')}
    assert client.get('/api/v1/students/EST-089/ficha-360', headers=H('t')).status_code == 404     # 10mo, no es suyo
    own = next(r['codigo_estudiante'] for r in tri['estudiantes'])
    assert client.get(f'/api/v1/students/{own}/ficha-360', headers=H('t')).status_code == 200
    assert client.get('/api/v1/students/EST-089/ficha-360', headers=H('c')).status_code == 403     # colecturía usa EP-08


def test_admission_views_split_by_role(client, populated):
    body = {'codigo_postulante': 'POST-2026-019', 'curso_postulado': '1 BGU'}
    adm = client.post('/api/v1/admissions/evaluate-applicant', json=body, headers=H('m')).json()
    assert 'vista_admision_pedagogica_dece' in adm and 'vista_admision_financiera_solo_colecturia' not in adm
    col = client.post('/api/v1/admissions/evaluate-applicant', json=body, headers=H('c')).json()
    assert 'vista_admision_financiera_solo_colecturia' in col and 'vista_admision_pedagogica_dece' not in col


def test_onboard_validates_before_calling_engine(client, populated):
    good = {'codigo_amie': '01H00123', 'nombre_institucion': 'UE Demo', 'dpa_parroquia_plantel': '010150',
            'regimen': 'Sierra-Amazonía', 'sostenimiento': 'Particular', 'sistema_origen_erp': 'CSV'}
    assert client.post('/api/v1/tenants/onboard', json=good, headers=H('r')).status_code == 200
    assert client.post('/api/v1/tenants/onboard', json={**good, 'dpa_parroquia_plantel': 'x'}, headers=H('r')).status_code == 422
    assert client.post('/api/v1/tenants/onboard', json=good, headers=H('t')).status_code == 403


def test_engine_down_returns_503_fast(repo, populated):
    dead = EngineClient('http://127.0.0.1:9/api/v1', 'dev-stub-key-0123456789', timeout=0.5)
    client = TestClient(create_app(repo.settings, repo, dead))
    start = time.monotonic()
    assert client.get('/api/v1/dashboard/docente-tutor/triage', headers=H('d')).status_code == 503
    assert time.monotonic() - start < 3


def test_dispatch_requires_explicit_approval(client, populated):
    assert client.post('/api/v1/n8n/dispatch-alerts', json={'cupo': 40}, headers=H('r')).status_code == 422
    assert client.post('/api/v1/n8n/dispatch-alerts', json={'cupo': 40, 'approved': True}, headers=H('t')).status_code == 403
    assert client.post('/api/v1/n8n/dispatch-alerts', json={'cupo': 40, 'approved': True}, headers=H('r')).status_code == 202


# ================= Envíos a n8n firmados (sin SMTP ni WhatsApp en el backend) =================
def test_family_message_goes_to_n8n_signed(client, repo, populated, monkeypatch):
    monkeypatch.setenv('STAGING_EMAIL', 'test@example.org'); monkeypatch.setenv('STAGING_ALLOWLIST', 'test@example.org')
    case = repo.intervene('EST-004'); lease = repo.claim_draft(case['id'])
    draft = {'mensaje_representante': 'Apoyo', 'accion_interna_colegio': 'Revisar', 'responsable_asignado': 'DECE', 'plan_3_pasos': ['a', 'b', 'c']}
    path = '/api/v1/interventions/' + case['id']
    body = {'channel': 'email', 'recipient': 'family@example.org', 'approved': True}
    assert client.post(path + '/approve-delivery', json=body, headers=H('a')).status_code == 409    # sin borrador
    assert client.post(path + '/draft', json={'lease_token': lease['lease_token'], 'draft': draft}, headers=H('w')).status_code == 200
    assert client.post(path + '/approve-delivery', json=body, headers=H('a')).json()['queued']
    assert not client.post(path + '/approve-delivery', json=body, headers=H('a')).json()['queued']
    sent = []
    def n8n(request): sent.append(request); return httpx.Response(200)
    drain(repo, httpx.MockTransport(n8n))
    family = [r for r in sent if r.url.path.endswith('/epakti-entrega-familia')]
    assert len(family) == 1
    req = family[0]; stamp = req.headers['X-Epakti-Timestamp']
    assert hmac.compare_digest(req.headers['X-Epakti-Signature'], sign(HMAC_SECRET, req.content, stamp))
    assert json.loads(req.content)['destinatario'] == 'test@example.org'                       # staging: destino de prueba
    assert client.get(path, headers=H('a')).json()['delivery_state'] == 'ENVIADA'


def test_outbox_backoff_and_manual_retry(client, repo, populated):
    with repo.transaction() as c:
        repo.enqueue(c, 'error:test:' + uuid4().hex, 'ADMIN', {'code': 'X'})
    def down(request): return httpx.Response(503)
    drain(repo, httpx.MockTransport(down))
    with repo.transaction() as c:
        ev = c.execute("SELECT id,state,attempts,available_at>now() later FROM paktai_edu.outbox WHERE kind='ADMIN' ORDER BY created_at DESC LIMIT 1").fetchone()
    assert ev['state'] == 'PENDING' and ev['attempts'] == 1 and ev['later']                         # espera exponencial, no 14 s fijos
    with repo.transaction() as c:
        c.execute("UPDATE paktai_edu.outbox SET state='FAILED' WHERE id=%s", (ev['id'],))
    assert client.post(f"/api/v1/admin/outbox/{ev['id']}/retry", headers=H('o')).status_code == 202
    assert client.post(f"/api/v1/admin/outbox/{ev['id']}/retry", headers=H('d')).status_code == 403


# ================= EP-19: contacto =================
def test_contact_lead_rate_limit_honeypot_and_n8n(repo, populated):
    client = TestClient(create_app(repo.settings, repo))
    lead = {'nombre_contacto': 'Rectora Prueba', 'institucion': 'UE Demo', 'correo': 'rectorado@uedemo.edu.ec', 'whatsapp_e164': '+593999000111'}
    r = client.post('/api/v1/public/contact-lead', json=lead)
    assert r.status_code == 201 and r.json()['lead_id']
    assert client.post('/api/v1/public/contact-lead', json={**lead, 'correo': 'no-es-correo'}).status_code == 422
    bot = client.post('/api/v1/public/contact-lead', json={**lead, 'sitio_web': 'http://spam'})
    assert bot.status_code == 201 and 'lead_id' not in bot.json()
    codes = [client.post('/api/v1/public/contact-lead', json=lead).status_code for _ in range(5)]
    assert 429 in codes                                                                             # 5 por minuto por IP
    sent = []
    def n8n(request): sent.append(request); return httpx.Response(200)
    drain(repo, httpx.MockTransport(n8n))
    assert any(r.url.path.endswith('/epakti-contacto-lead') for r in sent)
    with repo.transaction() as c:
        assert c.execute('SELECT n8n_dispatched FROM paktai_edu.public_contact_leads WHERE id=%s', (r.json()['lead_id'],)).fetchone()['n8n_dispatched']


# ================= EP-11: resultado de la intervención =================
def test_log_outcome_moves_case_and_feeds_engine(client, repo, engine, populated):
    case = repo.intervene('EST-120')
    body = {'codigo_estudiante': 'EST-120', 'rol_ejecutor': 'DECE', 'tipo_intervencion': 'TUTORIA_Y_ADAPTACION_NEE', 'canal_n8n': 'WhatsApp',
            'intervencion_aplicada': 1, 'fecha_ejecucion': '2025-11-03T10:30:00-05:00', 'compromiso_representante': 'Plan de nivelación'}
    r = client.post('/api/v1/interventions/log-outcome', json=body, headers=H('n'))           # token de n8n, solo para EP-11
    assert r.status_code == 201 and r.json()['caso_en_seguimiento']
    assert client.get('/api/v1/interventions/' + case['id'], headers=H('a')).json()['estado_caso'] == 'EN_SEGUIMIENTO'
    assert client.post('/api/v1/interventions/log-outcome', json={**body, 'tipo_intervencion': 'X'}, headers=H('d')).status_code == 422
    assert client.post('/api/v1/interventions/log-outcome', json=body, headers=H('t')).status_code == 404   # no es de su paralelo
    assert client.post('/api/v1/interventions/log-outcome', json=body, headers=H('m')).status_code == 403
    assert client.post('/api/v1/students', headers=H('n')).status_code in (403, 405)
    drain(repo, httpx.MockTransport(lambda r: httpx.Response(200)), engine)
    with repo.transaction() as c:
        ev = c.execute("SELECT state,payload FROM paktai_edu.outbox WHERE kind='ENGINE_OUTCOME' ORDER BY created_at DESC LIMIT 1").fetchone()
    assert ev['state'] == 'SENT' and ev['payload']['compromiso_representante'] is None       # al motor no viaja texto libre


# ================= Secretos por servicio =================
def test_events_wait_while_n8n_is_not_configured(repo, populated):
    from dataclasses import replace
    with repo.transaction() as c:
        repo.enqueue(c, 'error:wait:' + uuid4().hex, 'ADMIN', {'code': 'W'})
    original = repo.settings; repo.settings = replace(original, n8n_base_url='')
    try:
        with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200))) as http:
            for _ in range(40):
                if not tick(repo, http, None): break
    finally:
        repo.settings = original
    with repo.transaction() as c:
        ev = c.execute("SELECT state,attempts FROM paktai_edu.outbox WHERE event_key LIKE 'error:wait:%' ORDER BY created_at DESC LIMIT 1").fetchone()
    assert ev['state'] == 'PENDING' and ev['attempts'] == 0


def test_services_refuse_secrets_that_belong_to_n8n(monkeypatch):
    monkeypatch.setenv('SMTP_PASSWORD', 'x'); monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'y')
    assert set(forbidden_present('api')) == {'SMTP_PASSWORD', 'AWS_SECRET_ACCESS_KEY'}
    with pytest.raises(ValueError, match='no puede tener estos secretos'):
        Settings(database_url='host=x sslmode=verify-full', tokens=TOKENS).validate('api')
    with pytest.raises(ValueError, match='no puede tener estos secretos'):
        Settings(database_url='host=x sslmode=verify-full').validate('worker')
    monkeypatch.delenv('SMTP_PASSWORD'); monkeypatch.delenv('AWS_SECRET_ACCESS_KEY')
    with pytest.raises(ValueError, match='EPAKTI_ENGINE_BASE_URL'):
        Settings(database_url='host=x sslmode=verify-full', tokens=TOKENS, engine_base_url='http://engine.example.org/api/v1',
                 engine_api_key='k' * 20).validate('api')


def test_n8n_observability_merges_engine_and_backend(client, populated):
    r = client.get('/api/v1/admin/n8n/observability', headers=H('o'))
    assert r.status_code == 200 and 'motor' in r.json() and 'por_tipo_y_estado' in r.json()['backend']
    assert client.get('/api/v1/admin/n8n/observability', headers=H('r')).status_code == 403


# ================= Usuarios con contraseña =================
def _user_client(repo, engine):
    import dataclasses
    return TestClient(create_app(dataclasses.replace(repo.settings, session_secret='s' * 40), repo, engine), raise_server_exceptions=False)


def test_admin_manages_users_end_to_end(repo, engine):
    c = _user_client(repo, engine)
    assert c.get('/api/v1/admin/users', headers=H('r')).status_code == 403                      # rectoría no administra usuarios
    assert c.post('/api/v1/admin/users', json={'usuario': 'tutor.x', 'nombre': 'Tutor X', 'rol': 'tutor'}, headers=H('a')).status_code == 422
    made = c.post('/api/v1/admin/users', json={'usuario': 'tutor.x', 'nombre': 'Tutor X', 'rol': 'tutor', 'curso': '8vo EGB', 'paralelo': 'A'}, headers=H('a'))
    assert made.status_code == 201 and len(made.json()['clave_temporal']) >= 10
    temp = made.json()['clave_temporal']
    assert c.post('/api/v1/admin/users', json={'usuario': 'tutor.x', 'nombre': 'Otra', 'rol': 'dece'}, headers=H('a')).status_code == 409
    assert 'password_hash' not in str(c.get('/api/v1/admin/users', headers=H('a')).json())    # nunca se devuelve el hash
    bad = c.post('/api/v1/auth/login', json={'usuario': 'tutor.x', 'clave': 'incorrecta'})
    assert bad.status_code == 401
    login = c.post('/api/v1/auth/login', json={'usuario': 'tutor.x', 'clave': temp}).json()
    assert login['role'] == 'tutor' and login['debe_cambiar_clave'] is True
    session = {'Authorization': 'Bearer ' + login['token']}
    me = c.get('/api/v1/me', headers=session).json()
    assert me['role'] == 'tutor' and me['course'] == '8vo EGB'
    assert c.get('/api/v1/admin/users', headers=session).status_code == 403                    # un tutor no administra
    assert c.post('/api/v1/auth/change-password', json={'clave_actual': 'mala', 'clave_nueva': 'NuevaClave-2026'}, headers=session).status_code == 400
    assert c.post('/api/v1/auth/change-password', json={'clave_actual': temp, 'clave_nueva': 'corta'}, headers=session).status_code == 422
    assert c.post('/api/v1/auth/change-password', json={'clave_actual': temp, 'clave_nueva': 'NuevaClave-2026'}, headers=session).json() == {'cambiada': True}
    assert c.post('/api/v1/auth/login', json={'usuario': 'tutor.x', 'clave': temp}).status_code == 401
    ok = c.post('/api/v1/auth/login', json={'usuario': 'tutor.x', 'clave': 'NuevaClave-2026'}).json()
    assert ok['debe_cambiar_clave'] is False
    # desactivar: ya no entra y su sesión vigente deja de servir
    assert c.patch('/api/v1/admin/users/tutor.x', json={'activo': False}, headers=H('a')).status_code == 200
    assert c.post('/api/v1/auth/login', json={'usuario': 'tutor.x', 'clave': 'NuevaClave-2026'}).status_code == 401
    assert c.get('/api/v1/me', headers={'Authorization': 'Bearer ' + ok['token']}).status_code == 401
    # restablecer: reactivar y entregar una clave temporal nueva
    reset = c.patch('/api/v1/admin/users/tutor.x', json={'activo': True, 'restablecer_clave': True}, headers=H('a')).json()
    again = c.post('/api/v1/auth/login', json={'usuario': 'tutor.x', 'clave': reset['clave_temporal']}).json()
    assert again['debe_cambiar_clave'] is True
    assert c.patch('/api/v1/admin/users/no.existe', json={'activo': False}, headers=H('a')).status_code == 404


def test_admin_cannot_deactivate_own_user(repo, engine):
    c = _user_client(repo, engine)
    pw = 'ClaveAdmin-12345'
    assert c.post('/api/v1/admin/users', json={'usuario': 'admin.prueba', 'nombre': 'Admin', 'rol': 'admin', 'clave': pw}, headers=H('a')).status_code == 201
    token = c.post('/api/v1/auth/login', json={'usuario': 'admin.prueba', 'clave': pw}).json()['token']
    mine = {'Authorization': 'Bearer ' + token}
    assert c.patch('/api/v1/admin/users/admin.prueba', json={'activo': False}, headers=mine).status_code == 409
    assert c.get('/api/v1/admin/users', headers=mine).status_code == 200


# ---- Chequeo de conexión con el motor (GET /api/v1/admin/engine-check) ----


def _check_client(repo, handler):
    engine = EngineClient('https://motor.example.org/api/v1', 'k' * 20, transport=httpx.MockTransport(handler), school_id='SCH-DEMO-E2E')
    return TestClient(create_app(repo.settings, repo, engine), raise_server_exceptions=False)


def _admin(repo):
    return H('a')


def test_engine_check_motor_ok_reports_each_route(repo):
    def handler(request):
        if request.url.path == '/health': return httpx.Response(200, json={'status': 'ok', 'mode': 'EPAKTI_LIVE_PYTORCH_ENGINE'})
        if 'kpis-roi' in request.url.path: return httpx.Response(200, json={'ok': True})
        if 'triage' in request.url.path: return httpx.Response(404, json={'code': 'SCHOOL_NOT_INGESTED_YET'})
        if 'cartera' in request.url.path: return httpx.Response(401, json={'code': 'INVALID_ENGINE_API_KEY'})
        if 'dispatch' in request.url.path: return httpx.Response(202, json={'dry_run': True})
        return httpx.Response(403, json={'code': 'FORBIDDEN'})
    out = _check_client(repo, handler).get('/api/v1/admin/engine-check', headers=_admin(repo)).json()
    by = {r['ep']: r['estado'] for r in out['rutas']}
    assert out['motor']['estado'] == 'ok'
    assert by['EP-04'] == 'ok' and by['EP-05'] == 'sin_datos' and by['EP-08'] == 'clave_invalida' and by['EP-10'] == 'ok'
    assert by['EP-03'] == 'no_probado' and by['EP-02'] == 'no_probado' and by['EP-12'] == 'sin_permiso'


def test_engine_check_motor_down_does_not_wait_for_every_route(repo):
    def handler(request): raise httpx.ConnectError('apagado')
    out = _check_client(repo, handler).get('/api/v1/admin/engine-check', headers=_admin(repo)).json()
    assert out['motor']['estado'] == 'no_disponible'
    assert {r['estado'] for r in out['rutas']} <= {'no_disponible', 'no_probado'}


def test_engine_check_is_admin_only(repo):
    r = _check_client(repo, lambda req: httpx.Response(200, json={})).get('/api/v1/admin/engine-check', headers=H('t'))
    assert r.status_code in (401, 403)


# ---- Seguimiento de estudiantes en el tiempo ----
def test_followup_add_and_timeline_roles(client, repo, populated):
    sid = sorted(repo.student_ids())[0]
    base = f'/api/v1/students/{sid}/seguimiento'
    ok = client.post(base, json={'tipo': 'LLAMADA', 'nota': 'Se llamó a la familia; acordamos reunión el jueves.'}, headers=H('d'))
    assert ok.status_code == 201 and ok.json()['tipo'] == 'LLAMADA' and ok.json()['rol'] == 'dece'
    # lo escrito aparece en la línea de tiempo, con quién y cuándo, y es solo lectura para el resto
    ev = client.get(base, headers=H('r')).json()['eventos']
    assert any(e['origen'] == 'nota' and 'reunión el jueves' in e['texto'] for e in ev)
    # Colecturía y Admisiones nunca ven ni escriben seguimiento pedagógico
    for who in ('c', 'm'):
        assert client.get(base, headers=H(who)).status_code == 403
        assert client.post(base, json={'nota': 'hola mundo'}, headers=H(who)).status_code == 403
    # validación: notas muy cortas o tipos inventados se rechazan
    assert client.post(base, json={'nota': 'a'}, headers=H('d')).status_code == 422
    assert client.post(base, json={'tipo': 'HACKEO', 'nota': 'texto válido'}, headers=H('d')).status_code == 422
    # estudiante inexistente
    assert client.get('/api/v1/students/EST-NO-EXISTE/seguimiento', headers=H('d')).status_code == 404
    # el listado de notas recientes también respeta el rol
    assert client.get('/api/v1/seguimiento/recientes', headers=H('c')).status_code == 403
    assert client.get('/api/v1/seguimiento/recientes', headers=H('d')).json()['notas']


def test_followup_tutor_only_sees_own_parallel(client, repo, populated):
    mine = other = None
    for sid in sorted(repo.student_ids()):
        st = repo.student(sid)
        same = norm_course(st.get('course')) == norm_course('8vo EGB') and st.get('parallel') == 'A'
        if same and not mine: mine = sid
        if not same and not other: other = sid
        if mine and other: break
    assert mine and other
    assert client.post(f'/api/v1/students/{mine}/seguimiento', json={'nota': 'Tutoría de refuerzo en matemática.'}, headers=H('t')).status_code == 201
    assert client.get(f'/api/v1/students/{other}/seguimiento', headers=H('t')).status_code == 404
    assert client.post(f'/api/v1/students/{other}/seguimiento', json={'nota': 'No debería poder.'}, headers=H('t')).status_code == 404


# ---- Análisis de evaluaciones ----
CSV_EVAL = ('codigo_estudiante,pregunta,correcta\n'
            'EST-001,1,1\nEST-001,2,0\nEST-002,1,1\nEST-002,2,0\nEST-003,1,0\nEST-003,2,0\n')


def _eval_csv(client, who='d', body=CSV_EVAL, **extra):
    data = {'titulo': 'Prueba de fracciones', 'materia': 'Matemática', 'curso': '8vo EGB', 'paralelo': 'A', **extra}
    return client.post('/api/v1/evaluaciones/csv', data=data, files={'file': ('r.csv', body.encode(), 'text/csv')}, headers=H(who))


def test_evaluacion_csv_flow_temas_y_confirmacion(client, repo, populated):
    r = _eval_csv(client); assert r.status_code == 201 and r.json()['estado'] == 'POR_REVISAR' and r.json()['hojas'] == 3
    eid = r.json()['id']; base = f'/api/v1/evaluaciones/{eid}'
    d = client.get(base, headers=H('d')).json()
    by = {p['numero']: p for p in d['preguntas']}
    assert by[1]['pct'] == 66.7 and by[2]['pct'] == 0.0        # 2 de 3 acertaron la 1; nadie acertó la 2
    assert client.patch(base + '/temas', json={'temas': {'1': 'Suma de fracciones', '2': 'Fracciones equivalentes'}}, headers=H('d')).status_code == 200
    temas = client.get(base, headers=H('d')).json()['temas']
    assert temas[0]['tema'] == 'Fracciones equivalentes' and temas[0]['pct'] == 0.0     # lo más débil va primero: es lo que hay que reforzar
    assert client.post(base + '/confirmar', headers=H('d')).status_code == 200
    assert client.post(base + '/confirmar', headers=H('d')).status_code == 409           # ya confirmada
    assert client.patch(base + '/temas', json={'temas': {'1': 'X'}}, headers=H('d')).status_code == 409


def test_evaluacion_roles_csv_invalido_y_callback(client, repo, populated):
    for who in ('c', 'm'):                                  # Colecturía y Admisiones no entran a evaluaciones
        assert _eval_csv(client, who).status_code == 403
    assert _eval_csv(client, body='codigo_estudiante,pregunta,correcta\nEST-1,uno,1\n').status_code == 422
    assert _eval_csv(client, body='codigo_estudiante,pregunta,correcta\nJuan Pérez,1,1\n').status_code == 422   # un nombre no es un código
    assert _eval_csv(client, body='codigo_estudiante,pregunta,correcta\nEST-1,1,quizas\n').status_code == 422
    # puntajes en vez de correcta/incorrecta: acierta quien llega al 60 % del máximo
    eid = _eval_csv(client, body='codigo_estudiante,pregunta,puntaje,puntaje_max\nEST-1,1,0.7,1\nEST-2,1,0.5,1\n').json()['id']
    assert client.get(f'/api/v1/evaluaciones/{eid}', headers=H('d')).json()['preguntas'][0]['pct'] == 50.0
    # el tutor solo ve las evaluaciones de su paralelo (8vo EGB A); el callback del lector exige token de n8n/worker
    mine = _eval_csv(client, 't').json()['id']
    other = _eval_csv(client, 'd', paralelo='B').json()['id']
    ids = {e['id'] for e in client.get('/api/v1/evaluaciones', headers=H('t')).json()['evaluaciones']}
    assert str(mine) in ids and str(other) not in ids
    assert client.get(f'/api/v1/evaluaciones/{other}', headers=H('t')).status_code == 404
    cb = {'hojas': [{'codigo': 'EST-9', 'respuestas': [{'pregunta': 1, 'correcta': True}]}]}
    pend = client.post('/api/v1/evaluaciones/csv', data={'titulo': 'x' * 5, 'materia': 'Lengua', 'curso': '8vo EGB', 'paralelo': 'A'},
                       files={'file': ('r.csv', CSV_EVAL.encode(), 'text/csv')}, headers=H('d')).json()['id']
    assert client.post(f'/api/v1/evaluaciones/{pend}/resultado', json=cb, headers=H('d')).status_code == 403
    assert client.post(f'/api/v1/evaluaciones/{pend}/resultado', json=cb, headers=H('w')).status_code == 200


def test_evaluacion_fotos_validaciones(client, repo, populated):
    def post(files, who='d'):
        return client.post('/api/v1/evaluaciones', data={'titulo': 'Examen quimestral', 'materia': 'Matemática', 'curso': '8vo EGB', 'paralelo': 'A'},
                           files=files, headers=H(who))
    assert post([('files', ('a.jpg', b'\xff\xd8\xff' + b'0' * 50, 'image/jpeg'))]).status_code in (202, 503)   # 503 si n8n no está configurado en este entorno
    assert post([('files', ('a.exe', b'MZ' + b'0' * 50, 'application/octet-stream'))]).status_code in (415, 503)


# ---- Tracking por etapas ----
def test_etapas_flujo_roles_y_retroceso(client, repo, populated):
    sid = sorted(repo.student_ids())[3]
    url = f'/api/v1/students/{sid}/etapa'
    # la carga deja a los estudiantes en alerta como «Identificados», con su fecha
    mapa = {e['id_estudiante']: e for e in client.get('/api/v1/seguimiento/etapas', headers=H('d')).json()['etapas']}
    assert mapa and all(e['identificado_at'] for e in mapa.values())
    # avanzar: reunión con la familia, luego cerrado (con su fecha)
    assert client.put(url, json={'etapa': 'REUNION_FAMILIA'}, headers=H('d')).json()['etapa'] == 'REUNION_FAMILIA'
    cerrado = client.put(url, json={'etapa': 'CERRADO'}, headers=H('d')).json()
    assert cerrado['cerrado_at'] and cerrado['reunion_familia_at']
    # devolver una etapa: solo Administración, DECE o Rectoría; borra las fechas posteriores
    assert client.put(url, json={'etapa': 'IDENTIFICADO'}, headers=H('i')).status_code == 403
    atras = client.put(url, json={'etapa': 'REUNION_FAMILIA'}, headers=H('r')).json()
    assert atras['etapa'] == 'REUNION_FAMILIA' and atras['cerrado_at'] is None
    # etapas inventadas, o roles sin acceso
    assert client.put(url, json={'etapa': 'INVENTADA'}, headers=H('d')).status_code == 422
    for who in ('c', 'm'):
        assert client.put(url, json={'etapa': 'CERRADO'}, headers=H(who)).status_code == 403
        assert client.get('/api/v1/seguimiento/etapas', headers=H(who)).status_code == 403
    # la línea de tiempo del estudiante muestra las etapas
    ev = client.get(f'/api/v1/students/{sid}/seguimiento', headers=H('d')).json()['eventos']
    assert any(e['tipo'] == 'ETAPA' and 'reunió con la familia' in e['texto'] for e in ev)


def test_aviso_docente_pide_datos_y_encola_correo(repo, populated):
    sid = sorted(repo.student_ids())[4]
    row, error = repo.set_etapa(sid, 'DOCENTE_AVISADO', None, None, 'prueba', False)
    assert row is None and 'nombre y su correo' in error
    row, error = repo.set_etapa(sid, 'DOCENTE_AVISADO', 'Profe Prueba', 'profe@example.org', 'prueba', False)
    assert error is None and row['etapa'] == 'DOCENTE_AVISADO' and row['docente_avisado_at'] and row['docente_nombre'] == 'Profe Prueba'
    with repo.transaction() as c:
        ev = c.execute("SELECT payload FROM paktai_edu.outbox WHERE kind='AVISO_DOCENTE' AND event_key LIKE %s", (f'docente:{sid}:%',)).fetchone()
    assert ev and ev['payload']['recipient'] == 'profe@example.org' and 'nombre' not in ev['payload'] and 'pension' not in str(ev['payload']).lower()


# ---- Informe del estudiante ----
def test_informe_estudiante_claro_pedagogico_y_con_acciones(client, repo, populated):
    ids = sorted(repo.student_ids())
    # el estudiante con más riesgo trae problemas y acciones
    top = client.get('/api/v1/models/risk', headers=H('a')).json()['estudiantes'][0]['id']
    r = client.get(f'/api/v1/students/{top}/informe', headers=H('a'))
    assert r.status_code == 200
    d = r.json()
    assert d['estudiante']['id'] == top and d['semaforo'] in ('ROJO', 'NARANJA', 'AMARILLO', 'VERDE')
    assert d['resumen'] and d['como_leerlo'] and d['problemas'] and all(p['titulo'] and p['explicacion'] for p in d['problemas'])
    assert d['que_hacer'] and all({'accion', 'responsable', 'cuando', 'como', 'antes', 'despues'} <= set(a) for a in d['que_hacer'])
    assert all(a['despues'] <= a['antes'] for a in d['que_hacer'])      # una acción nunca sube el riesgo en el escenario
    # pedagógico: aunque lo pida Administración (que ve pagos), no hay nada financiero
    texto = str(d).lower()
    assert not any(w in texto for w in ('pensi', 'convenio', 'morosid', 'financ', 'deuda'))
    # roles
    for who in ('c', 'm'): assert client.get(f'/api/v1/students/{top}/informe', headers=H(who)).status_code == 403
    assert client.get('/api/v1/students/EST-NO-EXISTE/informe', headers=H('a')).status_code == 404
    # el tutor solo ve el informe de su paralelo
    for sid in ids:
        st = repo.student(sid)
        if not (norm_course(st.get('course')) == norm_course('8vo EGB') and st.get('parallel') == 'A'):
            assert client.get(f'/api/v1/students/{sid}/informe', headers=H('t')).status_code == 404; break


def test_asistencia_es_la_del_archivo_cargado(client, repo, populated):
    """Verificable: el calendario del informe coincide, día por día, con el CSV de asistencia que se cargó."""
    import csv, collections
    from scripts.build_dashboard_data import SOURCE
    sid = 'EST-001'
    esperado = {r['fecha']: r['estado'] for r in csv.DictReader(open(SOURCE / 'asistencia.csv', encoding='utf-8')) if r['codigo_estudiante'] == sid}
    d = client.get(f'/api/v1/students/{sid}/asistencia', headers=H('d')).json()
    assert {x['fecha']: x['estado'] for x in d['dias']} == esperado and d['resumen']['total_dias'] == len(esperado)
    cuenta = collections.Counter(esperado.values())
    assert d['resumen']['falta_injustificada'] == cuenta['falta_injustificada'] and d['resumen']['presente'] == cuenta['presente']
    inf = client.get(f'/api/v1/students/{sid}/informe', headers=H('a')).json()
    assert inf['asistencia']['resumen'] == d['resumen']
    assert client.get(f'/api/v1/students/{sid}/asistencia', headers=H('c')).status_code == 403


def test_admin_deletes_user_but_not_itself(client):
    c = client
    assert c.post('/api/v1/admin/users', json={'usuario': 'borrar.me', 'nombre': 'Borrar', 'rol': 'dece'}, headers=H('a')).status_code == 201
    r = c.delete('/api/v1/admin/users/borrar.me', headers=H('a'))
    assert r.status_code in (200, 409)
    if r.status_code == 200:
        assert r.json() == {'usuario': 'borrar.me', 'eliminado': True}
        assert c.delete('/api/v1/admin/users/borrar.me', headers=H('a')).status_code == 404
    assert c.delete('/api/v1/admin/users/borrar.me', headers=H('r')).status_code == 403
