# Entrada de datos escolares reales

Esta carpeta está vacía hasta que la institución entregue una extracción real,
autorizada y mapeada al contrato documentado. No copiar aquí datasets de ejemplo
ni datos inventados.

Requisitos:

- `manifest.json` con `data_mode: production`, `synthetic: false`, `approved_for_processing: true`, `institution_id`, `source_system`, `imported_at`, `approval_reference`, `payment_due_day` (1–28) y `financial_exposure_months` (entero positivo).
- CSV normalizados: `estudiantes.csv`, `asistencia.csv`, `docentes.csv`, `horarios.csv`, `notas.csv` y `pensiones.csv`, con los encabezados descritos en `../README.md` y registros reales.
- `asistencia_clase.csv` y `bienestar.csv` solo si la institución dispone de esos registros y su uso está autorizado.
- Las claves deben estar seudonimizadas antes de entrar al sistema. Los nombres y contactos se guardan en un sistema institucional separado, no en los datos enviados a Bedrock.

El pipeline rechaza esta carpeta mientras no haya manifiesto válido, datos reales
y un artefacto de modelo supervisado aprobado. No se rellenan valores faltantes
con datos de demostración.
