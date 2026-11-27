# AI_USAGE.md · E-Pakty

Usamos inteligencia artificial de dos formas: **para construir** el producto y **dentro** del producto.

## 1. IA para construir

| Herramienta | Para qué |
|---|---|
| Claude Code (Anthropic) | Escribir y revisar código del portal, el backend y los scripts; redactar documentación (README, `docs.html`, este archivo); desplegar en Vercel; revisar el proyecto contra la rúbrica. |

Las decisiones de producto las tomó el equipo: qué ve cada rol, qué textos usar y qué mostrar a las familias. Revisamos lo que generó la IA en el portal en vivo antes de publicarlo.

## 2. IA dentro del producto

| Pieza | Modelo | Qué hace | Dónde |
|---|---|---|---|
| Predicción del riesgo | Motor de Wilo (red neuronal tabular TabM-mini, `v2.4.0`) | Estima el riesgo de abandono de cada estudiante con notas, asistencia, bienestar y pagos. | Servidor externo; contrato en `engine_stub/` |
| Modelo de referencia | Regresión logística con 11 factores | Explica qué factores pesan y sirve de respaldo transparente. | `backend/reference_model.py` |
| Borradores de mensajes y alertas | Amazon Nova Lite (`amazon.nova-lite-v1:0`, AWS Bedrock) | Redacta en lenguaje simple el aviso para docentes y familias. | `n8n/workflows/paktai_borrador_bedrock_local.json`, `epakti_alerta_360_firmado.json` |
| Informe en palabras simples | Amazon Nova Lite | Convierte el informe técnico en texto entendible. | `n8n/workflows/epakti_redactar_informe.json` |
| Lector de exámenes | Amazon Nova Lite | Extrae notas de un examen escaneado. | `n8n/workflows/epakti_examen_ocr.json` |

## Qué verificamos y qué pasa si falla

- **Ningún mensaje a una familia sale sin aprobación humana.** El borrador de la IA queda pendiente hasta que una persona del colegio lo aprueba (`POST /api/v1/interventions/{case_id}/approve-delivery` en `backend/production/api.py`, que deja registro en la auditoría).
- **El motor puede no responder.** Si el motor está caído, la carga queda en estado `FAILED` con un mensaje claro y el panel conserva los resultados de la última carga válida. Los envíos pendientes se reintentan (patrón outbox).
- **Los mensajes del motor van firmados** con HMAC-SHA256. n8n rechaza lo que no trae una firma válida.
- **La IA no decide.** El semáforo es una señal para que el DECE, el docente tutor o el rectorado acompañen al estudiante; no reemplaza su criterio.

## Límites conocidos

- El modelo todavía no se valida con retiros reales de un colegio. El porcentaje es una alerta, no una predicción comprobada.
- Los colores comparan a los estudiantes dentro del mismo colegio.
- Que un factor pese mucho indica asociación, no causa.
- Nova Lite puede redactar algo impreciso. Por eso existe la aprobación humana antes de enviar.
