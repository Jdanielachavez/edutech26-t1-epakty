# Guía de Integración Desacoplada — Equipo Web / Supabase / n8n / UI ↔ Motor Privado de **E-Pakti** (CEO: Wilo)

Este documento resuelve **todos los puntos técnicos reportados por el equipo Web/Backend** sin necesidad de copiar ni exponer el código propietario del motor ML (`GEMINI/`) en las máquinas de desarrollo web.

---

## 1. Arquitectura de Desacoplamiento (Resuelve B4 sin entregar el código del Motor)

El sistema de **E-Pakti** se despliega como **dos servicios independientes conectados por HTTPS + API Contrato OpenAPI 3.1**:

```
[Frontend Next.js + BFF Proxy Ligero]  <--->  [Supabase Postgres + Auth JWT/RLS]
                 |
                 |  HTTPS + Bearer JWT + X-Engine-API-Key (SOLO datos pseudonimizados, CERO PII)
                 v
   ┌──────────────────────────────────────────────────────────────────────┐
   │  HOY EN DESARROLLO (Mac/Local):                                      │
   │     EPAKTI_ENGINE_BASE_URL=http://localhost:8090/api/v1              │
   │     (Usa `epakti_engine_stub_server.py` incluido en este ZIP)        │
   │                                                                      │
   │  DÍA DE INTEGRACIÓN / PRODUCCIÓN (Motor Privado de Wilo):            │
   │     EPAKTI_ENGINE_BASE_URL=https://engine.epakti.ec/api/v1           │
   └──────────────────────────────────────────────────────────────────────┘
                 |
                 v  Webhook RBAC (`POST /webhook/epakti-alerta-360`)
   [n8n + Amazon Bedrock + WhatsApp Business API + SMTP/Gmail]
                 |
                 v  Callback MLOps (`POST /api/v1/interventions/log-outcome`)
   [Bitácora `intervention_outcomes_log` en Supabase]
```

### Cómo arrancar el Stub del Motor HOY en tu Mac (30 segundos, cero dependencias):
```bash
cd UI_UX/05_KIT_INTEGRACION_SIN_EXPONER_MOTOR
python3 epakti_engine_stub_server.py --port 8090
```
* Verifica OpenAPI 3.1 estándar (`paths` completos): `curl http://localhost:8090/openapi.json`
* Prueba RBAC real:
  - Como Docente (`200 OK`, cero datos financieros): `curl -H "Authorization: Bearer ROLE:DOCENTE_TUTOR" http://localhost:8090/api/v1/dashboard/docente-tutor/triage`
  - Como Docente intentando ver Colecturía (**`403 Forbidden` automático**): `curl -i -H "Authorization: Bearer ROLE:DOCENTE_TUTOR" http://localhost:8090/api/v1/dashboard/colecturia/cartera-hogares`
  - Como CEO/MLOps en Plano B (`200 OK`): `curl -H "Authorization: Bearer ROLE:EPAKTI_CEO" http://localhost:8090/api/v1/admin/mlops/overview-and-drift`

---

## 2. Solución Exacta a los 5 Pendientes Reportados por el Equipo Web/Backend

### A. "El proxy recibe todos los secretos" → Separación de Secretos (*Least Privilege*)
El BFF/Proxy que habla con el navegador **NO puede recibir** llaves maestras de base de datos, Bedrock, SMTP ni WhatsApp. Distribuye los secretos estrictamente por servicio:

