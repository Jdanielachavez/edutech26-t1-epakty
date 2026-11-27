"""API de E-Pakti (BFF): lo único que habla con el navegador.

Qué resuelve aquí:   autenticación y roles, casos e intervenciones con aprobación humana, ingesta asíncrona,
                     bóveda de datos personales (LOPDP), formulario de contacto y cola hacia n8n.
Qué le pide al motor: todo lo predictivo (semáforos, SHAP, sensibilidad, Rectoría, DECE, Colecturía, Plano B),
                     por HTTP a EPAKTI_ENGINE_BASE_URL. Cambiar esa variable conecta el motor real sin tocar código.
Privacidad: además del control del motor, el backend vuelve a filtrar cada respuesta según el rol.
"""
from contextlib import asynccontextmanager
from collections import defaultdict, deque
from uuid import UUID
import asyncio
import base64
import csv
import io
import json
import hashlib
import hmac
import secrets
import logging
import os
import re
import time
from fastapi import FastAPI, Depends, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg import errors as pg_errors
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from .config import Settings
from .repository import Repository
from .validation import TABLES
from .contracts import (EtapaUpdate, SeguimientoCreate, ResultadoExamen, TemasExamen, DraftCallback, DraftEdit, StateUpdate, DeliveryRequest, WorkflowError, DispatchRequest,
                        OutcomeLog, Onboard, BatchSync, ContactLead, LoginRequest, SimulationRequest, UserCreate, UserPatch,
                        ChangePassword, enforce_draft)
from .delivery import recipient_for, DeliveryConfigurationError
from .engine import EngineClient, EngineUnavailable
from .privacy import for_role, scope_students, norm_course
from . import accounts, models, informes
import httpx
from urllib.parse import urlparse

log = logging.getLogger('paktai')
IDEMPOTENCY = re.compile(r'^[A-Za-z0-9_.:-]{8,100}$')
MAX_ENGINE_BODY = 256 * 1024

# Rutas del contrato v2.1 que responde el motor: (método, ruta, roles del backend que pueden usarla).
ENGINE_ROUTES = [
    ('GET', '/api/v1/dashboard/rectorado/kpis-roi', ('admin', 'rectoria')),                                   # EP-04
    ('GET', '/api/v1/dashboard/docente-tutor/triage', ('tutor', 'inspeccion', 'dece', 'admin', 'rectoria')),  # EP-05
    ('GET', '/api/v1/students/{codigo}/ficha-360', ('tutor', 'dece', 'inspeccion', 'admin', 'rectoria')),     # EP-06
    ('GET', '/api/v1/dashboard/dece/inclusion-nee', ('dece', 'admin', 'rectoria')),                           # EP-07
    ('GET', '/api/v1/dashboard/colecturia/cartera-hogares', ('colecturia', 'admin', 'rectoria')),             # EP-08
    ('GET', '/api/v1/dashboard/vicerrectorado/docentes-horarios', ('admin', 'rectoria', 'inspeccion')),       # EP-09
    ('POST', '/api/v1/admissions/evaluate-applicant', ('admisiones', 'dece', 'colecturia', 'admin', 'rectoria')),  # EP-03
    ('POST', '/api/v1/tenants/onboard', ('rectoria', 'admin', 'epakti_ceo', 'epakti_cs')),                    # EP-01
    ('GET', '/api/v1/admin/mlops/overview-and-drift', ('admin', 'epakti_ceo', 'epakti_mlops', 'epakti_ds')),           # EP-12
    ('GET', '/api/v1/admin/tenants', ('admin', 'epakti_ceo', 'epakti_cs', 'epakti_mlops')),                            # EP-13
    ('POST', '/api/v1/admin/mlops/retrain', ('epakti_mlops', 'epakti_ds', 'epakti_ceo')),                     # EP-14
    ('POST', '/api/v1/admin/mlops/models/{model_version}/promote', ('epakti_mlops', 'epakti_ceo')),          # EP-15
    ('GET', '/api/v1/admin/data-lake/anonymized-explorer', ('admin', 'epakti_ds', 'epakti_mlops', 'epakti_ceo')),      # EP-16
    ('PATCH', '/api/v1/admin/tenants/{school_id}/feature-flags', ('epakti_ceo', 'epakti_cs', 'epakti_mlops')),  # EP-17
]
# Qué prueba el chequeo de conexión: una sonda por ruta del motor, con el rol que la usa y el servicio al que alimenta.
# Las rutas que escriben (carga de CSV, admisión, bitácora) no se prueban en seco: se marcan «no_probado».
ENGINE_PROBES = [
    ('EP-04', 'GET', '/dashboard/rectorado/kpis-roi', 'rectoria', 'desercion', None),
    ('EP-05', 'GET', '/dashboard/docente-tutor/triage', 'dece', 'desercion', None),
    ('EP-06', 'GET', '/students/{codigo}/ficha-360', 'dece', 'desercion', None),
    ('EP-07', 'GET', '/dashboard/dece/inclusion-nee', 'dece', 'bienestar', None),
    ('EP-08', 'GET', '/dashboard/colecturia/cartera-hogares', 'colecturia', 'pagos', None),
    ('EP-09', 'GET', '/dashboard/vicerrectorado/docentes-horarios', 'rectoria', 'rendimiento', None),
    ('EP-03', 'POST', '/admissions/evaluate-applicant', 'admisiones', 'admisiones', 'no_probado'),
    ('EP-10', 'POST', '/n8n/dispatch-alerts', 'rectoria', 'familias', {'cupo': 1, 'approved': True, 'dry_run': True}),
    ('EP-11', 'POST', '/interventions/log-outcome', 'rectoria', 'familias', 'no_probado'),
    ('EP-18', 'GET', '/admin/n8n/observability', 'epakti_mlops', 'familias', None),
    ('EP-02', 'POST', '/ingestion/upload-csv', 'rectoria', 'datos', 'no_probado'),
    ('EP-12', 'GET', '/admin/mlops/overview-and-drift', 'epakti_mlops', 'modelos', None),
    ('EP-13', 'GET', '/admin/tenants', 'epakti_cs', 'modelos', None),
    ('EP-16', 'GET', '/admin/data-lake/anonymized-explorer', 'epakti_ds', 'modelos', None),
]
QUERY_PASSTHROUGH = {'curso', 'paralelo', 'semaforo_color', 'tiene_nee', 'k', 'limit'}


