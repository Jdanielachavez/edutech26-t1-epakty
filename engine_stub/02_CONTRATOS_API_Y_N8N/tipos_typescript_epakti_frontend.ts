/**
 * E-Pakti EduTech SaaS — Contratos TypeScript & Design Tokens para Frontend (Next.js / React)
 * Sincronizado con `openapi_especificacion_endpoints_ui_n8n.json` (20 Endpoints: EP-01 a EP-19 + EP-02B)
 * y con el Contract Stub Server (`05_KIT_INTEGRACION_SIN_EXPONER_MOTOR/epakti_engine_stub_server.py`).
 */

export type EpaktiPlane = "TENANT_SCHOOL" | "EPAKTI_CONTROL_PLANE";

export type TenantRole =
  | "RECTORADO"
  | "DOCENTE_TUTOR"
  | "DECE"
  | "INSPECCION"
  | "COLECTURIA"
  | "ADMISIONES";

export type EpaktiInternalRole =
  | "EPAKTI_CEO"
  | "EPAKTI_MLOPS"
  | "EPAKTI_DATA_SCIENCE"
  | "EPAKTI_CS";

export type SemaforoColor = "VERDE" | "AMARILLO" | "NARANJA" | "ROJO";

export const DESIGN_TOKENS_EPAKTI = {
  brand: {
    name: "E-Pakti",
    tenantAppUrl: "https://app.epakti.ec",
    adminControlPlaneUrl: "https://admin.epakti.ec",
    apiBaseUrl: "https://api.epakti.ec/api/v1",
  },
  planes: {
    tenantBg: "#F8FAFC",
    tenantCard: "#FFFFFF",
    tenantBorder: "#E2E8F0",
    adminBg: "#0F172A",
    adminCard: "#1E293B",
    adminBorder: "#334155",
  },
  semaforo: {
    VERDE: { hex: "#1B9E77", bg: "#E8F8F5", border: "#A3E4D7", label: "Acompañamiento Regular" },
    AMARILLO: { hex: "#D4AC0D", bg: "#FEF9E7", border: "#F9E79F", label: "Observación Preventiva" },
    NARANJA: { hex: "#D95F02", bg: "#FDF2E9", border: "#F5CBA7", label: "Apoyo Focalizado" },
    ROJO: { hex: "#C0392B", bg: "#FDEDEC", border: "#F5B7B1", label: "Intervención Prioritaria" },
  },
} as const;

// ============================================================================
// PLANO A — PORTAL DEL COLEGIO CLIENTE (EP-01 a EP-11)
// ============================================================================

/** EP-04: GET /api/v1/dashboard/rectorado/kpis-roi */
export interface RectoradoKpisRoiResponse {
  colegiatura_anual_total_240_alumnos_usd: number;
  colegiatura_restante_8_meses_total_usd: number;
  pension_mensual_neta_promedio_usd: number;
  alumnos_en_alerta_pedagogica_rojo_naranja: number;
  alumnos_en_alerta_financiera_rojo_naranja: number;
  alumnos_totales_en_alerta_360: number;
  cartera_restante_expuesta_en_alertas_360_usd: number;
  perdida_esperada_sin_intervencion_usd: number;
  ahorro_esperado_por_intervencion_360_top40_usd: number;
  ahorro_esperado_por_intervencion_360_plantel_usd: number;
}

/** EP-05: GET /api/v1/dashboard/docente-tutor/triage (CERO datos financieros — LOPDP/LOEI) */
export interface EstudianteTriageDocente {
  codigo_estudiante: string;
  nombre_ficticio: string;
  curso_paralelo: string;
  necesidad_educativa: "ninguna" | "TDAH" | "TEA" | "discalculia" | "dislexia" | "discapacidad visual";
  sobreedad_anios: number;
  semaforo_docente_color: SemaforoColor;
  foco_pedagogico:
    | "Doble Foco: Permanencia + Aprendizaje"
    | "Foco Principal: Aprendizaje (Notas < 7)"
    | "Foco Principal: Asistencia y Permanencia"
    | "Seguimiento Preventivo Regular";
  semaforo_permanencia_color: SemaforoColor;
  prob_oof_ausentismo_pct: number;
  semaforo_academico_color: SemaforoColor;
  prob_oof_riesgo_academico_q2_pct: number;
  materia_critica_corte: string;
  palanca_optima_recomendada: string;
}

