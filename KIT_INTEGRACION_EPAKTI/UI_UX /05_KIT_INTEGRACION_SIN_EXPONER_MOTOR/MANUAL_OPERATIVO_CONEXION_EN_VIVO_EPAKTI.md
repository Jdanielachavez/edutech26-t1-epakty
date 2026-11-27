# Manual Operativo de Conexión en Vivo — Motor ML Privado de **E-Pakti** ↔ Plataforma Web / Supabase / n8n

> **Versión:** `v2.4.0-tabm-mini-film-live`  
> **Propósito:** Conectar **EN VIVO** las dos mitades de E-Pakti (el motor predictivo PyTorch de Wilo + la plataforma UI/UX, BFF, Supabase y n8n/Bedrock del equipo) **sin datos ficticios precargados** y con **100 % de protección de propiedad intelectual** (`GEMINI/` nunca sale del entorno de Wilo).

---

## 1. Arquitectura en Vivo (Arranque 100 % Vacío + Multi-Tenant Real)

```
┌────────────────────────────────────────────────────────────────────────────┐
│  MUNDO 1 — EQUIPO UI/UX, BACKEND BFF, SUPABASE Y n8n (Mac / Cloud)         │
│  Next.js (Plano A + Plano B) <-> BFF Proxy <-> Supabase Postgres (RLS/PII) │
│                                     │                                      │
│  HTTPS + Authorization: Bearer <Supabase JWT HS256>                        │
│        + X-Epakti-Engine-Key: <llave compartida solo servidor>             │
│        + X-School-Id: <school_id del colegio> (SOLO datos pseudonimizados) │
└─────────────────────────────────────┼──────────────────────────────────────┘
                                      ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  MUNDO 2 — MOTOR PREDICTIVO EN VIVO DE WILO (Docker / PC Wilo / Cloud Run) │
│  `api_motor_epakti.py` — ARRANCA 100 % VACÍO (0 colegios, 0 alumnos)       │
│   • 7 redes PyTorch `TabM_mini-FiLM` serializadas (`bundle_modelos...`)    │
│   • Catálogos oficiales de Ecuador (1.042 parroquias Censo 2022,           │
│     24 provincias ENEMDU 2024, 6.647 planteles AMIE, INEVAL)               │
│   • Persistencia multi-tenant durable en SQLite WAL por `school_id`        │
│   • Ingesta dinámica real (`EP-02` JSON/CSV o `EP-02C` multipart CSV)      │
│   • Scoring PyTorch + SHAP aditivo exacto + What-If + Colecturía + RBAC    │
└─────────────────────────────────────┼──────────────────────────────────────┘
                                      ▼  Webhook firmado HMAC-SHA256 (`EP-10`)
┌────────────────────────────────────────────────────────────────────────────┐
│  ORQUESTACIÓN AGÉNTICA EN VIVO (n8n + AWS Bedrock + WhatsApp + Correo)     │
│  `workflow_n8n_epakti_360.json` (13 nodos / 12 conexiones)                 │
│   └─► Callback `EP-11` (`POST /api/v1/interventions/log-outcome`)          │
└────────────────────────────────────────────────────────────────────────────┘
```

### Regla de Oro del Arranque en Vivo
* **El motor NO trae precargados los 240 alumnos ficticios.** Si un colegio aún no ha cargado sus tablas, los endpoints de tablero (`EP-04`..`EP-10`) devuelven **`HTTP 404`** con `{"code": "SCHOOL_NOT_INGESTED_YET", ...}` para que la UI muestre el asistente de carga inicial (Onboarding / Subida CSV).
* **Autonomía total sin ERPs externos:** Ningún colegio necesita tener Runachay, Idukay ni Educalinks. Basta con subir `estudiantes.csv` (y opcionalmente `asistencia.csv`, `notas.csv`, `pensiones.csv`, `horarios.csv`, `docentes.csv`) por API o formulario web.
* **Cero PII obligatoria (LOPDP Ecuador):** El motor trabaja con `codigo` pseudonimizado (`EST-001`, etc.); la columna `nombre_ficticio` es completamente opcional. El BFF del equipo web cruza el `codigo` con su bóveda PII en Supabase (`student_pii_vault`).

---

## 2. Paso a Paso — Encendido del Motor en Vivo (Lado Wilo)

