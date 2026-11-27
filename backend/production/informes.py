"""Informe de acompañamiento de un estudiante, en lenguaje claro: quién es, qué problema tiene, por qué y cómo mitigarlo.

Sale del mismo modelo que la priorización (SHAP exacto del logit y simulador de acciones). Es un informe PEDAGÓGICO: nunca incluye
pensiones ni datos financieros, aunque lo pida un rol que puede verlos. Es asociación, no causa, y los escenarios no son promesas."""
from datetime import datetime, timezone
from . import models


def _f(x, d=1):
    return None if x is None else f'{x:.{d}f}'.replace('.', ',')


def _dias(n):
    return f'{n} día' if n == 1 else f'{n} días'


def _problema(clave, r):
    """Texto de cada factor, con el dato real del estudiante."""
    prom, caida = r.get('average'), r.get('delta_nota_ultimo_corte')
    faltas, racha, bien = r.get('unjustifiedAbsence'), r.get('racha_faltas_injustificadas'), r.get('score_bienestar')
    t = {
        'grade_gap': ('Notas bajas', f'Su promedio es {_f(prom)} sobre 10. Con menos de 7,5 aumenta el riesgo de repetir el año o dejar el colegio.'),
        'grade_decline': ('Sus notas están bajando', f'En el último corte bajó {_f(abs(caida or 0))} puntos. Esta caída suele avisar antes que el promedio total.'),
        'age_lag': ('Tiene más edad que sus compañeros de curso', f'Lleva {r.get("rezago_edad")} año(s) de retraso. Quien ya repitió un año tiene más riesgo de no terminar.'),
        'transition': ('Está cambiando de ciclo', 'Pasa de un nivel a otro (por ejemplo, de básica a bachillerato). En ese cambio se pierden muchos estudiantes.'),
        'nee': ('Necesita apoyos por su condición educativa', 'Tiene una necesidad educativa especial. Sin los apoyos a tiempo, aumenta el riesgo de que abandone.'),
        'absence_fraction': ('Falta a clases sin justificar', f'No asistió, sin avisar, al {_f(faltas)} % de las clases. Faltar seguido es la señal más temprana de abandono.'),
        'absence_streak': ('Falta varios días seguidos', f'Su racha más larga sin justificar fue de {_dias(racha)} seguidos.'),
        'wellbeing_gap': ('Su bienestar está bajo', f'Su puntaje de bienestar es {_f(bien)} de 5 (menos de 3 preocupa). Conviene una conversación con el DECE.'),
        'teacher_fail_fraction': ('Su curso es exigente', 'En su curso se reprueba más de lo habitual.'),
    }
    return t.get(clave)


def _fortaleza(clave, r):
    t = {'absence_fraction': 'Asiste más que el promedio del colegio.', 'absence_streak': 'No tiene rachas largas de faltas.',
         'grade_gap': 'Sus notas están por encima de lo esperado.', 'grade_decline': 'Sus notas se mantienen o suben.',
         'wellbeing_gap': 'Su bienestar es bueno.', 'age_lag': 'Está en la edad que corresponde a su curso.',
         'transition': 'No está en un cambio de ciclo.', 'nee': 'No necesita adaptaciones especiales.'}
    return t.get(clave)


PASOS = {
    'tutoria_academica': ('Tutoría semanal de refuerzo', 'Docente tutor', 'Esta semana',
                          'Una tutoría por semana en las materias con nota menor a 7{mat}. Fijar tareas pequeñas y revisar el avance cada viernes.'),
    'seguimiento_asistencia': ('Hablar con la familia sobre las faltas', 'Inspección o tutor', 'Hoy',
                               'Llamar a la familia el mismo día de cada falta, entender la causa y acordar un plan. Revisar cada viernes.'),
    'apoyo_socioemocional': ('Acompañamiento del DECE', 'DECE', 'En los próximos 3 días',
                             'Una entrevista individual y seguimiento cada 15 días. Si la causa está en casa, coordinar con la familia.'),
}


