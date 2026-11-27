# Stub del motor (contrato de Wilo, sin código del modelo)

Copia del kit `UI_UX 2` que entregó Wilo: contrato OpenAPI 3.1, payloads n8n, datos de ejemplo y el
servidor stub (`05_KIT_INTEGRACION_SIN_EXPONER_MOTOR/epakti_engine_stub_server.py`).

```bash
python3 engine_stub/05_KIT_INTEGRACION_SIN_EXPONER_MOTOR/epakti_engine_stub_server.py --port 8090
```

El backend lo usa con `EPAKTI_ENGINE_BASE_URL=http://localhost:8090/api/v1`. En producción solo cambia
esa variable (y `EPAKTI_ENGINE_API_KEY`) para apuntar al motor real de Wilo.
