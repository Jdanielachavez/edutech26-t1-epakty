"""Validate the official six-table contract before any write or join."""
import csv
import math
from datetime import date, time
from pathlib import Path

TABLES = {
    'estudiantes': ('codigo nombre_ficticio curso paralelo anio_nacimiento genero necesidad_educativa beca_porcentaje representante_codigo fecha_ingreso', ('codigo',)),
    'docentes': ('codigo nombre_ficticio materia_principal', ('codigo',)),
    'asistencia': ('codigo_estudiante fecha estado', ('codigo_estudiante', 'fecha')),
    'notas': ('codigo_estudiante anio_lectivo quimestre parcial materia nota', ('codigo_estudiante', 'anio_lectivo', 'quimestre', 'parcial', 'materia')),
    'pensiones': ('codigo_estudiante mes valor estado fecha_pago', ('codigo_estudiante', 'mes')),
    'horarios': ('curso paralelo dia hora_inicio hora_fin materia docente_codigo', ('curso', 'paralelo', 'dia', 'hora_inicio')),
}
class DataValidationError(ValueError):
    pass

def validate_source(source: Path) -> dict:
    tables = {}
    def check(ok, message):
        if not ok:
            raise DataValidationError(message)
    def numeric(row, field, low, high):
        try:
            n = float(row[field])
        except (KeyError, ValueError, TypeError):
            raise DataValidationError(f'{table} fila {index}: {field} debe ser numérico') from None
        check(math.isfinite(n) and low <= n <= high, f'{table} fila {index}: {field} fuera de rango')
        return n
    for table, (columns, key) in TABLES.items():
        path = source / f'{table}.csv'
        check(path.is_file(), f'Falta {table}.csv')
        try:
            with path.open(encoding='utf-8-sig', newline='') as stream:
                reader = csv.DictReader(stream)
                check(set(columns.split()) <= set(reader.fieldnames or []), f'{table}: faltan columnas obligatorias')
                rows = list(reader)
        except (UnicodeError, csv.Error):
            raise DataValidationError(f'{table}: CSV inválido') from None
        check(len(rows) <= 1_000_000, f'{table}: límite de filas excedido')
        seen = set()
        for index, row in enumerate(rows, 2):
            check(None not in row and None not in row.values(), f'{table} fila {index}: estructura irregular')
            required = set(columns.split()) - {'fecha_pago', 'necesidad_educativa'}
            check(all(row.get(f, '').strip() for f in required), f'{table} fila {index}: campo obligatorio vacío')
            pk = tuple(row[f] for f in key)
            check(pk not in seen, f'{table} fila {index}: llave duplicada')
            seen.add(pk)
            try:
                if table == 'estudiantes':
                    year = numeric(row, 'anio_nacimiento', 1900, date.today().year)
                    check(year.is_integer(), 'anio_nacimiento debe ser entero')
                    numeric(row, 'beca_porcentaje', 0, 100)
                    date.fromisoformat(row['fecha_ingreso'])
                    if 'tiene_nee' in row:
                        check(row['tiene_nee'] in ('0', '1'), 'tiene_nee debe ser 0 o 1')
                elif table == 'notas':
                    numeric(row, 'nota', 0, 10)
                    check(row['quimestre'] in ('1', '2') and row['parcial'] in ('1', '2', '3'), 'Corte académico inválido')
                elif table == 'pensiones':
                    numeric(row, 'valor', 0, 1e8)
                    date.fromisoformat(row['mes'] + '-01')
                    check(row['estado'] in ('pagado', 'vencido', 'por_vencer'), 'Estado de pensión inválido')
                    if row['fecha_pago']:
                        date.fromisoformat(row['fecha_pago'])
                    check(row['estado'] != 'pagado' or bool(row['fecha_pago']), 'Pensión pagada sin fecha')
                elif table == 'asistencia':
                    date.fromisoformat(row['fecha'])
                    check(row['estado'] in ('presente', 'atraso', 'falta_justificada', 'falta_injustificada'), 'Estado de asistencia inválido')
                elif table == 'horarios':
                    check(time.fromisoformat(row['hora_inicio']) < time.fromisoformat(row['hora_fin']), 'Horario inválido')
            except (ValueError, TypeError) as error:
                if isinstance(error, DataValidationError):
                    raise
                raise DataValidationError(f'{table} fila {index}: formato inválido') from None
        tables[table] = rows
    students = {r['codigo']: r for r in tables['estudiantes']}
    teachers = {r['codigo'] for r in tables['docentes']}
    check(bool(students), 'No hay estudiantes')
    assignments = {(r['curso'], r['paralelo'], r['materia']) for r in tables['horarios']}
    for name in ('notas', 'asistencia', 'pensiones'):
        for row in tables[name]:
            check(row['codigo_estudiante'] in students, f'{name}: estudiante inexistente')
            if name == 'notas':
                student = students[row['codigo_estudiante']]
                check((student['curso'], student['paralelo'], row['materia']) in assignments, 'Nota con materia sin horario del curso')
    check(all(r['docente_codigo'] in teachers for r in tables['horarios']), 'Horario con docente inexistente')
    # Optional source: preserve unknown values, reject impossible measurements.
    optional = source / 'bienestar.csv'
    if optional.exists():
        with optional.open(encoding='utf-8-sig') as stream:
            for row in csv.DictReader(stream):
                check(row.get('codigo_estudiante') in students, 'Bienestar: estudiante inexistente')
                if row.get('score_bienestar', '').strip():
                    table, index = 'bienestar', 0
                    numeric(row, 'score_bienestar', 1, 5)
    return tables
