-- Permite que administración elimine cargas del historial (Carga de datos · Historial de cargas).
-- Al borrar la carga que alimenta las pantallas se borran también sus resultados y el seguimiento de esos estudiantes,
-- para empezar una demostración desde cero. La regla institution_scope sigue limitando el borrado al propio colegio.
GRANT DELETE ON paktai_edu.pipeline_runs, paktai_edu.bronze_rows, paktai_edu.silver_estudiantes, paktai_edu.ingestion_jobs,
  paktai_edu.gold_estudiantes, paktai_edu.intervenciones_dece, paktai_edu.seguimiento, paktai_edu.seguimiento_etapas,
  paktai_edu.intervention_outcomes, paktai_edu.outbox TO paktai_service;
