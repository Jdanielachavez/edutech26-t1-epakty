# PROMPT E INSTRUCCIONES DE EJECUCIÓN — EQUIPO WEB / BACKEND / SUPABASE / n8n / BEDROCK (**E-PAKTI**)

> **De:** Wilo (CEO & Arquitecto del Motor Predictivo de E-Pakti)  
> **Para:** Equipo de Desarrollo Web, Backend BFF, Supabase, n8n y AWS Bedrock (Mac / Staging)  
> **Objetivo:** Cerrar el 100 % de los pendientes de integración, seguridad, Supabase, LOPDP, n8n/Bedrock, correo/WhatsApp y formulario de contacto **SIN necesitar la carpeta propietaria del motor ML (`GEMINI/`)**. Cuando ambos lados pasen sus pruebas, la conexión final toma **5 minutos cambiando 1 sola variable de entorno**.

---

## PARTE 1 — PROMPT LISTO PARA COPIAR Y PEGAR (A TU AGENTE DE CÓDIGO O COMO BRIEF DEL SPRINT)

Copia y pega el bloque siguiente directamente en Claude Code, Cursor, Codex o Antigravity dentro de tu repositorio Web/Backend en Mac (habiendo descomprimido `UI_UX.zip` al lado del repo):

```markdown
Actúa como Staff Full-Stack, Security & Cloud Integration Engineer en nuestro repositorio de **E-Pakti** (Web Next.js + BFF Proxy + Worker + Supabase + n8n + AWS Bedrock).

### Contexto Arquitectónico Crítico (Separación del Motor ML de Wilo)
El motor predictivo propietario de E-Pakti (red neuronal monótona `MonotonicSignConstrainedFiLMNet`, SHAP unificado, simulador de sensibilidad *What-If* y MLOps) vive en un servicio independiente administrado por Wilo (`GEMINI/`). **NO vamos a copiar `GEMINI/` a este repositorio ni a esta Mac.**
En su lugar, toda comunicación ocurre exclusivamente por contrato HTTP OpenAPI 3.1 usando los archivos del paquete `UI_UX/`:
- OpenAPI 3.1 ejecutable (20 endpoints): `UI_UX/02_CONTRATOS_API_Y_N8N/openapi_especificacion_endpoints_ui_n8n.json`
- Tipos TypeScript y endpoints: `UI_UX/02_CONTRATOS_API_Y_N8N/tipos_typescript_epakti_frontend.ts`
- Workflow n8n cableado (10 nodos, 9 conexiones): `UI_UX/02_CONTRATOS_API_Y_N8N/workflow_n8n_epakti_360.json`
- Payloads reales auditados: `UI_UX/02_CONTRATOS_API_Y_N8N/payloads_n8n_alertas_360.json`
- Servidor Stub local sin dependencias: `UI_UX/05_KIT_INTEGRACION_SIN_EXPONER_MOTOR/epakti_engine_stub_server.py`
- Esquema SQL Supabase + RLS + Retención LOPDP: `UI_UX/05_KIT_INTEGRACION_SIN_EXPONER_MOTOR/supabase_schema_rls_retencion_lopdp.sql`
- Plantilla de variables por servicio: `UI_UX/05_KIT_INTEGRACION_SIN_EXPONER_MOTOR/.env.templates_por_servicio.example`

### Tu Misión: Ejecutar estas 6 Tareas en Orden y Verificar Cada Criterio de Aceptación

#### TAREA 1 — Desacoplar el Cliente del Motor ML (Resuelve B4) y Ajustar el Copy de la Web
1. Crea un cliente HTTP tipado (`src/lib/epaktiEngineClient.ts` o equivalente) que lea **exclusivamente**:
   - `EPAKTI_ENGINE_BASE_URL` (en local/dev: `http://localhost:8090/api/v1`, apuntando a `epakti_engine_stub_server.py`; en producción: `https://engine.epakti.ec/api/v1`).
   - `EPAKTI_ENGINE_API_KEY` (header `X-Epakti-Engine-Key`, solo en servidor, nunca expuesto al navegador).
2. Reenvía el rol autenticado verificado por JWT de Supabase (`Authorization: Bearer ...` y/o rol validado en servidor) y consume los endpoints reales del contrato (`EP-01` a `EP-19` + `EP-02B`):
   - Ficha 360° + Cascada SHAP pedagógica + Sensibilidad *What-If* (`GET /api/v1/students/{codigo}/ficha-360`).
   - Matriz Triage Docente sin datos financieros (`GET /api/v1/dashboard/docente-tutor/triage`).
   - Tablero Colecturía exclusivo (`GET /api/v1/dashboard/colecturia/cartera-hogares`, asegurando que propague `403` si el rol no es `COLECTURIA`/`RECTORADO`).
   - Métricas auditadas (`18/18` pruebas) y curva MLOps en Plano B (`GET /api/v1/admin/mlops/overview-and-drift`).
