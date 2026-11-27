"""Worker en segundo plano. Nada de esto bloquea una petición del usuario.

1. Ingesta asíncrona (EP-02): procesa los trabajos en cola. Llama al motor con timeout de 5 s, hasta 3 intentos
   con espera exponencial + jitter (2 s → 4 s → 8 s). Si no lo logra, el trabajo queda en DEAD_LETTER y se puede
   reintentar sin duplicar nada (la carga es idempotente).
2. Cola de salida (outbox): entrega a n8n con firma HMAC. El correo, WhatsApp y Bedrock viven solo en n8n.
3. Purga LOPDP diaria de datos personales vencidos.
"""
import csv
import hashlib
import hmac
import io
import json
import logging
import os
import random
import tempfile
import time
from pathlib import Path

from dotenv import load_dotenv

from .config import Settings
from .delivery import tls_client, recipient_for
from .engine import EngineClient, EngineUnavailable
from .repository import Repository
from .validation import validate_source, DataValidationError

log = logging.getLogger('paktai')
# Webhook de n8n para cada tipo de evento.
WEBHOOKS = {'N8N': 'paktai-alerta', 'EMAIL': 'epakti-entrega-familia', 'WHATSAPP': 'epakti-entrega-familia',
            'ADMIN': 'epakti-errores', 'LEAD': 'epakti-contacto-lead', 'EXAMEN': 'epakti-examen-ocr', 'AVISO_DOCENTE': 'epakti-aviso-docente'}
OUTBOX_MAX_ATTEMPTS = 6           # 30 s, 1 min, 2 min, 4 min, 8 min: aguanta una caída corta de n8n
OUTBOX_BACKOFF_BASE_S = 30
NUMERIC_FOR_ENGINE = ('attendance', 'unjustifiedAbsence', 'justifiedAbsence', 'late', 'racha_faltas_injustificadas',
                      'average', 'gradeSlope', 'lowGrades', 'mathAverage', 'promedio_z_paralelo', 'overdueMonths',
                      'latePayments', 'debt', 'tiene_nee', 'rezago_edad', 'transicion_critica')


class Permanent(Exception):
    """Error que no se arregla reintentando."""


def sign(secret: str, body: bytes, timestamp: str) -> str:
    """Firma que n8n verifica: HMAC-SHA256 de «timestamp.cuerpo». El timestamp evita reenvíos viejos."""
    return 'sha256=' + hmac.new(secret.encode(), timestamp.encode() + b'.' + body, hashlib.sha256).hexdigest()


def backoff(base_s: float, attempt: int) -> float:
    return base_s * (2 ** (attempt - 1)) * random.uniform(0.8, 1.2)


def _strip_names(content: bytes) -> bytes:
    """LOPDP: al motor no viajan nombres. Se quita la columna nombre_ficticio de estudiantes (el motor trabaja con el código)."""
    rows = list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
    if not rows or 'nombre_ficticio' not in rows[0]:
        return content
    columns = [c for c in rows[0] if c != 'nombre_ficticio']
    out = io.StringIO(); writer = csv.DictWriter(out, fieldnames=columns, extrasaction='ignore', lineterminator='\n')
    writer.writeheader(); writer.writerows(rows)
    return out.getvalue().encode('utf-8')


def push_to_engine(engine, settings, files, job_id, silver, poll_s=2, max_wait_s=120):
    """Entrega la carga al motor. Motor en vivo de Wilo: sube los seis CSV y espera su trabajo (EP-02C + EP-02B).
    Stub del contrato (desarrollo): envía solo el seudónimo y variables numéricas por JSON (EP-02)."""
    if not engine.is_live():
        features = [{'student_pseudonym_id': r['id'], **{k: r.get(k) for k in NUMERIC_FOR_ENGINE if isinstance(r.get(k), (int, float))}}
                    for r in silver['students']]
        status, body = engine.request('POST', '/ingestion/batch-sync', 'worker', headers={'Idempotency-Key': job_id},
                                      json={'school_id': settings.institution, 'estudiantes': features})
        if status >= 400:
            raise Permanent(f'El motor rechazó la carga (HTTP {status})')
        return {'job_id': body.get('job_id'), 'status': body.get('status'), 'poll_url': body.get('poll_url')}
    upload = {name: (_strip_names(content) if name == 'estudiantes' else content) for name, content in files.items()}
    data = {'school_id': engine.school_id or settings.institution, 'nombre': settings.engine_school_name,
            'dpa_parroquia_plantel': settings.engine_school_dpa, 'regimen': settings.engine_school_regime,
            'fecha_corte': settings.engine_cutoff}
    status, body = engine.upload_csv('worker', upload, data, idempotency_key=job_id)
    if status >= 400:
        raise Permanent(f'El motor rechazó la carga (HTTP {status}): {str(body.get("detail") or body)[:200]}')
    engine_job = body.get('job_id') or job_id
    deadline = time.monotonic() + max_wait_s
    while time.monotonic() < deadline:
        status, job = engine.request('GET', f'/ingestion/jobs/{engine_job}', 'worker')
        state = (job or {}).get('status')
        if state == 'COMPLETED':
            return {'job_id': engine_job, 'status': state, 'estudiantes_procesados': job.get('estudiantes_procesados'),
                    'estudiantes_rechazados': job.get('estudiantes_rechazados')}
        if state in ('FAILED', 'DEAD_LETTER'):
            raise Permanent(f'El motor no pudo procesar la carga: {str(job.get("error") or job)[:200]}')
        time.sleep(poll_s)
    raise EngineUnavailable('El motor tardó más de lo esperado')


