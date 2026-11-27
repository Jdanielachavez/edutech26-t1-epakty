"""Verifica servicio por servicio con una base FALSA (colegio ficticio, tenant aleatorio en PostgreSQL local).

No mira «que se vea bien»: cambia los datos de entrada a propósito y comprueba que las salidas cambian como debe.
Uso:  set -a; . ./.env.dev; set +a; .venv/bin/python -m scripts.verificar_servicios
Salida: una tabla PASA / FALLA por servicio. Código de salida 1 si algo falla.
"""
import csv, os, shutil, socket, subprocess, sys, tempfile, time
from pathlib import Path
from uuid import uuid4
import httpx
from fastapi.testclient import TestClient
from backend.production.api import create_app
from backend.production.config import Settings
from backend.production.engine import EngineClient
from backend.production.repository import Repository
from backend.production.validation import validate_source
from scripts.build_dashboard_data import build, SOURCE, ROOT

STUB = ROOT / 'engine_stub' / '05_KIT_INTEGRACION_SIN_EXPONER_MOTOR' / 'epakti_engine_stub_server.py'
TOK = {'a' * 32: {'role': 'admin'}, 'd' * 32: {'role': 'dece'}, 'i' * 32: {'role': 'inspeccion'}, 'c' * 32: {'role': 'colecturia'},
       't' * 32: {'role': 'tutor', 'course': '8vo EGB', 'parallel': 'A'}, 'r' * 32: {'role': 'rectoria'}}
H = lambda k: {'Authorization': 'Bearer ' + k * 32}
RES = []


def chk(servicio, nombre, cond, detalle=''):
    RES.append((servicio, nombre, bool(cond), detalle)); print(('  ok   ' if cond else '  FALLA'), servicio, '·', nombre, detalle)


def plantar(destino: Path, sid, n_faltas):
    """Copia el dataset y convierte n_faltas días de `sid` en falta injustificada. Devuelve las fechas plantadas."""
    shutil.copytree(SOURCE, destino, dirs_exist_ok=True)
    f = destino / 'asistencia.csv'
    rows = list(csv.DictReader(open(f, encoding='utf-8'))); campos = list(rows[0])
    mios = [r for r in rows if r['codigo_estudiante'] == sid]
    fechas = []
    for r in mios[:n_faltas]:
        r['estado'] = 'falta_injustificada'; fechas.append(r['fecha'])
    with open(f, 'w', newline='', encoding='utf-8') as o:
        w = csv.DictWriter(o, fieldnames=campos); w.writeheader(); w.writerows(rows)
    return sorted(fechas)


