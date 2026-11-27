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
