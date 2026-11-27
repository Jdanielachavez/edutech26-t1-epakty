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
