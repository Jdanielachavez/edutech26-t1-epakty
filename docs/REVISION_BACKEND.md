# Revisión completa del backend E-Pakty (24 nov 2026)

Alcance: API (`backend/production/*`), worker, SQL, modelo, scripts, n8n, infra (Docker, Caddy, AWS) y pruebas.
Método: lectura de todo el código, pruebas unitarias, ejecución del pipeline sobre el dataset oficial y pruebas puntuales contra la API con una base simulada.

**No pude verificar** la capa de base de datos real (sin Postgres ni Docker corriendo). Los hallazgos de SQL salen de leer el código y están marcados como «por confirmar en BD».

## Estado en una línea

El diseño de seguridad es bueno y los 15 tests unitarios pasan. Pero hoy el backend **no produce ninguna alerta**, **no se puede construir en Docker** y varias promesas de la página web **no existen** en este repositorio.

---

## Correcciones aplicadas (24 nov, tarde)

| Hallazgo | Estado | Qué se hizo |
|---|---|---|
| B1 · Ninguna alerta | **Corregido** | `backend/reference_model.py`: los niveles ahora salen de percentiles de la cohorte (5 % superior = Crítico, siguiente 15 % = Moderado; con menos de 20 estudiantes se usan los umbrales absolutos 35/65 %). Resultado sobre el dataset oficial: **12 Crítico, 36 Moderado, 192 Bajo**, y 12 casos se encolan hacia n8n. Prueba nueva: `test_risk_levels_are_relative_so_alerts_exist`. Se regeneraron `data/models/reference-logit.json`, Silver, Gold y `frontend/data/dashboard.json`. |
| B2 · Docker no construye | **Corregido** | Se crearon `requirements.txt` (versiones fijas) y `requirements-dev.txt`. El `Dockerfile` pasó a `python:3.13-slim`, la misma versión con la que pasan las pruebas. Verificado en un entorno virtual limpio: instala, la API importa y pasan 16 pruebas (8 siguen omitidas por falta de base de datos). **La imagen Docker en sí no se construyó** (Docker no estaba corriendo). |

**Ojo con B1:** el nivel es un ranking relativo, no una probabilidad. Un estudiante «Crítico» tiene hoy un riesgo calibrado de ~2,4 % a 7,6 %, porque la media del modelo se ajusta a la tasa nacional de abandono. La interfaz no debe presentar ese porcentaje como «probabilidad de abandono». Sigue pendiente B3 y B4.

## Kit de integración de Wilo («UI_UX 2», 24 nov, noche)

Arquitectura nueva: el motor es un servicio aparte. El backend ya no guarda copias de sus resultados; le pide todo por HTTP a `EPAKTI_ENGINE_BASE_URL` (hoy el stub en `engine_stub/`, mañana `https://engine.epakti.ec/api/v1`). **43 pruebas pasan** contra PostgreSQL real y el stub, y las 7 comprobaciones del kit pasan contra nuestro backend en vivo.

