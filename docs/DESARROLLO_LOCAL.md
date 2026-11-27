# Cómo correr E-Pakty completo en tu Mac

Backend real + base PostgreSQL con TLS + interfaz. Todo escucha solo en `127.0.0.1`.

## 1. Base de datos (una vez)

Necesitas Docker en marcha (`colima start`).

```bash
infra/dev/dev-up.sh
```

Hace esto: crea certificados de desarrollo en `certs/`, levanta PostgreSQL 16 con TLS en el puerto 5544, crea los dos logins (el que migra y el que ejecuta la API), migra el esquema y genera `.env.dev` con tokens aleatorios para cada rol (admin, dece, rectoria, tutor, worker). Es seguro repetirlo.

## 1b. Motor (stub del contrato de Wilo)

```bash
python3 engine_stub/05_KIT_INTEGRACION_SIN_EXPONER_MOTOR/epakti_engine_stub_server.py --port 8090
```

El backend le pide todo lo predictivo (semáforos, SHAP, sensibilidad, Rectoría, DECE, Colecturía, Plano B) por HTTP. Para conectar el motor real de Wilo solo se cambian `EPAKTI_ENGINE_BASE_URL` y `EPAKTI_ENGINE_API_KEY`.

## 2. API

```bash
set -a; . ./.env.dev; set +a
.venv/bin/python -m backend.server --port 8000
```

Comprueba que responde y que la base usa TLS: `curl localhost:8000/health`.

### Worker (ingesta asíncrona, envíos a n8n y purga de datos personales)

```bash
set -a; . ./.env.dev; set +a
.venv/bin/python -m backend.production.worker
```

## 3. Interfaz

```bash
cd frontend-v2 && python3 -m http.server 8800 --bind 127.0.0.1
```

Abre `http://127.0.0.1:8800`, pulsa **Entrar** y escribe:

- Dirección de la API: `http://localhost:8000`
- Token: el del rol que quieras probar, como comentario en `.env.dev` (`# token rectoria: …`). Hay tokens para admin, rectoria, dece, tutor (8vo EGB A), inspeccion, colecturia, admisiones y worker. Cada rol ve solo su menú.

Luego **Carga de datos** → sube los seis CSV de `data/bronze/dataset-ficticio-colegio/` → marca la declaración de datos sintéticos.

### Interfaz: configuración pública y demo

- `frontend-v2/config.js` tiene la dirección de la API y el contacto público (sin secretos). Se genera con `python3 scripts/build_frontend_config.py` desde `env/frontend.env` (`EPAKTI_API_URL`, `EPAKTI_CONTACT_EMAIL`, `EPAKTI_WHATSAPP_NUMBER`). Si falta el contacto, la consola del navegador avisa.
- El modo demo usa `frontend-v2/data/demo-bundle.json`, con respuestas reales del motor. Con el stub encendido se regenera con `.venv/bin/python scripts/build_frontend_demo.py`. En el demo la interfaz aplica los mismos permisos y el mismo filtro de privacidad que el backend; el selector «Ver como» cambia de rol.

## 4. Pruebas (44: 16 unitarias + 28 de integración con base real y stub)

```bash
set -a; . ./.env.dev; set +a
TEST_DATABASE_URL="$DATABASE_URL" .venv/bin/python -m pytest -q
```

Sin `TEST_DATABASE_URL` las 27 de integración se omiten. El stub del motor lo levanta la prueba sola.

## 5. Imagen Docker de la API

```bash
docker build -t epakty-api:dev .
```

## Qué NO se probó aquí

- **n8n y Bedrock:** el borrador del mensaje lo escribe n8n con un modelo de AWS. En las pruebas simulé a n8n con el token `worker` (reservar caso y guardar borrador).
- **El flujo n8n de alertas 360 de Wilo:** el botón «Aprobar y enviar 40 alertas» (EP-10) necesita `WEBHOOK_N8N_360_URL`; sin eso responde 409. La entrega del worker se probó con un servidor simulado.
- **El worker de envíos** (correo y WhatsApp): no hay SMTP ni credenciales de Meta. Aprobar un envío lo deja en la cola de la base.
- **Supabase real:** el esquema se probó en PostgreSQL 16 local, no en Supabase.

## Apagar todo

```bash
pkill -f backend.server            # la API
docker compose -f compose.dev.yaml down   # la base (añade -v para borrar los datos)
colima stop                        # Docker
```
