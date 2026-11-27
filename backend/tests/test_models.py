"""Pruebas de los servicios calculados (modelos) y de las cuentas con contraseña. No necesitan base de datos."""
import json
import math
import time
from pathlib import Path

import pytest

from backend.production import accounts, models
from backend.reference_model import predict_reference

ROOT = Path(__file__).resolve().parents[2]
MODEL = json.loads((ROOT / 'data/models/reference-logit.json').read_text())
COHORT = json.loads((ROOT / 'data/gold/gold_estudiantes.json').read_text())['students']


def test_terms_match_reference_model_probability():
    for row in COHORT[:60]:
        p, _ = predict_reference(MODEL, row)
        assert models.probability(MODEL, row) == pytest.approx(p, rel=1e-12)


def test_shap_is_exactly_additive():
    row = COHORT[0]
    out = models.explain(MODEL, row, COHORT, 'admin')
    assert out['base_log_odds'] + sum(a['valor_log_odds'] for a in out['aportes']) == pytest.approx(out['log_odds'])
    assert 1 / (1 + math.exp(-out['log_odds'])) == pytest.approx(out['probabilidad'])


def test_non_financial_roles_never_see_money_factors_but_total_still_adds_up():
    row = max(COHORT, key=lambda r: r.get('overdueMonths') or 0)
    out = models.explain(MODEL, row, COHORT, 'tutor')
    text = json.dumps(out, ensure_ascii=False).lower()
    assert 'pensión' not in text and 'financiero' not in text and 'vencid' not in text
    assert out['base_log_odds'] + sum(a['valor_log_odds'] for a in out['aportes']) == pytest.approx(out['log_odds'])
    assert 'convenio_pago' not in models.allowed_actions('tutor')
    with pytest.raises(ValueError):
        models.simulate(MODEL, row, COHORT, ['convenio_pago'], 'tutor')
    assert 'meses_vencidos' not in models.risk_table(MODEL, COHORT, 'dece')['estudiantes'][0]


def test_simulation_lowers_risk_and_does_not_mutate_input():
    row = dict(COHORT[0]); snapshot = dict(row)
    out = models.simulate(MODEL, row, COHORT, ['tutoria_academica', 'seguimiento_asistencia', 'convenio_pago'], 'admin')
    assert out['despues']['probabilidad'] < out['antes']['probabilidad']
    assert row == snapshot


def test_wellbeing_is_not_invented():
    row = dict(next(r for r in COHORT if r.get('score_bienestar') is None))
    out = models.simulate(MODEL, row, COHORT, ['apoyo_socioemocional'], 'dece')
    assert out['despues']['probabilidad'] == pytest.approx(out['antes']['probabilidad'])


def test_levels_follow_cohort_thresholds():
    table = models.risk_table(MODEL, COHORT, 'admin')
    assert table['resumen']['por_nivel'] == {'Crítico': 12, 'Moderado': 36, 'Bajo': 192}


def test_territory_is_a_uniform_shift_and_rejects_unknown_province():
    info = models.territory('Pichincha')
    assert info['razon_provincia_nacional'] > 0 and info['pobreza_y_desempleo']['Pobreza por ingresos']['nacional']
    assert models.territory('Bolívar')['provincia'] == 'Bolívar'
    with pytest.raises(KeyError):
        models.territory('Atlantida')


def test_password_hashing_and_sessions():
    users = {'ana': {'hash': accounts.hash_password('Clave-Segura-1'), 'role': 'rectoria', 'name': 'Ana'}}
    assert accounts.authenticate_user(users, 'ANA ', 'Clave-Segura-1')['role'] == 'rectoria'
    assert accounts.authenticate_user(users, 'ana', 'otra') is None
    assert accounts.authenticate_user(users, 'nadie', 'Clave-Segura-1') is None
    secret = 's' * 40
    token, _ = accounts.issue_session(secret, accounts.authenticate_user(users, 'ana', 'Clave-Segura-1'), 60)
    assert accounts.read_session(secret, token)['role'] == 'rectoria'
    assert accounts.read_session('x' * 40, token) is None                       # otra clave de firma
    assert accounts.read_session(secret, token[:-2] + 'AA') is None             # firma alterada
    assert accounts.read_session(secret, token, now=time.time() + 120) is None  # vencida
    forged_payload = accounts._b64(json.dumps({'user': 'ana', 'role': 'admin', 'exp': time.time() + 99}).encode())
    assert accounts.read_session(secret, forged_payload + '.' + token.split('.')[1]) is None  # cambiar el rol invalida la firma


def test_four_color_semaforo_follows_percentiles():
    table = models.risk_table(MODEL, COHORT, 'admin')
    assert table['resumen']['por_semaforo'] == {'ROJO': 12, 'NARANJA': 36, 'AMARILLO': 48, 'VERDE': 144}
    assert all(r['semaforo'] == {'Crítico': 'ROJO', 'Moderado': 'NARANJA'}.get(r['nivel'], r['semaforo']) for r in table['estudiantes'])
    top = models.explain(MODEL, COHORT[0], COHORT, 'admin')
    assert top['semaforo'] in models.SEMAFORO_LABELS and top['semaforo_etiqueta'] == models.SEMAFORO_LABELS[top['semaforo']]
    sim = models.simulate(MODEL, COHORT[0], COHORT, ['tutoria_academica'], 'admin')
    assert sim['antes']['semaforo'] in models.SEMAFORO_LABELS and sim['despues']['semaforo'] in models.SEMAFORO_LABELS