| Tarea del kit | Estado | Evidencia |
|---|---|---|
| 1 · Desacoplar el motor (B4) | **Hecho (backend).** Cliente con clave solo de servidor y timeout de 5 s; 14 rutas del contrato pasan por el backend, que vuelve a filtrar cada respuesta por rol. Se borraron las copias locales del motor. | El **stub de Wilo envía la beca de 92 estudiantes al DECE**; el backend la elimina (prueba `test_pedagogical_roles_never_receive_financial_data`). Motor caído → 503 en < 3 s. |
| 1 · Texto honesto de la web | **Pendiente** (fase de interfaz). | — |
| 2 · Secretos por servicio | **Hecho.** `env/*.env.example` por servicio; `compose` da a cada contenedor solo lo suyo (el proxy, solo el dominio). La API y el worker **se niegan a arrancar** con secretos de n8n. El worker ya no tiene SMTP ni WhatsApp: entrega a n8n con firma HMAC (`docs/N8N_WEBHOOKS.md`). | `test_services_refuse_secrets_that_belong_to_n8n`, `test_family_message_goes_to_n8n_signed` |
| 3 · Ingesta 202 asíncrona | **Hecho.** EP-02 (exige `Idempotency-Key`) y la subida de CSV responden 202 con `poll_url`; EP-02B consulta el estado; el worker reintenta al motor 3 veces (2 s → 4 s, con jitter) y deja `DEAD_LETTER` con reintento manual. Datos inválidos van directo a `DEAD_LETTER`. La cola hacia n8n reintenta 6 veces (30 s a 8 min) en lugar de rendirse a los 14 s. | En vivo: 202 en 172 ms (subiendo 1,5 MB), completado en ~2 s. |
| 4 · Supabase + RLS + retención | **Hecho en PostgreSQL local; falta Supabase real** (necesito la URL y la contraseña del proyecto). Bóveda `student_pii_vault`: Bronze, Silver y Gold ya no guardan nombres; la purga diaria (worker o `pg_cron`) los borra al vencer. | `test_pii_is_pseudonymized_and_purged`, aislamiento entre colegios y tutor sin acceso a Colecturía. |
| 5 · Formulario de contacto | **Hecho (backend).** EP-19 con validación, trampa para bots y 5 solicitudes por minuto por IP; se guarda con vencimiento y se avisa a n8n firmado. Falta conectarlo en la web y el correo/WhatsApp reales. | `test_contact_lead_rate_limit_honeypot_and_n8n` |
| 6 · n8n + Bedrock + correo + WhatsApp reales | **Bloqueado:** necesita la instancia de n8n y las credenciales. | — |

### Problemas en el SQL de Supabase del kit (`supabase_schema_rls_retencion_lopdp.sql`)

No lo apliqué tal cual; nuestro esquema `paktai_edu` cubre lo mismo con estas correcciones. Wilo debería ajustarlo:

1. **`auth.jwt() ->> 'role'` no sirve para roles propios.** En Supabase ese campo es el rol de Postgres (`authenticated`/`anon`); poner ahí `DOCENTE_TUTOR` rompe las peticiones. Los roles propios van en `app_metadata` (por ejemplo `auth.jwt() -> 'app_metadata' ->> 'epakti_role'`).
2. **`ingestion_jobs` y `public_contact_leads` no tienen RLS.** En el esquema `public`, con los permisos por defecto de Supabase, cualquiera con la clave pública (`anon`) podría leer los correos y teléfonos de los leads.
3. **La función de purga es `SECURITY DEFINER` sin `search_path`** y se puede ejecutar por RPC desde la clave pública. Debe fijar `search_path` y revocar `EXECUTE` a `public`, `anon` y `authenticated`.
4. **La bitácora de intervenciones permite `FOR ALL`:** cualquier usuario del colegio podría editar o borrar registros. Debe ser solo inserción.
5. El `pg_cron` queda como comentario; hay que programarlo.

## Integración del paquete «BACKEND COMPLETO» de Wilo (24 nov, noche)

> **Reemplazado por la sección anterior:** las copias locales del motor (`data/motor`, `motor.py`) se eliminaron al adoptar el kit de Wilo.

El paquete trae los **resultados** del motor multinivel (predicciones fuera de muestra, SHAP, simulador, semáforos, DECE, colecturía, docentes, 7 territorios, alertas n8n) y el contrato de la API v2.1 (18 endpoints, 11 pantallas). **No trae el código del modelo.**

