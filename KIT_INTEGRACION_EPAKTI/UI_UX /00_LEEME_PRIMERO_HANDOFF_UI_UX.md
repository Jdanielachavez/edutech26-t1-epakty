# Paquete Oficial de Handoff UI/UX — Plataforma SaaS **E-Pakti**

Bienvenido al paquete técnico y de diseño de **E-Pakti** (*Plataforma Multi-Tenant de Inteligencia Educativa Preventiva, Permanencia y Sostenibilidad Escolar*). Aquí tienes todo lo necesario para diseñar en Figma y conectar el frontend (`Next.js / React + Tailwind + shadcn/ui + Recharts`) contra nuestro motor predictivo FastAPI y los flujos agénticos de **n8n**.

---

## 1. Contenido del Archivo `UI_UX.zip`

| Carpeta | Archivos Incluidos | Para qué sirve |
| --- | --- | --- |
| **`01_ESTRATEGIA_Y_PROMPT_UI_UX/`** | `DOSSIER_MAESTRO_E_PAKTI_ARQUITECTURA_API_N8N_Y_UI_UX.md`<br>`INFORME_MEJORA_MODELOS_SOTA_GPU_2026.md`<br>`PROMPT_MAESTRO_UI_UX_E_PAKTI.md`<br>`RESUMEN_EJECUTIVO_COLEGIO_DEMO.md` | Giro de negocio de E-Pakti, arquitectura Dual-Plane (`app.epakti.ec` + `admin.epakti.ec`), informe científico SOTA v2.4 en GPU RTX 5070 con ablaciones controladas (`2,92M` registros reales), diccionario de los **48 indicadores estimados**, especificación de las **11 pantallas** y **Prompt Maestro listo para copiar y pegar**. |
| **`02_CONTRATOS_API_Y_N8N/`** | `openapi_especificacion_endpoints_ui_n8n.json`<br>`tipos_typescript_epakti_frontend.ts`<br>`payloads_n8n_alertas_360.json`<br>`workflow_n8n_epakti_360.json`<br>`api_contrato_onboarding_colegio.json`<br>`arquitectura_mlops_flywheel_saas.json`<br>`resumen_semaforizacion_morosidad_y_auditoria.json`<br>`validacion_motor_nacional_amie_censo_enemdu.json`<br>`reporte_benchmark_sota_gpu_multinivel.json`<br>`reporte_verificacion_integral_15_tests.json` | Contratos OpenAPI 3.1 ejecutables (`paths` reales) de los **20 Endpoints REST (`EP-01` a `EP-19` + `EP-02B`)**, **interfaces TypeScript + Design Tokens**, payloads RBAC consistentes (`0/40` desfases) con colas separadas Permanencia (`23/40`) + Académico (`39/40`), workflow **n8n v2 real (`13` nodos / `12` conexiones: `body`, `IfV2`, `Bedrock ai_languageModel` y `jsonBody`)**, benchmark GPU RTX 5070 y reporte de auditoría (**`22/22` pruebas**). |
| **`03_DATOS_REALES_PARA_MOCKS_Y_PROTOTIPOS/`** | 14 tablas CSV reales auditadas (`240` alumnos, `204` hogares, `92` NEE, `14` docentes, `7` territorios de Ecuador, `1→25` colegios MLOps, SHAP y sensibilidad pedagógica unificada) | Datos reales ya estimados y calibrados para poblar Figma, tablas interactivas, gráficos Waterfall SHAP, simulador de sensibilidad *What-If* y curvas MLOps sin inventar datos falsos. |
| **`04_GRAFICOS_REFERENCIA_VISUAL/`** | 5 gráficos PNG de alta resolución generados por el motor | Referencia exacta de cómo lucen los semáforos calibrados, la cascada SHAP, las reducciones de sensibilidad, el sesgo territorial hipotético y el Data Flywheel MLOps. |
| **`05_KIT_INTEGRACION_SIN_EXPONER_MOTOR/`** | **`MANUAL_OPERATIVO_CONEXION_EN_VIVO_EPAKTI.md`** *(runbook en vivo para conectar el motor real de Wilo + cargar demos/colegios nuevos!)*<br>**`PROMPT_E_INSTRUCCIONES_EQUIPO_WEB_BACKEND.md`** *(brief de tareas del equipo dev Mac)*<br>`.env.templates_por_servicio.example`<br>`epakti_engine_stub_server.py` (Python stdlib, 0 dependencias)<br>`supabase_schema_rls_retencion_lopdp.sql`<br>`GUIA_INTEGRACION_EQUIPO_WEB_SUPABASE_N8N.md` | **Para el Equipo Web / Backend / Supabase / n8n / Bedrock:** Manual operativo para conectar **EN VIVO** contra el motor PyTorch multi-tenant de Wilo (que arranca 100 % vacío y recibe cualquier base CSV/JSON nueva) + Prompt de ejecución + separación de secretos por servicio + Servidor Stub local en `http://localhost:8090` con los **20 endpoints OpenAPI 3.1** y RBAC real + esquema Supabase RLS/LOPDP — **sin exponer nunca el código propietario `GEMINI/`**. |