def resumen_asistencia(dias):
    n = {k: 0 for k in ('presente', 'falta_injustificada', 'falta_justificada', 'atraso')}
    for d in dias:
        if d['estado'] in n: n[d['estado']] += 1
    return {'total_dias': len(dias), **n}


def informe_estudiante(model, row, cohort, etapa=None, eventos=None, entorno='staging', asistencia=None):
    ex = models.explain(model, row, cohort, 'dece')        # 'dece' oculta lo financiero: el informe es pedagógico
    p, base = round(ex['probabilidad'] * 100, 1), round(ex['probabilidad_base_cohorte'] * 100, 1)
    pos = [a for a in ex['aportes'] if a['valor_log_odds'] > 0 and a['clave'] != 'reservado']
    neg = [a for a in ex['aportes'] if a['valor_log_odds'] < 0 and a['clave'] != 'reservado']
    problemas = []
    for a in pos:
        txt = _problema(a['clave'], row)
        if txt: problemas.append({'titulo': txt[0], 'explicacion': txt[1], 'peso': round(a['valor_log_odds'], 2)})
        if len(problemas) == 3: break
    fortalezas = [x for x in (_fortaleza(a['clave'], row) for a in neg[:3]) if x][:2]
    acciones = []
    for key in models.allowed_actions('dece'):
        if key not in PASOS: continue
        s = models.simulate(model, row, cohort, [key], 'dece')
        a0, a1 = round(s['antes']['probabilidad'] * 100, 1), round(s['despues']['probabilidad'] * 100, 1)
        nombre, quien, cuando, como = PASOS[key]
        mat = f' (sobre todo {row["materia_critica"]})' if key == 'tutoria_academica' and row.get('materia_critica') else ''
        acciones.append({'clave': key, 'accion': nombre, 'responsable': quien, 'cuando': cuando, 'como': como.format(mat=mat),
                         'antes': a0, 'despues': a1, 'baja_puntos': round(a0 - a1, 1), 'supuesto': s['acciones'][0]['supuesto'],
                         'tiene_efecto': a0 - a1 >= 0.1})
    acciones.sort(key=lambda x: x['baja_puntos'], reverse=True)
    juntas = None
    claves = [a['clave'] for a in acciones if a['tiene_efecto']]
    if len(claves) > 1:
        s = models.simulate(model, row, cohort, claves, 'dece')
        juntas = {'acciones': [a['accion'] for a in acciones if a['tiene_efecto']], 'antes': round(s['antes']['probabilidad'] * 100, 1), 'despues': round(s['despues']['probabilidad'] * 100, 1)}
    sem = ex['semaforo']
    if problemas:
        resumen = (f'{row.get("name") or row["id"]} ({row["course"]} {row["parallel"]}) está en {ex["semaforo_etiqueta"].lower()} ({sem}). '
                   f'Su riesgo es {_f(p)} %; el de un estudiante promedio del colegio es {_f(base)} %. '
                   f'Lo principal: {problemas[0]["titulo"].lower()}.')
    else:
        resumen = f'{row.get("name") or row["id"]} ({row["course"]} {row["parallel"]}) está en {sem}. No se ven factores de riesgo destacados.'
    return {'generado': datetime.now(timezone.utc).isoformat(), 'entorno': entorno,
            'estudiante': {'id': row['id'], 'nombre': row.get('name'), 'curso': row['course'], 'paralelo': row['parallel'],
                           'promedio': row.get('average'), 'asistencia_pct': row.get('attendance'), 'faltas_injustificadas_pct': row.get('unjustifiedAbsence'),
                           'materia_critica': row.get('materia_critica')},
            'asistencia': {'dias': asistencia or [], 'resumen': resumen_asistencia(asistencia or [])},
            'semaforo': sem, 'semaforo_etiqueta': ex['semaforo_etiqueta'], 'riesgo_pct': p, 'riesgo_promedio_colegio_pct': base,
            'resumen': resumen, 'problemas': problemas, 'fortalezas': fortalezas, 'que_hacer': acciones, 'todas_juntas': juntas,
            'seguimiento': {'etapa': (etapa or {}).get('etapa', 'IDENTIFICADO'), 'docente': (etapa or {}).get('docente_nombre'),
                            'identificado_at': (etapa or {}).get('identificado_at'), 'eventos': eventos or []},
            'como_leerlo': 'El porcentaje es una señal de alerta, no un pronóstico de que el estudiante se va a retirar: compara a este estudiante con el promedio de su colegio. '
                           'Los porcentajes de «Cómo mitigarlo» son escenarios, no promesas: solo el acompañamiento real dirá si funcionó. '
                           'Este informe es pedagógico y no incluye datos económicos.'}