| Qué | Estado |
|---|---|
| Resultados del motor | **Integrados.** `scripts/import_motor.py` los copia a `data/motor/` y valida que los 240 códigos coincidan con el dataset. Si se cargan otros datos, los endpoints responden 409 en lugar de mostrar resultados de otra cohorte. |
| KPI de Rectoría (EP-04) | **Recalculados** con las pensiones guardadas en la base: 401.357,50 · 321.086 · 167,23 · 99/46/123 alumnos · 164.872 · ahorro 35.751. Coinciden con los de Wilo. La pérdida esperada (102.486) y el ahorro del top 40 (14.334) **no se pudieron reproducir** porque el paquete no incluye su fórmula: se muestran marcados como «valor publicado por el motor». |
| EP-03, EP-05 a EP-09, territorios | **Implementados** con el control de acceso del contrato. Docentes, tutores, inspección y DECE no reciben ningún dato financiero (se retira también la parte de pagos del SHAP y la palanca de convenio); colecturía no ve lo pedagógico; el tutor solo ve su paralelo. EP-03 solo devuelve evaluaciones ya calculadas; un postulante nuevo necesita el motor en línea (422). |
| EP-10 (alertas a n8n) | **Implementado.** Encola las 40 alertas priorizadas hacia el flujo `epakti-alerta-360` de Wilo (`WEBHOOK_N8N_360_URL`), una vez por día y con aprobación explícita. |
| EP-11 (resultado de intervención) | **Implementado** con tabla nueva `intervention_outcomes` (RLS por colegio). Si se aplicó, el caso pasa a «en seguimiento». |
| Roles | Se agregaron `inspeccion`, `colecturia` y `admisiones`. Equivalencias: rectoria = RECTORADO, tutor = DOCENTE_TUTOR, worker = N8N_ORCHESTRATOR. |
| Interfaz | Pantallas de Rectoría, semáforo pedagógico, ficha 360 (SHAP en 4 niveles y simulador), DECE, Colecturía, docentes y horarios, territorios y admisiones; menú según el rol. El demo usa los resultados reales del motor y permite «ver como» cada rol. |
| Pruebas | **36 pasan** contra PostgreSQL real, incluida la privacidad por rol. |

**No integrado:** EP-01 (alta de colegio), EP-02 (sincronización por API; se mantiene la carga de los seis CSV) y todo el Plano B (EP-12 a EP-18: consola interna, reentrenamiento, promoción de modelos, data lake). Requieren el código del motor y su infraestructura MLOps, que no vienen en el paquete.

## Integración con base de datos real (24 nov, noche)

Se levantó PostgreSQL 16 con TLS (`infra/dev/dev-up.sh`) y se probó todo contra ella. **28 pruebas pasan, ninguna omitida** (antes 15 + 8 omitidas). Se construyó la imagen Docker (297 MB, Python 3.13, usuario sin privilegios).

| Hallazgo | Estado |
|---|---|
| B3 · permiso de las vistas | **Reproducido y corregido.** Con el SQL original, `paktai_service` recibía `permission denied for view`. Ahora se concede el `SELECT` después de crear las vistas, las vistas son `security_invoker` y las columnas de reserva de borradores van dentro de la transacción. Probado en una instalación limpia. |
| **Nuevo · `/health` siempre 503** | **Corregido.** Tras `SET ROLE paktai_service`, `pg_stat_ssl` oculta la fila de la propia sesión, así que el TLS salía siempre como «falso». El healthcheck de Docker habría marcado la API como caída para siempre. La prueba anterior aceptaba ambos resultados y por eso no lo detectaba; ahora es estricta. |
| A1 · autenticación | **Corregido.** Se exige el esquema `Bearer` y se compara en bytes (un token con `ñ` ya devuelve 401, no 500). |
| Casos y borrador editable | **Añadido.** `GET /api/v1/interventions` (lista) y `PATCH /api/v1/interventions/{id}/draft` (la persona corrige el mensaje antes de aprobar; no se puede cambiar una vez en cola; queda en la auditoría). Los casos y el detalle devuelven `entrega_en_cola`. |
| Prueba desactualizada | **Ajustada.** `test_concurrent_interventions...` suponía que el lote nunca creaba casos críticos. |
| Interfaz | **Integrada** con la API real: carga de los seis CSV, panel, casos reales, edición y aprobación del borrador. Verificado de punta a punta: 240 estudiantes analizados, 12 casos críticos, mensaje editado y encolado hacia el correo de prueba de `staging`. Se corrigió un fallo propio: con la API real, `delivery_state` viene como `PENDIENTE_REVISION_HUMANA` desde el inicio y el formulario de aprobación nunca habría aparecido. |