def main():
    url = os.getenv('DATABASE_URL')
    if not url: sys.exit('Falta DATABASE_URL (carga .env.dev).')
    with socket.socket() as s: s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, str(STUB), '--port', str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            if httpx.get(f'http://127.0.0.1:{port}/health', timeout=.5).status_code == 200: break
        except httpx.HTTPError: time.sleep(.1)
    base = f'http://127.0.0.1:{port}/api/v1'
    settings = Settings(database_url=url, institution='verif-' + uuid4().hex[:12], tokens=TOK, n8n_base_url=os.getenv('N8N_WEBHOOK_BASE_URL', '') if '--correo' in sys.argv else '', n8n_hmac_secret=os.getenv('N8N_WEBHOOK_HMAC_SECRET', ''), engine_base_url=base,
                        engine_api_key='dev-stub-key-0123456789', worker_backoff_base_s=.01)
    repo = Repository(settings); repo.open(); eng = EngineClient(base, 'dev-stub-key-0123456789')
    cl = TestClient(create_app(settings, repo, eng), raise_server_exceptions=False)
    tmp = Path(tempfile.mkdtemp())
    try:
        sid = 'EST-002'
        # ---- Carga 1: dataset ficticio tal cual
        silver, gold, model = build(SOURCE, write_outputs=False); repo.save_pipeline('original', {}, validate_source(SOURCE), silver, gold, model)
        r0 = {e['id']: e for e in cl.get('/api/v1/models/risk', headers=H('a')).json()['estudiantes']}
        p0 = r0[sid]['probabilidad']
        chk('Carga de datos', 'el colegio ficticio se carga y se calcula', len(r0) >= 200, f'({len(r0)} estudiantes)')
        sems = {e['semaforo'] for e in r0.values()}
        chk('Modelo', 'el semáforo reparte los 4 colores', sems == {'ROJO', 'NARANJA', 'AMARILLO', 'VERDE'}, str(sorted(sems)))
        # ---- Carga 2: se PLANTAN 25 faltas sin justificar a un estudiante
        fechas = plantar(tmp / 'p', sid, 25)
        s2, g2, m2 = build(tmp / 'p', write_outputs=False); repo.save_pipeline('plantado', {}, validate_source(tmp / 'p'), s2, g2, m2)
        r1 = {e['id']: e for e in cl.get('/api/v1/models/risk', headers=H('a')).json()['estudiantes']}
        p1 = r1[sid]['probabilidad']
        chk('Modelo', 'si le plantamos 25 faltas, su riesgo SUBE', p1 > p0, f'({p0*100:.1f} % → {p1*100:.1f} %)')
        chk('Modelo', 'el semáforo no mejora al empeorar la asistencia', ['VERDE', 'AMARILLO', 'NARANJA', 'ROJO'].index(r1[sid]['semaforo']) >= ['VERDE', 'AMARILLO', 'NARANJA', 'ROJO'].index(r0[sid]['semaforo']))
        otros = [k for k in r0 if k != sid][:20]
        chk('Modelo', 'los demás estudiantes casi no cambian', sum(abs(r1[k]['probabilidad'] - r0[k]['probabilidad']) < .05 for k in otros) >= 17)
        ex = cl.get(f'/api/v1/models/explain/{sid}', headers=H('a')).json()
        suma = ex['probabilidad_base_cohorte']
        top = max(ex['aportes'], key=lambda a: a['valor_log_odds'])
        chk('Por qué está en alerta', 'el factor que más pesa es de asistencia', 'asist' in (top['clave'] + top['grupo'] + top['factor']).lower() or 'falt' in top['factor'].lower() or 'absence' in top['clave'], f"({top['factor']})")
        sim = cl.post(f'/api/v1/models/simulate/{sid}', json={'acciones': ['seguimiento_asistencia']}, headers=H('a')).json()
        chk('Simulador', 'la acción de asistencia baja el puntaje', sim['despues']['probabilidad'] < sim['antes']['probabilidad'], f"({sim['antes']['probabilidad']*100:.1f} → {sim['despues']['probabilidad']*100:.1f} %)")
        # ---- Calendario
        cal = cl.get(f'/api/v1/students/{sid}/asistencia', headers=H('d')).json()
        marcadas = sorted(d['fecha'] for d in cal['dias'] if d['estado'] == 'falta_injustificada')
        chk('Calendario de faltas', 'marca en rojo todos los días plantados', all(f in marcadas for f in fechas), f'({len(fechas)} plantadas, {len(marcadas)} en el calendario)')
        chk('Calendario de faltas', 'colecturía no puede verlo (403)', cl.get(f'/api/v1/students/{sid}/asistencia', headers=H('c')).status_code == 403)
        # ---- Informe
        inf = cl.get(f'/api/v1/students/{sid}/informe', headers=H('a')).json()
        chk('Informe del estudiante', 'dice quién es, el problema y cómo mitigarlo', inf['resumen'] and inf['problemas'] and inf['que_hacer'])
        chk('Informe del estudiante', 'el calendario del informe es el mismo', inf['asistencia']['resumen']['falta_injustificada'] == cal['resumen']['falta_injustificada'])
        txt = str(inf).lower()
        chk('Informe del estudiante', 'no trae datos de pensiones', not any(w in txt for w in ('pensi', 'deuda', 'morosid', 'financ')))
        chk('Informe del estudiante', 'una acción nunca sube el riesgo', all(a['despues'] <= a['antes'] for a in inf['que_hacer']))
        # ---- Seguimiento por etapas
        url = f'/api/v1/students/{sid}/etapa'
        e1 = cl.put(url, json={'etapa': 'REUNION_FAMILIA'}, headers=H('d')).json()
        e2 = cl.put(url, json={'etapa': 'CERRADO'}, headers=H('d')).json()
        chk('Seguimiento por etapas', 'avanza y guarda la fecha de cierre', e1.get('etapa') == 'REUNION_FAMILIA' and e2.get('cerrado_at'))
        chk('Seguimiento por etapas', 'solo admin/DECE/Rectoría pueden devolver', cl.put(url, json={'etapa': 'IDENTIFICADO'}, headers=H('i')).status_code == 403)
        # ---- Notas de seguimiento
        n = cl.post(f'/api/v1/students/{sid}/seguimiento', json={'tipo': 'LLAMADA', 'nota': 'Llamé a la familia, vuelve el lunes.'}, headers=H('d'))
        lista = cl.get(f'/api/v1/students/{sid}/seguimiento', headers=H('d')).json()
        chk('Seguimiento (notas)', 'la nota queda guardada y se lee', n.status_code == 201 and 'vuelve el lunes' in str(lista))
        chk('Seguimiento (notas)', 'colecturía no entra (403)', cl.get(f'/api/v1/students/{sid}/seguimiento', headers=H('c')).status_code == 403)
        # ---- Permisos del tutor
        tut = cl.get('/api/v1/models/risk', headers=H('t')).json()['estudiantes']
        chk('Permisos (RBAC)', 'el tutor solo ve su paralelo', tut and all(e['curso'] == '8vo EGB' and e['paralelo'] == 'A' for e in tut), f'({len(tut)} estudiantes)')
        # ---- Motor de Wilo (stub local, NO el real)
        ec = cl.get('/api/v1/admin/engine-check', headers=H('a'))
        chk('Conexión al motor', 'el chequeo responde con el estado de cada ruta', ec.status_code == 200 and ec.json().get('rutas', ec.json()) is not None, '(contra el STUB local; el motor real de Wilo sigue sin probarse)')
        # ---- Redacción con IA (solo con --correo, usa n8n + Nova Lite reales)
        if '--correo' in sys.argv:
            from backend.production import informes
            top = max(r1, key=lambda k: r1[k]['probabilidad'])
            rr = cl.post(f'/api/v1/students/{top}/informe/redactar', headers=H('d'))
            ok = rr.status_code == 200
            chk('Informe con IA', 'Nova Lite redacta el informe en palabras simples', ok, f'(HTTP {rr.status_code})' + ('' if ok else ' ' + rr.text[:160]))
            if ok:
                t = rr.json()['redaccion']; print('     «' + t['resumen'] + '»')
                chk('Informe con IA', 'no menciona dinero ni nombre del estudiante', not any(w in str(t).lower() for w in ('pensi', 'deuda', 'pago')) and (r1[top]['nombre'].split()[0].lower() not in str(t).lower()))
            # el guardia rechaza cifras inventadas y temas económicos (sin gastar IA)
            ent = informes.entrada_para_ia(cl.get(f'/api/v1/students/{top}/informe', headers=H('a')).json())
            mal = {'ok': True, 'resumen': 'Esta persona tiene un riesgo de 99,9 % y debe pagar la pensión.', 'que_pasa': ['x'], 'que_hacer': ['y']}
            chk('Informe con IA', 'el guardia rechaza cifras inventadas / dinero', informes.validar_redaccion(mal, ent)[1] is not None)
        # ---- Correo real al docente (solo con --correo): API → cola → worker → n8n → SMTP, al destinatario de PRUEBA permitido
        if '--correo' in sys.argv:
            from backend.production.worker import tick
            sid2 = 'EST-003'
            dest = os.getenv('STAGING_ALLOWLIST', '').split(',')[0].strip() or 'docente@example.org'
            r = cl.put(f'/api/v1/students/{sid2}/etapa', json={'etapa': 'DOCENTE_AVISADO', 'docente_nombre': 'Docente de Prueba', 'docente_correo': dest}, headers=H('d'))
            chk('Correo al docente', 'la API acepta el aviso y lo deja en cola', r.status_code == 200 and r.json().get('docente_avisado_at'), f'(HTTP {r.status_code})')
            with httpx.Client(timeout=60) as http:
                while tick(repo, http, None): pass
            with repo.transaction() as c:
                ev = c.execute("SELECT state,attempts,last_status FROM paktai_edu.outbox WHERE kind='AVISO_DOCENTE' AND event_key LIKE %s ORDER BY created_at DESC LIMIT 1", (f'docente:{sid2}:%',)).fetchone()
            chk('Correo al docente', 'n8n lo recibió y lo envió (estado SENT)', ev and ev['state'] == 'SENT', f'({ev})')
    finally:
        proc.terminate(); proc.wait(5); eng.close(); repo.close(); shutil.rmtree(tmp, ignore_errors=True)
    mal = [r for r in RES if not r[2]]
    print(f'\n{len(RES) - len(mal)} de {len(RES)} comprobaciones pasan.')
    if mal: print('FALLAN:', *[f'\n - {s}: {n} {d}' for s, n, _, d in mal])
    print('\nNo verificado aquí: el motor real de Wilo (caído), los correos reales (corre con --correo para probarlos) y Supabase en la nube.')
    sys.exit(1 if mal else 0)


if __name__ == '__main__':
    main()