3. **Alineación honesta del copy en la web:**
   - Reemplaza cualquier texto que prometa "deserción confirmada predicha al 100 %" o "ROI causal garantizado en USD" por el lenguaje auditado: *"Prototipo Auditado — Listo para Piloto Controlado · Alertas tempranas calibradas de ausentismo recurrente, riesgo académico y morosidad escolar, con explicabilidad SHAP individual y simulador de sensibilidad del puntaje (escenario ilustrativo, no efecto causal)"*.
   - **Prohibido** mostrar letras de buró bancario (`AAA`–`C`); usar únicamente semáforos escolares calibrados (`VERDE`, `AMARILLO`, `NARANJA`, `ROJO`).

#### TAREA 2 — Separar los Secretos del Proxy BFF (*Least Privilege*)
1. Audita el backend proxy que habla con el frontend y **ELIMINA** de su entorno: `SUPABASE_SERVICE_ROLE_KEY`, credenciales de AWS Bedrock (`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`), contraseñas SMTP y tokens de WhatsApp Business API.
2. Separa las configuraciones exactamente según `.env.templates_por_servicio.example`:
   - **Frontend Next.js:** solo `NEXT_PUBLIC_*` (URL/anon key de Supabase, URL del BFF, correo/WhatsApp públicos de contacto).
   - **Proxy BFF Web:** solo validación JWT Supabase (`SUPABASE_JWKS_URL` / `SUPABASE_JWT_SECRET`), `EPAKTI_ENGINE_BASE_URL`, `EPAKTI_ENGINE_API_KEY` y `N8N_WEBHOOK_HMAC_SECRET`.
   - **Worker Asíncrono:** `SUPABASE_SERVICE_ROLE_KEY` + `EPAKTI_ENGINE_BASE_URL` + `EPAKTI_ENGINE_API_KEY` (sin secretos de Bedrock, WhatsApp ni SMTP).
   - **n8n:** credenciales de AWS Bedrock, WhatsApp Cloud API, SMTP/Resend y `EPAKTI_CALLBACK_TOKEN`.
3. Añade una validación al arrancar el Proxy BFF que falle en CI/staging si detecta variables prohibidas (`AWS_SECRET_ACCESS_KEY`, `WHATSAPP_META_TOKEN`, `SMTP_APP_PASSWORD`) cargadas en el proceso del proxy.

#### TAREA 3 — Eliminar Bloqueos y Reintentos de 14 Segundos en el Worker (`202 Accepted`)
1. Convierte la ingesta/cálculo batch en flujo **100 % asíncrono**:
   - `POST /api/v1/ingestion/batch-sync` debe exigir `Idempotency-Key`, crear/reusar el registro en `public.ingestion_jobs` con `status = 'QUEUED'` y responder **`202 Accepted`** en `< 150 ms` devolviendo `{ "status": "ACCEPTED_ASYNC", "job_id": "...", "poll_url": "/api/v1/ingestion/jobs/{job_id}" }`.
   - Implementa `GET /api/v1/ingestion/jobs/{job_id}` (`EP-02B`) leyendo el estado real en `public.ingestion_jobs` (`QUEUED | PROCESSING | COMPLETED | FAILED`).
2. Configura el worker en background para que:
   - Use timeout estricto por intento (`5s` hacia el engine), máximo `3` intentos con backoff exponencial + jitter (`2s -> 4s -> 8s`), sin bloquear nunca el hilo HTTP del usuario.
   - Si falla tras 3 intentos, marque el job `FAILED` con `error_message` sanitizado y permita reintento idempotente.
3. En la UI, muestra una barra/estado de progreso con polling a `EP-02B` cada `2s` hasta `COMPLETED` o `FAILED`.

#### TAREA 4 — Migrar a Supabase Real + RLS Estricto + Retención LOPDP de Datos Originales
1. Deja atrás el Postgres local para staging: ejecuta `UI_UX/05_KIT_INTEGRACION_SIN_EXPONER_MOTOR/supabase_schema_rls_retencion_lopdp.sql` en el proyecto real de **Supabase**.
2. Asegura la separación física PII vs. Analítica:
   - Datos identificables (nombre real, correo, teléfono, cédula) se guardan **únicamente** en `public.student_pii_vault` con `pii_retention_expires_at` (por defecto `365 días`, configurable por convenio escolar).
   - Al llamar al motor predictivo (`EPAKTI_ENGINE_BASE_URL`), envía **únicamente** `student_pseudonym_id` + variables numéricas + `dpa_parroquia` (**CERO nombres, correos ni teléfonos**).
