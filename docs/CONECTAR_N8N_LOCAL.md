# n8n local de E-Pakty (estado al 2026-11-25)

n8n corre en Docker en tu Mac (`epakty-n8n`, versión 2.49.5), **solo en `localhost:5678`**, con sus datos en el volumen `epakty_n8n_data`
y sus variables en `env/n8n.local.env` (permisos 600, no se comparte). Respaldo previo a la última recreación: `~/.epakti/n8n_data_respaldo.tgz`.

## Flujos activos
| Flujo | Ruta | Protección | Qué hace |
|---|---|---|---|
| Borrador con Nova Lite (`paktai_borrador_bedrock_local.json`) | `/webhook/paktai-alerta` | token `X-Epakti-Webhook-Token` | Reserva el caso, Nova Lite redacta, guarda el borrador en la API |
| Entrega por correo (`epakti_entrega_correo.json`) | `/webhook/epakti-entrega-familia` | token | Envía por SMTP el mensaje aprobado por una persona |
| Contacto web (`epakti_contacto_lead.json`) | `/webhook/epakti-contacto-lead` | token | Avisa por correo al equipo |
| Registro de errores (`epakti_errores.json`) | `/webhook/epakti-errores` | token | Avisa por correo a administración |
| **Alertas del motor** (`epakti_alerta_360_firmado.json`) | `/webhook/epakti-alerta-360` | **firma HMAC** del motor | Agentes con Nova Lite → correo a destinatario interno → callback EP-11 al motor |

El worker de la API envía a los cuatro primeros con el token `N8N_WEBHOOK_TOKEN` de `.env.dev`. El motor de Wilo envía al quinto firmando con
`N8N_WEBHOOK_HMAC_SECRET` (el mismo valor en su motor y en `env/n8n.local.env`). Los flujos viejos están en `_archivo/n8n_obsoletos/`.

## Variables de n8n (`env/n8n.local.env`)
`N8N_BLOCK_ENV_ACCESS_IN_NODE=false` y `NODE_FUNCTION_ALLOW_BUILTIN=crypto` (necesarias para verificar la firma), `N8N_WEBHOOK_HMAC_SECRET`,
`EPAKTI_CALLBACK_TOKEN` y `EPAKTI_CALLBACK_BASE_URL` (callback al motor), `EPAKTI_MAIL_FROM` y `EPAKTI_TEST_RECIPIENT_EMAIL` (correo de prueba).
Para cambiar una variable hay que recrear el contenedor (los datos se conservan en el volumen):
```bash
docker rm -f epakty-n8n && docker run -d --name epakty-n8n --restart unless-stopped -p 127.0.0.1:5678:5678 \
  -v epakty_n8n_data:/home/node/.n8n --env-file env/n8n.local.env \
  n8nio/n8n@sha256:c349b24d6e242b4ea14d75e6f1a90c50e348cf4b1c4512b4a0a50219ead6533d
```

## Publicar el webhook del motor (túnel temporal)
```bash
./scripts/tunel_webhook.sh
```
Levanta `scripts/webhook_proxy.py`, que **solo** deja pasar `POST /webhook/epakti-alerta-360` (el editor y los demás flujos no se publican),
y un túnel de Cloudflare hacia él. Imprime la URL HTTPS que se le da a Wilo como `N8N_WEBHOOK_URL`. Funciona mientras tu Mac esté encendida;
la URL cambia si se reinicia. La solución permanente es el servidor de `docs/DESPLIEGUE_PRODUCCION.md`.

## Verificado
- Desde Internet: sin firma → 401, firma falsa → 401, editor y API interna de n8n → 404.
- Alerta firmada real (EST-064, `SCH-DEMO-E2E`): 202 → Nova Lite → correo → callback al motor (que responde `INVALID_CALLBACK_TOKEN` hasta que
  Wilo configure el token compartido).

## Pendiente
- Que Wilo configure en el motor `N8N_WEBHOOK_URL`, `N8N_WEBHOOK_HMAC_SECRET` y `EPAKTI_CALLBACK_TOKEN` (valores entregados por canal privado).
- Borrar desde el editor el flujo «ZZ copia sin usar (borrar)» (inactivo) y, si todo funciona, el contenedor detenido `epakty-n8n-anterior`.
