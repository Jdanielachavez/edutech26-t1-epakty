"""Los cuatro servicios de E-Pakty calculados de verdad sobre los datos cargados del colegio.

1. Alerta temprana       -> `risk_table`: probabilidad de referencia por estudiante y nivel por percentil de la cohorte.
2. Contexto territorial  -> `territory`: abandono (AMIE) y pobreza/desempleo (ENEMDU) de la provincia frente al país.
3. Explicación (SHAP)    -> `explain`: en un modelo logístico lineal el valor SHAP exacto de cada factor es
                            coeficiente × (valor del estudiante − valor medio de la cohorte), medido en log-odds.
                            La suma de los aportes más la base reproduce exactamente la probabilidad del estudiante.
   Sensibilidad          -> `simulate`: se cambian las variables que una acción puede mover y se vuelve a calcular.
4. Asistente de IA       -> vive en n8n (Nova Lite); aquí solo se prepara el expediente sin datos personales.

Honestidad del modelo: los coeficientes son de diseño (`reference_not_trained`), no se entrenaron con retiros reales.
Los resultados ordenan al estudiantado dentro de su colegio; no son probabilidades individuales validadas, y las
simulaciones son escenarios supuestos, no efectos causales medidos.
"""
from __future__ import annotations

import csv
import math
import unicodedata
from functools import lru_cache
from pathlib import Path

from backend.reference_model import COEFFICIENTS, sigmoid

_here = Path(__file__).resolve().parent
_candidates = [
    _here / 'public',                               # local dev copy (si existe)
    _here.parents[1] / 'api' / 'public',            # Vercel: ROOT/api/public
    _here.parents[1] / 'data' / 'bronze' / 'public' # repo original
]
PUBLIC_DIR = next((p for p in _candidates if (p / 'amie_abandono.csv').exists()), _candidates[-1])

# (clave del modelo, etiqueta para personas, grupo causal)
FEATURES = (
    ('grade_gap', 'Notas bajas (menos de 7,5)', 'academico'),
    ('grade_decline', 'Las notas le bajaron en el último corte', 'academico'),
    ('age_lag', 'Tiene más edad que sus compañeros de curso', 'academico'),
    ('transition', 'Está cambiando de ciclo', 'academico'),
    ('nee', 'Necesita apoyos para aprender', 'academico'),
    ('teacher_fail_fraction', 'Cuánto se reprueba en sus materias', 'academico'),
    ('absence_fraction', 'Falta a clase sin justificar', 'conductual'),
    ('absence_streak', 'Faltó varios días seguidos', 'conductual'),
    ('wellbeing_gap', 'Se siente mal (bienestar bajo)', 'conductual'),
    ('overdue_months', 'Pensiones atrasadas', 'financiero'),
    ('payment_shock', 'La familia tuvo un apuro de dinero', 'financiero'),
)
GROUP_LABELS = {'academico': 'Notas y aprendizaje', 'conductual': 'Faltas y bienestar', 'financiero': 'Pagos'}
NAMES = {f[0]: f for f in FEATURES}
FINANCIAL_VIEWERS = {'admin', 'rectoria', 'colecturia', 'epakti_ceo', 'epakti_mlops', 'epakti_ds', 'epakti_cs'}


def terms(row: dict) -> dict:
    """Aporte de cada factor al log-odds del estudiante (coeficiente × variable)."""
    c = COEFFICIENTS
    avg = row.get('average')
    wellbeing = row.get('score_bienestar')
    return {
        'grade_gap': c['grade_gap'] * max(0, 7.5 - avg) if avg is not None else 0.0,
        'grade_decline': c['grade_decline'] * max(0, -(row.get('delta_nota_ultimo_corte') or 0)),
        'age_lag': c['age_lag'] * (row.get('rezago_edad') or 0),
        'transition': c['transition'] * (row.get('transicion_critica') or 0),
        'nee': c['nee'] * (row.get('tiene_nee') or 0),
        'teacher_fail_fraction': c['teacher_fail_fraction'] * (row.get('tasa_reprobacion_docente_contexto') or 0) / 100,
        'absence_fraction': c['absence_fraction'] * (row.get('unjustifiedAbsence') or 0) / 100,
        'absence_streak': c['absence_streak'] * (row.get('racha_faltas_injustificadas') or 0),
        'wellbeing_gap': c['wellbeing_gap'] * max(0, 3 - wellbeing) if wellbeing is not None else 0.0,
        'overdue_months': c['overdue_months'] * (row.get('overdueMonths') or 0),
        'payment_shock': c['payment_shock'] * (row.get('dummy_shock_financiero') or 0),
    }


def probability(model: dict, row: dict) -> float:
    return sigmoid(model['intercept'] + sum(terms(row).values()))


