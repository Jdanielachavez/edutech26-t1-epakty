#!/usr/bin/env python3
"""E-Pakti Engine Contract Stub Server (Zero-Dependency Python 3 Stdlib — Mac / Linux / Windows).

PROPÓSITO (PROTECCIÓN DE IP DEL MOTOR E-PAKTI):
Permite al equipo Web / Supabase / UI / n8n / Bedrock desarrollar, integrar y probar el 100 %
de la interfaz y el backend proxy SIN necesitar la carpeta propietaria del motor ML (`GEMINI/`).
Usa ÚNICAMENTE los snapshots JSON/CSV de contrato de este paquete.

Uso en Mac / Linux / Windows:
    python3 epakti_engine_stub_server.py --port 8090

En producción, el equipo Web cambia UNA sola variable de entorno:
    EPAKTI_ENGINE_BASE_URL=http://localhost:8090/api/v1   -->   https://engine.epakti.ec/api/v1

Autenticación simulada para probar RBAC en desarrollo:
    Header: `Authorization: Bearer ROLE:DOCENTE_TUTOR` (o `RECTORADO`, `DECE`, `COLECTURIA`, `ADMISIONES`, `EPAKTI_CEO`, `EPAKTI_MLOPS`)
    Nota: Si un token con rol `DOCENTE_TUTOR` llama a `/api/v1/dashboard/colecturia/cartera-hogares`
    o a `/api/v1/admin/*`, este servidor responde `403 Forbidden` exactamente como producción!
"""

from __future__ import annotations

import argparse
import csv
import json
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent.parent
DIR_CONTRATOS = ROOT / "02_CONTRATOS_API_Y_N8N"
DIR_DATOS = ROOT / "03_DATOS_REALES_PARA_MOCKS_Y_PROTOTIPOS"

JOBS_STORE: dict[str, dict] = {}
INTERVENTIONS_LOG: list[dict] = []
CONTACT_LEADS: list[dict] = []
FEATURE_FLAGS_STATE: dict[str, dict] = {
    "SCH-01H00123": {
        "plan_comercial": "ENTERPRISE_360",
        "feature_flags": {
            "modulo_preingreso_m1": True,
            "simulador_contrafactual_what_if": True,
            "agentes_whatsapp_n8n": True,
            "modelo_canary_v2_2": False,
            "encuesta_bienestar_whatsapp_beta": True,
        },
        "cupo_mensual_mensajes_whatsapp": 1500,
    }
}


def cargar_json(nombre: str) -> dict:
    p = DIR_CONTRATOS / nombre
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def cargar_csv(nombre: str) -> list[dict]:
    p = DIR_DATOS / nombre
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


OPENAPI_DOC = cargar_json("openapi_especificacion_endpoints_ui_n8n.json")
PAYLOADS_N8N = cargar_json("payloads_n8n_alertas_360.json")
MLOPS_JSON = cargar_json("arquitectura_mlops_flywheel_saas.json")
ONBOARD_JSON = cargar_json("api_contrato_onboarding_colegio.json")
TESTS_JSON = cargar_json("reporte_verificacion_integral_15_tests.json")

SEM_DOC_ROWS = cargar_csv("semaforo_docente_permanencia_y_aprendizaje.csv")
SHAP_PED_ROWS = cargar_csv("shap_y_sensibilidad_pedagogica_unificada_240.csv") or cargar_csv(
    "shap_explicabilidad_individual_240_estudiantes.csv"
)
DECE_ROWS = cargar_csv("tablero_dece_nee.csv")
NEE_MAT_ROWS = cargar_csv("analisis_nee_por_materia.csv")
COLECT_ROWS = cargar_csv("indicador_morosidad_estudiantes_y_porque_shap.csv")
HOGARES_ROWS = cargar_csv("seguimiento_mora_familiar.csv")
DOCENTES_ROWS = cargar_csv("diagnostico_carga_y_desempeno_docente.csv")
HORARIOS_ROWS = cargar_csv("diagnostico_horarios_primer_bloque.csv")
PREING_ROWS = cargar_csv("semaforo_preingreso_admision_240_estudiantes.csv")
TERR_ROWS = cargar_csv("simulacion_7_territorios_ecuador.csv")
FLYWHEEL_ROWS = cargar_csv("simulacion_flywheel_mlops_multicolegio.csv")
AUD_SIGNOS_ROWS = cargar_csv("auditoria_limpieza_y_signos_economicos.csv")