# ================= Cola de salida =================
def tick(repo, client, engine=None):
    s = repo.settings
    with repo.transaction() as c:
        # Un envío interrumpido se reintenta: todos los destinos reciben Idempotency-Key.
        c.execute("UPDATE paktai_edu.outbox SET state='PENDING' WHERE state='SENDING' AND locked_at<now()-interval '5 minutes'")
        # Sin n8n (o sin motor) configurado, esos eventos esperan en la cola sin gastar reintentos.
        event = c.execute("""SELECT * FROM paktai_edu.outbox WHERE state='PENDING' AND available_at<=now()
             AND ((kind='ENGINE_OUTCOME' AND %s) OR (kind<>'ENGINE_OUTCOME' AND %s))
             ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1""", (engine is not None, bool(s.n8n_base_url))).fetchone()
        if not event:
            return False
        c.execute("UPDATE paktai_edu.outbox SET state='SENDING',locked_at=now(),attempts=attempts+1 WHERE id=%s", (event['id'],))
    status = None; state = 'SENT'; attempt = event['attempts'] + 1; kind = event['kind']; payload = event['payload']
    try:
        if kind == 'ENGINE_OUTCOME':
            if engine is None:
                raise Permanent('Motor no configurado')
            status, _ = engine.request('POST', '/interventions/log-outcome', 'worker', json=payload,
                                       headers={'Idempotency-Key': event['event_key']})
            if status >= 400:
                raise Permanent(f'El motor rechazó el registro (HTTP {status})')
        else:
            hook = WEBHOOKS.get(kind)
            if hook is None:
                raise Permanent('Tipo desconocido')
            if not s.n8n_base_url:
                raise ValueError('n8n sin configurar')
            if kind == 'AVISO_DOCENTE':
                if payload.get('environment') != s.environment:
                    raise Permanent('Cambio de entorno; requiere nuevo aviso')
                body = {**{k: v for k, v in payload.items() if k != 'recipient'}, 'destinatario': recipient_for('email', payload['recipient'], s.environment)}
            elif kind in ('EMAIL', 'WHATSAPP'):
                if payload.get('environment') != s.environment:
                    raise Permanent('Cambio de entorno; requiere nueva revisión')
                body = {'canal': kind.lower(), **payload,
                        'destinatario': recipient_for(kind.lower(), payload['recipient'], s.environment)}
            else:
                body = payload
            raw = json.dumps(body, ensure_ascii=False, separators=(',', ':'), default=str).encode()
            stamp = str(int(time.time()))
            headers = {'Content-Type': 'application/json', 'Idempotency-Key': event['event_key'],
                       'X-Epakti-Timestamp': stamp, 'X-Epakti-Signature': sign(s.n8n_hmac_secret, raw, stamp)}
            if os.getenv('N8N_WEBHOOK_TOKEN'):   # n8n con «Header Auth» en el webhook (n8n no puede leer variables de entorno en Code)
                headers['X-Epakti-Webhook-Token'] = os.environ['N8N_WEBHOOK_TOKEN']
            response = client.post(f"{s.n8n_base_url.rstrip('/')}/{hook}", content=raw, headers=headers)
            status = response.status_code
            if 300 <= status < 400:
                raise Permanent('Redirección rechazada')
            response.raise_for_status()
    except Permanent:
        state = 'FAILED'
    except Exception:
        definitive = status is not None and 400 <= status < 500 and status != 429
        state = 'FAILED' if definitive or attempt >= OUTBOX_MAX_ATTEMPTS else 'PENDING'
    delay = backoff(OUTBOX_BACKOFF_BASE_S, attempt) if state == 'PENDING' else 0
    with repo.transaction() as c:
        c.execute("""UPDATE paktai_edu.outbox SET state=%s,last_status=%s,available_at=now()+(%s * interval '1 second') WHERE id=%s""",
                  (state, status, delay, event['id']))
        repo.audit(c, 'outbox_attempt', {'event_id': str(event['id']), 'kind': kind, 'state': state, 'attempt': attempt, 'http_status': status})
        if state == 'SENT' and kind in ('EMAIL', 'WHATSAPP'):
            c.execute("UPDATE paktai_edu.intervenciones_dece SET delivery_state='ENVIADA' WHERE id=%s", (payload['case_id'],))
        if kind == 'EXAMEN' and state in ('SENT', 'FAILED'):   # la foto no se conserva: se borra del registro apenas se entrega o se rinde
            c.execute("UPDATE paktai_edu.outbox SET payload=jsonb_build_object('evaluacion_id',payload->>'evaluacion_id') WHERE id=%s", (event['id'],))
        if kind == 'EXAMEN' and state == 'FAILED':
            c.execute("UPDATE paktai_edu.evaluaciones SET estado='ERROR',error=%s,updated_at=now() WHERE id=%s AND estado='PROCESANDO'",
                      ('No se pudo enviar al lector de exámenes (n8n). Revisa Integraciones y vuelve a subir.', payload['evaluacion_id']))
        if state == 'SENT' and kind == 'LEAD':
            c.execute('UPDATE paktai_edu.public_contact_leads SET n8n_dispatched=true WHERE id=%s', (payload['lead_id'],))
    log.info(json.dumps({'event': 'outbox_attempt', 'id': str(event['id']), 'kind': kind, 'state': state, 'status': status, 'attempt': attempt}))
    return True


