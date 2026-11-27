# PRIOR_WORK.md · E-Pakty

**E-Pakty existía antes del hackathon.** Lo declaramos completo, como acordamos con la organización: el proyecto se empezó a construir antes del kick-off del viernes 27 de noviembre de 2026 a las 17:00 (hora de Ecuador) y llega al evento ya funcionando.

## Qué existía antes del kick-off

| Parte | Desde cuándo | Dónde está |
|---|---|---|
| Dominio `paktai-ec.com` (marca PAKTAI) | julio de 2026 | Vercel |
| Backend FastAPI, roles y permisos, worker de cargas | 23 al 26 de noviembre de 2026 | `backend/`, `api/` |
| Esquema de base de datos con Row Level Security | 24 al 26 de noviembre de 2026 | `sql/` |
| Workflows n8n (alertas, correo, informes, OCR, errores) | desde el 23 de noviembre de 2026 | `n8n/workflows/` |
| Portal web por rol (landing, semáforo, DECE, Colecturía, Mi aula, informes) | 24 al 27 de noviembre de 2026 | `frontend-v2/` |
| Contrato y stub del motor de predicción | 24 y 25 de noviembre de 2026 | `engine_stub/`, `KIT_INTEGRACION_EPAKTI/` |
| Despliegue público | antes del 27 de noviembre de 2026 | `https://ed.paktai-ec.com` |

El repositorio Git se creó después del kick-off. Por eso los commits llevan fechas del hackathon aunque gran parte del código es anterior: **la fecha del commit no es la fecha en que se escribió el código.** Esta tabla es la referencia.

## Motor de predicción (Wilo)

El modelo de predicción lo desarrolló Wilo, integrante del equipo, por separado y antes del hackathon. Corre en su propio servidor y E-Pakty lo consume por API (versión `v2.4.0-tabm-mini-film-live`). El código del modelo **no está en este repositorio**; aquí solo está el contrato de la API y un stub para desarrollo local (`engine_stub/`).

## Datos

- **Públicos y oficiales:** abandono escolar AMIE (Ministerio de Educación, datos abiertos) y pobreza y desempleo ENEMDU (INEC), en `data/bronze/public/`. Se descargan con `scripts/sync_public_sources.py`.
- **Sintéticos:** el colegio ficticio de `data/bronze/dataset-ficticio-colegio/`. No contiene datos reales de estudiantes, familias ni docentes.

## Librerías y servicios de terceros

Dependencias de Python en `requirements.txt` (FastAPI, Uvicorn, Pydantic, psycopg, httpx, boto3, entre otras). Servicios: Supabase (PostgreSQL), n8n, Vercel, AWS Bedrock (Amazon Nova Lite) y Cloudflare Tunnel. Tipografía Instrument Sans (licencia SIL Open Font).

## Qué hicimos durante el hackathon

Todo lo que se cambie desde el kick-off queda en el historial de commits de este repositorio.
