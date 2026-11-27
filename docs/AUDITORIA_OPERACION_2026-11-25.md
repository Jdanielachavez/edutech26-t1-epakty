# Auditoría de operación de E-Pakty

Fecha: 25 de noviembre de 2026. Alcance: interfaz, API, worker, motor, n8n, entrega y preparación de producción.

## Verificado localmente

- `backend/tests`: **44 pruebas aprobadas**.
- API: `GET /health` responde 200; PostgreSQL está cifrado con TLS 1.3.
- Motor: responde el servicio de contrato local en `:8090`.
- n8n: su healthcheck local responde 200.
- CORS permite la interfaz local en `http://127.0.0.1:8800`.
- Un token de Rectoría obtuvo 200 en `/me`, triage y ficha 360.
- La interfaz usa la API real para: inicio de sesión por token, carga asíncrona de CSV, consulta de trabajos, triage, ficha 360, admisiones, casos, edición de borradores, aprobación de entrega y despacho hacia n8n.

## Lo que funciona en la interfaz

1. Sitio público: explica los cuatro servicios como entradas, cálculo, salida y aplicación.
2. Demos: identifican explícitamente los datos sintéticos y permiten recorrer alertas, territorio, SHAP/sensibilidad y revisión humana.
3. Administración: carga los seis CSV oficiales, muestra el trabajo asíncrono y evita interpretar resultados antes de que termine.
4. Equipo del colegio: el menú se ajusta al rol confirmado por `/api/v1/me`; el backend sigue siendo quien impone RBAC.
5. Intervenciones: un caso puede recibir borrador, edición humana y aprobación explícita de canal/destinatario.

## Bloqueadores para declarar producción

| Prioridad | Estado actual | Qué falta para cerrar |
|---|---|---|
| P0 | El motor local responde `EPAKTI_CONTRACT_STUB`; el readiness reporta `REFERENCE_IMPLEMENTED_NOT_TRAINED_ON_WITHDRAWALS`. | Conectar `EPAKTI_ENGINE_BASE_URL` al motor productivo, validar el modelo en datos fuera de muestra y guardar evidencia de calibración, drift y versión. |
| P0 | Los JSON de workflows n8n tienen `active: false`. | Importar el workflow elegido, crear credenciales HMAC, Bedrock, correo y WhatsApp; probar callback de borrador y entrega con datos sintéticos; activar recién después de la prueba de aceptación. |
| P0 | Faltan `N8N_WEBHOOK_BASE_URL`, firma HMAC, AWS/Bedrock, SMTP y WhatsApp en el readiness. | Configurarlos solo en n8n/secret manager; no en frontend, API ni worker. |
| P0 | Vercel sirve la interfaz/API, pero no es un worker persistente. | Desplegar API y worker en un runtime de contenedores o jobs gestionados; el worker debe seguir vivo para ingesta, outbox, reintentos y purga LOPDP. |
| P1 | El acceso operativo actual usa tokens Bearer. | Si el requisito es usuario y contraseña, integrar un proveedor de identidad (por ejemplo Supabase Auth/SSO) y emitir las claims de rol. No debe simularse un login de contraseña solo en frontend. |
| P1 | No hay evidencia de restore, IAM efectivo, presupuesto AWS ni SPF/DKIM. | Ejecutar los cuatro controles y adjuntar resultados: restore drill, `bedrock:InvokeModel`, alerta de presupuesto y prueba de entrega del proveedor. |

## Condición de salida a producción

No publicar ni activar mensajes a familias hasta completar esta secuencia:

1. Staging con API, worker, base y motor productivo aislados.
2. Prueba de carga con los seis CSV sintéticos y trazabilidad de trabajo completado.
3. Prueba end-to-end: motor → n8n → Nova Lite → callback de borrador → edición humana → aprobación → proveedor de entrega en sandbox.
4. Verificación de RBAC: un tutor y DECE no reciben datos financieros; Colecturía no recibe datos pedagógicos innecesarios.
5. Prueba de idempotencia, reintento, caída de n8n, cancelación de entrega y auditoría.
6. Aprobación de protección de datos, retención, backups y responsable institucional.

## Cambio aplicado a la verificación

`scripts/preflight.py` ya no intenta enviar un POST sin firma a un webhook externo. Ese comportamiento podía activar un flujo de producción. Ahora informa `CONFIGURED_NOT_VERIFIED` hasta que se haga una prueba controlada y firmada.
