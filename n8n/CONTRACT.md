# Contrato del flujo n8n

Flujo importable: `n8n/workflows/paktai_alerta_temprana.json`. Permanece
inactivo hasta importarlo en una instancia n8n y configurar las credenciales
AWS, API y canal. La exportación permite revisar el contrato, pero no prueba una
ejecución real en n8n.

1. El webhook n8n `POST /webhook/paktai/alerta-temprana` recibe `{ "estudiantes": [...] }` con expedientes Gold.
2. Split Out procesa un expediente por ejecución. Code conserva el ID para registrar el caso, pero lo quita del prompt enviado al modelo.
3. El expediente pasa por filtro NEE y enrutamiento causal; Bedrock devuelve `mensaje_representante` y `accion_interna` con salida JSON validada.
4. n8n envía el resultado a `POST {PAKTAI_API_URL}/api/interventions`; el backend valida responsable y ruta y lo guarda como `ABIERTA`.
5. La bitácora se actualiza con `PATCH /api/interventions/{id}`. `POST /api/webhook/n8n` es una ruta alternativa de backend y no es la entrada de este workflow.

El nodo final que entrega el borrador está deshabilitado deliberadamente. No se
activa hasta configurar el gateway y consentimiento institucional. No se envía
mensajería real desde este flujo.

El expediente Gold incluye los campos que consume el flujo: `driver_principal`
(`FINANCIERO`, `ACADEMICO` o `SOCIOEMOCIONAL_CONDUCTUAL`), `tiene_nee`,
`materia_critica`, `causas_pct` y `value_risk_usd`. El driver visible puede
seguir mostrando `Inclusión NEE`; en ese caso el filtro NEE agrega la adaptación
curricular y la rama causal se mantiene en `ACADEMICO`.

La respuesta estructurada de cada agente contiene:

```json
{
  "mensaje_representante": "...",
  "accion_interna": "...",
  "responsable_asignado": "...",
  "ruta_causal": "FINANCIERO",
  "canal_sugerido": "WhatsApp Business / Gmail",
  "provider": "aws-bedrock-n8n",
  "prompt_version": "mvp-0.2",
  "driver_principal": "FINANCIERO",
  "tiene_nee": 0
}
```

La exportación conecta AI Agent con AWS Bedrock Chat Model y Structured Output
Parser; sus credenciales siguen como marcadores vacíos. El flujo manda al modelo
solo el driver, score, causas, materia crítica y mora; el ID del expediente se
conserva para registrar el resultado, pero no va en el prompt. El backend acepta
el borrador estructurado sin hacer una segunda llamada al modelo.