def create_app(settings=None, repository=None, engine=None):
    config = settings or Settings()
    repo = repository or Repository(config)
    if engine is None and config.engine_base_url:
        engine = EngineClient(config.engine_base_url, config.engine_api_key, config.engine_timeout_s, school_id=config.engine_school_id, jwt_secret=config.engine_jwt_secret)

    @asynccontextmanager
    async def lifespan(app):
        config.validate('api'); repo.open()
        try: yield
        finally: repo.close()
    app = FastAPI(title='E-Pakti API', version='2.1.0', lifespan=lifespan, docs_url=None, redoc_url=None)
    origins = [x.strip() for x in os.getenv('CORS_ORIGINS', '').split(',') if x.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=['GET', 'POST', 'PATCH', 'PUT'],
                       allow_headers=['Authorization', 'Content-Type', 'Idempotency-Key'])

    def authenticate(authorization: str = Header(default='')):
        # Exige el esquema Bearer y compara bytes: un texto no ASCII no provoca un 500.
        scheme, _, supplied = authorization.partition(' ')
        if scheme.lower() == 'bearer':
            raw = supplied.strip().encode('utf-8', 'ignore')
            for token, identity in config.tokens.items():
                if hmac.compare_digest(token.encode('utf-8'), raw): return identity
            session = accounts.read_session(config.session_secret, supplied.strip())
            if session:
                if repo.user_active(session['user']) is False: raise HTTPException(401, 'Usuario desactivado')
                return session
        raise HTTPException(401, 'No autorizado')

    def roles(*allowed):
        def check(identity=Depends(authenticate)):
            if identity['role'] not in allowed: raise HTTPException(403, 'Rol no autorizado')
            return identity
        return check

    @app.get('/health')
    def health():
        try:
            result = repo.health()
            if not result['ssl']: raise RuntimeError('SSL requerido')
            return {'status': 'ok', 'database': result, 'motor_configurado': engine is not None}
        except Exception:
            raise HTTPException(503, 'Base no disponible o sin cifrado') from None

    attempts = defaultdict(deque)

    @app.post('/api/v1/auth/login')
    def login(body: LoginRequest, request: Request):
        if not config.session_secret:
            raise HTTPException(503, 'El inicio de sesión con contraseña no está configurado')
        ip = request.client.host if request.client else 'desconocido'
        forwarded = request.headers.get('x-forwarded-for', '')
        if config.trust_proxy_headers and forwarded: ip = forwarded.split(',')[0].strip()
        now = time.monotonic(); window = attempts[ip]
        while window and now - window[0] > 60: window.popleft()
        if len(window) >= config.login_rate_limit:
            raise HTTPException(429, 'Demasiados intentos; espera un minuto')
        window.append(now)
        name = body.usuario.strip().lower()
        users = dict(config.users)
        db_user = repo.get_user(name)
        must_change = False
        if db_user:   # un usuario de la base manda sobre uno del mismo nombre en el servidor; desactivado = no entra
            users = {name: {'hash': db_user['password_hash'], 'role': db_user['role'], 'name': db_user['display_name'],
                            'course': db_user['course'], 'parallel': db_user['parallel']}} if db_user['active'] else {}
            must_change = db_user['must_change_password']
        identity = accounts.authenticate_user(users, body.usuario, body.clave)
        with repo.transaction() as c:
            repo.audit(c, 'login_ok' if identity else 'login_failed', {'usuario': body.usuario.strip().lower()[:60], 'ip_hash': hashlib.sha256(ip.encode()).hexdigest()[:12]})
        if not identity: raise HTTPException(401, 'Usuario o contraseña incorrectos')
        if db_user: repo.touch_login(name)
        token, expires = accounts.issue_session(config.session_secret, identity, config.session_ttl_s)
        return {'token': token, 'expira': expires, 'usuario': identity['name'], 'role': identity['role'],
                'operador': identity['role'] in accounts.OPERATOR_ROLES, 'debe_cambiar_clave': must_change}

    @app.post('/api/v1/auth/change-password')
    def change_password(body: ChangePassword, identity=Depends(authenticate)):
        name = identity.get('user')
        record = repo.get_user(name) if name else None
        if not record: raise HTTPException(409, 'Este usuario se administra en el servidor; pide el cambio a la administración')
        if not accounts.verify_password(body.clave_actual, record['password_hash']): raise HTTPException(400, 'La contraseña actual no es correcta')
        if body.clave_nueva == body.clave_actual: raise HTTPException(422, 'La contraseña nueva debe ser distinta')
        repo.update_user(name, password_hash=accounts.hash_password(body.clave_nueva), must_change=False, by=name)
        return {'cambiada': True}

    # ================= Usuarios (administración) =================
    def temp_password(): return secrets.token_urlsafe(9)

    @app.get('/api/v1/admin/users')
    def list_users(identity=Depends(roles('admin'))):
        return {'usuarios': repo.list_users(), 'del_servidor': sorted(config.users)}

    @app.exception_handler(pg_errors.UndefinedTable)
    async def missing_table(request, exc):
        return JSONResponse({'detail': 'Falta migrar la base de datos (tabla de usuarios). Ejecuta scripts/supabase_migrate.sh'}, status_code=503)

    @app.post('/api/v1/admin/users', status_code=201)
    def create_user(body: UserCreate, identity=Depends(roles('admin'))):
        if body.rol == 'tutor' and not (body.curso and body.paralelo): raise HTTPException(422, 'El tutor necesita curso y paralelo')
        if body.usuario in config.users: raise HTTPException(409, 'Ese usuario ya existe en el servidor')
        password = body.clave or temp_password()
        ok = repo.create_user(body.usuario, accounts.hash_password(password), body.rol, body.nombre,
                              body.curso if body.rol == 'tutor' else None, body.paralelo if body.rol == 'tutor' else None,
                              identity.get('user') or 'admin', must_change=body.clave is None)
        if not ok: raise HTTPException(409, 'Ese usuario ya existe')
        return {'usuario': body.usuario, 'clave_temporal': password if body.clave is None else None}

    @app.patch('/api/v1/admin/users/{username}')
    def patch_user(username: str, body: UserPatch, identity=Depends(roles('admin'))):
        if body.activo is None and not body.restablecer_clave: raise HTTPException(422, 'Nada que cambiar')
        if username == identity.get('user') and body.activo is False: raise HTTPException(409, 'No puedes desactivar tu propio usuario')
        password = temp_password() if body.restablecer_clave else None
        if not repo.update_user(username, active=body.activo, password_hash=accounts.hash_password(password) if password else None,
                                must_change=True if password else None, by=identity.get('user') or 'admin'):
            raise HTTPException(404, 'Usuario no encontrado en la base (los del servidor se cambian en su configuración)')
        return {'usuario': username, 'clave_temporal': password}

    def engine_is_live():
        if engine is None: return False
        try: return engine.is_live()
        except EngineUnavailable: return False

    @app.get('/api/v1/me')
    def me(identity=Depends(authenticate)):
        record = repo.get_user(identity['user']) if identity.get('user') else None
        return {'role': identity['role'], 'name': identity.get('name'), 'usuario': identity.get('user'),
                'clave_editable': record is not None, 'debe_cambiar_clave': bool(record and record['must_change_password']),
                'course': identity.get('course'),
                'parallel': identity.get('parallel'), 'operador': identity['role'] in accounts.OPERATOR_ROLES,
                'motor_configurado': engine is not None, 'motor_vivo': engine_is_live()}

    # ================= Datos del colegio (modelo de referencia propio) =================
    @app.get('/api/v1/students')
    def students(identity=Depends(roles('admin', 'dece', 'tutor'))):
        if identity['role'] == 'tutor':
            rows = repo.students(identity['course'], identity['parallel'])
            fields = ('id', 'name', 'course', 'parallel', 'average', 'attendance', 'materia_critica', 'riskLabel', 'tiene_nee')
            return [{k: r.get(k) for k in fields} for r in rows]
        return for_role(identity['role'], repo.students())

    @app.get('/api/v1/summary')
    def summary(identity=Depends(roles('admin', 'dece', 'rectoria'))):
        with repo.transaction() as c:
            row = c.execute('SELECT * FROM paktai_edu.vista_kpi_rectoria').fetchone()
        return for_role(identity['role'], {'summary': row, 'model_status': 'reference_not_trained'})

    # ================= Modelos reales sobre los datos cargados =================
    VIEW = ('admin', 'rectoria', 'dece', 'tutor', 'inspeccion', 'colecturia')

    def cohort_and_model():
        model = repo.latest_model()
        if not model: raise HTTPException(409, 'Aún no hay datos cargados: el administrador debe subir los seis CSV')
        return model, repo.students()

    def in_scope(identity, row):
        return identity['role'] != 'tutor' or (norm_course(row.get('course')) == norm_course(identity['course'])
                                               and row.get('parallel') == identity['parallel'])

    # La ficha técnica del modelo (coeficientes, fórmula, límites) es para quien audita E-Pakty,
    # no para el colegio: un docente solo necesita el resultado y el porqué en palabras.
    @app.get('/api/v1/models/card')
    def model_card(identity=Depends(roles(*accounts.OPERATOR_ROLES))):
        model = repo.latest_model()
        if not model: raise HTTPException(409, 'Aún no hay modelo calculado')
        return models.model_card(model)

    @app.get('/api/v1/models/risk')
    def model_risk(identity=Depends(roles(*VIEW))):
        model, cohort = cohort_and_model()
        return models.risk_table(model, [r for r in cohort if in_scope(identity, r)], identity['role'])

    @app.get('/api/v1/models/explain/{student_id}')
    def model_explain(student_id: str, identity=Depends(roles(*VIEW))):
        model, cohort = cohort_and_model()
        row = next((r for r in cohort if r['id'] == student_id.upper() and in_scope(identity, r)), None)
        if not row: raise HTTPException(404, 'Estudiante no encontrado')
        return models.explain(model, row, cohort, identity['role'])

    @app.get('/api/v1/models/actions')
    def model_actions(identity=Depends(roles(*VIEW))):
        return [{'clave': k, 'nombre': v['nombre'], 'responsable': v['responsable'], 'supuesto': v['supuesto']}
                for k, v in models.allowed_actions(identity['role']).items()]

    @app.post('/api/v1/models/simulate/{student_id}')
    def model_simulate(student_id: str, body: SimulationRequest, identity=Depends(roles(*VIEW))):
        model, cohort = cohort_and_model()
        row = next((r for r in cohort if r['id'] == student_id.upper() and in_scope(identity, r)), None)
        if not row: raise HTTPException(404, 'Estudiante no encontrado')
        try: return models.simulate(model, row, cohort, body.acciones, identity['role'])
        except ValueError as error: raise HTTPException(422, str(error)) from None

    @app.get('/api/v1/models/provinces')
    def model_provinces(identity=Depends(roles(*VIEW))):
        return models.provinces()

    @app.get('/api/v1/models/territory')
    def model_territory(provincia: str, identity=Depends(roles('admin', 'rectoria', 'dece'))):
        model, cohort = cohort_and_model()
        try: return models.territory_adjusted(model, cohort, provincia)
        except KeyError: raise HTTPException(404, 'Provincia no encontrada') from None

    # ================= Estado de integraciones (administrador) =================
    @app.get('/api/v1/admin/status')
    async def admin_status(identity=Depends(roles('admin', 'epakti_ceo', 'epakti_mlops', 'epakti_ds', 'epakti_cs'))):
        def n8n_health():
            if not config.n8n_base_url: return {'estado': 'sin_configurar', 'detalle': 'Falta N8N_WEBHOOK_BASE_URL'}
            u = urlparse(config.n8n_base_url)
            try:
                r = httpx.get(f'{u.scheme}://{u.netloc}/healthz', timeout=3, follow_redirects=False)
                return {'estado': 'ok' if r.status_code == 200 else 'error', 'detalle': f'HTTP {r.status_code}'}
            except httpx.HTTPError as error:
                return {'estado': 'error', 'detalle': type(error).__name__}

        def engine_health():
            if engine is None: return {'estado': 'sin_configurar', 'detalle': 'Falta EPAKTI_ENGINE_BASE_URL'}
            try:
                r = engine.http.get(engine.base + '/health', timeout=3)
                mode = r.json().get('mode') if r.status_code == 200 else None
                return {'estado': 'ok' if r.status_code == 200 else 'error', 'detalle': mode or f'HTTP {r.status_code}',
                        'es_simulado': bool(mode and 'STUB' in mode.upper())}
            except (httpx.HTTPError, ValueError):
                return {'estado': 'error', 'detalle': 'No responde'}

        def collect():
            return {'run': repo.latest_run(), 'jobs': repo.recent_jobs(), 'audit': repo.recent_audit(), 'outbox': repo.outbox_stats(),
                    'modelo': repo.latest_model(), 'db': repo.health()}
        data = await run_in_threadpool(collect)
        n8n = await run_in_threadpool(n8n_health); motor = await run_in_threadpool(engine_health)
        model = data['modelo']
        pending = {(x['kind'], x['state']): x['n'] for x in data['outbox']['por_tipo_y_estado']}
        return {'entorno': config.environment, 'colegio': config.institution,
                'base_datos': {'estado': 'ok' if data['db']['ssl'] else 'error', 'tls': data['db']['tls_version']},
                'motor': motor, 'n8n': n8n,
                'firma_hmac_configurada': len(config.n8n_hmac_secret) >= 32,
                'cola_salida': {f'{k}:{s}': n for (k, s), n in pending.items()},
                'modelo': None if not model else {'version': model['version'], 'estado': model['status'], 'umbrales': model['thresholds']},
                'ultima_carga': data['run'], 'trabajos': data['jobs'], 'auditoria': data['audit'],
                'ingesta': data['outbox']['trabajos_ingesta']}

    # ================= Seguimiento en el tiempo (solo equipo pedagógico; nunca Colecturía ni Admisiones) =================
    SEGUIMIENTO = ('admin', 'rectoria', 'dece', 'tutor', 'inspeccion')

    async def _estudiante_visible(identity, student_id):
        student = await run_in_threadpool(repo.student, student_id.upper())
        if not student: raise HTTPException(404, 'Estudiante no encontrado')
        if identity['role'] == 'tutor' and (norm_course(student.get('course')) != norm_course(identity['course']) or student.get('parallel') != identity['parallel']):
            raise HTTPException(404, 'Estudiante no encontrado')
        return student

    @app.get('/api/v1/students/{student_id}/seguimiento')
    async def seguimiento_get(student_id: str, identity=Depends(roles(*SEGUIMIENTO))):
        await _estudiante_visible(identity, student_id)
        return {'estudiante': student_id.upper(), 'eventos': await run_in_threadpool(repo.timeline, student_id.upper())}

    @app.post('/api/v1/students/{student_id}/seguimiento', status_code=201)
    async def seguimiento_add(student_id: str, body: SeguimientoCreate, identity=Depends(roles(*SEGUIMIENTO))):
        await _estudiante_visible(identity, student_id)
        row = await run_in_threadpool(repo.add_followup, student_id.upper(), body.tipo, body.nota, identity.get('user') or identity['role'], identity['role'])
        return {'cuando': row['created_at'], 'tipo': row['tipo'], 'texto': row['nota'], 'autor': row['autor_usuario'], 'rol': row['autor_rol'], 'origen': 'nota'}

    async def _informe(identity, student_id):
        model, cohort = await run_in_threadpool(lambda: (repo.latest_model(), repo.students()))
        if not model: raise HTTPException(409, 'Aún no hay datos cargados: el administrador debe subir los seis CSV')
        row = next((r for r in cohort if r['id'] == student_id.upper() and in_scope(identity, r)), None)
        if not row: raise HTTPException(404, 'Estudiante no encontrado')
        etapa = next((e for e in (await run_in_threadpool(repo.etapas))['etapas'] if e['id_estudiante'] == row['id']), None)
        eventos = await run_in_threadpool(repo.timeline, row['id'])
        dias = await run_in_threadpool(repo.asistencia, row['id'])
        return informes.informe_estudiante(model, row, cohort, etapa, eventos, config.environment, dias)

    @app.get('/api/v1/students/{student_id}/informe')
    async def informe_estudiante(student_id: str, identity=Depends(roles(*SEGUIMIENTO))):
        """Informe de acompañamiento en lenguaje claro: quién es, qué problema tiene, por qué y cómo mitigarlo. Es pedagógico: sin pensiones."""
        data = await _informe(identity, student_id)
        with repo.transaction() as c: repo.audit(c, 'informe_estudiante', {'estudiante': data['estudiante']['id'], 'rol': identity['role']})
        return data

    @app.post('/api/v1/students/{student_id}/informe/redactar')
    async def informe_redactar(student_id: str, identity=Depends(roles(*SEGUIMIENTO))):
        """La IA (Nova Lite, vía n8n) reescribe el informe en palabras simples. No ve el nombre ni nada económico, y se descarta
        si inventa una cifra que no estaba en el informe. Si algo falla, el informe sigue con su texto normal."""
        if not config.n8n_base_url: raise HTTPException(503, 'La redacción con IA (n8n) aún no está configurada. El informe se ve igual con su texto normal.')
        data = await _informe(identity, student_id)
        entrada = informes.entrada_para_ia(data)
        raw = json.dumps({'informe': entrada}, ensure_ascii=False, separators=(',', ':')).encode()
        stamp = str(int(time.time()))
        h = {'Content-Type': 'application/json', 'X-Epakti-Timestamp': stamp, 'X-Epakti-Signature': 'sha256=' + hmac.new(config.n8n_hmac_secret.encode(), stamp.encode() + b'.' + raw, hashlib.sha256).hexdigest()}
        if os.getenv('N8N_WEBHOOK_TOKEN'): h['X-Epakti-Webhook-Token'] = os.environ['N8N_WEBHOOK_TOKEN']
        def llamar():
            with httpx.Client(timeout=40, follow_redirects=False) as c:
                return c.post(f"{config.n8n_base_url.rstrip('/')}/epakti-redactar-informe", content=raw, headers=h)
        try:
            r = await run_in_threadpool(llamar); r.raise_for_status(); out = r.json()
        except Exception:
            raise HTTPException(502, 'La IA no respondió ahora. Intenta de nuevo en un momento; el informe normal sigue disponible.')
        texto, error = informes.validar_redaccion(out, entrada)
        if error: raise HTTPException(502, 'La IA devolvió un texto que no pasó la revisión (' + error + '). Se muestra el informe normal.')
        with repo.transaction() as c: repo.audit(c, 'informe_redactado_ia', {'estudiante': data['estudiante']['id'], 'rol': identity['role']})
        return {'estudiante': data['estudiante']['id'], 'redaccion': texto, 'aviso': 'Redactado con IA a partir de los datos del informe; revísalo antes de compartirlo.'}

    @app.get('/api/v1/students/{student_id}/asistencia')
    async def asistencia_estudiante(student_id: str, identity=Depends(roles(*SEGUIMIENTO))):
        """Calendario de asistencia: cada día con su estado (presente, falta justificada, falta injustificada o atraso), tal como se cargó."""
        await _estudiante_visible(identity, student_id)
        dias = await run_in_threadpool(repo.asistencia, student_id.upper())
        return {'estudiante': student_id.upper(), 'dias': dias, 'resumen': informes.resumen_asistencia(dias)}

    @app.get('/api/v1/seguimiento/etapas')
    async def etapas_lista(identity=Depends(roles(*SEGUIMIENTO))):
        data = await run_in_threadpool(repo.etapas)
        if identity['role'] == 'tutor':   # el tutor ve solo su paralelo
            ids = {r['id'] for r in await run_in_threadpool(repo.students, identity['course'], identity['parallel'])}
            data['etapas'] = [e for e in data['etapas'] if e['id_estudiante'] in ids]
        return data

    @app.put('/api/v1/students/{student_id}/etapa')
    async def etapa_set(student_id: str, body: EtapaUpdate, identity=Depends(roles(*SEGUIMIENTO))):
        await _estudiante_visible(identity, student_id)
        if body.etapa == 'DOCENTE_AVISADO' and not config.n8n_base_url:
            raise HTTPException(503, 'El envío de correos (n8n) aún no está configurado: no se puede avisar al docente.')
        resumen = None
        if body.etapa == 'DOCENTE_AVISADO':
            try:
                inf = await _informe(identity, student_id)
                resumen = {'resumen': inf['resumen'], 'problemas': [{'titulo': p['titulo'], 'explicacion': p['explicacion']} for p in inf['problemas']],
                           'que_hacer': [{'accion': a['accion'], 'responsable': a['responsable'], 'cuando': a['cuando'], 'como': a['como'], 'baja_puntos': a['baja_puntos'], 'antes': a['antes'], 'despues': a['despues']}
                                         for a in inf['que_hacer'] if a['tiene_efecto']][:3], 'riesgo': inf['riesgo_pct'], 'promedio_colegio': inf['riesgo_promedio_colegio_pct']}
            except HTTPException: resumen = None
        row, error = await run_in_threadpool(repo.set_etapa, student_id.upper(), body.etapa, body.docente_nombre, body.docente_correo,
                                             identity.get('user') or identity['role'], identity['role'] in ('admin', 'dece', 'rectoria'), resumen)
        if error: raise HTTPException(403 if 'Solo' in error else 422, error)
        return row

    @app.get('/api/v1/seguimiento/recientes')
    async def seguimiento_recientes(identity=Depends(roles(*SEGUIMIENTO))):
        rows = await run_in_threadpool(repo.recent_followups)
        if identity['role'] == 'tutor':
            rows = [r for r in rows if norm_course(r.get('curso')) == norm_course(identity['course']) and r.get('paralelo') == identity['parallel']]
        return {'notas': rows}

    # ================= Análisis de evaluaciones: exámenes -> resultados por pregunta -> qué reforzar =================
    EVAL = ('admin', 'rectoria', 'dece', 'tutor')
    MAX_FOTOS, MAX_FOTO_BYTES = 4, 2_500_000
    FIRMAS = ((b'\xff\xd8\xff', 'image/jpeg'), (b'\x89PNG\r\n\x1a\n', 'image/png'))

    def _mime(data):
        for sig, mime in FIRMAS:
            if data.startswith(sig): return mime
        return 'image/webp' if data[:4] == b'RIFF' and data[8:12] == b'WEBP' else None

    def _datos_eval(identity, titulo, materia, curso, paralelo, fecha):
        titulo, materia = (titulo or '').strip(), (materia or '').strip()
        if identity['role'] == 'tutor': curso, paralelo = identity['course'], identity['parallel']   # el tutor no elige el curso
        curso, paralelo = (curso or '').strip(), (paralelo or '').strip().upper()
        if len(titulo) < 3 or len(materia) < 2 or not curso or not re.fullmatch(r'[A-Z]{1,2}', paralelo):
            raise HTTPException(422, 'Completa título, materia, curso y paralelo (una letra).')
        if len(titulo) > 120 or len(materia) > 80 or len(curso) > 40: raise HTTPException(422, 'Algún texto es demasiado largo.')
        if fecha and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', fecha): raise HTTPException(422, 'La fecha debe ser AAAA-MM-DD.')
        return {'titulo': titulo, 'materia': materia, 'curso': curso, 'paralelo': paralelo, 'fecha': fecha or None}

    async def _eval_visible(identity, eid):
        ev = await run_in_threadpool(repo.evaluacion, eid)
        if not ev: raise HTTPException(404, 'Evaluación no encontrada')
        if identity['role'] == 'tutor' and (norm_course(ev['curso']) != norm_course(identity['course']) or ev['paralelo'] != identity['parallel']):
            raise HTTPException(404, 'Evaluación no encontrada')
        return ev

    @app.post('/api/v1/evaluaciones', status_code=202)
    async def evaluacion_fotos(titulo: str = Form(...), materia: str = Form(...), curso: str = Form(''), paralelo: str = Form(''), fecha: str = Form(''),
                               files: list[UploadFile] = File(...), identity=Depends(roles(*EVAL))):
        d = _datos_eval(identity, titulo, materia, curso, paralelo, fecha)
        if not config.n8n_base_url: raise HTTPException(503, 'El lector de exámenes (n8n) aún no está configurado. Puedes cargar los resultados por CSV.')
        if not 1 <= len(files) <= MAX_FOTOS: raise HTTPException(422, f'Sube de 1 a {MAX_FOTOS} fotos por evaluación.')
        imgs = []
        for f in files:
            data = await f.read(MAX_FOTO_BYTES + 1)
            if len(data) > MAX_FOTO_BYTES: raise HTTPException(413, 'Una foto pesa más de 2,5 MB. Reduce su tamaño.')
            mime = _mime(data)
            if not mime: raise HTTPException(415, 'Solo se aceptan fotos JPG, PNG o WEBP.')
            imgs.append({'mime': mime, 'b64': base64.b64encode(data).decode()})
        eid = await run_in_threadpool(repo.create_evaluacion, d, identity.get('user') or identity['role'], 'FOTOS', imgs)
        return {'id': eid, 'estado': 'PROCESANDO', 'hojas': len(imgs)}

    @app.post('/api/v1/evaluaciones/csv', status_code=201)
    async def evaluacion_csv(titulo: str = Form(...), materia: str = Form(...), curso: str = Form(''), paralelo: str = Form(''), fecha: str = Form(''),
                             file: UploadFile = File(...), identity=Depends(roles(*EVAL))):
        d = _datos_eval(identity, titulo, materia, curso, paralelo, fecha)
        raw = await file.read(2_000_001)
        if len(raw) > 2_000_000: raise HTTPException(413, 'El archivo supera 2 MB.')
        try: rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
        except (UnicodeDecodeError, csv.Error): raise HTTPException(422, 'El archivo debe ser un CSV en UTF-8.') from None
        if not rows or len(rows) > 20000: raise HTTPException(422, 'El CSV está vacío o tiene demasiadas filas (máximo 20.000).')
        si = {'1', 'si', 'sí', 's', 'true', 'x', 'correcta', 'ok'}; no = {'0', 'no', 'n', 'false', 'incorrecta'}
        hojas = {}
        for n, r in enumerate(rows, 2):
            r = {(k or '').strip().lower(): (v or '').strip() for k, v in r.items()}
            try:
                preg = int(r.get('pregunta', ''))
                code = r.get('codigo_estudiante') or r.get('codigo') or ''
                hoja = hojas.setdefault(code or r.get('hoja') or '1', {'codigo': code or None, 'respuestas': []})
                resp = {'pregunta': preg}
                cor = r.get('correcta', '').lower()
                if cor:
                    if cor not in si | no: raise ValueError('correcta no válida')
                    resp['correcta'] = cor in si
                elif r.get('puntaje'):
                    resp['puntaje'] = float(r['puntaje'].replace(',', '.')); resp['puntaje_max'] = float((r.get('puntaje_max') or '1').replace(',', '.'))
                else: raise ValueError('sin resultado')
                hoja['respuestas'].append(resp)
            except (ValueError, TypeError):
                raise HTTPException(422, f'Fila {n}: revisa «pregunta» (número) y «correcta» (1/0) o «puntaje» y «puntaje_max».') from None
        try: modelo = ResultadoExamen.model_validate({'hojas': list(hojas.values())})
        except ValidationError as error:
            raise HTTPException(422, [{'campo': '.'.join(map(str, e['loc'])), 'error': e['msg']} for e in error.errors()[:5]]) from None
        user = identity.get('user') or identity['role']
        eid = await run_in_threadpool(repo.create_evaluacion, d, user, 'CSV', None)
        await run_in_threadpool(repo.save_resultados, eid, [h.model_dump() for h in modelo.hojas], user)
        return {'id': eid, 'estado': 'POR_REVISAR', 'hojas': len(modelo.hojas)}

    @app.post('/api/v1/evaluaciones/{eid}/resultado')
    async def evaluacion_resultado(eid: UUID, body: ResultadoExamen, identity=Depends(roles('worker', 'n8n_callback'))):
        """Callback del lector de exámenes (n8n). Las respuestas quedan «por revisar»: una persona las corrige y confirma."""
        if body.error or not body.hojas:
            await run_in_threadpool(repo.evaluacion_error, str(eid), body.error or 'El lector no encontró respuestas en las fotos. Prueba con fotos más nítidas o carga un CSV.')
            return {'guardado': False}
        ok = await run_in_threadpool(repo.save_resultados, str(eid), [h.model_dump() for h in body.hojas], 'lector-n8n')
        if not ok: raise HTTPException(409, 'Evaluación inexistente o ya confirmada')
        return {'guardado': True, 'revision_humana_requerida': True}

    @app.get('/api/v1/evaluaciones')
    async def evaluaciones_lista(identity=Depends(roles(*EVAL))):
        tutor = identity['role'] == 'tutor'
        return {'evaluaciones': await run_in_threadpool(repo.list_evaluaciones, identity.get('course') if tutor else None, identity.get('parallel') if tutor else None)}

    @app.get('/api/v1/evaluaciones/{eid}')
    async def evaluacion_detalle(eid: UUID, identity=Depends(roles(*EVAL))):
        await _eval_visible(identity, str(eid))
        return await run_in_threadpool(repo.evaluacion_detalle, str(eid))

    @app.patch('/api/v1/evaluaciones/{eid}/temas')
    async def evaluacion_temas(eid: UUID, body: TemasExamen, identity=Depends(roles(*EVAL))):
        ev = await _eval_visible(identity, str(eid))
        if ev['estado'] == 'CONFIRMADA': raise HTTPException(409, 'La evaluación ya está confirmada')
        if any(not k.isdigit() or len(v) > 80 for k, v in body.temas.items()): raise HTTPException(422, 'Tema o número de pregunta no válido')
        await run_in_threadpool(repo.set_temas, str(eid), body.temas)
        return {'guardado': True}

    @app.post('/api/v1/evaluaciones/{eid}/confirmar')
    async def evaluacion_confirmar(eid: UUID, identity=Depends(roles(*EVAL))):
        await _eval_visible(identity, str(eid))
        if not await run_in_threadpool(repo.confirm_evaluacion, str(eid), identity.get('user') or identity['role']):
            raise HTTPException(409, 'Solo se confirma una evaluación que esté por revisar')
        return {'estado': 'CONFIRMADA'}

    @app.get('/api/v1/admin/engine-check')
    async def engine_check(identity=Depends(roles('admin', 'epakti_ceo', 'epakti_mlops', 'epakti_ds', 'epakti_cs'))):
        """Prueba, ahora mismo, cada ruta del motor de Wilo y dice qué responde, qué falta y por qué. No modifica nada."""
        started = time.monotonic()
        if engine is None:
            return {'motor': {'estado': 'sin_configurar', 'detalle': 'Falta EPAKTI_ENGINE_BASE_URL'}, 'rutas': [], 'ms': 0}
        def health():
            try:
                r = engine.http.get(engine.base.rsplit('/api/', 1)[0] + '/health', timeout=4)
                j = r.json() if r.status_code == 200 else {}
                return {'estado': 'ok' if r.status_code == 200 else 'error', 'detalle': j.get('mode') or f'HTTP {r.status_code}',
                        'modelos': j.get('models') or j.get('modelos')}
            except (httpx.HTTPError, ValueError):
                return {'estado': 'no_disponible', 'detalle': 'No responde (¿túnel apagado?)'}
        motor = await run_in_threadpool(health)
        codigo = next(iter(await run_in_threadpool(repo.student_ids)), None) if motor['estado'] == 'ok' else None
        def probe(item):
            ep, method, path, role, servicio, extra = item
            base = {'ep': ep, 'metodo': method, 'ruta': path, 'rol_prueba': role, 'servicio': servicio}
            if extra == 'no_probado':
                return {**base, 'estado': 'no_probado', 'detalle': 'Escribe datos: se prueba con una carga o un caso reales'}
            if motor['estado'] != 'ok':
                return {**base, 'estado': 'no_disponible', 'detalle': 'El motor no responde'}
            if '{codigo}' in path:
                if not codigo: return {**base, 'estado': 'no_probado', 'detalle': 'Aún no hay estudiantes cargados'}
                path = path.format(codigo=codigo)
            t0 = time.monotonic()
            try:
                status, body = engine.request(method, path, role, json=extra if isinstance(extra, dict) else None)
            except EngineUnavailable as error:
                return {**base, 'estado': 'error', 'detalle': str(error), 'ms': round((time.monotonic() - t0) * 1000)}
            ms = round((time.monotonic() - t0) * 1000)
            code = (body.get('code') or body.get('detail') or '') if isinstance(body, dict) else ''
            if status < 300: return {**base, 'estado': 'ok', 'http': status, 'ms': ms, 'detalle': 'Responde'}
            if status == 404 and 'NOT_INGESTED' in str(code).upper(): return {**base, 'estado': 'sin_datos', 'http': status, 'ms': ms, 'detalle': 'Conectado; falta cargar los datos del colegio'}
            if status == 401: return {**base, 'estado': 'clave_invalida', 'http': status, 'ms': ms, 'detalle': 'El motor rechazó la clave (EPAKTI_ENGINE_API_KEY)'}
            if status == 403: return {**base, 'estado': 'sin_permiso', 'http': status, 'ms': ms, 'detalle': 'El motor rechazó el rol de prueba'}
            return {**base, 'estado': 'error', 'http': status, 'ms': ms, 'detalle': str(code)[:120] or 'El motor rechazó la solicitud'}
        rutas = await asyncio.gather(*[run_in_threadpool(probe, it) for it in ENGINE_PROBES])
        with repo.transaction() as c: repo.audit(c, 'engine_check', {'por': identity.get('user') or identity['role'], 'motor': motor['estado']})
        return {'motor': motor, 'colegio_motor': config.engine_school_id, 'rutas': list(rutas), 'ms': round((time.monotonic() - started) * 1000)}

    # ================= Ingesta asíncrona: EP-02, EP-02B y subida de CSV =================
    def accepted(job_id, created):
        return {'status': 'ACCEPTED_ASYNC', 'job_id': job_id, 'poll_url': f'/api/v1/ingestion/jobs/{job_id}', 'nuevo': created}

    @app.post('/api/v1/ingestion/batch-sync', status_code=202)                                          # EP-02
    def batch_sync(body: BatchSync, idempotency_key: str = Header(default='', alias='Idempotency-Key'),
                   identity=Depends(roles('rectoria', 'admin', 'worker', 'epakti_mlops'))):
        if not IDEMPOTENCY.match(idempotency_key):
            raise HTTPException(428, 'Falta la cabecera Idempotency-Key (8 a 100 caracteres: letras, números, _ . : -)')
        if set(body.tablas) != set(TABLES): raise HTTPException(422, 'Se requieren las seis tablas oficiales')
        if any(not rows for rows in body.tablas.values()): raise HTTPException(422, 'Hay tablas vacías')
        job_id, created = repo.create_job('sync:' + idempotency_key, 'json', {'formato': 'json', 'tablas': body.tablas}, {})
        return accepted(job_id, created)

    @app.post('/api/v1/pipeline/batch', status_code=202)
    async def batch(files: list[UploadFile] = File(...), synthetic_declaration: bool = Form(...), identity=Depends(roles('admin'))):
        if synthetic_declaration is not True: raise HTTPException(422, 'El hackathon solo permite datos sintéticos declarados')
        names = [f.filename for f in files]
        if len(names) != 6 or set(names) != {t + '.csv' for t in TABLES}:
            raise HTTPException(422, 'Se requieren exactamente los seis CSV oficiales')
        archivos, hashes, total = {}, {}, 0
        for upload in files:
            data = b''
            while chunk := await upload.read(65536):
                total += len(chunk)
                if total > config.max_upload_bytes: raise HTTPException(413, 'Lote demasiado grande')
                data += chunk
            try: archivos[upload.filename] = data.decode('utf-8-sig')
            except UnicodeDecodeError: raise HTTPException(422, f'{upload.filename}: el archivo debe estar en UTF-8') from None
            hashes[upload.filename] = hashlib.sha256(data).hexdigest()
        key = 'csv:' + hashlib.sha256(''.join(hashes[k] for k in sorted(hashes)).encode()).hexdigest()
        job_id, created = await run_in_threadpool(repo.create_job, key, 'csv', {'formato': 'csv', 'archivos': archivos}, hashes)
        return accepted(job_id, created)

    @app.get('/api/v1/ingestion/jobs/{job_id}')                                                         # EP-02B
    def job_status(job_id: str, identity=Depends(roles('rectoria', 'admin', 'worker', 'epakti_mlops'))):
        job = repo.job(job_id)
        if not job: raise HTTPException(404, 'Trabajo no encontrado')
        return job

    @app.post('/api/v1/ingestion/jobs/{job_id}/retry', status_code=202)
    def job_retry(job_id: str, identity=Depends(roles('rectoria', 'admin', 'epakti_mlops'))):
        if not repo.retry_job(job_id, identity['role']):
            raise HTTPException(409, 'Solo se reintentan trabajos fallidos que conservan sus datos')
        return accepted(job_id, False)

    # ================= Casos, borradores y aprobación humana =================
    @app.post('/api/v1/intervene/{student_id}', status_code=202)
    def intervene(student_id: str, identity=Depends(roles('admin', 'dece'))):
        result = repo.intervene(student_id)
        if not result: raise HTTPException(404, 'Estudiante no encontrado')
        return result

    @app.post('/api/v1/interventions/{case_id}/claim')
    def claim(case_id: UUID, identity=Depends(roles('worker'))):
        return repo.claim_draft(case_id)

    @app.post('/api/v1/interventions/{case_id}/draft')
    def draft(case_id: UUID, body: DraftCallback, identity=Depends(roles('worker'))):
        case = repo.case(case_id)
        if not case: raise HTTPException(404, 'Caso no encontrado')
        student = repo.student(case['id_estudiante'])
        return {'stored': repo.complete_draft(case_id, enforce_draft(body.draft, student), body.lease_token), 'human_review_required': True}

    @app.get('/api/v1/interventions')
    def list_cases(identity=Depends(roles('admin', 'dece'))):
        return repo.list_cases()

    @app.patch('/api/v1/interventions/{case_id}/draft')
    def edit_draft(case_id: UUID, body: DraftEdit, identity=Depends(roles('admin', 'dece'))):
        # La persona puede corregir el texto antes de aprobarlo; el resto del borrador no cambia.
        if not repo.edit_draft_message(case_id, body.mensaje_representante, identity['role']):
            raise HTTPException(409, 'Caso sin borrador, ya aprobado para envío o cerrado')
        return {'updated': True, 'human_review_required': True}

    @app.get('/api/v1/interventions/{case_id}')
    def get_case(case_id: UUID, identity=Depends(roles('admin', 'dece'))):
        case = repo.case(case_id)
        if not case: raise HTTPException(404, 'Caso no encontrado')
        return case

    @app.patch('/api/v1/interventions/{case_id}')
    def update(case_id: UUID, body: StateUpdate, identity=Depends(roles('admin', 'dece'))):
        if not repo.update_case(case_id, body.estado_caso): raise HTTPException(409, 'Caso inexistente o ya cerrado')
        return {'updated': True}

    @app.post('/api/v1/interventions/{case_id}/approve-delivery', status_code=202)
    def delivery(case_id: UUID, body: DeliveryRequest, identity=Depends(roles('admin', 'dece'))):
        case = repo.case(case_id)
        if not case or not case['agent']: raise HTTPException(409, 'Caso sin borrador')
        if case['estado_caso'] not in ('ABIERTA', 'EN_SEGUIMIENTO'): raise HTTPException(409, 'Caso cerrado')
        try: destination = recipient_for(body.channel, body.recipient, config.environment)
        except DeliveryConfigurationError as error: raise HTTPException(422, str(error)) from None
        with repo.transaction() as c:
            created = repo.enqueue(c, 'delivery:' + str(case_id), body.channel.upper(),
                                   {'case_id': str(case_id), 'recipient': destination, 'message': case['agent']['mensaje_representante'],
                                    'environment': config.environment})
            repo.audit(c, 'delivery_approved', {'case_id': str(case_id), 'role': identity['role'], 'channel': body.channel})
        return {'queued': bool(created), 'environment': config.environment}

    @app.post('/api/v1/interventions/log-outcome', status_code=201)                                     # EP-11
    def log_outcome(body: OutcomeLog, identity=Depends(roles('tutor', 'dece', 'inspeccion', 'colecturia', 'n8n_callback', 'admin', 'rectoria'))):
        student = repo.student(body.codigo_estudiante)
        if not student: raise HTTPException(404, 'Estudiante no encontrado')
        if identity['role'] == 'tutor' and (norm_course(student.get('course')) != norm_course(identity['course'])
                                            or student.get('parallel') != identity['parallel']):
            raise HTTPException(404, 'Estudiante no encontrado')
        return repo.log_outcome(body, identity['role'])

    @app.post('/api/v1/workflow-errors', status_code=202)
    def workflow_error(body: WorkflowError, identity=Depends(roles('worker'))):
        with repo.transaction() as c:
            repo.audit(c, 'n8n_error', body.model_dump())
            repo.enqueue(c, 'error:' + body.workflow_id + ':' + body.execution_id, 'ADMIN', body.model_dump())
        return {'recorded': True}

    # ================= EP-19: formulario público de contacto =================
    hits = defaultdict(deque)

    def client_ip(request: Request):
        forwarded = request.headers.get('x-forwarded-for', '')
        if config.trust_proxy_headers and forwarded:
            return forwarded.split(',')[0].strip()
        return request.client.host if request.client else 'desconocido'

    @app.post('/api/v1/public/contact-lead', status_code=201)
    def contact_lead(body: ContactLead, request: Request):
        ip = client_ip(request); now = time.monotonic(); window = hits[ip]
        while window and now - window[0] > 60: window.popleft()
        if len(window) >= config.contact_rate_limit:
            raise HTTPException(429, 'Demasiadas solicitudes; intenta en un minuto')
        window.append(now)
        if body.sitio_web:   # trampa para bots: se responde igual, pero no se guarda nada
            return {'recibido': True}
        return {'recibido': True, 'lead_id': repo.contact_lead(body)}

    # ================= Motor predictivo (contrato v2.1) =================
    async def call_engine(method, path, identity, *, json=None, params=None):
        if engine is None:
            raise HTTPException(503, 'Motor no configurado (EPAKTI_ENGINE_BASE_URL)')
        role = identity['role']
        # En el motor, admin equivale a rectorado; para leer los tableros internos va como CEO, solo lectura.
        if role == 'admin' and method == 'GET' and path.startswith('/admin/'): role = 'epakti_ceo'
        try:
            status, body = await run_in_threadpool(engine.request, method, path, role, json=json, params=params)
        except EngineUnavailable:
            raise HTTPException(503, 'El motor no está disponible en este momento') from None
        if status >= 400:
            detail = body.get('detail') if isinstance(body, dict) else None
            raise HTTPException(status, detail or 'El motor rechazó la solicitud')
        return status, body

    def shape(identity, body, path):
        body = for_role(identity['role'], body)
        if identity['role'] == 'colecturia' and 'admissions' in path and isinstance(body, dict):
            body = {k: v for k, v in body.items() if 'pedagog' not in k}   # colecturía no ve lo pedagógico
        if identity['role'] == 'tutor':
            body = scope_students(body, identity['course'], identity['parallel'])
        return body

    def make_proxy(method, route, allowed):
        engine_path = route.removeprefix('/api/v1')

        async def proxy(request: Request, identity=Depends(roles(*allowed))):
            path = engine_path.format(**request.path_params)
            if identity['role'] == 'tutor' and '{codigo}' in route:
                student = await run_in_threadpool(repo.student, request.path_params['codigo'].upper())
                if not student or norm_course(student.get('course')) != norm_course(identity['course']) or student.get('parallel') != identity['parallel']:
                    raise HTTPException(404, 'Estudiante no encontrado')
            payload = None
            if method in ('POST', 'PATCH'):
                raw = await request.body()
                if len(raw) > MAX_ENGINE_BODY: raise HTTPException(413, 'Solicitud demasiado grande')
                try: payload = (await request.json()) if raw else {}
                except ValueError: raise HTTPException(422, 'JSON inválido') from None
                if route.endswith('/onboard'):
                    try: payload = Onboard.model_validate(payload).model_dump()
                    except ValidationError as error:
                        raise HTTPException(422, [{'campo': '.'.join(map(str, e['loc'])), 'error': e['msg']} for e in error.errors()]) from None
            params = {k: v for k, v in request.query_params.items() if k in QUERY_PASSTHROUGH}
            if identity['role'] == 'tutor':   # el tutor no elige curso: se descarta el filtro del navegador y abajo se recorta a su paralelo
                params.pop('curso', None); params.pop('paralelo', None)
            status, body = await call_engine(method, path, identity, json=payload, params=params)
            if method != 'GET':
                with repo.transaction() as c: repo.audit(c, 'engine_' + method.lower(), {'route': route, 'role': identity['role'], 'status': status})
            return shape(identity, body, route)
        proxy.__name__ = 'motor_' + re.sub(r'\W+', '_', route)
        app.add_api_route(route, proxy, methods=[method])

    for method, route, allowed in ENGINE_ROUTES:
        make_proxy(method, route, allowed)

    @app.post('/api/v1/n8n/dispatch-alerts', status_code=202)                                           # EP-10
    async def dispatch(body: DispatchRequest, identity=Depends(roles('admin', 'rectoria', 'dece', 'colecturia'))):
        status, result = await call_engine('POST', '/n8n/dispatch-alerts', identity, json=body.model_dump())
        with repo.transaction() as c: repo.audit(c, 'alerts_360_dispatched', {'cupo': body.cupo, 'role': identity['role']})
        return for_role(identity['role'], result)

    @app.get('/api/v1/admin/n8n/observability')                                                         # EP-18
    async def n8n_observability(identity=Depends(roles('admin', 'epakti_mlops', 'epakti_cs', 'epakti_ceo'))):
        _, body = await call_engine('GET', '/admin/n8n/observability', identity)
        return {'motor': body, 'backend': await run_in_threadpool(repo.outbox_stats),
                'n8n_configurado': bool(config.n8n_base_url)}

    @app.post('/api/v1/admin/outbox/{event_id}/retry', status_code=202)
    def outbox_retry(event_id: UUID, identity=Depends(roles('epakti_mlops', 'epakti_cs', 'admin'))):
        if not repo.retry_outbox(event_id, identity['role']): raise HTTPException(409, 'Solo se reintentan envíos fallidos')
        return {'reintentado': True}
    return app


app = create_app()