# ================= Ingesta asíncrona =================
def _write_sources(directory: Path, payload):
    if payload.get('formato') == 'csv':
        for name, text in payload['archivos'].items():
            (directory / name).write_text(text, encoding='utf-8')
        return
    for name, rows in payload['tablas'].items():
        columns = list(dict.fromkeys(k for r in rows for k in r))
        buffer = io.StringIO(); writer = csv.DictWriter(buffer, fieldnames=columns); writer.writeheader()
        writer.writerows([{k: ('' if r.get(k) is None else r.get(k)) for k in columns} for r in rows])
        (directory / f'{name}.csv').write_text(buffer.getvalue(), encoding='utf-8')


def process_job(repo, engine=None):
    from backend.reference_model import VERSION
    from scripts.build_dashboard_data import build, ROOT
    job = repo.claim_job()
    if not job:
        return False
    s = repo.settings; start = time.monotonic(); job_id = job['job_id']
    elapsed = lambda: round((time.monotonic() - start) * 1000)
    try:
        with tempfile.TemporaryDirectory(prefix='paktai-job-') as directory:
            source = Path(directory)
            _write_sources(source, job['payload'])
            hashes = dict(job['hashes'] or {})
            hashes['amie'] = hashlib.sha256((ROOT / 'data/bronze/public/amie_abandono.csv').read_bytes()).hexdigest()
            run_id = hashlib.sha256(json.dumps({'hashes': hashes, 'model': VERSION, 'pipeline': '1.0.0'}, sort_keys=True).encode()).hexdigest()
            tables = validate_source(source)
            source_files = {p.stem: p.read_bytes() for p in source.glob('*.csv')}
            silver, gold, model = build(source, write_outputs=False)
            result = repo.save_pipeline(run_id, hashes, tables, silver, gold, model)
    except DataValidationError as error:
        # Datos inválidos: reintentar no los arregla.
        repo.finish_job(job_id, 'DEAD_LETTER', error=str(error)[:500], duration_ms=elapsed())
        return True
    except Exception as error:
        retry = job['attempts'] < job['max_attempts']
        repo.finish_job(job_id, 'FAILED_RETRYABLE' if retry else 'DEAD_LETTER', error=f'Error interno ({type(error).__name__})',
                        retry_in_s=backoff(s.worker_backoff_base_s, job['attempts']) if retry else None, duration_ms=elapsed())
        return True
    if engine is not None:
        try:
            outcome = push_to_engine(engine, s, source_files, job_id, silver)
        except EngineUnavailable as error:
            retry = job['attempts'] < job['max_attempts']
            repo.finish_job(job_id, 'FAILED_RETRYABLE' if retry else 'DEAD_LETTER',
                            error=f'Motor no disponible ({error})' + ('' if retry else f' tras {job["attempts"]} intentos'),
                            retry_in_s=backoff(s.worker_backoff_base_s, job['attempts']) if retry else None, duration_ms=elapsed())
            return True
        except Permanent as error:
            repo.finish_job(job_id, 'DEAD_LETTER', error=str(error)[:300], duration_ms=elapsed())
            return True
        result['motor'] = outcome
    else:
        result['motor'] = 'no configurado: solo modelo de referencia'
    repo.finish_job(job_id, 'COMPLETED', result=result, duration_ms=elapsed())
    return True


def main():
    load_dotenv(); logging.basicConfig(level=logging.INFO, format='%(message)s')
    settings = Settings(); settings.validate('worker')
    repo = Repository(settings); repo.open()
    engine = EngineClient(settings.engine_base_url, settings.engine_api_key, settings.engine_timeout_s, school_id=settings.engine_school_id, jwt_secret=settings.engine_jwt_secret) if settings.engine_base_url else None
    last_purge = 0.0
    try:
        with tls_client() as client:
            while True:
                if time.time() - last_purge > 24 * 3600:
                    log.info(json.dumps({'event': 'lopdp_purge', 'purged': repo.purge_expired_pii()})); last_purge = time.time()
                busy = process_job(repo, engine)
                busy = tick(repo, client, engine) or busy
                if not busy:
                    time.sleep(1)
    finally:
        repo.close()
        if engine: engine.close()


if __name__ == '__main__':
    main()