3. Habilita `pg_cron` en Supabase para ejecutar diariamente a las 03:00 UTC:
   `select cron.schedule('epakti-lopdp-purge', '0 3 * * *', $$select public.epakti_purge_expired_pii();$$);`
4. Escribe y corre pruebas automáticas contra Supabase real verificando:
   - JWT con `role = DOCENTE_TUTOR` devuelve **0 filas** en `public.colecturia_wallet_alerts` y **403** en `GET /api/v1/dashboard/colecturia/cartera-hogares`.
   - JWT de `school_id = A` devuelve **0 filas** de `school_id = B` (aislamiento multi-tenant).
   - Un registro en `student_pii_vault` con `pii_retention_expires_at < now()` queda purgado a `NULL` / `REDACTED_LOPDP` tras llamar `select public.epakti_purge_expired_pii();`.

#### TAREA 5 — Conectar el Formulario de Contacto Web + Correo y WhatsApp Reales
1. Conecta el formulario de la landing/web a `POST /api/v1/public/contact-lead` (`EP-19`), validando `nombre_contacto`, `institucion`, `correo`, y opcionales `whatsapp`, `ciudad`, `mensaje`.
2. Aplica rate-limit (`5 req/min` por IP) y protección anti-spam (honeypot o Turnstile), guarda el lead en `public.public_contact_leads` en Supabase y dispara un webhook firmado HMAC a n8n para notificar al equipo comercial.
3. Reemplaza todos los enlaces/textos placeholder de contacto en la web por variables de entorno configurables:
   - `NEXT_PUBLIC_EPAKTI_CONTACT_EMAIL`
   - `NEXT_PUBLIC_EPAKTI_WHATSAPP_NUMBER` (formato E.164 sin `+`, ej. `5939XXXXXXXX`, para `https://wa.me/...`)
   - Si falta alguna variable en desarrollo, mostrar advertencia clara en consola de build para no publicar placeholders rotos.

#### TAREA 6 — Probar Realmente n8n + AWS Bedrock + Correo + WhatsApp en Staging (Sin Simulación)
1. Importa `UI_UX/02_CONTRATOS_API_Y_N8N/workflow_n8n_epakti_360.json` en la instancia real de **n8n** (los 10 nodos y sus 9 conexiones ya vienen cableados).
2. Reemplaza el borrador simulado conectando el nodo LLM a la credencial real de **AWS Bedrock** (modelo Claude / Nova con temperatura baja `<= 0.3`) y valida que:
   - La rama pedagógica (`Docente/DECE/Inspección`) usa `prompt_ia_pedagogico` y **jamás menciona deuda, mora ni pagos**.
   - La rama de Colecturía usa únicamente el contexto financiero por hogar sin datos clínicos DECE.
3. Configura credenciales reales en n8n de **Correo (SMTP / Resend / SES)** y **WhatsApp Business Cloud API** apuntando a un correo y celular de prueba internos del equipo.
4. Ejecuta una prueba real con 2 alertas de `payloads_n8n_alertas_360.json` (1 pedagógica y 1 de colecturía) y verifica:
   - Llega el correo real y el mensaje real de WhatsApp con el texto redactado por Bedrock.
   - El **Nodo 9** invoca `POST /api/v1/interventions/log-outcome` (`EP-11`) y el registro aparece en `public.intervention_outcomes_log` en Supabase con `intervencion_aplicada = 1`.

