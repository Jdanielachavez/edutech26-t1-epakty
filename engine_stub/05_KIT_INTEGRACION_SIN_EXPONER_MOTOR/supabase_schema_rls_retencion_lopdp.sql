-- =============================================================================
-- E-PAKTI — ESQUEMA SUPABASE POSTGRES CON RLS POR ROL Y RETENCIÓN PII (LOPDP)
-- =============================================================================
-- Soluciona los hallazgos del equipo Web/Backend:
-- 1. Plazo explícito de retención de datos personales de estudiantes (LOPDP Ecuador)
--    separando `student_pii_vault` (con expiración automática) de `student_pseudonym_vectors`
--    (lo único que viaja al Motor ML privado de Wilo y al Data Lake MLOps).
-- 2. Row-Level Security (RLS) estricto por `school_id` y `role`: Docentes/DECE/Inspección
--    NUNCA pueden consultar la tabla financiera `colecturia_wallet_alerts` en Postgres.
-- 3. Tabla `ingestion_jobs` asíncrona con `idempotency_key` para eliminar timeouts de 14s.
-- 4. Tabla `public_contact_leads` para conectar el formulario comercial de la web.

create extension if not exists "pgcrypto";

-- 1. Bóveda de Datos Personales (PII) con Plazo de Retención Legal (LOPDP Ecuador)
create table if not exists public.student_pii_vault (
    id uuid primary key default gen_random_uuid(),
    school_id text not null,
    student_pseudonym_id text not null,          -- Ej. EST-089 o SHA256 opaco enviado al Motor ML
    representative_pseudonym_id text not null,   -- Ej. REP-076
    full_name text,                              -- Se purga a NULL al vencer `pii_retention_expires_at`
    representative_email text,
    representative_whatsapp_e164 text,
    retention_policy_days integer not null default 365,
    pii_retention_expires_at timestamptz not null default (now() + interval '365 days'),
    pii_purged_at timestamptz,
    created_at timestamptz not null default now(),
    unique (school_id, student_pseudonym_id)
);

-- Función programable vía `pg_cron` (diaria a las 03:00 AM) para purgar PII vencida sin perder analítica anónima
create or replace function public.epakti_purge_expired_pii()
returns integer language plpgsql security definer as $$
declare
    purged_count integer;
begin
    update public.student_pii_vault
    set full_name = null,
        representative_email = null,
        representative_whatsapp_e164 = null,
        pii_purged_at = now()
    where pii_purged_at is null
      and pii_retention_expires_at <= now();
    get diagnostics purged_count = row_count;
    return purged_count;
end;
$$;

-- 2. Tabla Pedagógica (Visible a Docentes/Tutores/DECE/Inspección/Rectorado — CERO campos financieros)
create table if not exists public.pedagogical_alerts_snapshot (
    id uuid primary key default gen_random_uuid(),
    school_id text not null,
    cutoff_date date not null,
    student_pseudonym_id text not null,
    curso text not null,
    paralelo text not null,
    necesidad_educativa text not null default 'ninguna',
    semaforo_docente_color text not null check (semaforo_docente_color in ('VERDE','AMARILLO','NARANJA','ROJO')),
    foco_pedagogico text not null,
    semaforo_permanencia_color text not null,
    prob_permanencia_pct numeric(5,2) not null,
    semaforo_academico_color text not null,
    prob_academico_q2_pct numeric(5,2) not null,
    shap_pedagogico_json jsonb not null,
    sensibilidad_what_if_json jsonb not null,
    model_version text not null,
    updated_at timestamptz not null default now(),
    unique (school_id, cutoff_date, student_pseudonym_id)
);

-- 3. Tabla Financiera Exclusiva Colecturía (BLOQUEADA por RLS a Docentes/DECE/Inspección)
create table if not exists public.colecturia_wallet_alerts (
    id uuid primary key default gen_random_uuid(),
    school_id text not null,
    cutoff_date date not null,
    student_pseudonym_id text not null,
    representative_pseudonym_id text not null,
    semaforo_pagos_color text not null check (semaforo_pagos_color in ('VERDE','AMARILLO','NARANJA','ROJO')),
    prob_incumplimiento_o_tardio_pct numeric(5,2) not null,
    prob_dos_meses_incumpl_pct numeric(5,2) not null,
    tipologia_morosidad text not null,
    shap_financiero_json jsonb not null,
    accion_colecturia text not null,
    updated_at timestamptz not null default now(),
    unique (school_id, cutoff_date, student_pseudonym_id)
);

-- 4. Cola Asíncrona de Jobs de Ingesta/Scoring (Elimina timeouts del worker de 14s)
create table if not exists public.ingestion_jobs (
    job_id text primary key,
    school_id text not null,
    idempotency_key text not null unique,
    status text not null check (status in ('QUEUED','PROCESSING','COMPLETED','FAILED_RETRYABLE','DEAD_LETTER')),
    attempts integer not null default 0,
    max_attempts integer not null default 3,
    next_retry_at timestamptz,
    duration_ms integer,
    error_message text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- 5. Bitácora de Intervenciones (Candado MLOps contra Feedback Loops)
create table if not exists public.intervention_outcomes_log (
    id uuid primary key default gen_random_uuid(),
    school_id text not null,
    student_pseudonym_id text not null,
    rol_ejecutor text not null,
    tipo_intervencion text not null,
    canal_n8n text not null,
    intervencion_aplicada smallint not null check (intervencion_aplicada in (0, 1)),
    compromiso_resumen text,
    executed_at timestamptz not null default now()
);

-- 6. Formulario Público de Contacto Comercial de la Web (epakti.ec)
create table if not exists public.public_contact_leads (
    id uuid primary key default gen_random_uuid(),
    nombre_contacto text not null,
    institucion text not null,
    ciudad text,
    correo text not null,
    whatsapp_e164 text,
    n_estudiantes_aprox integer,
    erp_actual text,
    n8n_dispatched boolean not null default false,
    created_at timestamptz not null default now()
);

-- =============================================================================
-- ROW LEVEL SECURITY (RLS) ESTRICTO POR `school_id` Y `role` EN SUPABASE JWT
-- =============================================================================
alter table public.student_pii_vault enable row level security;
alter table public.pedagogical_alerts_snapshot enable row level security;
alter table public.colecturia_wallet_alerts enable row level security;
alter table public.intervention_outcomes_log enable row level security;

create policy "tenant_isolation_pedagogical" on public.pedagogical_alerts_snapshot
for select using (
    school_id = (auth.jwt() ->> 'school_id')
    and (auth.jwt() ->> 'role') in ('RECTORADO','DOCENTE_TUTOR','DECE','INSPECCION')
);

create policy "rbac_exclusive_colecturia" on public.colecturia_wallet_alerts
for select using (
    school_id = (auth.jwt() ->> 'school_id')
    and (auth.jwt() ->> 'role') in ('RECTORADO','COLECTURIA')
);

create policy "tenant_isolation_interventions" on public.intervention_outcomes_log
for all using (
    school_id = (auth.jwt() ->> 'school_id')
);