**Sigue pendiente:** B4 (la web promete red neuronal, SHAP y simulador que este backend no tiene) y los hallazgos A2 a A5 (reintentos del worker, retención de datos, `proxy` sin secretos). **No probado:** n8n, Bedrock, el worker de envíos (SMTP/WhatsApp) y Supabase real. Cómo correr todo: `docs/DESARROLLO_LOCAL.md`.

## Bloqueantes

### B1. Nadie sale en riesgo: el pipeline nunca crea un caso (verificado)
- Ejecuté `validate_source` + `build` sobre `dataset-ficticio-colegio`: validación OK (240 estudiantes, 18.480 asistencias, 10.080 notas).
- Resultado: **los 240 estudiantes son «Bajo»**, riesgo mínimo 0,21 % y máximo 7,61 %.
- Causa: `reference_model.fit_reference` ajusta el intercepto (−6,01) para que el promedio coincida con la tasa nacional de abandono de AMIE Particular (**0,84 %**). Con ese promedio, ninguna persona llega a los umbrales fijos de `0,35` (moderado) y `0,65` (crítico).
- Consecuencia en cadena: `save_pipeline` solo crea casos para `riskLabel == 'Crítico'` → no hay casos → no se encola nada para n8n → no hay borradores → el panel muestra todo en cero.
- Arreglo: usar umbrales relativos (percentil, por ejemplo el 5 % y el 15 % superior) o un riesgo relativo respecto a la media, y decir en el panel que es un ranking y no una probabilidad.

### B2. El contenedor no se construye (verificado)
- Falta `requirements.txt`; el `Dockerfile` lo copia en la línea 5 y falla.
- Dependencias reales: `fastapi`, `uvicorn`, `psycopg[binary]`, `psycopg_pool`, `boto3`, `httpx`, `python-dotenv`, `python-multipart`, `pydantic`.
- El venv es Python 3.13 y la imagen usa 3.11. Fijar una sola versión.
- Corrección de mi revisión anterior: **no** hace falta `scripts/__init__.py` (funciona como paquete de espacio de nombres) **ni** copiar `data/models` a la imagen (`write_outputs=False` no los lee; el pipeline corrió sin ellos).

### B3. `/api/v1/summary` probablemente falla con «permission denied» (por confirmar en BD)
- En `sql/04_schema_base_datos.sql`, `GRANT SELECT,INSERT,UPDATE ON ALL TABLES ... TO paktai_service` va **antes** de `CREATE VIEW vista_kpi_rectoria`. Ese GRANT solo cubre objetos que ya existen, así que `paktai_service` no puede leer la vista. La API siempre corre `SET LOCAL ROLE paktai_service`.
- Una segunda ejecución de la migración lo taparía (la vista ya existiría), así que falla en el primer despliegue y se «arregla» solo al migrar dos veces.
- Además, con `FORCE ROW LEVEL SECURITY`, la vista corre como su dueño y las políticas solo cubren a `paktai_service` y `dece_write`; si el dueño no es superusuario ni `BYPASSRLS`, devolvería cero filas. Confirmar con el rol real de Supabase.
- Arreglo: mover el `GRANT SELECT` de las vistas a `paktai_service` después de crearlas, o ejecutar la consulta con `security_invoker`.

### B4. La web promete cosas que este backend no hace (verificado)
Busqué `torch`, `shap`, `FiLM` y `GatedResNet` en todo el repositorio: **no existe código**. Lo que sí hay es `reference_model.py`: coeficientes fijos de diseño, `status: reference_not_trained`, sin validación predictiva.

