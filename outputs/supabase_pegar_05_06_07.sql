-- Seguimiento de estudiantes en el tiempo: notas de acompañamiento (solo se agregan; no se editan ni se borran).
-- Pegar en Supabase › SQL Editor › Run (y se aplica igual a la base local). Es seguro correrlo más de una vez.
CREATE TABLE IF NOT EXISTS paktai_edu.seguimiento (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, institution_id text NOT NULL, id_estudiante text NOT NULL,
 tipo text NOT NULL CHECK(tipo IN ('NOTA','LLAMADA','REUNION','TUTORIA','ACOMPANAMIENTO')),
 nota text NOT NULL CHECK(char_length(nota) BETWEEN 3 AND 1000),
 autor_usuario text NOT NULL, autor_rol text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), retention_expires_at timestamptz NOT NULL DEFAULT now()+interval '365 days'
);
CREATE INDEX IF NOT EXISTS idx_seguimiento_estudiante ON paktai_edu.seguimiento(institution_id,id_estudiante,created_at DESC);
ALTER TABLE paktai_edu.seguimiento ENABLE ROW LEVEL SECURITY;
ALTER TABLE paktai_edu.seguimiento FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
 IF NOT EXISTS(SELECT FROM pg_policies WHERE schemaname='paktai_edu' AND tablename='seguimiento' AND policyname='institution_scope') THEN
  CREATE POLICY institution_scope ON paktai_edu.seguimiento TO paktai_service
   USING (institution_id=current_setting('paktai.institution_id',true)) WITH CHECK (institution_id=current_setting('paktai.institution_id',true));
 END IF;
END $$;
GRANT SELECT,INSERT ON paktai_edu.seguimiento TO paktai_service;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA paktai_edu TO paktai_service;
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
-- Tracking del seguimiento por etapas: Identificado -> Docente avisado -> Reunión con la familia -> Cerrado.
-- Pegar en Supabase › SQL Editor › Run. Es seguro correrlo más de una vez.
CREATE TABLE IF NOT EXISTS paktai_edu.seguimiento_etapas (
 institution_id text NOT NULL, id_estudiante text NOT NULL,
 etapa text NOT NULL DEFAULT 'IDENTIFICADO' CHECK(etapa IN ('IDENTIFICADO','DOCENTE_AVISADO','REUNION_FAMILIA','CERRADO')),
 identificado_at timestamptz NOT NULL DEFAULT now(), docente_avisado_at timestamptz, reunion_familia_at timestamptz, cerrado_at timestamptz,
 docente_nombre text CHECK(docente_nombre IS NULL OR char_length(docente_nombre) BETWEEN 2 AND 120), docente_correo text,
 actualizado_por text, updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(institution_id,id_estudiante)
);
ALTER TABLE paktai_edu.seguimiento_etapas ENABLE ROW LEVEL SECURITY;
ALTER TABLE paktai_edu.seguimiento_etapas FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
 IF NOT EXISTS(SELECT FROM pg_policies WHERE schemaname='paktai_edu' AND tablename='seguimiento_etapas' AND policyname='institution_scope') THEN
  CREATE POLICY institution_scope ON paktai_edu.seguimiento_etapas TO paktai_service
   USING (institution_id=current_setting('paktai.institution_id',true)) WITH CHECK (institution_id=current_setting('paktai.institution_id',true));
 END IF;
END $$;
GRANT SELECT,INSERT,UPDATE ON paktai_edu.seguimiento_etapas TO paktai_service;
-- Estudiantes ya cargados antes de esta tabla: quedan «Identificados» con la fecha de la última carga.
INSERT INTO paktai_edu.seguimiento_etapas(institution_id,id_estudiante,identificado_at)
SELECT g.institution_id,g.id_estudiante,coalesce((SELECT max(r.created_at) FROM paktai_edu.pipeline_runs r WHERE r.institution_id=g.institution_id),now())
FROM paktai_edu.gold_estudiantes g WHERE g.nivel_riesgo<>'Bajo' ON CONFLICT DO NOTHING;