def extraer_rol(headers) -> str:
    auth = headers.get("Authorization", "")
    if "ROLE:" in auth:
        return auth.split("ROLE:", 1)[1].strip().upper()
    return headers.get("X-Epakti-Role", "RECTORADO").strip().upper()


def extraer_school_id(headers) -> str:
    return headers.get("X-School-Id", "SCH-01H00123").strip().upper()


def evaluar_postulante_dinamico(body: dict) -> dict:
    """Evaluación N=1 determinista, monótona y alineada 100 % con el contrato OpenAPI 3.1 (anidado o plano).

    Separa estrictamente proporciones (`prop_areas_bajo_7`, `prop_materias_bajo_7` en [0, 1]) de conteos enteros
    (`materias_bajo_7`, `n_materias_bajo_7` divididos siempre por `total_materias`, por defecto 7), evitando la
    ambigüedad donde 1 materia se interpretaba como 100 % y 2 materias como 28,6 %.
    """
    import math

    def sig(z: float) -> float:
        return 1.0 / (1.0 + math.exp(-max(-20.0, min(20.0, z))))

    diag = body.get("evaluacion_diagnostica_o_libreta_previa") or body.get("diagnostico_academico_previo") or {}
    if not isinstance(diag, dict):
        diag = {}
    mat1 = body.get("comportamiento_matricula_mes1") or body.get("matricula_mes_1") or {}
    if not isinstance(mat1, dict):
        mat1 = {}

    # 1. Bloque educativo: soporta contrato anidado OpenAPI (nota_matematica_0_10, nota_lengua_0_10, prop_areas_bajo_7, n_areas_criticas_bajo_6) y plano
    total_mat = max(1.0, float(diag.get("total_materias", body.get("total_materias", 7.0))))
    nota_mat = diag.get("nota_matematica_0_10", body.get("nota_matematica_0_10"))
    nota_len = diag.get("nota_lengua_0_10", body.get("nota_lengua_0_10"))
    if "promedio_general" in diag:
        prom = float(diag["promedio_general"])
    elif "promedio_previo" in body or "nota_media_p1" in body:
        prom = float(body.get("promedio_previo", body.get("nota_media_p1", 7.8)))
    elif nota_mat is not None or nota_len is not None:
        vals_n = [float(v) for v in (nota_mat, nota_len) if v is not None]
        prom = sum(vals_n) / len(vals_n)
    else:
        prom = 7.8

    if "prop_areas_bajo_7" in diag:
        prop_b7 = min(1.0, max(0.0, float(diag["prop_areas_bajo_7"])))
    elif "prop_materias_bajo_7" in body:
        prop_b7 = min(1.0, max(0.0, float(body["prop_materias_bajo_7"])))
    elif "materias_bajo_7" in diag or "n_materias_bajo_7" in diag:
        cnt = float(diag.get("materias_bajo_7", diag.get("n_materias_bajo_7", 0.0)))
        prop_b7 = min(1.0, max(0.0, cnt / total_mat))
    elif "materias_bajo_7" in body or "n_materias_bajo_7" in body:
        cnt = float(body.get("materias_bajo_7", body.get("n_materias_bajo_7", 0.0)))
        prop_b7 = min(1.0, max(0.0, cnt / total_mat))
    else:
        prop_b7 = 0.0

    n_crit6 = max(0.0, float(diag.get("n_areas_criticas_bajo_6", body.get("n_areas_criticas_bajo_6", 0.0))))
    def_mat = max(0.0, 7.0 - float(nota_mat)) if nota_mat is not None else 0.0
    def_len = max(0.0, 7.0 - float(nota_len)) if nota_len is not None else 0.0

    nee_raw = str(body.get("necesidad_educativa", "ninguna")).strip().lower()
    tiene_nee = 1.0 if nee_raw not in ("ninguna", "none", "0", "false", "") else 0.0
    nbi = float(body.get("tasa_nbi_parroquia", 0.15))
    z_edu = (
        -2.55
        + 3.10 * prop_b7
        + 0.45 * min(4.0, n_crit6)
        + 0.85 * max(0.0, 7.5 - prom)
        + 0.25 * (def_mat + def_len)
        + 0.35 * tiene_nee
        + 0.40 * max(0.0, nbi - 0.15)
    )
    p_edu = round(100.0 * sig(z_edu), 1)
    c_edu = "ROJO" if p_edu >= 65.0 else ("NARANJA" if p_edu >= 35.0 else ("AMARILLO" if p_edu >= 15.0 else "VERDE"))

    # 2. Bloque financiero: soporta contrato anidado OpenAPI (`comportamiento_matricula_mes1`) y plano
    cuota_venc = 1.0 if float(mat1.get("cuota_matricula_vencida", body.get("cuota_vencida_matricula_sep", 0))) > 0 else 0.0
    pago_tard = 1.0 if float(mat1.get("pago_posterior_dia_10", body.get("pago_tardio_matricula_sep", 0))) > 0 else 0.0
    dia_pago = float(mat1.get("dia_pago_matricula", body.get("dia_pago_matricula_sep", 5.0)))
    herm_atraso = 1.0 if float(mat1.get("hermano_con_atraso_matricula", body.get("hermano_con_atraso_matricula", 0))) > 0 else 0.0
    n_herm = float(body.get("n_hijos_representante", body.get("n_hermanos_en_plantel", body.get("n_hermanos", 1))))
    z_fin = (
        -1.40
        + 1.15 * cuota_venc
        + 0.75 * pago_tard
        + 0.06 * max(0.0, dia_pago - 5.0)
        + 0.50 * herm_atraso
        + 0.15 * max(0.0, n_herm - 1.0)
    )
    p_fin = round(100.0 * sig(z_fin), 1)
    p_cron = round(100.0 * sig(z_fin - 1.45), 1)
    c_fin = "ROJO" if p_fin >= 35.0 else ("AMARILLO" if p_fin >= 25.0 else "VERDE")

    return {
        "modo_evaluacion": "N1_DINAMICO_MONOTONO_OPENAPI_V24",
        "nota_uso_etico_lopdp": "Indicador exclusivamente de apoyo preventivo y acompañamiento escolar; prohibido su uso para exclusión de admisión.",
        "vista_admision_pedagogica_dece": {
            "semaforo_ingreso_educativo": c_edu,
            "etiqueta": f"{c_edu} — {'Plan DECE / Nivelación Día 1' if c_edu in ('ROJO','NARANJA') else 'Seguimiento Ordinario'}",
            "prob_riesgo_academico_pct": p_edu,
            "indice_estabilidad_educativa_0_100": round(100.0 - p_edu, 1),
            "protocolo_dia_1": "Tutoría diagnóstica y ficha DECE" if c_edu in ("ROJO", "NARANJA") else "Ingreso regular",
        },
        "vista_admision_financiera_solo_colecturia": {
            "semaforo_ingreso_financiero": c_fin,
            "etiqueta": f"{c_fin} — {'Fecha Flexible Día 15-20 / Convenio' if c_fin == 'ROJO' else 'Facturación Ordinaria'}",
            "prob_incumplimiento_pago_pct": p_fin,
            "prob_morosidad_cronica_2m_pct": p_cron,
            "protocolo_matricula": "Ofrecer fecha flexible día 15-20" if c_fin == "ROJO" else "Recordatorio preventivo",
        },
    }