### Paso 2.1: Crear el archivo de secretos del motor (`GEMINI/.env.engine`)
Copia `GEMINI/.env.engine.example` a `GEMINI/.env.engine` y completa los secretos reales:
1. Genera una llave compartida servidor-a-servidor para `EPAKTI_ENGINE_API_KEY`:
   ```powershell
   C:\Users\wilog\AppData\Local\Temp\n8n-ml-educativo-py311\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
2. Copia el **`JWT Secret`** de tu proyecto real de Supabase (*Project Settings → API → JWT Secret*) y pégalo en `SUPABASE_JWT_SECRET`.
3. Coloca `N8N_WEBHOOK_URL` apuntando al webhook activo de `workflow_n8n_epakti_360.json`, más `N8N_WEBHOOK_HMAC_SECRET` y `EPAKTI_CALLBACK_TOKEN`.
4. Deja `EPAKTI_ALLOW_DEV_ROLE_TOKENS=false` para producción (o `true` temporalmente si quieren hacer el primer smoke test sin JWT antes de activar Supabase Auth).

### Paso 2.2: Arrancar el motor en vivo (Opción A: Directo en PowerShell · Opción B: Docker)

**Opción A — Directo en el PC de Wilo (arranca en ~2 segundos, 100 % vacío):**
```powershell
cd c:\Users\wilog\OneDrive\Desktop\N8N\GEMINI
C:\Users\wilog\AppData\Local\Temp\n8n-ml-educativo-py311\Scripts\python.exe api_motor_epakti.py --host 0.0.0.0 --port 8090
```

**Opción B — Contenedor Docker listo para VPS / AWS ECS / Google Cloud Run:**
```powershell
cd c:\Users\wilog\OneDrive\Desktop\N8N\GEMINI
docker build -t epakti-live-engine:v24 .
docker run -d --name epakti-engine -p 8090:8090 --env-file .env.engine -v epakti_live_data:/data epakti-live-engine:v24
```

### Paso 2.3: Exponer HTTPS seguro hacia el equipo Web / Backend (en 1 minuto para pruebas en vivo)
Si el motor corre en tu PC de Windows y el equipo Web está en sus Macs / Vercel / Staging:
```powershell
# Instala Cloudflare Tunnel una sola vez: winget install Cloudflare.cloudflared
cloudflared tunnel --url http://127.0.0.1:8090
```
Cloudflare te entrega inmediatamente una URL HTTPS pública temporal tipo `https://xxxx-xxxx.trycloudflare.com` (o usa tu dominio definitivo `https://engine.epakti.ec` con un Named Tunnel o Cloud Run).

Verifica que responde vivo y vacío:
```bash
curl -s https://<TU-URL-HTTPS>/health
# Esperado:
# {"status":"ok","mode":"EPAKTI_LIVE_PYTORCH_ENGINE","colegios_registrados":0,"datos_ficticios_precargados":false,...}
```

---

## 3. Paso a Paso — Conexión de la Plataforma Web / Supabase / n8n (Lado Equipo UI/UX)

El contrato OpenAPI 3.1 es **100 % idéntico** al del servidor Stub que el equipo ya probó en `localhost:8090`. Para conectar ambos mundos **NO hay que reescribir el frontend**:

1. **Actualizar 2 variables en el BFF Proxy y en el Worker Asíncrono:**
   ```env
   EPAKTI_ENGINE_BASE_URL=https://<TU-URL-HTTPS>/api/v1
   EPAKTI_ENGINE_API_KEY=<LA_MISMA_LLAVE_QUE_GENERO_WILO>
   ```
   *(Recuerda: **NUNCA** pongas `EPAKTI_ENGINE_API_KEY` en variables `NEXT_PUBLIC_*` del navegador!)*
2. **Asegurar claims en el JWT de Supabase (`app_metadata`):**
   Cada usuario autenticado en Supabase debe tener en su `raw_app_meta_data`:
   ```json
   {
     "role": "RECTORADO",
     "school_id": "SCH-DEMO-240"
   }
   ```
   Roles soportados en Plano A: `RECTORADO`, `DOCENTE_TUTOR`, `DECE`, `INSPECCION`, `COLECTURIA`, `ADMISIONES`.  
   Roles soportados en Plano B (`/api/v1/admin/*`): `EPAKTI_CEO`, `EPAKTI_MLOPS`, `EPAKTI_DATA_SCIENCE`, `EPAKTI_CS`.