def level(model: dict, p: float) -> str:
    t = model['thresholds']
    return 'Crítico' if p >= t['critical'] else 'Moderado' if p >= t['moderate'] else 'Bajo'


# ---- Semáforo escolar de 4 colores (relativo al propio colegio) ----
SEMAFORO_LABELS = {'ROJO': 'Intervención prioritaria', 'NARANJA': 'Apoyo focalizado',
                   'AMARILLO': 'Observación preventiva', 'VERDE': 'Acompañamiento regular'}
OBSERVE_PERCENTILE = 60   # 5 % ROJO, 15 % NARANJA, 20 % AMARILLO (P60-P80) y el resto VERDE


def bands(model: dict, probs: list[float]) -> dict:
    t = model['thresholds']
    ordered = sorted(probs)
    observe = ordered[int(len(ordered) * OBSERVE_PERCENTILE / 100)] if len(ordered) >= 20 else t['moderate'] / 2
    return {'ROJO': t['critical'], 'NARANJA': t['moderate'], 'AMARILLO': min(observe, t['moderate'])}


def semaforo(th: dict, p: float) -> str:
    return 'ROJO' if p >= th['ROJO'] else 'NARANJA' if p >= th['NARANJA'] else 'AMARILLO' if p >= th['AMARILLO'] else 'VERDE'


def model_card(model: dict) -> dict:
    return {'id': model['model_id'], 'version': model['version'], 'estado': model['status'],
            'coeficientes': model['coefficients'], 'intercepto': model['intercept'], 'umbrales': model['thresholds'],
            'entrenamiento': model['training'], 'validacion': model['validation'], 'referencia': model['reference'],
            'limitaciones': model['limitations'],
            'semaforo': [{'color': 'ROJO', 'etiqueta': SEMAFORO_LABELS['ROJO'], 'regla': 'el 5 % del colegio con más riesgo'},
                         {'color': 'NARANJA', 'etiqueta': SEMAFORO_LABELS['NARANJA'], 'regla': 'el 15 % siguiente'},
                         {'color': 'AMARILLO', 'etiqueta': SEMAFORO_LABELS['AMARILLO'], 'regla': 'el 20 % siguiente'},
                         {'color': 'VERDE', 'etiqueta': SEMAFORO_LABELS['VERDE'], 'regla': 'el 60 % restante'}],
            'formula': 'probabilidad = 1 / (1 + e^-(intercepto + Σ coeficiente × variable))',
            'factores': [{'clave': k, 'etiqueta': label, 'grupo': GROUP_LABELS[g], 'coeficiente': COEFFICIENTS[k]}
                         for k, label, g in FEATURES]}


# ================= 1. Alerta temprana =================
def risk_table(model: dict, rows: list[dict], viewer: str) -> dict:
    probs = [probability(model, r) for r in rows]
    th = bands(model, probs)
    show_money = viewer in FINANCIAL_VIEWERS
    out = []
    for r, p in zip(rows, probs):
        t = terms(r)
        group = {g: sum(v for k, v in t.items() if NAMES[k][2] == g) for g in GROUP_LABELS}
        main = max((g for g in group if show_money or g != 'financiero'), key=lambda g: group[g])
        item = {'id': r['id'], 'nombre': r.get('name'), 'curso': r['course'], 'paralelo': r['parallel'],
                'probabilidad': p, 'nivel': level(model, p), 'semaforo': semaforo(th, p), 'semaforo_etiqueta': SEMAFORO_LABELS[semaforo(th, p)],
                'factor_principal': GROUP_LABELS[main],
                'asistencia': r.get('attendance'), 'promedio': r.get('average'), 'materia_critica': r.get('materia_critica'),
                'tiene_nee': r.get('tiene_nee')}
        if show_money:
            item['meses_vencidos'] = r.get('overdueMonths')
        out.append(item)
    out.sort(key=lambda x: x['probabilidad'], reverse=True)
    counts = {n: sum(1 for x in out if x['nivel'] == n) for n in ('Crítico', 'Moderado', 'Bajo')}
    por_semaforo = {c: sum(1 for x in out if x['semaforo'] == c) for c in SEMAFORO_LABELS}
    return {'estudiantes': out, 'resumen': {'total': len(out), 'por_nivel': counts, 'por_semaforo': por_semaforo,
            'probabilidad_media': sum(probs) / len(probs) if probs else None},
            'modelo': {'version': model['version'], 'estado': model['status'], 'umbrales': model['thresholds']}}


