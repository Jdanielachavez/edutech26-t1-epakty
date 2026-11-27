# API de E-Pakty

Especificación completa y máquina-legible: [`openapi.json`](openapi.json) (OpenAPI 3.1, 49 rutas). Se regenera con:
`set -a; . ./.env.dev; set +a; .venv/bin/python -c "import json;from backend.production.api import create_app;json.dump(create_app().openapi(),open('docs/openapi.json','w'),ensure_ascii=False,indent=1)"`

**Base:** `http://localhost:8000` (local). Todas las rutas van bajo `/api/v1`, salvo `/health`.
**Formato:** JSON. Los errores traen `{"detail": "..."}`.

## 1. Entrar
```bash
curl -s -X POST localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"usuario":"admin.epakty","clave":"<tu contraseña>"}'
# → {"token":"...","expira":...,"usuario":"...","role":"admin","operador":true,"debe_cambiar_clave":false}
```
Después, en cada llamada: `Authorization: Bearer <token>` (la sesión dura 8 h). `GET /api/v1/me` dice quién eres.
Los servicios (worker, n8n) usan tokens fijos por rol (`worker`, `n8n_callback`), no contraseña.

## 2. Rutas principales
| Grupo | Ruta | Quién |
|---|---|---|
| Autenticación | `POST /auth/login` · `POST /auth/change-password` · `GET /me` | todos |
| Modelos calculados | `GET /models/risk` (lista y semáforo) · `GET /models/explain/{EST-001}` (SHAP) · `POST /models/simulate/{EST-001}` `{"acciones":["tutoria_academica"]}` · `GET /models/actions` · `GET /models/card` · `GET /models/provinces` · `GET /models/territory?provincia=Pichincha` | admin, rectoría, DECE, tutor*, inspección, colecturía |
| Datos y carga | `POST /pipeline/batch` (6 CSV, multipart) · `GET /ingestion/jobs/{id}` · `POST /ingestion/batch-sync` | admin |
| Casos y borradores | `POST /intervene/{EST-001}` · `GET /interventions` · `GET/PATCH /interventions/{id}` · `PATCH /interventions/{id}/draft` · `POST /interventions/{id}/approve-delivery` | admin, DECE |
| Usuarios | `GET/POST /admin/users` · `PATCH /admin/users/{usuario}` | admin |
| Estado | `GET /admin/status` · `GET /admin/n8n/observability` | admin / internos |
| Motor de Wilo (proxy) | `GET /dashboard/rectorado/kpis-roi`, `/dashboard/docente-tutor/triage`, `/students/{id}/ficha-360`, `/dashboard/dece/inclusion-nee`, `/dashboard/colecturia/cartera-hogares`, `/dashboard/vicerrectorado/docentes-horarios`; `POST /admissions/evaluate-applicant`, `/n8n/dispatch-alerts` | según rol |
| Público | `POST /public/contact-lead` (formulario web, con límite de intentos) | sin sesión |

\* El tutor solo recibe a los estudiantes de su paralelo.

## 3. Ejemplos
```bash
TOK=...   # el token del login
curl -s localhost:8000/api/v1/models/risk -H "Authorization: Bearer $TOK"
curl -s localhost:8000/api/v1/models/explain/EST-153 -H "Authorization: Bearer $TOK"
curl -s -X POST localhost:8000/api/v1/models/simulate/EST-153 -H "Authorization: Bearer $TOK" \
  -H 'Content-Type: application/json' -d '{"acciones":["tutoria_academica","seguimiento_asistencia"]}'
curl -s -X POST localhost:8000/api/v1/intervene/EST-021 -H "Authorization: Bearer $TOK"
```

## 4. Privacidad por rol
Docentes, tutores, DECE e inspección nunca reciben datos financieros: el backend los quita aunque el motor los envíe.
Colecturía solo recibe lo financiero. Los nombres de estudiantes viven en una bóveda con vencimiento (LOPDP).

## 5. Qué base usa
Por defecto, PostgreSQL local (`DATABASE_URL` de `.env.dev`). Para Supabase: `./scripts/dev_supabase.sh 8000`.
Para que Supabase tenga la tabla de usuarios: `./scripts/supabase_migrate.sh` (pide la contraseña de dueño por teclado).
