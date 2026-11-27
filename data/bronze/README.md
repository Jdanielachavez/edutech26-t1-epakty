# Bronze · fuentes originales

Bronze conserva datos de origen sin transformar. La ruta activa es
`production/`; solo puede recibir extracciones institucionales reales,
autorizadas y seudonimizadas. Está vacía mientras la institución no entregue
sus archivos.

## Fuentes públicas

`public/` contiene agregados de AMIE y ENEMDU, además de un extracto agregado de
INEVAL. Son referencias de contexto y nunca se asignan a expedientes individuales.
Para actualizar AMIE y ENEMDU ejecuta `python3 scripts/sync_public_sources.py
--force`. La generación de indicadores estudiantiles también requiere un modelo
supervisado aprobado; sin él, Silver/Gold y la API permanecen bloqueados.

## Contratos institucionales

Los CSV escolares se entregan en `production/` con estos nombres y campos:

- `estudiantes.csv`: `codigo,alias,curso,paralelo,tiene_nee,beca_porcentaje,representante_codigo,fecha_ingreso`. `codigo`, `alias` y el representante deben estar seudonimizados; `tiene_nee` es un indicador 0/1, sin diagnóstico.
- `asistencia.csv`: `codigo_estudiante,fecha,estado`.
- `docentes.csv`: `codigo,alias,materia_principal`, con identificador seudonimizado.
- `horarios.csv`: `curso,paralelo,dia,hora_inicio,hora_fin,materia,docente_codigo`.
- `notas.csv`: `codigo_estudiante,anio_lectivo,quimestre,parcial,materia,nota`.
- `pensiones.csv`: `codigo_estudiante,mes,valor,estado,fecha_pago`.
- `asistencia_clase.csv` (si existe): `codigo_estudiante,fecha,materia,estado,hora_inicio,es_primera_hora`.
- `bienestar.csv` (si existe): `codigo_estudiante,fecha_corte,score_bienestar`.
- `resultados_historicos.csv`: `codigo_estudiante,fecha_corte,fecha_resultado,resultado_final`, con resultados confirmados `PERMANECE` o `RETIRA`.

El manifiesto `production/manifest.json` registra la institución, origen,
autorización, fecha de extracción, día de vencimiento y exposición financiera
usada por la institución. No reemplazar esos valores con supuestos.

La racha de faltas se calcula sobre registros ordenados por fecha. El
ausentismo de primera hora y el indicador de bienestar requieren sus CSV
específicos. La tasa de reprobación por docente es contexto descriptivo, no un
efecto causal. El proxy de desvinculación no reemplaza un resultado
administrativo confirmado.