/** EP-06: GET /api/v1/students/{codigo_estudiante}/ficha-360 */
export interface Ficha360ShapResponse {
  codigo_estudiante: string;
  nombre_ficticio: string;
  prob_base_plantel_pct: number;
  prob_actual_ausentismo_oof_pct: number;
  prob_actual_ausentismo_full_pct: number;
  desglose_shap_4_niveles_pp: {
    micro_asistencia_pp: number;
    micro_academico_nee_pp: number;
    sinergia_doble_vulnerabilidad_pp: number;
    contexto_meso_macro_film_pp: number;
  };
  top_3_impulsores_shap: string[];
  simulador_contrafactual_what_if: {
    reduccion_plan_asistencia_pp: number;
    reduccion_tutoria_y_nee_pp: number;
    reduccion_paquete_integral_360_pp: number;
    prob_post_intervencion_360_pct: number;
  };
}

/** EP-08: GET /api/v1/dashboard/colecturia/cartera-hogares (EXCLUSIVO COLECTURÍA/RECTORADO) */
export interface ColecturiaCasoShap {
  codigo_estudiante: string;
  representante_codigo: string;
  n_hermanos_en_plantel: number;
  semaforo_pagos_color: SemaforoColor;
  semaforo_pagos_etiqueta: string;
  prob_incumplimiento_nov_ene_pct: number;
  prob_morosidad_cronica_2m_pct: number;
  tipologia_morosidad: string;
  por_que_morosidad_shap: string;
  accion_recomendada_colecturia: string;
}

/** EP-03: POST /api/v1/admissions/evaluate-applicant (Inferencia N=1) */
export interface PreIngresoEvaluationResponse {
  vista_admision_pedagogica_dece: {
    semaforo_ingreso_educativo: SemaforoColor;
    etiqueta: string;
    prob_riesgo_academico_pct: number;
    indice_estabilidad_educativa_0_100: number;
    protocolo_dia_1: string;
  };
  vista_admision_financiera_solo_colecturia: {
    semaforo_ingreso_financiero: Exclude<SemaforoColor, "NARANJA">;
    etiqueta: string;
    prob_incumplimiento_pago_pct: number;
    prob_morosidad_cronica_2m_pct: number;
    protocolo_matricula: string;
  };
}

/** EP-11: POST /api/v1/interventions/log-outcome (Candado MLOps Feedback Loop) */
export interface InterventionLogRequest {
  school_id: string;
  codigo_estudiante: string;
  rol_ejecutor: TenantRole | "N8N_ORCHESTRATOR";
  tipo_intervencion:
    | "PLAN_ASISTENCIA_INSPECCION"
    | "TUTORIA_Y_ADAPTACION_NEE"
    | "CONVENIO_O_FECHA_FLEXIBLE_COLECTURIA"
    | "PAQUETE_INTEGRAL_360";
  canal_n8n: string;
  intervencion_aplicada: 0 | 1;
  fecha_ejecucion: string;
  compromiso_representante: string;
}

// ============================================================================
// PLANO B — CONSOLA INTERNA E-PAKTI CEO & MLOPS (EP-12 a EP-18)
// ============================================================================

/** EP-12: GET /api/v1/admin/mlops/overview-and-drift */
export interface EpaktiMlopsOverviewResponse {
  colegios_activos_en_flywheel: number;
  estudiantes_anonimizados_pool: number;
  psi_global_drift: number;
  ece_actual_calibracion_pp: number;
  ece_si_reentrenamiento_ingenuo_sin_log_pp: number;
  intervenciones_registradas_protegidas: number;
  versiones_champion_activas: Record<string, string>;
}

/** EP-13: GET /api/v1/admin/tenants */
export interface EpaktiTenantHealthItem {
  school_id: string;
  nombre: string;
  provincia: string;
  dpa_parroquia: string;
  erp_conectado: "Idukay" | "Runachay" | "Educalinks" | "Academium" | "CSV";
  estudiantes_activos: number;
  completitud_datos_pct: number;
  lambda_empirical_bayes: number;
  psi_drift_local: number;
  roi_retenido_estimado_usd: number;
  estado_sync_n8n: "HEALTHY" | "WARNING" | "ERROR";
}

/** EP-15: POST /api/v1/admin/mlops/models/{model_version}/promote */
export interface ModelPromoteRequest {
  accion: "PROMOTE_CANARY" | "PROMOTE_100_CHAMPION" | "ROLLBACK";
  porcentaje_colegios_canary?: number;
  justificacion_release: string;
}