### Criterio de Terminación (Reportar Evidencia Real)
No des por terminada la tarea hasta entregar un reporte corto con evidencia ejecutada (logs/capturas/comandos) confirmando:
1. Stub `localhost:8090` conectado + Ficha 360° SHAP + Sensibilidad *What-If* funcionando en la UI.
2. Auditoría de secretos por servicio aprobada (proxy sin llaves de Bedrock/WhatsApp/SMTP/`service_role`).
3. Ingesta `202 Accepted` (< 200 ms) + polling `EP-02B` probado sin bloqueo de 14 s.
4. Supabase real con RLS verificado (`DOCENTE_TUTOR` bloqueado en Colecturía) y purga LOPDP ejecutada en prueba.
5. Formulario de contacto guardando en `public_contact_leads` + correo/WhatsApp reales leídos por env.
6. Prueba real exitosa de n8n + Bedrock + correo + WhatsApp + callback `EP-11` en Supabase.
```

---

## PARTE 2 — INSTRUCCIONES PASO A PASO PARA ARRANCAR HOY EN MAC (SIN `GEMINI/`)

### Paso 1: Levantar el Stub del Motor de Wilo en 10 segundos
No requiere `pip install`, entornos virtuales ni Docker (usa solo librería estándar de Python 3):

```bash
cd UI_UX/05_KIT_INTEGRACION_SIN_EXPONER_MOTOR
python3 epakti_engine_stub_server.py --port 8090
```

### Paso 2: Verificar los contratos y RBAC en otra terminal de Mac
```bash
# 1) Salud y OpenAPI 3.1 (20 paths reales)
curl -s http://localhost:8090/health
curl -s http://localhost:8090/openapi.json | head -n 30

# 2) Vista Docente (200 OK — 240 alumnos, CERO campos financieros)
curl -s -H "Authorization: Bearer ROLE:DOCENTE_TUTOR" \
  http://localhost:8090/api/v1/dashboard/docente-tutor/triage | head -n 30

# 3) Aislamiento RBAC/LOPDP (DEBE devolver HTTP 403 Forbidden!)
curl -i -H "Authorization: Bearer ROLE:DOCENTE_TUTOR" \
  http://localhost:8090/api/v1/dashboard/colecturia/cartera-hogares

# 4) Ficha 360° con SHAP unificado + Sensibilidad What-If (EST-089)
curl -s -H "Authorization: Bearer ROLE:DOCENTE_TUTOR" \
  http://localhost:8090/api/v1/students/EST-089/ficha-360

# 5) Ingesta asíncrona (202 Accepted) + polling de job (resuelve worker de 14s)
curl -i -X POST http://localhost:8090/api/v1/ingestion/batch-sync \
  -H "Authorization: Bearer ROLE:RECTORADO" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: JOB-MAC-001" \
  -d '{"school_id":"SCH-01H00123"}'

curl -s -H "Authorization: Bearer ROLE:RECTORADO" \
  http://localhost:8090/api/v1/ingestion/jobs/JOB-MAC-001

# 6) Formulario público de contacto web (201 Created, sin JWT)
curl -i -X POST http://localhost:8090/api/v1/public/contact-lead \
  -H "Content-Type: application/json" \
  -d '{"nombre_contacto":"Rectora Prueba","institucion":"UE Demo","correo":"rectorado@uedemo.edu.ec","whatsapp":"+593999000111"}'

# 7) Plano B Consola CEO/MLOps (403 para Docente, 200 para EPAKTI_CEO)
curl -i -H "Authorization: Bearer ROLE:DOCENTE_TUTOR" \
  http://localhost:8090/api/v1/admin/mlops/overview-and-drift

curl -s -H "Authorization: Bearer ROLE:EPAKTI_CEO" \
  http://localhost:8090/api/v1/admin/mlops/overview-and-drift | head -n 30
```

---

## PARTE 3 — QUÉ NECESITA ENTREGAR WILO (CEO) Y CÓMO CONECTAMOS LAS 2 MITADES AL FINAL

### Datos comerciales que Wilo les entrega cuando estén listos para Staging/Go-Live
1. **Correo oficial comercial de E-Pakti** (para `NEXT_PUBLIC_EPAKTI_CONTACT_EMAIL` y destinatario de `EPAKTI_SALES_EMAIL`).
2. **Número oficial de WhatsApp Business de E-Pakti** (para `NEXT_PUBLIC_EPAKTI_WHATSAPP_NUMBER` y Meta Cloud API en n8n).
3. **Cuando el motor de Wilo esté publicado en su nube privada:**
   - `EPAKTI_ENGINE_BASE_URL=https://engine.epakti.ec/api/v1`
   - `EPAKTI_ENGINE_API_KEY=<token-rotado-solo-servidor>`

### Switch Final de Integración (Cero Cambios de Código)
Una vez que el equipo Web/Backend marque en verde las 6 tareas contra `http://localhost:8090/api/v1`:
1. Cambian únicamente `EPAKTI_ENGINE_BASE_URL` y `EPAKTI_ENGINE_API_KEY` en el BFF y en el Worker.
2. Corren la misma batería de 7 pruebas `curl` + 1 flujo real de n8n/Bedrock/WhatsApp/Supabase.
3. Quedan conectadas las dos mitades manteniendo el **100 % de la propiedad intelectual del motor ML protegida** en el entorno de Wilo.
