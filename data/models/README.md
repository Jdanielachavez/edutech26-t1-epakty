# Modelo supervisado de riesgo

No hay un artefacto de modelo cargado. PAKTAI no calcula ni sirve puntajes hasta
recibir `approved-risk-model.json` entrenado con historiales reales autorizados
de la misma institución que figura en `data/bronze/production/manifest.json`.

El archivo debe cumplir `risk-model.schema.json`. Se requieren resultados
confirmados `PERMANECE`/`RETIRA`, separación temporal entre entrenamiento y
validación, calibración aprobada por un responsable institucional, variables
permitidas del contrato Silver y umbrales definidos por validación. El código no
crea coeficientes por defecto ni entrena con datos de ejemplo.
