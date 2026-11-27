"""Carga el dataset ficticio al motor en vivo de Wilo (mismo camino que usa el worker). Datos sintéticos, sin nombres.

Uso: set -a; . ./.env.dev; set +a; python -m scripts.load_engine [carpeta_con_los_6_csv]
"""
import sys
import uuid
from pathlib import Path

from backend.production.config import Settings
from backend.production.engine import EngineClient
from backend.production.worker import push_to_engine
from scripts.build_dashboard_data import SOURCE


def main():
    s = Settings(); s.validate('worker')
    if not s.engine_base_url:
        sys.exit('Falta EPAKTI_ENGINE_BASE_URL')
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else SOURCE
    files = {p.stem: p.read_bytes() for p in folder.glob('*.csv')}
    engine = EngineClient(s.engine_base_url, s.engine_api_key, 30, school_id=s.engine_school_id, jwt_secret=s.engine_jwt_secret)
    if not engine.is_live():
        sys.exit('El motor configurado no es el de Wilo (EPAKTI_LIVE_PYTORCH_ENGINE).')
    print(f'Colegio {engine.school_id}: subiendo {len(files)} archivos desde {folder} ...')
    print(push_to_engine(engine, s, files, 'LOAD-' + uuid.uuid4().hex[:8].upper(), silver={'students': []}))


if __name__ == '__main__':
    main()