---

## 2. Reglas de Oro de Arquitectura (Leer Antes de Diseñar)

1. **Dos Planos Separados (Dual-Plane SaaS):**
   * **Plano A (`app.epakti.ec` — Portal Colegio Cliente, 6 Pantallas, `EP-01` a `EP-11`):** Tema claro limpio (`#F8FAFC`). Roles: `RECTORADO`, `DOCENTE_TUTOR`, `DECE`, `INSPECCION`, `COLECTURIA`, `ADMISIONES`. **Nunca muestra MLOps interno ni otros colegios.**
   * **Plano B (`admin.epakti.ec` — Consola Interna E-Pakti, 5 Pantallas, `EP-12` a `EP-18`):** Tema técnico diferenciado (`#0F172A`). Roles: `EPAKTI_CEO`, `EPAKTI_MLOPS`, `EPAKTI_DATA_SCIENCE`, `EPAKTI_CS`. Controla multi-tenancy, Data Lake k-anónimo (LOPDP), re-entrenamiento, 5 Candados *Champion vs. Challenger*, *Canary/Rollback*, drift `PSI/ECE`, *Feature Flags* y observabilidad n8n.
2. **Semaforización Escolar Calibrada (PROHIBIDO usar letras bancarias `AAA`–`C`):**
   * 🟢 `VERDE` (`#1B9E77` / `#E8F8F5`) — Acompañamiento Regular / Trayectoria Lograda / Pago Regular
   * 🟡 `AMARILLO` (`#D4AC0D` / `#FEF9E7`) — Observación Preventiva en Aula / Seguimiento de Fecha
   * 🟠 `NARANJA` (`#D95F02` / `#FDF2E9`) — Apoyo Focalizado / Fecha Flexible Día 15–20
   * 🔴 `ROJO` (`#C0392B` / `#FDEDEC`) — Intervención Prioritaria Inmediata / Convenio
3. **Privacidad Estricta RBAC (LOPDP / LOEI Ecuador):**
   * **Docentes, Tutores, Inspección y DECE** ven **CERO datos financieros** (sin deuda, sin cuotas vencidas, sin pagos tardíos).
   * **Colecturía** ve únicamente su tablero financiero de pagos por hogar y su explicación SHAP financiera, sin expedientes clínicos del DECE.
4. **Autonomía Total (CERO Dependencia de ERPs de Terceros):**
   * **E-Pakti NO requiere que el colegio tenga Runachay, Idukay, Educalinks, Academium ni ningún software previo.** El onboarding y la ingesta (`EP-01`, `EP-02`) funcionan 100 % de forma autónoma con plantillas **Excel/CSV, registro nativo o API genérica**; si el colegio ya tiene un sistema externo, el conector es **estrictamente opcional**.
5. **Conexión con Backend y n8n (Sin exponer el motor ML `GEMINI/`):**
   * Base URL del motor: `EPAKTI_ENGINE_BASE_URL=http://localhost:8090/api/v1` en desarrollo local con el Stub incluido (`https://engine.epakti.ec/api/v1` en producción) con header `Authorization: Bearer <JWT>`.
   * Todos los envíos a WhatsApp/Gmail desde el botón *"Aprobar y Enviar vía n8n"* (`EP-10`) deben confirmar el registro de intervención (`EP-11: POST /api/v1/interventions/log-outcome`) para alimentar el candado MLOps contra *Feedback Loops*.
   * **¿Eres el equipo Web / Backend / Supabase / n8n en Mac?** Abre directamente [`05_KIT_INTEGRACION_SIN_EXPONER_MOTOR/PROMPT_E_INSTRUCCIONES_EQUIPO_WEB_BACKEND.md`](05_KIT_INTEGRACION_SIN_EXPONER_MOTOR/PROMPT_E_INSTRUCCIONES_EQUIPO_WEB_BACKEND.md) para copiar el prompt de ejecución y seguir los 6 pasos con criterios de verificación.