/** EP-17: PATCH /api/v1/admin/tenants/{school_id}/feature-flags */
export interface TenantFeatureFlagsPatch {
  plan_comercial: "BASICO" | "PRO" | "ENTERPRISE_360";
  feature_flags: {
    modulo_preingreso_m1: boolean;
    simulador_contrafactual_what_if: boolean;
    agentes_whatsapp_n8n: boolean;
    modelo_canary_v2_2: boolean;
    encuesta_bienestar_whatsapp_beta: boolean;
  };
  cupo_mensual_mensajes_whatsapp: number;
}

/** EP-18: GET /api/v1/admin/n8n/observability */
export interface N8nObservabilityResponse {
  alertas_despachadas_30d: number;
  tasa_entrega_whatsapp_pct: number;
  tasa_callback_bitacora_mlops_pct: number;
  latencia_media_agente_ia_seg: number;
  webhooks_fallidos_pendientes_reintento: number;
}

/** EP-02B: GET /api/v1/ingestion/jobs/{job_id} (Polling asíncrono — evita bloqueos de 14s) */
export interface IngestionJobStatusResponse {
  job_id: string;
  school_id: string;
  status: "QUEUED" | "PROCESSING" | "COMPLETED" | "FAILED";
  estudiantes_procesados: number;
  hogares_procesados: number;
  duracion_ms: number;
}

/** EP-19: POST /api/v1/public/contact-lead (Formulario web comercial sin JWT) */
export interface PublicContactLeadRequest {
  nombre_contacto: string;
  institucion: string;
  correo: string;
  whatsapp?: string;
  ciudad?: string;
  mensaje?: string;
}

export interface PublicContactLeadResponse {
  recibido: boolean;
  despachado_a_n8n_simulado?: boolean;
  lead: PublicContactLeadRequest & {
    lead_id: string;
    recibido_en: string;
  };
}

export const EPAKTI_API_ENDPOINTS = {
  // Plano A — Colegio Cliente (app.epakti.ec)
  ONBOARD_TENANT: "POST /api/v1/tenants/onboard",
  BATCH_SYNC: "POST /api/v1/ingestion/batch-sync",
  BATCH_SYNC_JOB_STATUS: "GET /api/v1/ingestion/jobs/{job_id}",
  EVALUATE_APPLICANT_N1: "POST /api/v1/admissions/evaluate-applicant",
  RECTORADO_KPIS_ROI: "GET /api/v1/dashboard/rectorado/kpis-roi",
  DOCENTE_TRIAGE_SIN_MORA: "GET /api/v1/dashboard/docente-tutor/triage",
  ESTUDIANTE_FICHA_360: "GET /api/v1/students/{codigo_estudiante}/ficha-360",
  DECE_INCLUSION_NEE: "GET /api/v1/dashboard/dece/inclusion-nee",
  COLECTURIA_CARTERA: "GET /api/v1/dashboard/colecturia/cartera-hogares",
  DOCENTES_HORARIOS: "GET /api/v1/dashboard/vicerrectorado/docentes-horarios",
  N8N_DISPATCH: "POST /api/v1/n8n/dispatch-alerts",
  INTERVENTION_LOG_MLOPS: "POST /api/v1/interventions/log-outcome",
  // Plano B — Consola Interna E-Pakti (admin.epakti.ec)
  ADMIN_MLOPS_OVERVIEW: "GET /api/v1/admin/mlops/overview-and-drift",
  ADMIN_TENANTS_LIST: "GET /api/v1/admin/tenants",
  ADMIN_MLOPS_RETRAIN: "POST /api/v1/admin/mlops/retrain",
  ADMIN_MODEL_PROMOTE: "POST /api/v1/admin/mlops/models/{model_version}/promote",
  ADMIN_DATALAKE_EXPLORER: "GET /api/v1/admin/data-lake/anonymized-explorer",
  ADMIN_FEATURE_FLAGS: "PATCH /api/v1/admin/tenants/{school_id}/feature-flags",
  ADMIN_N8N_OBSERVABILITY: "GET /api/v1/admin/n8n/observability",
  // Público — Landing Web Comercial
  PUBLIC_CONTACT_LEAD: "POST /api/v1/public/contact-lead",
} as const;
