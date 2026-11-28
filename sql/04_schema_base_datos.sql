-- PostgreSQL 15+. Isolated from the existing PAKTAI GEO public schema.
BEGIN;
CREATE SCHEMA IF NOT EXISTS paktai_edu;
REVOKE ALL ON SCHEMA paktai_edu FROM PUBLIC;
DO $$ BEGIN
 IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='paktai_service') THEN CREATE ROLE paktai_service NOLOGIN NOBYPASSRLS; END IF;
 IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='rectoria_read') THEN CREATE ROLE rectoria_read NOLOGIN NOBYPASSRLS; END IF;
 IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='dece_write') THEN CREATE ROLE dece_write NOLOGIN NOBYPASSRLS; END IF;
 IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='tutor_read') THEN CREATE ROLE tutor_read NOLOGIN NOBYPASSRLS; END IF;
END $$;
CREATE TABLE IF NOT EXISTS paktai_edu.pipeline_runs (
 institution_id text NOT NULL, run_id text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 data_mode text NOT NULL CHECK(data_mode='synthetic_official'), model jsonb NOT NULL,
 source_hashes jsonb NOT NULL, summary jsonb NOT NULL, PRIMARY KEY(institution_id,run_id)
);
CREATE TABLE IF NOT EXISTS paktai_edu.bronze_rows (
 institution_id text NOT NULL, run_id text NOT NULL, source_table text NOT NULL, row_number integer NOT NULL,
 payload jsonb NOT NULL, PRIMARY KEY(institution_id,run_id,source_table,row_number),
 FOREIGN KEY(institution_id,run_id) REFERENCES paktai_edu.pipeline_runs
);
CREATE TABLE IF NOT EXISTS paktai_edu.silver_estudiantes (
 institution_id text NOT NULL, run_id text NOT NULL, id_estudiante text NOT NULL, payload jsonb NOT NULL,
 PRIMARY KEY(institution_id,run_id,id_estudiante), FOREIGN KEY(institution_id,run_id) REFERENCES paktai_edu.pipeline_runs
);
CREATE TABLE IF NOT EXISTS paktai_edu.gold_estudiantes (
 institution_id text NOT NULL, id_estudiante text NOT NULL, run_id text NOT NULL,
 nivel_riesgo text NOT NULL CHECK(nivel_riesgo IN ('Bajo','Moderado','Crítico')),
 grado_curso text NOT NULL, paralelo text NOT NULL, probabilidad numeric NOT NULL CHECK(probabilidad BETWEEN 0 AND 1),
 saldo_mora numeric NOT NULL CHECK(saldo_mora>=0), payload jsonb NOT NULL,
 updated_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(institution_id,id_estudiante),
 FOREIGN KEY(institution_id,run_id) REFERENCES paktai_edu.pipeline_runs
);
CREATE INDEX IF NOT EXISTS idx_gold_riesgo ON paktai_edu.gold_estudiantes(institution_id,nivel_riesgo);
CREATE INDEX IF NOT EXISTS idx_gold_curso ON paktai_edu.gold_estudiantes(institution_id,grado_curso,paralelo);
CREATE TABLE IF NOT EXISTS paktai_edu.intervenciones_dece (
 id uuid PRIMARY KEY, institution_id text NOT NULL, id_estudiante text NOT NULL,
 estado_caso text NOT NULL DEFAULT 'ABIERTA' CHECK(estado_caso IN ('ABIERTA','EN_SEGUIMIENTO','RETENIDO','RETIRO')),
 probabilidad numeric NOT NULL CHECK(probabilidad BETWEEN 0 AND 1), value_risk_usd numeric NOT NULL CHECK(value_risk_usd>=0),
 agent jsonb, delivery_state text NOT NULL DEFAULT 'PENDIENTE_REVISION_HUMANA',
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(institution_id,id_estudiante) REFERENCES paktai_edu.gold_estudiantes
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_interv_un_caso_abierto ON paktai_edu.intervenciones_dece(institution_id,id_estudiante)
 WHERE estado_caso IN ('ABIERTA','EN_SEGUIMIENTO');
CREATE INDEX IF NOT EXISTS idx_interv_estado ON paktai_edu.intervenciones_dece(institution_id,estado_caso);
CREATE TABLE IF NOT EXISTS paktai_edu.outbox (
 id uuid PRIMARY KEY, institution_id text NOT NULL, event_key text NOT NULL, kind text NOT NULL,
 payload jsonb NOT NULL, state text NOT NULL DEFAULT 'PENDING' CHECK(state IN ('PENDING','SENDING','SENT','FAILED','UNCERTAIN')),
 attempts integer NOT NULL DEFAULT 0, available_at timestamptz NOT NULL DEFAULT now(),
 locked_at timestamptz, last_status integer, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(institution_id,event_key)
);
CREATE INDEX IF NOT EXISTS idx_outbox_pending ON paktai_edu.outbox(institution_id,state,available_at);
CREATE TABLE IF NOT EXISTS paktai_edu.audit_events (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, institution_id text NOT NULL,
 event text NOT NULL, details jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
-- EP-11: intervenciones aplicadas (retorno desde n8n o la interfaz). Alimenta el candado MLOps contra feedback loops.
CREATE TABLE IF NOT EXISTS paktai_edu.intervention_outcomes (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, institution_id text NOT NULL, codigo_estudiante text NOT NULL,
 rol_ejecutor text NOT NULL, tipo_intervencion text NOT NULL, canal text NOT NULL, aplicada boolean NOT NULL,
 fecha_ejecucion timestamptz NOT NULL, compromiso text, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_outcomes_estudiante ON paktai_edu.intervention_outcomes(institution_id,codigo_estudiante);
-- LOPDP: bóveda de datos personales con vencimiento. Bronze/Silver/Gold solo guardan el seudónimo (EST-xxx).
CREATE TABLE IF NOT EXISTS paktai_edu.student_pii_vault (
 institution_id text NOT NULL, student_pseudonym_id text NOT NULL, representative_pseudonym_id text NOT NULL DEFAULT '',
 full_name text, representative_email text, representative_whatsapp_e164 text,
 retention_policy_days integer NOT NULL DEFAULT 365 CHECK(retention_policy_days BETWEEN 1 AND 3650),
 pii_retention_expires_at timestamptz NOT NULL, pii_purged_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(institution_id,student_pseudonym_id)
);
-- EP-02/EP-02B: cola de ingesta asíncrona (202 Accepted + consulta del estado).
CREATE TABLE IF NOT EXISTS paktai_edu.ingestion_jobs (
 job_id text PRIMARY KEY, institution_id text NOT NULL, idempotency_key text NOT NULL, source text NOT NULL,
 status text NOT NULL CHECK(status IN ('QUEUED','PROCESSING','COMPLETED','FAILED_RETRYABLE','DEAD_LETTER')),
 attempts integer NOT NULL DEFAULT 0, max_attempts integer NOT NULL DEFAULT 3, next_retry_at timestamptz,
 duration_ms integer, error_message text, payload jsonb, hashes jsonb, result jsonb,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(institution_id,idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_jobs_pending ON paktai_edu.ingestion_jobs(institution_id,status,next_retry_at);
-- EP-19: formulario público de contacto. Datos personales con vencimiento; no pertenece a ningún colegio.
-- Usuarios con contraseña (solo el hash scrypt). La administración los crea desde la interfaz.
CREATE TABLE IF NOT EXISTS paktai_edu.app_users (
 institution_id text NOT NULL, username text NOT NULL, password_hash text NOT NULL,
 role text NOT NULL, display_name text, course text, parallel text,
 active boolean NOT NULL DEFAULT true, must_change_password boolean NOT NULL DEFAULT false,
 created_by text, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 last_login_at timestamptz, PRIMARY KEY(institution_id,username),
 CHECK(username ~ '^[a-z0-9._-]{3,40}$')
);
CREATE TABLE IF NOT EXISTS paktai_edu.public_contact_leads (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), nombre_contacto text NOT NULL, institucion text NOT NULL, ciudad text,
 correo text NOT NULL, whatsapp_e164 text, n_estudiantes_aprox integer, erp_actual text, mensaje text,
 n8n_dispatched boolean NOT NULL DEFAULT false, retention_expires_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE paktai_edu.public_contact_leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE paktai_edu.public_contact_leads FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
 IF NOT EXISTS(SELECT FROM pg_policies WHERE schemaname='paktai_edu' AND tablename='public_contact_leads' AND policyname='leads_service') THEN
  CREATE POLICY leads_service ON paktai_edu.public_contact_leads TO paktai_service USING (true) WITH CHECK (true);
 END IF;
END $$;
-- No anonymous, public or authenticated Supabase grants. All access goes through API.
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['pipeline_runs','bronze_rows','silver_estudiantes','gold_estudiantes','intervenciones_dece','outbox','audit_events','intervention_outcomes','student_pii_vault','ingestion_jobs','app_users'] LOOP
  EXECUTE format('ALTER TABLE paktai_edu.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE paktai_edu.%I FORCE ROW LEVEL SECURITY',t);
  IF NOT EXISTS(SELECT FROM pg_policies WHERE schemaname='paktai_edu' AND tablename=t AND policyname='institution_scope') THEN
   EXECUTE format('CREATE POLICY institution_scope ON paktai_edu.%I TO paktai_service USING (institution_id=current_setting(''paktai.institution_id'',true)) WITH CHECK (institution_id=current_setting(''paktai.institution_id'',true))',t);
  END IF;
 END LOOP;
END $$;
GRANT USAGE ON SCHEMA paktai_edu TO paktai_service,rectoria_read,dece_write,tutor_read;
GRANT SELECT,INSERT,UPDATE ON ALL TABLES IN SCHEMA paktai_edu TO paktai_service;
-- Solo las cuentas de acceso se pueden borrar; el resto de tablas guarda historial.
GRANT DELETE ON paktai_edu.app_users TO paktai_service;
GRANT DELETE ON paktai_edu.pipeline_runs, paktai_edu.bronze_rows, paktai_edu.silver_estudiantes, paktai_edu.ingestion_jobs TO paktai_service;
REVOKE UPDATE ON paktai_edu.audit_events FROM paktai_service;
REVOKE UPDATE ON paktai_edu.intervention_outcomes FROM paktai_service;
-- Solo la purga LOPDP borra, y solo leads vencidos.
GRANT DELETE ON paktai_edu.public_contact_leads TO paktai_service;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA paktai_edu TO paktai_service;
-- Aggregate view deliberately excludes names, NEE and individual wellbeing.
-- security_invoker: la vista se ejecuta con los permisos y las políticas RLS de quien la consulta
-- (paktai_service), no con las del dueño. Sin esto el dueño de la migración podía ver 0 filas.
CREATE OR REPLACE VIEW paktai_edu.vista_kpi_rectoria WITH (security_barrier=true, security_invoker=true) AS
 SELECT institution_id,count(*) estudiantes,
 count(*) FILTER(WHERE nivel_riesgo='Crítico') criticos,
 count(*) FILTER(WHERE nivel_riesgo='Moderado') moderados,
 count(*) FILTER(WHERE nivel_riesgo='Bajo') bajos,sum(saldo_mora) cartera_mora
 FROM paktai_edu.gold_estudiantes WHERE institution_id=current_setting('paktai.institution_id',true) GROUP BY institution_id;
CREATE OR REPLACE VIEW paktai_edu.vista_tutor WITH (security_barrier=true, security_invoker=true) AS
 SELECT institution_id,id_estudiante,grado_curso,paralelo,nivel_riesgo,
 payload->'average' promedio,payload->'materia_critica' materia_critica,payload->'attendance' asistencia
 FROM paktai_edu.gold_estudiantes WHERE institution_id=current_setting('paktai.institution_id',true)
 AND grado_curso=current_setting('paktai.course',true) AND paralelo=current_setting('paktai.parallel',true);
-- El GRANT ... ON ALL TABLES de arriba se ejecuta ANTES de crear las vistas y no las cubre:
-- la API (SET ROLE paktai_service) recibía "permission denied" al leer el resumen.
GRANT SELECT ON paktai_edu.vista_kpi_rectoria, paktai_edu.vista_tutor TO paktai_service;
GRANT SELECT ON paktai_edu.vista_kpi_rectoria TO rectoria_read;
GRANT SELECT ON paktai_edu.vista_tutor TO tutor_read;
GRANT SELECT ON paktai_edu.gold_estudiantes,paktai_edu.intervenciones_dece TO dece_write;
GRANT UPDATE(estado_caso,updated_at) ON paktai_edu.intervenciones_dece TO dece_write;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['gold_estudiantes','intervenciones_dece'] LOOP
  IF NOT EXISTS(SELECT FROM pg_policies WHERE schemaname='paktai_edu' AND tablename=t AND policyname='dece_scope') THEN
   EXECUTE format('CREATE POLICY dece_scope ON paktai_edu.%I TO dece_write USING (institution_id=current_setting(''paktai.institution_id'',true)) WITH CHECK (institution_id=current_setting(''paktai.institution_id'',true))',t);
  END IF;
 END LOOP;
END $$;
-- Purga diaria LOPDP (worker o pg_cron): borra nombres y contactos vencidos sin perder la analítica seudonimizada.
CREATE OR REPLACE FUNCTION paktai_edu.epakti_purge_expired_pii() RETURNS integer
 LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, paktai_edu AS $fn$
DECLARE n integer; m integer;
BEGIN
 UPDATE paktai_edu.student_pii_vault SET full_name=NULL,representative_email=NULL,representative_whatsapp_e164=NULL,pii_purged_at=now()
  WHERE pii_purged_at IS NULL AND pii_retention_expires_at<=now();
 GET DIAGNOSTICS n = ROW_COUNT;
 DELETE FROM paktai_edu.public_contact_leads WHERE retention_expires_at<=now();
 GET DIAGNOSTICS m = ROW_COUNT;
 -- Datos crudos de trabajos fallidos que nadie reintentó en 30 días.
 UPDATE paktai_edu.ingestion_jobs SET payload=NULL WHERE payload IS NOT NULL AND status='DEAD_LETTER' AND updated_at<now()-interval '30 days';
 RETURN n+m;
END $fn$;
REVOKE ALL ON FUNCTION paktai_edu.epakti_purge_expired_pii() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION paktai_edu.epakti_purge_expired_pii() TO paktai_service;
-- Columnas de reserva de borradores: dentro de la misma transacción (antes estaban después del COMMIT).
ALTER TABLE paktai_edu.intervenciones_dece ADD COLUMN IF NOT EXISTS draft_lease uuid;
ALTER TABLE paktai_edu.intervenciones_dece ADD COLUMN IF NOT EXISTS draft_lease_until timestamptz;
COMMIT;

-- Seguimiento de estudiantes (ver sql/05_seguimiento.sql)
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

-- Análisis de evaluaciones (ver sql/06_evaluaciones.sql)
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

-- Tracking por etapas (ver sql/07_etapas.sql)
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
