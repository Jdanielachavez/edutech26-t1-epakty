"""Genera frontend-v2/data/demo-modelo.json: el MISMO modelo y los MISMOS cálculos de la API, para que el demo público
los ejecute en el navegador con los 240 estudiantes ficticios (nada sale del navegador).

Uso: python -m scripts.build_frontend_model
"""
import csv
import json
from pathlib import Path

from backend.production import models
from scripts.build_dashboard_data import SOURCE

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ('id', 'name', 'course', 'parallel', 'average', 'attendance', 'materia_critica', 'tiene_nee', 'delta_nota_ultimo_corte',
          'rezago_edad', 'transicion_critica', 'tasa_reprobacion_docente_contexto', 'unjustifiedAbsence',
          'racha_faltas_injustificadas', 'score_bienestar', 'overdueMonths', 'dummy_shock_financiero')


def main():
    model = json.loads((ROOT / 'data/models/reference-logit.json').read_text(encoding='utf-8'))
    gold = json.loads((ROOT / 'data/gold/gold_estudiantes.json').read_text(encoding='utf-8'))['students']
    out = {'aviso': 'Datos ficticios del hackathon. Modelo de referencia sin entrenar con retiros.',
           'modelo': models.model_card(model),
           'estudiantes': [{k: r.get(k) for k in FIELDS} for r in gold],
           'acciones': {k: {'nombre': v['nombre'], 'responsable': v['responsable'], 'supuesto': v['supuesto'], 'financiero': v['financiero']}
                        for k, v in models.ACTIONS.items()},
           'provincias': {p: models.territory(p) for p in models.provinces()}}
    # Asistencia día por día, la MISMA del archivo cargado (una letra por día: P presente, I falta injustificada, J falta justificada, A atraso)
    cod = {'presente': 'P', 'falta_injustificada': 'I', 'falta_justificada': 'J', 'atraso': 'A'}
    por, fechas = {}, set()
    for r in csv.DictReader(open(SOURCE / 'asistencia.csv', encoding='utf-8')):
        por.setdefault(r['codigo_estudiante'], {})[r['fecha']] = cod.get(r['estado'], '?'); fechas.add(r['fecha'])
    fechas = sorted(fechas)
    out['asistencia'] = {'fechas': fechas, 'por_estudiante': {k: ''.join(v.get(f, '-') for f in fechas) for k, v in por.items()}}
    target = ROOT / 'frontend-v2/data/demo-modelo.json'
    target.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'{target} ({target.stat().st_size // 1024} KB, {len(out["estudiantes"])} estudiantes, {len(out["provincias"])} provincias)')


if __name__ == '__main__':
    main()
