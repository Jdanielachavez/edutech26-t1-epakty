# PAKTAI EDU · backend con bloqueo seguro

El backend rechaza Gold sin datos de una institución real y un modelo
supervisado aprobado para esa misma institución. No hay un artefacto de modelo
cargado todavía, por lo que la API no debe arrancar ni mostrar expedientes.

## Entradas obligatorias

- Fuente normalizada: `data/bronze/production/` o ruta `PAKTAI_SOURCE_DIR`, con
  manifiesto válido y CSV escolares reales autorizados.
- Artefacto de modelo: `data/models/approved-risk-model.json` o ruta
  `PAKTAI_MODEL_ARTIFACT`, conforme a `data/models/risk-model.schema.json`.
- Token API y configuración AWS Bedrock. Los secretos se inyectan al entorno;
  no se guardan en el repositorio.

Sin esas entradas, `scripts/build_dashboard_data.py` falla antes de escribir
Silver/Gold y `backend.server` se niega a iniciar. No hay generador local de
respaldo en el modo operativo.

## Endpoints cuando el despliegue esté habilitado

| Método | Ruta | Uso |
| --- | --- | --- |
| GET | `/api/health` | Estado del servicio |
| GET | `/api/summary` | KPIs y distribución del modelo aprobado |
| GET | `/api/references` | Contexto agregado AMIE, ENEMDU e INEVAL |
| GET | `/api/students` | Expedientes filtrables |
| GET | `/api/interventions` | Bitácora de seguimiento |
| POST | `/api/interventions` | Registra el borrador estructurado de n8n o Bedrock |
| PATCH | `/api/interventions/{id}` | Actualiza el estado confirmado por el equipo |

El endpoint legado `POST /api/webhook/n8n` está deshabilitado para impedir que
un motor local genere alertas de prueba. El workflow n8n registra cada caso en
`POST /api/interventions` e incluye `agent_result`.

## Estado pendiente

La bitácora todavía usa JSON local; antes de exponer el servicio se debe conectar
un almacenamiento institucional persistente y autorizado, desplegar HTTPS,
configurar IAM, n8n y el canal aprobado, y validar los roles de acceso. La
mensajería externa sigue deshabilitada y requiere revisión humana.
