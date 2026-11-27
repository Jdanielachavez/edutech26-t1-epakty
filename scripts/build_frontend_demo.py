"""Genera frontend-v2/data/demo-bundle.json para el modo demo de la interfaz.

Pide las respuestas al motor (por defecto el stub de Wilo en localhost:8090) con los roles más amplios
(Rectorado y CEO). La interfaz, en modo demo, aplica sobre ellas los mismos permisos y el mismo filtro de
privacidad que el backend, así que cada rol ve exactamente lo que vería conectado.

Uso:  python3 engine_stub/05_KIT_INTEGRACION_SIN_EXPONER_MOTOR/epakti_engine_stub_server.py --port 8090 &
      .venv/bin/python scripts/build_frontend_demo.py [http://localhost:8090/api/v1]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.production.engine import EngineClient  # noqa: E402


def main(base):
    engine = EngineClient(base, 'dev-stub-key-replace-in-prod')
    get = lambda path, role='rectoria': engine.request('GET', path, role)[1]
    triage = get('/dashboard/docente-tutor/triage')
    codes = [r['codigo_estudiante'] for r in triage['estudiantes']]
    bundle = {
        'fuente': base,
        'kpis': get('/dashboard/rectorado/kpis-roi'),
        'triage': triage,
        'fichas': {c: get(f'/students/{c}/ficha-360') for c in codes},
        'dece': get('/dashboard/dece/inclusion-nee'),
        'colecturia': get('/dashboard/colecturia/cartera-hogares'),
        'vice': get('/dashboard/vicerrectorado/docentes-horarios'),
        'admision': engine.request('POST', '/admissions/evaluate-applicant', 'rectoria', json={'codigo_postulante': 'DEMO'})[1],
        'mlops': get('/admin/mlops/overview-and-drift', 'epakti_ceo'),
        'tenants': get('/admin/tenants', 'epakti_ceo'),
        'datalake': get('/admin/data-lake/anonymized-explorer', 'epakti_ceo'),
        'n8n': get('/admin/n8n/observability', 'epakti_ceo'),
    }
    out = ROOT / 'frontend-v2' / 'data' / 'demo-bundle.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'{out.relative_to(ROOT)}: {out.stat().st_size // 1024} KB · {len(codes)} fichas')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8090/api/v1')
