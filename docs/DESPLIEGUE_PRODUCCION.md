# Despliegue en un servidor permanente

Un servidor con Docker corre todo lo que no puede vivir en Vercel: **API, worker, n8n y el proxy HTTPS**. La base de datos es tu
Supabase y el motor predictivo lo aloja Wilo.

```
Internet ──HTTPS──> Caddy ─┬─> api:8000        (navegador → API)
                           └─> n8n:5678        (SOLO /webhook/*; el editor no se publica)
worker ──> Supabase · motor de Wilo · n8n (firmado con HMAC)
```

## Requisitos
- Un servidor Linux (1 vCPU / 2 GB bastan para el piloto) con Docker y Docker Compose.
- Dos nombres DNS apuntando a su IP: uno para la API (`API_DOMAIN`) y otro para n8n (`N8N_DOMAIN`). Puertos 80 y 443 abiertos.
- Tu Supabase con el esquema migrado (`scripts/supabase_migrate.sh`) y el certificado `certs/supabase-ca.crt`.

## 1. Variables (cada servicio solo recibe las suyas)
```bash
for f in api worker n8n proxy; do cp env/$f.env.example env/$f.env; done
```
Completa cada archivo. Lo esencial:

| Archivo | Variables clave |
|---|---|
| `env/api.env` | `DATABASE_URL` (login `paktai_app`), `PAKTAI_USERS` + `SESSION_SECRET` (administrador inicial), `EPAKTI_ENGINE_BASE_URL/KEY`, `EPAKTI_SCHOOL_ID`, `CORS_ORIGINS` |
| `env/worker.env` | `DATABASE_URL`, `EPAKTI_ENGINE_*`, `EPAKTI_SCHOOL_*`, `N8N_WEBHOOK_BASE_URL` (`https://<N8N_DOMAIN>/webhook`), `N8N_WEBHOOK_HMAC_SECRET`, `N8N_WEBHOOK_TOKEN` |
| `env/n8n.env` | `N8N_ENCRYPTION_KEY` (guárdala), `WEBHOOK_URL`, `N8N_WEBHOOK_HMAC_SECRET` (el mismo del worker) |
| `env/proxy.env` | `API_DOMAIN`, `N8N_DOMAIN` |

El administrador inicial: `.venv/bin/python -m scripts.create_user env/api.env admin.colegio admin` (la contraseña queda como comentario;
bórrala del archivo cuando la guardes). Después, el resto de cuentas se crean desde **Usuarios**.

## 2. Levantar
```bash
docker compose up -d --build
docker compose ps          # los cuatro servicios deben quedar "healthy"/"Up"
curl -s https://$API_DOMAIN/health        # {"status":"ok","database":{"ssl":true,...}}
```

## 3. n8n: flujos y credenciales
El editor de n8n **no está en Internet**. Entra por túnel SSH:
`ssh -L 5678:localhost:5678 usuario@servidor` y publica el puerto del contenedor (`docker compose exec n8n ...` o mapea 127.0.0.1:5678 solo en el servidor).
```bash
PAKTAI_API_INTERNAL_URL=http://api:8000 ./scripts/n8n_import_all.sh      # importa los 4 flujos
```
Luego, en el editor: crea las credenciales **Header Auth** `X-Epakti-Webhook-Token` (= `N8N_WEBHOOK_TOKEN`) y `Authorization` (`Bearer <token del rol worker>`),
**AWS** (Bedrock, `us-east-1`, política mínima de `infra/bedrock-n8n-policy.json`) y **SMTP**; asígnalas a los nodos y activa los flujos.
El flujo de «Entrega SANDBOX» y el de «correo SMTP real» usan la misma ruta: **activa solo uno**.

## 4. Conectar con Wilo
Dale a Wilo, por un canal privado: `N8N_WEBHOOK_URL=https://<N8N_DOMAIN>/webhook/epakti-alerta-360`, el `N8N_WEBHOOK_HMAC_SECRET` y el `EPAKTI_CALLBACK_TOKEN`.
El flujo del motor es `n8n/epakti_alerta_360_firmado.json` (el script de importación lo incluye). **No uses los flujos de `_archivo/n8n_obsoletos/`** (p. ej. `epakti_alerta_360_nova_lite.json`):
no verifica firmas y, además, su ruta no queda en `/webhook/epakti-alerta-360` porque le falta `webhookId`.
La versión firmada rechaza con **401** todo envío sin `X-Epakti-Signature: sha256=<hex>` válida (HMAC-SHA256 de los bytes originales con
`N8N_WEBHOOK_HMAC_SECRET`), cuerpo alterado, cuerpo vacío o no-JSON, y envíos con `X-Epakti-Timestamp` de más de 5 minutos; con firma válida responde **202**
y procesa exactamente el cuerpo firmado. Necesita en n8n: `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` y `NODE_FUNCTION_ALLOW_BUILTIN=crypto`
(si faltan, el flujo falla cerrado con 500 y no procesa nada). Probado: 9 de 9 casos y continuidad de las alertas tras la firma.

## 5. Verificación (en este orden)
1. `https://API_DOMAIN/health` → 200.
2. Entrar con el administrador, **Estado del sistema**: base, motor y n8n en verde.
3. **Carga de datos** con los 6 CSV → «Listo» (el worker procesa y sube al motor).
4. Abrir una intervención → aparece el borrador → aprobar → llega el correo (en `staging` va al destino de prueba).
5. `POST /api/v1/n8n/dispatch-alerts` con `"dry_run": true` → 202.

## 6. Mantenimiento
- **Copias:** Supabase hace respaldos; el volumen `n8n_data` (flujos y credenciales cifradas) se respalda con `docker run --rm -v n8n_data:/d -v $PWD:/b alpine tar czf /b/n8n_data.tgz -C /d .` y se guarda junto a `N8N_ENCRYPTION_KEY`.
- **Actualizar:** `git pull && docker compose up -d --build`. n8n está fijado por digest: cambiar de versión es una decisión explícita.
- **Rotación:** cambia `SESSION_SECRET` para cerrar todas las sesiones; cambia la clave del motor cuando Wilo la renueve.
- **Producción real:** `ENVIRONMENT=production` desbloquea el envío a familias reales; antes, las pruebas de aceptación de `docs/AUDITORIA_PRODUCCION.md`.