# ---- Redacción con IA: la IA solo reescribe; estos dos pasos limitan lo que puede entrar y salir ----
_PROHIBIDAS = ('pensi', 'deuda', 'morosid', 'financ', 'cobro', 'pago')


def entrada_para_ia(inf):
    """Solo lo pedagógico y SIN nombre: es lo único que sale hacia la IA."""
    e = inf['estudiante']
    return {'curso': f"{e['curso']} {e['paralelo']}", 'semaforo': inf['semaforo_etiqueta'], 'riesgo_pct': inf['riesgo_pct'], 'riesgo_promedio_colegio_pct': inf['riesgo_promedio_colegio_pct'],
            'promedio': e.get('promedio'), 'asistencia_pct': e.get('asistencia_pct'), 'faltas_sin_justificar_pct': e.get('faltas_injustificadas_pct'),
            'materia_que_mas_preocupa': e.get('materia_critica'),
            'dias_registrados': inf['asistencia']['resumen'],
            'problemas': [{'titulo': p['titulo'], 'explicacion': p['explicacion']} for p in inf['problemas']],
            'acciones': [{'accion': a['accion'], 'quien': a['responsable'], 'cuando': a['cuando'], 'como': a['como'], 'riesgo_hoy_pct': a['antes'], 'riesgo_despues_pct': a['despues']}
                         for a in inf['que_hacer'] if a['tiene_efecto']]}


def validar_redaccion(out, entrada):
    """Devuelve (texto, None) o (None, motivo). Rechaza respuestas vacías, con temas económicos o con cifras que no estaban en los datos."""
    import re, json
    if not isinstance(out, dict) or not out.get('ok'): return None, 'sin respuesta válida'
    texto = {'resumen': str(out.get('resumen', ''))[:600], 'que_pasa': [str(x)[:300] for x in out.get('que_pasa', [])][:3], 'que_hacer': [str(x)[:300] for x in out.get('que_hacer', [])][:3]}
    todo = ' '.join([texto['resumen'], *texto['que_pasa'], *texto['que_hacer']])
    if len(texto['resumen']) < 20 or not texto['que_pasa'] or not texto['que_hacer']: return None, 'texto incompleto'
    if any(w in todo.lower() for w in _PROHIBIDAS): return None, 'menciona temas económicos'
    norm = lambda n: n.replace(',', '.').rstrip('.')
    permitidas = {norm(n) for n in re.findall(r'\d+(?:[.,]\d+)?', json.dumps(entrada, ensure_ascii=False))}
    permitidas |= {str(int(float(n))) for n in permitidas if re.fullmatch(r'\d+(\.\d+)?', n)}
    sobran = [n for n in map(norm, re.findall(r'\d+(?:[.,]\d+)?', todo)) if n not in permitidas and n not in ('1', '2', '3', '7')]
    if sobran: return None, 'cifras que no estaban en los datos: ' + ', '.join(sobran[:3])
    return texto, None