# ================= 3. Explicación (SHAP exacto del logit) =================
def explain(model: dict, row: dict, cohort: list[dict], viewer: str) -> dict:
    mean = {k: sum(terms(r)[k] for r in cohort) / len(cohort) for k in NAMES}
    mine = terms(row)
    base_logit = model['intercept'] + sum(mean.values())
    show_money = viewer in FINANCIAL_VIEWERS
    contributions, hidden = [], 0.0
    for key, label, group in FEATURES:
        shap = mine[key] - mean[key]
        if group == 'financiero' and not show_money:
            hidden += shap
            continue
        contributions.append({'clave': key, 'factor': label, 'grupo': GROUP_LABELS[group], 'valor_log_odds': shap,
                              'efecto': 'sube el riesgo' if shap > 0 else 'baja el riesgo' if shap < 0 else 'sin efecto'})
    if hidden:
        contributions.append({'clave': 'reservado', 'factor': 'Otros factores (no visibles para tu rol)', 'grupo': 'Reservado',
                              'valor_log_odds': hidden, 'efecto': 'sube el riesgo' if hidden > 0 else 'baja el riesgo'})
    contributions.sort(key=lambda c: abs(c['valor_log_odds']), reverse=True)
    logit = base_logit + sum(c['valor_log_odds'] for c in contributions)
    p, p0 = sigmoid(logit), sigmoid(base_logit)
    th = bands(model, [probability(model, r) for r in cohort])
    inputs = {'promedio': row.get('average'), 'caida_ultimo_corte': row.get('delta_nota_ultimo_corte'),
              'faltas_injustificadas_pct': row.get('unjustifiedAbsence'), 'racha_faltas': row.get('racha_faltas_injustificadas'),
              'bienestar': row.get('score_bienestar'), 'rezago_edad': row.get('rezago_edad'),
              'transicion_critica': row.get('transicion_critica'), 'tiene_nee': row.get('tiene_nee')}
    if show_money:
        inputs.update(meses_vencidos=row.get('overdueMonths'), golpe_financiero=row.get('dummy_shock_financiero'))
    return {'id': row['id'], 'nombre': row.get('name'), 'curso': row['course'], 'paralelo': row['parallel'],
            'probabilidad': p, 'probabilidad_base_cohorte': p0, 'nivel': level(model, p),
            'semaforo': semaforo(th, p), 'semaforo_etiqueta': SEMAFORO_LABELS[semaforo(th, p)],
            'base_log_odds': base_logit, 'log_odds': logit, 'aportes': contributions, 'entradas': inputs,
            'como_leerlo': 'Las barras de arriba son las que más pesan. Juntas explican todo el riesgo de este estudiante. '
                           'Son cosas que suelen ir junto con el riesgo, no la causa comprobada.'}


# ================= 3b. Sensibilidad: ¿qué pasaría si...? =================
def _tutoria(r):
    r['average'] = min(10, (r.get('average') or 0) + 1.0); r['delta_nota_ultimo_corte'] = max(0, r.get('delta_nota_ultimo_corte') or 0)


def _asistencia(r):
    r['unjustifiedAbsence'] = (r.get('unjustifiedAbsence') or 0) * 0.5; r['racha_faltas_injustificadas'] = 0


def _convenio(r):
    r['overdueMonths'] = 0; r['dummy_shock_financiero'] = 0


def _bienestar(r):
    if r.get('score_bienestar') is not None:
        r['score_bienestar'] = max(r['score_bienestar'], 3)


ACTIONS = {
    'tutoria_academica': {'nombre': 'Tutoría académica semanal', 'responsable': 'Docente tutor', 'financiero': False, 'cambia': _tutoria,
                          'supuesto': 'Sube el promedio 1 punto y frena la caída de notas del último corte.'},
    'seguimiento_asistencia': {'nombre': 'Seguimiento de asistencia con la familia', 'responsable': 'Inspección / tutor', 'financiero': False,
                               'cambia': _asistencia, 'supuesto': 'Reduce a la mitad las faltas injustificadas y corta la racha actual.'},
    'apoyo_socioemocional': {'nombre': 'Acompañamiento socioemocional (DECE)', 'responsable': 'DECE', 'financiero': False, 'cambia': _bienestar,
                             'supuesto': 'Lleva el bienestar al menos a 3 de 5. Sin dato de bienestar no se inventa nada: no tiene efecto.'},
    'convenio_pago': {'nombre': 'Convenio de pago', 'responsable': 'Colecturía', 'financiero': True, 'cambia': _convenio,
                      'supuesto': 'Pone al día las pensiones vencidas y elimina el golpe financiero.'},
}


def allowed_actions(viewer: str) -> dict:
    return {k: v for k, v in ACTIONS.items() if viewer in FINANCIAL_VIEWERS or not v['financiero']}


