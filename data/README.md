# Datos de E-Pakty

**Este repositorio no contiene datos reales de estudiantes, familias ni docentes.** Solo hay datos públicos agregados y un colegio ficticio, como exige la LOPDP y la regla del hackathon.

## Qué hay en cada carpeta

| Carpeta | Qué contiene | Origen |
|---|---|---|
| `bronze/public/` | Abandono escolar por provincia, sostenimiento y área (`amie_abandono.csv`), pobreza y desempleo por provincia (`enemdu_hogar.csv`) y un extracto agregado de INEVAL (`ineval_factores.csv`). | Datos abiertos oficiales: AMIE (Ministerio de Educación), ENEMDU (INEC), INEVAL. Se descargan con `scripts/sync_public_sources.py`. |
| `bronze/dataset-ficticio-colegio/` | Colegio **ficticio** de 240 estudiantes: `estudiantes`, `asistencia`, `notas`, `pensiones`, `horarios` y `docentes`. | Generado para pruebas. Nombres y códigos (`EST-…`, `REP-…`) son inventados y no corresponden a personas reales. |
| `bronze/production/` | Vacía a propósito. Ahí van los archivos de un colegio real, seudonimizados y con autorización. Solo se versionan el `README.md` y un manifiesto de ejemplo. | — |
| `bronze/*.csv` (raíz) | Plantillas vacías de bienestar, asistencia por clase y resultados históricos (solo encabezados). | — |
| `models/` | Coeficientes del modelo de referencia (`reference-logit.json`) y el esquema que debe cumplir un modelo aprobado. | Equipo E-Pakty. |
| `silver/`, `gold/`, `operational/` | Resultados intermedios que se generan al procesar una carga. No se versionan. | Generados. |

## Formato que entrega un colegio

Los nombres y columnas de cada CSV están en [`bronze/README.md`](bronze/README.md). Los identificadores deben llegar seudonimizados y `tiene_nee` es solo un indicador 0/1, sin diagnóstico.

## Cómo se usan los datos públicos

Los datos de AMIE y ENEMDU **nunca se asignan a un estudiante**. Solo sirven para ajustar el riesgo promedio del colegio según su provincia: en zonas con más abandono, el riesgo de todos sube un poco por igual, sin cambiar el orden entre estudiantes.
