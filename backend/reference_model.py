"""Versioned reference Logit from the supplied design; NOT a fitted dropout model."""
import csv
import hashlib
import math
from pathlib import Path

VERSION = 'reference-logit-1.0.0'
COEFFICIENTS = {'grade_gap': .55, 'grade_decline': .30, 'absence_fraction': 4.5,
                'absence_streak': .25, 'overdue_months': .75, 'payment_shock': .60,
                'wellbeing_gap': .45, 'age_lag': .35, 'transition': .25,
                'nee': .20, 'teacher_fail_fraction': -.40}

def contributions(row):
    c = COEFFICIENTS
    avg = row.get('average')
    academic = c['grade_gap'] * max(0, 7.5 - avg) if avg is not None else 0
    academic += c['grade_decline'] * max(0, -(row.get('delta_nota_ultimo_corte') or 0))
    academic += c['age_lag'] * row.get('rezago_edad', 0) + c['transition'] * row.get('transicion_critica', 0)
    academic += c['nee'] * row.get('tiene_nee', 0)
    academic += c['teacher_fail_fraction'] * (row.get('tasa_reprobacion_docente_contexto') or 0) / 100
    conduct = c['absence_fraction'] * (row.get('unjustifiedAbsence') or 0) / 100 + c['absence_streak'] * row.get('racha_faltas_injustificadas', 0)
    if row.get('score_bienestar') is not None:
        conduct += c['wellbeing_gap'] * max(0, 3 - row['score_bienestar'])
    financial = c['overdue_months'] * row.get('overdueMonths', 0) + c['payment_shock'] * row.get('dummy_shock_financiero', 0)
    return {'academico': academic, 'socioemocional_conductual': conduct, 'financiero': financial}

def sigmoid(x):
    return 1 / (1 + math.exp(-max(-700, min(700, x))))

MODERATE_PERCENTILE = 80   # el 20 % con más riesgo relativo pasa a Moderado o más
CRITICAL_PERCENTILE = 95   # el 5 % con más riesgo relativo es Crítico
MIN_COHORT = 20            # con menos estudiantes un percentil no es estable

def cohort_thresholds(probabilities):
    """Umbrales por percentil de la cohorte.

    La media del modelo se ajusta a la tasa nacional de abandono (~0,8 %), así que
    ninguna persona llega a 35 % o 65 % y nunca habría alertas. Los niveles son por
    eso un ranking relativo dentro del colegio, no una probabilidad absoluta.
    """
    fallback = {'moderate': .35, 'critical': .65, 'method': 'absolute_fallback'}
    n = len(probabilities)
    if n < MIN_COHORT:
        return fallback
    ordered = sorted(probabilities)
    moderate = ordered[int(n * MODERATE_PERCENTILE / 100)]
    critical = ordered[int(n * CRITICAL_PERCENTILE / 100)]
    if not 0 < moderate < critical < 1:
        return fallback
    return {'moderate': moderate, 'critical': critical, 'method': 'cohort_percentile',
            'moderate_percentile': MODERATE_PERCENTILE, 'critical_percentile': CRITICAL_PERCENTILE}

def fit_reference(rows, public_path: Path):
    with public_path.open(encoding='utf-8-sig') as f:
        amie = list(csv.DictReader(f))
    latest = max(r['periodo'] for r in amie)
    cohort = [r for r in amie if r['periodo'] == latest and r['sostenimiento'].casefold() == 'particular']
    enrolled = sum(int(float(r['total_matriculados'])) for r in cohort)
    retired = sum(int(float(r['total_abandono'])) for r in cohort)
    if not enrolled or not 0 < retired < enrolled:
        raise ValueError('No existe tasa AMIE Particular válida')
    target = retired / enrolled
    offsets = [sum(contributions(row).values()) for row in rows]
    low, high = -750., 750.
    for _ in range(100):
        mid = (low + high) / 2
        if sum(sigmoid(mid + z) for z in offsets) / len(offsets) > target:
            high = mid
        else:
            low = mid
    intercept = (low + high) / 2
    thresholds = cohort_thresholds([sigmoid(intercept + z) for z in offsets])
    return {'model_id': 'paktai-reference-logit', 'version': VERSION, 'status': 'reference_not_trained',
            'intercept': intercept, 'coefficients': COEFFICIENTS,
            'thresholds': thresholds,
            'training': {'real_outcomes': False, 'outcome_counts': {}, 'method': 'fixed_design_coefficients'},
            'validation': {'predictive_validation': False, 'reference_mean_matched': True},
            'reference': {'period': latest, 'sector': 'Particular', 'enrolled': enrolled, 'retired': retired,
                          'target_rate': target, 'source_sha256': hashlib.sha256(public_path.read_bytes()).hexdigest()},
            'limitations': ['Todavía no está entrenado con casos reales de estudiantes que se retiraron: el porcentaje es una señal de alerta, no una predicción comprobada.',
                            'Los colores comparan a los estudiantes dentro del mismo colegio (el 5 % y el 15 % con más riesgo). No dicen cuántos se van a retirar.',
                            'La cifra oficial del Ministerio (AMIE) solo sirve para ajustar el promedio del colegio; no comprueba que el cálculo acierte.',
                            'Que un factor pese mucho no prueba que sea la causa.',
                            'Lo de necesidades educativas y el efecto del docente viene de la investigación y aquí no está comprobado: no se debe usar para decidir si un estudiante entra o se queda.',
                            'Cuando falta el dato de bienestar o de la primera hora, se deja vacío: no se inventa.']}

def predict_reference(model, row):
    parts = contributions(row)
    return sigmoid(model['intercept'] + sum(parts.values())), parts
