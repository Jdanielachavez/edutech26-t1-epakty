-- Análisis de evaluaciones: resultados por pregunta de exámenes (leídos de fotos o cargados por CSV). La foto original NO se guarda.
-- Pegar en Supabase › SQL Editor › Run. Es seguro correrlo más de una vez.
CREATE TABLE IF NOT EXISTS paktai_edu.evaluaciones (
 id uuid PRIMARY KEY, institution_id text NOT NULL, titulo text NOT NULL, materia text NOT NULL, curso text NOT NULL, paralelo text NOT NULL,
 fecha date, estado text NOT NULL DEFAULT 'PROCESANDO' CHECK(estado IN ('PROCESANDO','POR_REVISAR','CONFIRMADA','ERROR')),
 origen text NOT NULL DEFAULT 'FOTOS' CHECK(origen IN ('FOTOS','CSV')), n_hojas integer NOT NULL DEFAULT 0, error text,
 creado_por text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 retention_expires_at timestamptz NOT NULL DEFAULT now()+interval '365 days'
);
CREATE TABLE IF NOT EXISTS paktai_edu.evaluacion_preguntas (
 evaluacion_id uuid NOT NULL REFERENCES paktai_edu.evaluaciones(id) ON DELETE CASCADE, institution_id text NOT NULL,
 numero integer NOT NULL CHECK(numero BETWEEN 1 AND 300), tema text CHECK(tema IS NULL OR char_length(tema) <= 80),
 PRIMARY KEY(evaluacion_id,numero)
);
CREATE TABLE IF NOT EXISTS paktai_edu.evaluacion_resultados (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, institution_id text NOT NULL,
 evaluacion_id uuid NOT NULL REFERENCES paktai_edu.evaluaciones(id) ON DELETE CASCADE, hoja integer NOT NULL,
 codigo_estudiante text CHECK(codigo_estudiante IS NULL OR codigo_estudiante ~ '^[A-Za-z0-9-]{1,24}$'),
 pregunta integer NOT NULL CHECK(pregunta BETWEEN 1 AND 300), correcta boolean, puntaje numeric, puntaje_max numeric
);
CREATE INDEX IF NOT EXISTS idx_eval_res ON paktai_edu.evaluacion_resultados(evaluacion_id,pregunta);
CREATE INDEX IF NOT EXISTS idx_eval_curso ON paktai_edu.evaluaciones(institution_id,curso,paralelo,created_at DESC);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['evaluaciones','evaluacion_preguntas','evaluacion_resultados'] LOOP
  EXECUTE format('ALTER TABLE paktai_edu.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE paktai_edu.%I FORCE ROW LEVEL SECURITY',t);
  IF NOT EXISTS(SELECT FROM pg_policies WHERE schemaname='paktai_edu' AND tablename=t AND policyname='institution_scope') THEN
   EXECUTE format('CREATE POLICY institution_scope ON paktai_edu.%I TO paktai_service USING (institution_id=current_setting(''paktai.institution_id'',true)) WITH CHECK (institution_id=current_setting(''paktai.institution_id'',true))',t);
  END IF;
 END LOOP;
END $$;
GRANT SELECT,INSERT,UPDATE ON paktai_edu.evaluaciones,paktai_edu.evaluacion_preguntas TO paktai_service;
GRANT SELECT,INSERT,DELETE ON paktai_edu.evaluacion_resultados TO paktai_service;
GRANT DELETE ON paktai_edu.evaluacion_preguntas TO paktai_service;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA paktai_edu TO paktai_service;