3. **Configurar n8n (Workflow `workflow_n8n_epakti_360.json` — 13 nodos / 12 conexiones):**
   * En el **Nodo 9** (callback `POST /api/v1/interventions/log-outcome`), apunta a `https://<TU-URL-HTTPS>/api/v1/interventions/log-outcome` enviando los headers:
     - `X-Epakti-Callback-Token: <EPAKTI_CALLBACK_TOKEN>`
     - `X-School-Id: {{ $json.school_id }}`

---

## 4. Prueba en Vivo #1 — Conectar y Estimar la Base Ficticia de 240 Alumnos

Una vez encendidos ambos lados, puedes inyectar la base ficticia de prueba **EN VIVO** por cualquiera de las 3 vías reales:

### Vía A — Desde la UI / BFF del equipo (Subida Multipart de CSVs reales `EP-02C`)
```bash
curl -i -X POST "https://<TU-URL-HTTPS>/api/v1/ingestion/upload-csv" \
  -H "Authorization: Bearer <JWT_RECTORADO_SCH_DEMO_240>" \
  -H "X-Epakti-Engine-Key: <EPAKTI_ENGINE_API_KEY>" \
  -H "X-School-Id: SCH-DEMO-240" \
  -H "Idempotency-Key: DEMO-LIVE-001" \
  -F "school_id=SCH-DEMO-240" \
  -F "nombre=UE Piloto Ficticio Cuenca" \
  -F "dpa_parroquia_plantel=010150" \
  -F "regimen=Sierra-Amazonía" \
  -F "fecha_corte=2025-10-31" \
  -F "estudiantes=@estudiantes.csv" \
  -F "asistencia=@asistencia.csv" \
  -F "notas=@notas.csv" \
  -F "pensiones=@pensiones.csv" \
  -F "horarios=@horarios.csv" \
  -F "docentes=@docentes.csv"
```
Responde **`202 Accepted`** en `< 100 ms` con `{"job_id": "DEMO-LIVE-001", "poll_url": "/api/v1/ingestion/jobs/DEMO-LIVE-001"}`.  
El frontend hace polling a `GET /api/v1/ingestion/jobs/DEMO-LIVE-001` cada `1s` hasta recibir `"status": "COMPLETED"` (`~3-6 segundos` para 240 alumnos con PyTorch + SHAP exacto + What-If + Colecturía!).

### Vía B — Desde el BFF / Worker por JSON (`POST /api/v1/ingestion/batch-sync`, `EP-02`)
Envía las tablas directamente como arrays JSON (`estudiantes: [...]`, `asistencia: [...]`, `notas: [...]`, `pensiones: [...]`) o como strings CSV en `archivos_csv: { "estudiantes_csv": "...", ... }`.

### Vía C — En 1 solo comando desde la máquina de Wilo (Script CLI incluido)
```powershell
cd c:\Users\wilog\OneDrive\Desktop\N8N\GEMINI
C:\Users\wilog\AppData\Local\Temp\n8n-ml-educativo-py311\Scripts\python.exe cargar_colegio_en_vivo.py `
  --url http://127.0.0.1:8090 `
  --school-id SCH-DEMO-240 `
  --nombre "UE Piloto Ficticio Cuenca" `
  --dpa 010150 `
  --regimen "Sierra-Amazonía" `
  --fecha-corte 2025-10-31 `
  --csv-dir "..\bronce\Colegio\Demo_Escolar\2025-2026\exportado\extraido\dataset-ficticio-colegio\dataset-ficticio-colegio" `
  --api-key "<EPAKTI_ENGINE_API_KEY>" `
  --jwt-secret "<SUPABASE_JWT_SECRET>"
```
*(Agrega `--dispatch-n8n` al final si además quieres disparar en ese mismo instante las alertas reales hacia n8n/Bedrock/WhatsApp!)*

---

## 5. Prueba en Vivo #2 — Demostraciones Comerciales con Cualquier Colegio NUEVO

Cuando quieras hacer una **demo en vivo ante un colegio nuevo** con una base nueva (de 15, 100, 500 o 2.000 alumnos, en Quito, Guayaquil, Cuenca, Manta, Ambato, etc.), **NO reinicias el servidor ni tocas código**:

