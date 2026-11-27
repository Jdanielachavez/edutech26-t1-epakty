"""Privacidad por rol (LOPDP / LOEI) aplicada por el backend a todo lo que devuelve el motor.

El motor ya filtra, pero el backend no confía en eso: docentes, tutores, inspección y DECE nunca reciben un
dato financiero, aunque el motor (o el stub) se equivoque. Y un tutor solo ve a los estudiantes de su paralelo.
"""
from __future__ import annotations

import re

# Con límites de palabra: «cabecera» no es «beca», «suspensión» no es «pensión», «moral» no es «mora».
FINANCIAL = re.compile(r'\bpagos?\b|pagar|\bmora\b|morosidad|cuota|deuda|\bpensi[oó]n|\bbecas?\b|cartera|convenio|colectur|'
                       r'financ|\bmontos?\b|matr[ií]cula|liquidez|cobranza|\busd\b|tard[ií]o', re.I)
# Claves que guardan nombres propios: hay apellidos como «Mora» que no son datos financieros.
NAME_KEYS = re.compile(r'^(nombre|name)', re.I)
# Etiquetas de política que el propio motor usa («CERO_DATOS_FINANCIEROS_EXPUESTOS»).
POLICY_KEYS = {'politica_rbac', 'acceso_rbac', 'politica_privacidad_rbac'}
REDACTED = '[reservado a Colecturía]'
FINANCIAL_ROLES = {'admin', 'rectoria', 'colecturia', 'epakti_ceo', 'epakti_mlops', 'epakti_ds', 'epakti_cs'}


def is_financial(text):
    """Las claves usan guion bajo (`..._usd`): se compara como palabras separadas."""
    return bool(FINANCIAL.search(str(text).replace('_', ' ')))


def strip_financial(value, key=''):
    """Quita claves financieras y redacta textos que las mencionan (recursivo)."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k in POLICY_KEYS or NAME_KEYS.match(k):
                out[k] = v
            elif is_financial(k):
                continue
            else:
                out[k] = strip_financial(v, k)
        return out
    if isinstance(value, list):
        items = [strip_financial(v, key) for v in value]
        # Listas de textos (p. ej. «top 3 factores»): se quitan los elementos financieros.
        return [v for v in items if v != REDACTED]
    if isinstance(value, str) and is_financial(value):
        return REDACTED
    return value


def for_role(role: str, body):
    return body if role in FINANCIAL_ROLES else strip_financial(body)


def norm_course(text):
    match = re.match(r'\s*(\d+)\D*?\s*(EGB|BGU)', text or '', re.I)
    return f'{int(match.group(1))} {match.group(2).upper()}' if match else (text or '').strip()


def _in_scope(row, course, parallel):
    if 'curso_paralelo' in row:
        cp = str(row['curso_paralelo'])
        return norm_course(cp) == norm_course(course) and cp.strip().endswith(' ' + parallel)
    if 'curso' in row and 'paralelo' in row:
        return norm_course(str(row['curso'])) == norm_course(course) and str(row['paralelo']) == parallel
    return True


def scope_students(body, course, parallel):
    """Deja solo estudiantes del paralelo del tutor en cualquier lista de estudiantes de la respuesta."""
    if isinstance(body, dict):
        out = {}
        for k, v in body.items():
            if isinstance(v, list) and v and all(isinstance(x, dict) and 'codigo_estudiante' in x for x in v):
                kept = [x for x in v if _in_scope(x, course, parallel)]
                out[k] = kept
                if 'total' in body:
                    out['total'] = len(kept)
            else:
                out[k] = scope_students(v, course, parallel)
        return out
    return body