class EpaktiStubHandler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict | list) -> None:
        raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Epakti-Role, Idempotency-Key")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
        self.send_header("X-Epakti-Mode", "CONTRACT_STUB_NO_PROPRIETARY_ENGINE")
        self.end_headers()
        self.wfile.write(raw)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_OPTIONS(self) -> None:
        self._send_json(200, {"ok": True})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)
        rol = extraer_rol(self.headers)

        # Health & OpenAPI 3.1
        if path in ("", "/health", "/api/v1/health"):
            return self._send_json(200, {"status": "ok", "mode": "EPAKTI_CONTRACT_STUB", "version": "2.2.0", "endpoints": len(OPENAPI_DOC.get("paths", {}))})
        if path in ("/openapi.json", "/api/v1/openapi.json"):
            return self._send_json(200, OPENAPI_DOC)

        # Aislamiento Multi-Tenant por `X-School-Id` en rutas de colegio (Plano A)
        req_school = extraer_school_id(self.headers)
        qs_school = qs.get("school_id", [req_school])[0].strip().upper()
        if path.startswith("/api/v1/dashboard/") or path.startswith("/api/v1/students/") or path.startswith("/api/v1/ingestion/"):
            if rol not in ("EPAKTI_CEO", "EPAKTI_MLOPS", "EPAKTI_DATA_SCIENCE", "EPAKTI_CS") and qs_school != req_school:
                return self._send_json(403, {"code": "TENANT_ISOLATION_VIOLATION", "detail": f"Acceso cruzado bloqueado entre '{req_school}' y '{qs_school}'."})

        # Control estricto RBAC para Plano B (/api/v1/admin/*)
        if path.startswith("/api/v1/admin/"):
            if rol not in ("EPAKTI_CEO", "EPAKTI_MLOPS", "EPAKTI_DATA_SCIENCE", "EPAKTI_CS"):
                return self._send_json(403, {"code": "RBAC_CONTROL_PLANE_ONLY", "detail": f"Rol '{rol}' no autorizado en Consola Interna E-Pakti."})

        # EP-02B: Estado de job asíncrono (solución al worker de 14s)
        if path.startswith("/api/v1/ingestion/jobs/"):
            job_id = path.rsplit("/", 1)[-1]
            job = JOBS_STORE.get(job_id)
            if not job:
                return self._send_json(404, {"detail": f"Job {job_id} no encontrado"})
            elapsed = time.time() - job["created_at"]
            status_now = "COMPLETED" if elapsed >= 1.5 else "PROCESSING"
            return self._send_json(200, {**job, "status": status_now, "duracion_ms": int(elapsed * 1000)})

        # EP-04: Rectorado KPIs & Escenario Ilustrativo Financiero
        if path == "/api/v1/dashboard/rectorado/kpis-roi":
            if rol not in ("RECTORADO", "EPAKTI_CEO"):
                return self._send_json(403, {"code": "RBAC_DENIED", "detail": "Solo RECTORADO accede a KPIs financieros."})
            ep4 = next((e for e in OPENAPI_DOC.get("endpoints_catalogo", []) if e["id"] == "EP-04"), {})
            return self._send_json(200, {"kpis_financieros_ilustrativos": ep4.get("response_example", {}), "simulacion_7_territorios_sensibilidad": TERR_ROWS})

        # EP-05: Matriz Triage Docente (CERO datos financieros — lista blanca estricta)
        if path == "/api/v1/dashboard/docente-tutor/triage":
            rows = SEM_DOC_ROWS
            if "curso" in qs:
                rows = [r for r in rows if r.get("curso") == qs["curso"][0]]
            if "semaforo_color" in qs:
                rows = [r for r in rows if r.get("semaforo_docente_color") == qs["semaforo_color"][0].upper()]
            return self._send_json(200, {"politica_rbac": "CERO_DATOS_FINANCIEROS_EXPUESTOS", "total": len(rows), "estudiantes": rows})

        # EP-06: Ficha 360° + Cascada SHAP + Sensibilidad What-If
        if path.startswith("/api/v1/students/") and path.endswith("/ficha-360"):
            cod = path.split("/")[-2].upper()
            row = next((r for r in SHAP_PED_ROWS if r.get("codigo_estudiante") == cod), None)
            if not row:
                return self._send_json(404, {"detail": f"Estudiante {cod} no encontrado"})
            return self._send_json(200, {"politica_rbac": "CERO_DATOS_FINANCIEROS_EXPUESTOS", "nota_metodologica": "Sensibilidad del puntaje (no efecto causal).", "ficha": row})

        # EP-07: Bandeja DECE NEE
        if path == "/api/v1/dashboard/dece/inclusion-nee":
            if rol not in ("DECE", "RECTORADO", "EPAKTI_CEO"):
                return self._send_json(403, {"code": "RBAC_DECE_ONLY", "detail": "Acceso exclusivo DECE / Rectorado."})
            return self._send_json(200, {"total_nee": len(DECE_ROWS), "estudiantes_nee": DECE_ROWS, "matriz_nee_por_materia": NEE_MAT_ROWS})

        # EP-08: Colecturía Exclusiva (BLOQUEADA para Docentes / DECE / Inspección!)
        if path == "/api/v1/dashboard/colecturia/cartera-hogares":
            if rol not in ("COLECTURIA", "RECTORADO", "EPAKTI_CEO"):
                return self._send_json(403, {"code": "RBAC_LOPDP_BLOCKED", "detail": f"Bloqueado por LOPDP/LOEI: rol '{rol}' no puede ver datos de morosidad familiar."})
            return self._send_json(200, {"acceso_rbac": "SOLO_COLECTURIA_RECTORADO", "hogares": HOGARES_ROWS, "estudiantes_morosidad_shap": COLECT_ROWS})

        # EP-09: Vicerrectorado Carga Docente y Horarios
        if path == "/api/v1/dashboard/vicerrectorado/docentes-horarios":
            return self._send_json(200, {"docentes": DOCENTES_ROWS, "primer_bloque_diario": HORARIOS_ROWS})

        # EP-12: Admin MLOps Overview & Drift
        if path == "/api/v1/admin/mlops/overview-and-drift":
            return self._send_json(200, {"mlops_manifiesto": MLOPS_JSON, "curva_flywheel_simulada": FLYWHEEL_ROWS, "suite_integridad": TESTS_JSON})

        # EP-13: Admin Multi-Tenant
        if path == "/api/v1/admin/tenants":
            ep13 = next((e for e in OPENAPI_DOC.get("endpoints_catalogo", []) if e["id"] == "EP-13"), {})
            return self._send_json(200, ep13.get("response_example", {}))

        # EP-16: Admin Data Lake K-Anónimo
        if path == "/api/v1/admin/data-lake/anonymized-explorer":
            ep16 = next((e for e in OPENAPI_DOC.get("endpoints_catalogo", []) if e["id"] == "EP-16"), {})
            return self._send_json(200, {**ep16.get("response_example", {}), "variables_auditadas_sin_pii": AUD_SIGNOS_ROWS})

        # EP-18: Admin n8n Observability
        if path == "/api/v1/admin/n8n/observability":
            ep18 = next((e for e in OPENAPI_DOC.get("endpoints_catalogo", []) if e["id"] == "EP-18"), {})
            return self._send_json(200, {**ep18.get("response_example", {}), "intervenciones_registradas_en_sesion": len(INTERVENTIONS_LOG), "leads_recibidos_en_sesion": len(CONTACT_LEADS)})

        return self._send_json(404, {"detail": f"Ruta GET no encontrada: {path}"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path.rstrip("/")
        body = self._read_body()
        rol = extraer_rol(self.headers)

        # EP-19: Formulario público de contacto web (resuelve contacto desconectado)
        if path == "/api/v1/public/contact-lead":
            for req_k in ("nombre_contacto", "institucion", "correo"):
                if not body.get(req_k):
                    return self._send_json(422, {"detail": f"Campo requerido faltante: {req_k}"})
            lead = {"lead_id": f"LEAD-{uuid.uuid4().hex[:8].upper()}", "recibido_en": time.strftime("%Y-%m-%dT%H:%M:%S"), **body}
            CONTACT_LEADS.append(lead)
            return self._send_json(201, {"recibido": True, "despachado_a_n8n_simulado": True, "lead": lead})

        # EP-01: Onboarding Colegio
        if path == "/api/v1/tenants/onboard":
            ep1 = next((e for e in OPENAPI_DOC.get("endpoints_catalogo", []) if e["id"] == "EP-01"), {})
            return self._send_json(200, {**ep1.get("response_example", {}), "entrada_recibida": body})

        # EP-02: Ingesta Batch Asíncrona (202 Accepted -> cuenta los registros REALES enviados en el payload!)
        if path == "/api/v1/ingestion/batch-sync":
            req_school = extraer_school_id(self.headers)
            body_school = str(body.get("school_id", req_school)).strip().upper()
            if rol not in ("EPAKTI_CEO", "EPAKTI_MLOPS", "N8N_ORCHESTRATOR") and body_school != req_school:
                return self._send_json(403, {"code": "TENANT_ISOLATION_VIOLATION", "detail": "El school_id del payload no coincide con el tenant autenticado."})
            idem = self.headers.get("Idempotency-Key") or f"JOB-{uuid.uuid4().hex[:8].upper()}"
            if idem not in JOBS_STORE:
                arch_decl = body.get("archivos_cargados") or body.get("archivos")
                if isinstance(body.get("estudiantes"), list):
                    n_est = len(body["estudiantes"])
                    reps = {str(e.get("representante_codigo", e.get("codigo", i))) for i, e in enumerate(body["estudiantes"])}
                    n_hog = len(reps)
                    modo_ing = "PAYLOAD_ENVIADO_REAL"
                    n_arch = len(arch_decl) if isinstance(arch_decl, (list, dict)) else 0
                elif "n_estudiantes" in body:
                    n_est = int(body["n_estudiantes"])
                    n_hog = int(body.get("n_hogares", n_est))
                    modo_ing = "CONTEO_DECLARADO"
                    n_arch = len(arch_decl) if isinstance(arch_decl, (list, dict)) else 0
                elif isinstance(arch_decl, dict) and isinstance(arch_decl.get("estudiantes_csv"), str) and "\n" in arch_decl["estudiantes_csv"]:
                    rows_csv = list(csv.DictReader(arch_decl["estudiantes_csv"].splitlines()))
                    n_est = len(rows_csv)
                    n_hog = len({str(r.get("representante_codigo", r.get("codigo", i))) for i, r in enumerate(rows_csv)})
                    modo_ing = "CSV_INLINE_PARSED"
                    n_arch = len(arch_decl)
                elif isinstance(arch_decl, (list, dict)):
                    # Contrato OpenAPI con solo nombres de archivo (sin contenido tabular adjunto): JAMÁS inventar 240!
                    n_est, n_hog = 0, 0
                    modo_ing = "METADATOS_ARCHIVO_SIN_REGISTROS_ADJUNTOS"
                    n_arch = len(arch_decl)
                elif body.get("modo_demo") is True or not body:
                    n_est, n_hog, modo_ing, n_arch = 240, 204, "DEMO_COHORT_SNAPSHOT", 6
                else:
                    n_est, n_hog, modo_ing, n_arch = 0, 0, "PAYLOAD_SIN_REGISTROS", 0
                JOBS_STORE[idem] = {
                    "job_id": idem,
                    "school_id": body_school,
                    "modo_ingesta": modo_ing,
                    "archivos_declarados": n_arch,
                    "created_at": time.time(),
                    "estudiantes_procesados": n_est,
                    "hogares_procesados": n_hog,
                }
            return self._send_json(202, {"status": "ACCEPTED_ASYNC", "job_id": idem, "poll_url": f"/api/v1/ingestion/jobs/{idem}"})

        # EP-03: Admisión Pre-Ingreso N=1 (Cálculo dinámico según los atributos reales del postulante!)
        if path == "/api/v1/admissions/evaluate-applicant":
            resp = evaluar_postulante_dinamico(body)
            if rol in ("DOCENTE_TUTOR", "DECE", "INSPECCION"):
                resp.pop("vista_admision_financiera_solo_colecturia", None)
            return self._send_json(200, resp)

        # EP-10: Dispatch Alertas a n8n
        if path == "/api/v1/n8n/dispatch-alerts":
            return self._send_json(200, {"enviado_a_n8n_simulado": True, "total_alertas": len(PAYLOADS_N8N.get("alertas_priorizadas_360", [])), "payload_ejemplo": PAYLOADS_N8N.get("alertas_priorizadas_360", [])[:3]})

        # EP-11: Callback Bitácora Intervenciones (Candado MLOps)
        if path == "/api/v1/interventions/log-outcome":
            entry = {"log_id": f"INT-{uuid.uuid4().hex[:8].upper()}", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), **body}
            INTERVENTIONS_LOG.append(entry)
            return self._send_json(201, {"registrado_en_bitacora_mlops": True, "entry": entry})

        # EP-14 & EP-15: Admin MLOps Retrain & Promote
        if path.startswith("/api/v1/admin/"):
            if rol not in ("EPAKTI_CEO", "EPAKTI_MLOPS", "EPAKTI_DATA_SCIENCE"):
                return self._send_json(403, {"code": "RBAC_CONTROL_PLANE_ONLY", "detail": "Solo equipo E-Pakti MLOps."})
            if path == "/api/v1/admin/mlops/retrain":
                ep14 = next((e for e in OPENAPI_DOC.get("endpoints_catalogo", []) if e["id"] == "EP-14"), {})
                return self._send_json(202, ep14.get("response_example", {}))
            if path.endswith("/promote"):
                ep15 = next((e for e in OPENAPI_DOC.get("endpoints_catalogo", []) if e["id"] == "EP-15"), {})
                return self._send_json(200, {**ep15.get("response_example", {}), "request": body})

        return self._send_json(404, {"detail": f"Ruta POST no encontrada: {path}"})

    def do_PATCH(self) -> None:
        path = urlparse(self.path).path.rstrip("/")
        body = self._read_body()
        rol = extraer_rol(self.headers)
        if path.endswith("/feature-flags") and path.startswith("/api/v1/admin/tenants/"):
            if rol not in ("EPAKTI_CEO", "EPAKTI_CS", "EPAKTI_MLOPS"):
                return self._send_json(403, {"code": "RBAC_CONTROL_PLANE_ONLY", "detail": "Solo equipo E-Pakti."})
            sid = path.split("/")[-2]
            FEATURE_FLAGS_STATE[sid] = body
            return self._send_json(200, {"school_id": sid, "actualizado": True, "estado": body})
        return self._send_json(404, {"detail": f"Ruta PATCH no encontrada: {path}"})


def main() -> None:
    parser = argparse.ArgumentParser(description="E-Pakti Engine Contract Stub Server (Zero Proprietary ML Code)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), EpaktiStubHandler)
    print(f"[E-Pakti Contract Stub] Escuchando en http://{args.host}:{args.port}/api/v1 (OpenAPI en /openapi.json)")
    srv.serve_forever()


if __name__ == "__main__":
    main()
