"""Carga el dataset ficticio en la base de Supabase por el mismo camino que usa la API (valida, seudonimiza, calcula, guarda).

Uso: ./scripts/load_supabase.sh   (o: DATABASE_URL=<supabase> python -m scripts.load_supabase [carpeta])
Escribe en la base apuntada por DATABASE_URL. Solo datos sintéticos.
"""
import hashlib
import sys
from pathlib import Path

from backend.production.config import Settings
from backend.production.repository import Repository
from backend.production.validation import TABLES
from backend.production.worker import process_job
from scripts.build_dashboard_data import SOURCE


def main():
    s = Settings(); s.validate('worker')
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else SOURCE
    archivos, hashes = {}, {}
    for table in TABLES:
        raw = (folder / f'{table}.csv').read_bytes()
        archivos[f'{table}.csv'] = raw.decode('utf-8-sig'); hashes[f'{table}.csv'] = hashlib.sha256(raw).hexdigest()
    repo = Repository(s); repo.open()
    try:
        key = 'csv:' + hashlib.sha256(''.join(hashes[k] for k in sorted(hashes)).encode()).hexdigest()
        job_id, created = repo.create_job(key, 'csv', {'formato': 'csv', 'archivos': archivos}, hashes)
        print(f'Trabajo {job_id} ({"nuevo" if created else "ya existía"}) · colegio {s.institution}')
        while process_job(repo, None):   # sin motor: el colegio ya está cargado en el motor de Wilo
            pass
        job = repo.job(job_id)
        print('Estado:', job['status'], '|', (job.get('result') or {}) if job['status'] == 'COMPLETED' else job.get('error_message'))
    finally:
        repo.pool.close()


if __name__ == '__main__':
    main()