| Lo que dice la página | Qué hay en este backend |
|---|---|
| Red neuronal con contexto territorial | Logit con coeficientes fijos; el territorio no entra en el puntaje, solo calibra la media con AMIE nacional |
| Explicación SHAP por estudiante | Solo `causas_pct` (porcentaje por grupo) |
| Simulador: cuánto baja el riesgo con cada acción | No existe; el demo lo estima en el navegador |
| 65 % y 100 % de acierto en las 40 primeras alertas | Viene de la carpeta de Wilo (GEMINI/), no de este repositorio |
| «Tú lo lees, lo cambias si quieres y lo apruebas» | No hay endpoint para editar el borrador; solo se aprueba tal cual |

Decidir: o se integra el motor de Wilo al backend, o se ajusta el texto de la web y se marca como «próximamente».

---

## Altos

### A1. Autenticación (verificado con pruebas)
- Un token con caracteres no ASCII (por ejemplo `Bearer ñññ`) devuelve **HTTP 500**, porque `hmac.compare_digest` lanza `TypeError` con texto no ASCII. No es una brecha de acceso, pero genera ruido y errores 5xx. Comparar como `bytes`.
- Un token **sin** el prefijo `Bearer ` se acepta (HTTP 200). Exigir el prefijo.
- Sin `CORS_ORIGINS` el preflight devuelve 400 y el navegador bloquea toda la interfaz. Hay que configurarlo con el origen del frontend.

