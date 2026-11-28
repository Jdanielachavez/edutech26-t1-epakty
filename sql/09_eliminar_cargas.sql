-- Permite que administración elimine una carga del historial (Carga de datos · Historial de cargas).
-- Solo afecta a las tablas de esa carga; la regla institution_scope sigue limitando el borrado al propio colegio.
-- La carga que alimenta las pantallas (gold_estudiantes) no se puede borrar: la API lo impide.
GRANT DELETE ON paktai_edu.pipeline_runs, paktai_edu.bronze_rows, paktai_edu.silver_estudiantes, paktai_edu.ingestion_jobs TO paktai_service;
