# E-Pakty · Alerta temprana de abandono escolar (Ecuador)

**Track 1 · Problemáticas de la educación** · Hackathon EduTech Eight Academy by n8n 2026
Demo en vivo: **https://ed.paktai-ec.com** · Documentación completa: **https://ed.paktai-ec.com/docs.html**

> E-Pakty existía antes del hackathon. Lo que ya estaba hecho está declarado en [`PRIOR_WORK.md`](PRIOR_WORK.md) y el uso de IA en [`AI_USAGE.md`](AI_USAGE.md).

## Problema

En Ecuador, un estudiante que deja el colegio casi nunca lo hace de un día para otro. Antes aparecen señales: le bajan las notas, falta sin justificar, su bienestar empeora o la familia se atrasa con la pensión. Esas señales están repartidas entre el docente, el DECE, inspección y colecturía, y nadie las ve juntas a tiempo. Cuando el colegio se entera, el estudiante ya se fue.

Datos públicos que usamos como contexto: tasas de abandono por provincia de AMIE (Ministerio de Educación) y pobreza y desempleo de ENEMDU (INEC).

## Usuario

Colegios de Ecuador, y dentro de cada uno:

| Rol | Qué necesita |
|---|---|
| Docente tutor | Saber a quién de su aula acompañar esta semana y por qué (notas, faltas o bienestar). |
| DECE | Ver los casos de bienestar e inclusión y registrar el acompañamiento. |
| Rectorado | Ver el colegio completo y decidir dónde poner esfuerzo. |
| Colecturía | Ver qué familias se atrasan con la pensión, sin ver datos académicos. |
| Familia | Recibir un aviso claro y humano, aprobado por el colegio. |

**Qué no resuelve:** no decide por el colegio, no reemplaza al DECE ni al docente, y no le muestra a la familia un porcentaje de riesgo.

## Arquitectura

```
Colegio sube CSV (notas, asistencia, bienestar, pensiones)
        │
        ▼
Portal web (frontend-v2, Vercel) ──► API FastAPI (backend, Vercel) ──► Supabase PostgreSQL con RLS por rol
                                          │
                                          ├──► Motor de predicción de Wilo (API externa, TabM-mini)
                                          │        └── devuelve riesgo + factores, firmado con HMAC
                                          │
                                          └──► n8n (webhooks)
                                                   ├── Amazon Nova Lite redacta el borrador del aviso
                                                   ├── una persona del colegio lo aprueba
                                                   └── se envía por correo / WhatsApp a la familia
```

- **Semáforo:** cada estudiante sale en rojo, naranja, amarillo o verde según su riesgo comparado con el resto del colegio.
- **Permisos:** cada rol ve solo lo suyo, tanto en la API como en la base (Row Level Security).
- **Si el motor falla:** la carga queda en `FAILED` con un mensaje claro y el panel conserva la última carga válida.

## Estructura

| Carpeta | Qué hay |
|---|---|
| `frontend-v2/` | Página web + app (landing, demo, pantallas por rol). `config.js` = contacto y URL de la API |
| `backend/` | API FastAPI (`production/`), modelo de referencia, `server.py` (arranque), `tests/` |
| `engine_stub/` | Motor de Wilo (stub en el puerto 8090) |
| `sql/` | Esquema `paktai_edu` con RLS (Supabase/Postgres) |
| `n8n/workflows/` | Flujos n8n vigentes: borrador con Nova Lite, entrega por correo, contacto, errores y `epakti_alerta_360_firmado.json` (alertas del motor con firma HMAC). |
| `env/` | Plantillas de variables por servicio (`*.env.example`) |
| `infra/` | Caddy, scripts de desarrollo local, políticas AWS |
| `scripts/` | Migración, construcción de datos y de la demo |
| `data/` | Datos bronze/silver/gold (incluye `bronze/dataset-ficticio-colegio`) |
| `docs/` | Desarrollo local, webhooks n8n, revisión del backend |
| `assets/` | Logo original |

## Arranque rápido

Ver `docs/DESARROLLO_LOCAL.md`. Resumen:

```bash
infra/dev/dev-up.sh
set -a; . ./.env.dev; set +a; .venv/bin/python -m backend.server
cd frontend-v2 && python3 -m http.server 8800 --bind 127.0.0.1
```

Pruebas: `TEST_DATABASE_URL="$DATABASE_URL" .venv/bin/python -m pytest -q` (44).

## Operación diaria

| Qué | Comando |
|---|---|
| Reiniciar API (8000) y worker con el código actual | `./scripts/reiniciar_local.sh` (registros en `logs/`) |
| API contra Supabase (8011) | `./scripts/dev_supabase.sh 8011` |
| Publicar el webhook del motor por túnel temporal | `./scripts/tunel_webhook.sh` (muestra la URL HTTPS) |
| Importar los flujos en n8n | `./scripts/n8n_import_all.sh epakty-n8n` |
| Variables de Vercel / rotar administrador | `.venv/bin/python scripts/vercel_env.py [--solo-admin]` y luego `vercel --prod` |
| Despliegue en servidor | `docs/DESPLIEGUE_PRODUCCION.md` |

## Contacto
paktai_ec@outlook.com · WhatsApp +593 96 271 9099