def simulate(model: dict, row: dict, cohort: list[dict], action_keys: list[str], viewer: str) -> dict:
    options = allowed_actions(viewer)
    unknown = [a for a in action_keys if a not in options]
    if unknown or not action_keys:
        raise ValueError('Acción no disponible: ' + ', '.join(unknown or ['(ninguna)']))
    after = dict(row)
    for key in action_keys:
        options[key]['cambia'](after)
    p_before, p_after = probability(model, row), probability(model, after)
    probs = sorted(probability(model, r) for r in cohort)
    pos = lambda p: 100 * sum(1 for x in probs if x < p) / len(probs)
    th = bands(model, probs)
    face = lambda p: {'probabilidad': p, 'nivel': level(model, p), 'semaforo': semaforo(th, p), 'semaforo_etiqueta': SEMAFORO_LABELS[semaforo(th, p)], 'percentil_en_colegio': pos(p)}
    return {'id': row['id'], 'acciones': [{'clave': k, 'nombre': options[k]['nombre'], 'responsable': options[k]['responsable'],
                                           'supuesto': options[k]['supuesto']} for k in action_keys],
            'antes': face(p_before),
            'despues': face(p_after),
            'reduccion_relativa': 1 - p_after / p_before if p_before else 0.0,
            'nota': 'Así quedaría el riesgo si la acción logra su objetivo. Es una estimación, no una promesa: '
                    'solo el acompañamiento real dirá si funcionó.'}


# ================= 2. Contexto territorial =================
def _plain(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', text or '') if unicodedata.category(c) != 'Mn').casefold().strip()


@lru_cache(maxsize=1)
def _public():
    def read(name):
        with (PUBLIC_DIR / name).open(encoding='utf-8-sig', newline='') as f:
            return list(csv.DictReader(f))
    return read('amie_abandono.csv'), read('enemdu_hogar.csv')


def provinces() -> list[str]:
    amie, _ = _public()
    names = {r['provincia'] for r in amie if r['provincia'] != 'Zona No Delimitada'}
    return sorted(names, key=_plain)


def _rate(rows):
    enrolled = sum(float(r['total_matriculados'] or 0) for r in rows)
    left = sum(float(r['total_abandono'] or 0) for r in rows)
    return {'matriculados': int(enrolled), 'abandono': int(left), 'tasa_pct': round(100 * left / enrolled, 3) if enrolled else None}


def territory(province: str, sector: str = 'Particular') -> dict:
    amie, enemdu = _public()
    key = _plain(province)
    if key not in {_plain(p) for p in provinces()}:
        raise KeyError(province)
    period = max(r['periodo'] for r in amie)
    latest = [r for r in amie if r['periodo'] == period]
    mine = [r for r in latest if _plain(r['provincia']) == key]
    mine_sector = [r for r in mine if r['sostenimiento'] == sector]
    national_sector = [r for r in latest if r['sostenimiento'] == sector]
    prov, nat = _rate(mine_sector), _rate(national_sector)
    ratio = prov['tasa_pct'] / nat['tasa_pct'] if prov['tasa_pct'] and nat['tasa_pct'] else None
    by_area = {a: _rate([r for r in mine_sector if r['area'] == a]) for a in sorted({r['area'] for r in mine_sector})}
    year = max(r['periodo'] for r in enemdu)

    def indicator(name, scope):
        pick = [r for r in enemdu if r['periodo'] == year and r['indicador'] == name and _plain(r['provincia']) == scope and r['area'] == 'Total']
        return float(pick[0]['valor']) if pick else None
    social = {name: {'provincia': indicator(name, key), 'nacional': indicator(name, 'nacional')}
              for name in ('Pobreza por ingresos', 'Tasa de desempleo')}
    adjustment = math.log(min(2.0, max(0.5, ratio))) if ratio else 0.0
    return {'provincia': province, 'sostenimiento': sector, 'periodo_amie': period, 'anio_enemdu': year,
            'abandono_provincia': prov, 'abandono_nacional': nat, 'razon_provincia_nacional': ratio,
            'abandono_por_area': by_area, 'pobreza_y_desempleo': social,
            'ajuste_log_odds': adjustment,
            'lectura': 'En zonas donde más estudiantes dejan el colegio, el riesgo de todos sube un poco por igual. '
                       'Eso cambia cuánto riesgo esperar en la zona, pero no cambia el orden entre estudiantes: '
                       'a nadie se le sube el riesgo por el barrio donde vive. El dato oficial llega por provincia.',
            'fuentes': ['AMIE · Ministerio de Educación (datos abiertos)', 'ENEMDU anual · INEC']}


def territory_adjusted(model: dict, rows: list[dict], province: str) -> dict:
    """Probabilidad media del colegio antes y después del ajuste territorial."""
    info = territory(province)
    shift = info['ajuste_log_odds']
    base = [probability(model, r) for r in rows]
    adj = [sigmoid(model['intercept'] + sum(terms(r).values()) + shift) for r in rows]
    return {**info, 'colegio': {'probabilidad_media_base': sum(base) / len(base) if base else None,
                                'probabilidad_media_ajustada': sum(adj) / len(adj) if adj else None, 'estudiantes': len(rows)}}