### Formato de Archivos CSV Aceptados (100 % Autónomo)
| Archivo CSV | Requerido | Columnas clave | Notas de validación automática |
| --- | --- | --- | --- |
| **`estudiantes.csv`** | **OBLIGATORIO** | `codigo`, `curso`, `paralelo`, `anio_nacimiento`, `genero`, `necesidad_educativa`, `beca_porcentaje`, `representante_codigo`, *(opcional)* `dpa_residencia`, *(opcional)* `nombre_ficticio` | Rechaza códigos vacíos, duplicados o `beca_porcentaje` fuera de `[0, 100]`. Reporta conteo exacto en `validacion_calidad`. |
| **`asistencia.csv`** | Opcional | `codigo_estudiante`, `fecha` (`YYYY-MM-DD`), `estado` (`presente`, `falta_injustificada`, `falta_justificada`, `atraso`) | Filtra automáticamente `fecha <= fecha_corte` (cero fuga temporal). |
| **`notas.csv`** | Opcional | `codigo_estudiante`, `quimestre`, `parcial`, `materia`, `nota` (`0` a `10`), *(opcional)* `fecha_publicacion` | Rechaza notas `< 0` o `> 10`; si trae `fecha_publicacion`, filtra estrictamente `<= fecha_corte`. |
| **`pensiones.csv`** | Opcional | `codigo_estudiante`, `mes` (`YYYY-MM`), `valor`, `estado`, `fecha_pago` | Si el colegio no sube pensiones (ej. fiscal o piloto solo pedagógico), el motor funciona igual y desactiva el semáforo financiero limpiamente. |
| **`horarios.csv` / `docentes.csv`** | Opcional | `curso`, `paralelo`, `materia`, `docente_codigo` / `codigo`, `nombre_ficticio` | Habilita el tablero de Vicerrectorado (`EP-09`). |

### Cargar el Nuevo Colegio en Vivo (Ejemplo Quito `170150` o Guayaquil `090150`):
Simplemente sube sus CSVs desde el portal del nuevo `school_id` (ej. `SCH-DEMO-QUITO-02`) o ejecuta `cargar_colegio_en_vivo.py --school-id SCH-DEMO-QUITO-02 --dpa 170150 --csv-dir <carpeta_nueva>`.
* Automáticamente el motor:
  1. Cruza su DPA/AMIE con el **Censo INEC 2022 + ENEMDU 2024 + AMIE + INEVAL** real de esa parroquia/provincia.
  2. Calcula los semáforos PyTorch `TabM_mini-FiLM`, cascada SHAP aditiva exacta, What-If y alertas n8n en vivo.
  3. Lo aísla completamente de `SCH-DEMO-240` (`403 TENANT_ISOLATION_VIOLATION` ante cualquier intento cruzado).
  4. Aparece de inmediato en la Consola CEO/MLOps (`GET /api/v1/admin/tenants`) junto a los demás colegios activos.

---

## 6. Checklist Rápido de Verificación E2E Antes de Demo con Clientes

1. [ ] `GET /health` responde `200 OK` con `mode: "EPAKTI_LIVE_PYTORCH_ENGINE"` y `7` modelos cargados.
2. [ ] Una llamada sin `X-Epakti-Engine-Key` o con JWT alterado responde **`401 Unauthorized`**.
3. [ ] Un colegio nuevo antes de subir CSV responde **`404 SCHOOL_NOT_INGESTED_YET`** (sin inventar 240 filas).
4. [ ] Tras subir CSVs (`EP-02` / `EP-02C`), `GET /api/v1/ingestion/jobs/{job_id}` llega a `COMPLETED` con conteos exactos `aceptados` / `rechazados`.
5. [ ] En la UI con usuario **`DOCENTE_TUTOR`**: Triage (`EP-05`) y Ficha 360° SHAP + What-If (`EP-06`) cargan en vivo con **0 datos financieros**, y el acceso a Colecturía (`EP-08`) devuelve **`403 RBAC_LOPDP_BLOCKED`**.
6. [ ] En la UI con usuario **`COLECTURIA`**: Cartera por hogares (`EP-08`) carga con SHAP financiero, y el acceso a DECE (`EP-07`) devuelve **`403 RBAC_DECE_ONLY`**.
7. [ ] Al pulsar **"Aprobar y Enviar vía n8n"** (`EP-10`), n8n recibe las alertas con firma HMAC, AWS Bedrock redacta el mensaje sin filtrar mora a docentes, llega el WhatsApp/Correo real y el Nodo 9 dispara `EP-11` registrando la intervención en SQLite/Supabase.
8. [ ] En Plano B (**`EPAKTI_CEO`**), `GET /api/v1/admin/tenants` y `GET /api/v1/admin/mlops/overview-and-drift` reflejan los colegios cargados en vivo y el contador de intervenciones MLOps actualizado.