| Servicio | Secretos que SÍ debe tener | Secretos PROHIBIDOS en este servicio |
| --- | --- | --- |
| **Frontend Next.js (Navegador)** | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_URL` | **NINGUNA** API key privada, `service_role`, Bedrock ni WhatsApp |
| **Proxy BFF Web** | `SUPABASE_JWT_SECRET` (o JWKS público), `EPAKTI_ENGINE_API_KEY` (solo inferencia), `N8N_WEBHOOK_HMAC_SECRET` | `SUPABASE_SERVICE_ROLE_KEY`, llaves AWS Bedrock, credenciales WhatsApp/SMTP |
| **Worker Asíncrono (Backend)** | `SUPABASE_SERVICE_ROLE_KEY`, `EPAKTI_ENGINE_API_KEY` | Credenciales WhatsApp/SMTP, llaves Bedrock |
| **n8n (Orquestador)** | `AWS_BEDROCK_ROLE/KEY`, `WHATSAPP_META_TOKEN`, `SMTP_APP_PASSWORD`, `EPAKTI_CALLBACK_TOKEN` | `SUPABASE_SERVICE_ROLE_KEY`, pesos del Motor ML |

### B. "Los reintentos del worker duran ~14 segundos" → Patrón Asíncrono `202 Accepted`
* Nunca mantengas una petición HTTP abierta esperando el scoring batch ni reintentos síncronos.
* `POST /api/v1/ingestion/batch-sync` exige header `Idempotency-Key`, inserta una fila en `public.ingestion_jobs` (`status='QUEUED'`) y responde **`202 Accepted`** en `< 150 ms` con `poll_url: "/api/v1/ingestion/jobs/{job_id}"`.
* El worker procesa en background con **backoff exponencial con jitter** (`2s → 4s → 8s`, `max_attempts = 3`) y timeout por intento de `5s` hacia el motor.

### C. "Los datos originales de estudiantes no tienen plazo de retención" → Cumplimiento LOPDP Ecuador
* Aplica el script listo [`supabase_schema_rls_retencion_lopdp.sql`](supabase_schema_rls_retencion_lopdp.sql) en tu proyecto **Supabase Postgres**:
  - Separa la bóveda PII (`student_pii_vault`, con `pii_retention_expires_at = now() + 365 days`) de las alertas pseudonimizadas (`pedagogical_alerts_snapshot` y `colecturia_wallet_alerts`).
  - Programa `select cron.schedule('epakti-lopdp-purge', '0 3 * * *', $$select public.epakti_purge_expired_pii();$$);` en `pg_cron` de Supabase para purgar automáticamente nombres, correos y teléfonos al vencer el plazo legal.
  - Al enviar datos al Motor privado de Wilo (`EPAKTI_ENGINE_BASE_URL`), envía **únicamente** `student_pseudonym_id` + variables numéricas + `dpa_parroquia` (**cero PII**).

### D. "El formulario de contacto de la web no está conectado + faltan correo y WhatsApp reales"
* Conecta el formulario de la landing de **E-Pakti** a **`POST /api/v1/public/contact-lead`** (ya definido en `openapi_especificacion_endpoints_ui_n8n.json` y activo en el Stub local!), con rate-limit (5 req/min por IP) y guardado en `public.public_contact_leads` + disparo a un webhook comercial en n8n.
* Define en `.env` de n8n las variables oficiales de contacto de E-Pakti (`EPAKTI_SALES_EMAIL`, `EPAKTI_WHATSAPP_PHONE_ID`, `EPAKTI_WHATSAPP_ACCESS_TOKEN`).

### E. Copy Honesto en la Web (Alineado con Auditoría Científica)
Mientras estemos en fase de **Piloto Controlado** (antes de acumular cohortes reales cerradas con etiquetas oficiales de retiro):
* Presentar el producto como **alertas tempranas calibradas de ausentismo recurrente, riesgo académico Q2 y fricción/incumplimiento de pagos** con explicabilidad SHAP y **simulador de sensibilidad de puntaje (*What-If*)**.
* Evitar prometer en la web "deserción confirmada predicha al 100 %" o "ROI causal garantizado en USD" hasta validar con datos fechados reales del primer colegio piloto.

---

## 3. Checklist de Pruebas de Integración en Staging (Antes de Conectar con el Motor de Wilo)
1. **Supabase Postgres (no local):** Aplicar `supabase_schema_rls_retencion_lopdp.sql` y ejecutar prueba RLS con JWT de `DOCENTE_TUTOR` verificando `0 filas / 403` en `colecturia_wallet_alerts`.
2. **n8n + Amazon Bedrock:** Importar `02_CONTRATOS_API_Y_N8N/workflow_n8n_epakti_360.json` (ya incluye los **10 nodos y todas sus `connections`**) y conectar el nodo LLM a tu credencial de Bedrock (`Claude / Nova`) usando un lote de 3 alumnos de `payloads_n8n_alertas_360.json`.
3. **WhatsApp Sandbox + Correo Real:** Probar envío real a un número de prueba del equipo y verificar que el **Nodo 9** ejecuta el callback `POST /api/v1/interventions/log-outcome` registrando `intervencion_aplicada = 1` en Supabase.
4. **Switch Final al Motor de Wilo:** Cuando los 3 puntos pasen en verde contra el Stub (`localhost:8090`), Wilo enciende `https://engine.epakti.ec/api/v1` y solo cambian `EPAKTI_ENGINE_BASE_URL` en el `.env`.