### A2. Worker: reintentos y estados (lectura de código)
- Espera entre reintentos de n8n: `2**intento` segundos (2, 4, 8 s) y máximo 4 intentos: **unos 14 s en total**. Una caída de n8n de un minuto deja el evento en `FAILED` sin aviso. Usar espera creciente de minutos y alertar al administrador.
- Para correo y WhatsApp, un rechazo definitivo (HTTP 400) se guarda como `UNCERTAIN`, porque `status` queda en `None` cuando `send_whatsapp` lanza la excepción. El `if` de «4xx → FAILED` nunca se activa para esos canales.
- No hay forma de resolver los eventos `UNCERTAIN` (ni endpoint ni script).
- `available_at` se actualiza aun cuando el estado final es `SENT`.

### A3. WhatsApp (por verificar contra las reglas de Meta)
- El mensaje de 3.000 caracteres máximo, con saltos de línea, va como **un solo parámetro** de la plantilla. Meta limita esos parámetros (sin saltos de línea y longitud acotada). Es probable que rechace los mensajes largos. Validar y recortar antes de encolar.

### A4. Carga de datos (lectura de código)
- `save_pipeline` solo hace UPSERT: un estudiante que **no aparece** en una carga nueva queda con datos viejos en `gold_estudiantes` y sigue en `/students` y con su caso abierto.
- `bronze_rows` guarda **todas las filas originales** (incluido el nombre) sin plazo de retención. Con datos reales de menores esto es dato personal: definir retención, minimización y base legal (LOPDP).
- `gold.payload` conserva el nombre del estudiante; la vista de rectoría lo excluye bien, pero el endpoint `/students` lo devuelve completo a `admin` y `dece`.

### A5. Docker Compose
- El servicio `proxy` (Caddy) recibe **todo el `.env`** (`env_file`): base de datos, tokens, SMTP y AWS. Solo necesita `API_DOMAIN`. Pasar únicamente esa variable.
- `./certs` no existe y `DATABASE_URL` apunta a `/certs/supabase-ca.crt`. Con `API_DOMAIN` vacío, Caddy no arranca.
- El worker no tiene `healthcheck`; si se cuelga nadie se entera.
- Caddy limita el cuerpo a 20 MB y la app también (20 MB de archivos): el multipart con encabezados rechaza lotes cercanos al límite. Dar margen en Caddy.

---

## Medios

- **Lease de borradores:** `complete_draft` verifica el token pero no que `draft_lease_until` siga vigente; un worker lento puede escribir tras vencer su turno.
- **`approve-delivery`:** cada caso admite una sola entrega (clave `delivery:<caso>`); aprobar un segundo canal responde `queued:false` sin explicar por qué. No se valida que el destinatario sea el representante del estudiante (el sistema no guarda contactos); depende de la aprobación humana.
- **`enforce_draft`:** lanza `KeyError` (HTTP 500) si `driver_principal` no es uno de los tres valores esperados.
- **`/health`:** es público, consulta la base en cada llamada y devuelve la versión de TLS. Bajo carga puede agotar el pool de 8 conexiones.
- **Roles SQL sin uso:** `rectoria_read`, `dece_write` y `tutor_read` no se usan; la API siempre corre como `paktai_service`. El control de acceso por rol vive **solo** en la capa de la aplicación. `vista_tutor` exige `paktai.course` y `paktai.parallel`, que nunca se establecen.
- **Etiquetas de riesgo:** el backend usa 3 niveles (`Crítico`, `Moderado`, `Bajo`). La interfaz nueva asumía 4 (`Alto`/`Medio`); hay que mapear `Moderado` o el color del nivel sale vacío.
- **`build_dashboard_data.py`** escribe una fecha fija (`"imported_at": "2026-01-01"`).
- **Bedrock** (`production/bedrock.py`) fija modelo y región, ignorando `BEDROCK_MODEL_ID` y `AWS_REGION`, y no lo usa la API ni el worker (la generación ocurre en n8n).

## Bajos y documentación

- **Código sin uso:** `domain.py`, `risk_model.py` (cargador de modelo aprobado), `agents.py`, `bedrock_agent.py`, `store.py` y `production/bedrock.py` no los importa ninguna ruta operativa. Borrar o documentar.
- **Documentos desactualizados:** `n8n/CONTRACT.md` describe rutas `/api/interventions` y un webhook `/webhook/paktai/alerta-temprana`; el flujo real usa `/api/v1/interventions/{id}/claim|draft` y `/webhook/paktai-alerta`. `backend/README.md` y `docs/BACKEND_READY.md` dicen que la API se niega a arrancar sin un modelo aprobado y que la bitácora es un JSON local, pero el código usa PostgreSQL y el modelo de referencia.
- **Pruebas:** 15 pasan y **8 se omiten** (todas las de base de datos: RLS, idempotencia, concurrencia, worker). No hay prueba de `/summary`, de los permisos de las vistas ni del flujo completo con n8n. No hay CI.

---

## Lo que está bien hecho

- Consultas parametrizadas; el único `format()` usa nombres de tabla fijos con `%I`. Sin inyección SQL.
- Aislamiento por institución con RLS forzado y `SET LOCAL` por transacción.
- Patrón *outbox* con idempotencia por clave, `SKIP LOCKED` y recuperación de eventos atascados.
- Aprobación humana obligatoria (`approved: Literal[True]`) y destino de prueba con lista blanca en `staging`.
- Los nombres de archivo subidos se validan contra los seis nombres esperados (sin recorrido de directorios), con tope de tamaño y huella SHA-256.
- Tokens con rol y mínimo privilegio: el rol `worker` solo puede reservar caso, guardar borrador y registrar errores.
- Conexión a la base con `verify-full`, TLS 1.3 en SMTP, en Caddy y en las llamadas HTTP, y sin redirecciones.
- n8n envía al modelo solo los campos mínimos (sin el ID del estudiante) y exige salida JSON validada; las políticas de AWS son de mínimo privilegio y el presupuesto se declara como alerta, no como tope.
- El `.env` real tiene permisos `600` y está en `.gitignore`.
- El propio backend se declara honesto: `model_status: reference_not_trained` en la respuesta de la API.

---

## Orden sugerido

1. **B1:** umbrales relativos, para que el panel y n8n tengan algo que mostrar.
2. **B2:** `requirements.txt` y alinear versión de Python.
3. **B3:** reordenar los `GRANT` y probar la migración contra un Postgres real (`TEST_DATABASE_URL`), para activar las 8 pruebas omitidas.
4. **B4:** decidir con Wilo qué del motor neuronal entra al backend y ajustar la web.
5. **A1–A5:** autenticación, reintentos, retención de datos y `proxy` sin secretos.
6. Limpiar código sin uso y actualizar `CONTRACT.md` y los README.
