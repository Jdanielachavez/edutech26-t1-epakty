# Webhooks que el worker envía a n8n

El backend **no** envía correos ni WhatsApp: le pasa el trabajo a n8n, que es el único con esas credenciales.
Base: `N8N_WEBHOOK_BASE_URL` (por ejemplo `https://n8n.epakti.ec/webhook`).

| Ruta | Cuándo | Cuerpo |
|---|---|---|
| `POST /paktai-alerta` | Casos críticos nuevos (lote o manual) para que el agente redacte el borrador | `{run_id?, estudiantes:[{id, driver_principal, risk, causas_pct, materia_critica, overdueMonths, tiene_nee, intervention_id}]}` (sin nombres) |
| `POST /epakti-entrega-familia` | Una persona aprobó el mensaje a la familia | `{canal: "email"\|"whatsapp", case_id, destinatario, message, environment}` |
| `POST /epakti-contacto-lead` | Llegó un contacto desde la web (EP-19) | `{lead_id, nombre_contacto, institucion, correo, whatsapp_e164, ciudad, n_estudiantes_aprox, erp_actual, mensaje}` |
| `POST /epakti-errores` | Un flujo de n8n reportó un error | `{execution_id, workflow_id, node, code}` |

Las alertas 360 (EP-10) las envía el **motor** al flujo `epakti-alerta-360` de Wilo.

## Cabeceras de cada envío

- `Idempotency-Key`: única por evento. Si n8n la recibe dos veces (por ejemplo, tras un corte de red), **debe ignorar la segunda** para no enviar dos WhatsApp.
- `X-Epakti-Timestamp`: segundos Unix.
- `X-Epakti-Signature`: `sha256=` + HMAC-SHA256 en hexadecimal de `"{timestamp}.{cuerpo}"` con `N8N_WEBHOOK_HMAC_SECRET`.

## Verificación en n8n (nodo Code, al inicio de cada flujo)

```javascript
const crypto = require('crypto');
const ts = $json.headers['x-epakti-timestamp'];
const sig = $json.headers['x-epakti-signature'] || '';
const raw = JSON.stringify($json.body);            // usa el cuerpo crudo si tu versión de n8n lo expone
if (Math.abs(Date.now() / 1000 - Number(ts)) > 300) throw new Error('Firma vencida');
const expected = 'sha256=' + crypto.createHmac('sha256', $env.N8N_WEBHOOK_HMAC_SECRET).update(`${ts}.${raw}`).digest('hex');
if (sig.length !== expected.length || !crypto.timingSafeEqual(Buffer.from(sig), Buffer.from(expected))) throw new Error('Firma inválida');
return $input.all();
```

El worker serializa el JSON sin espacios (`separators=(',', ':')`) y con UTF-8; `JSON.stringify` produce lo mismo para estos cuerpos, pero si n8n permite leer el cuerpo crudo, úsalo.

## Respuestas

- `2xx`: entregado.
- `4xx` (salvo 429): rechazo definitivo; el evento queda `FAILED` y se puede reintentar con `POST /api/v1/admin/outbox/{id}/retry`.
- `5xx`, 429 o sin respuesta: se reintenta con espera exponencial y jitter (30 s, 1, 2, 4 y 8 min).

## Retorno a la API

- Borradores: `POST /api/v1/interventions/{id}/claim` y `/draft` con el token de rol `worker`.
- Resultado de la intervención (nodo 9 del flujo de Wilo): `POST /api/v1/interventions/log-outcome` con el token de rol `n8n_callback`, que solo sirve para eso.
