# Resultado de la prueba de carga — SCH-PRUEBA-EQUIPO
Fecha: 26 de noviembre de 2026. Ejecutada desde el portal de E-Pakty (backend + Worker de pruebas) contra el motor en vivo
`employees-formerly-subsequently-variety.trycloudflare.com/api/v1`, con `EPAKTI_SCHOOL_ID=SCH-PRUEBA-EQUIPO`.
Los colegios compartidos `SCH-DEMO-E2E` y `SCH-DEMO-240` no se tocaron.

## Estado inicial
`GET /dashboard/docente-tutor/triage` devolvió **404** para el colegio: sin datos, como estaba previsto.

## Los cuatro trabajos

| # | Paso | job_id (mismo en portal y motor) | Estado | Procesados / Rechazados |
|---|---|---|---|---|
| 1 | Seis CSV originales | `JOB-52EC47C9D8F3` | COMPLETED | 240 / 0 |
| 2 | Versión con `EST-241` | `JOB-C49649BAB162` | COMPLETED | 241 / 0 |
| 3 | `estudiantes.csv` inválido (portal) | `JOB-9733018E997B` | DEAD_LETTER | 0 / 0 |
| 3b | El mismo archivo inválido, directo al motor | `QA-FALLO-001` | FAILED | 0 / 0 |
| 4 | Corrección y reintento | `JOB-C49649BAB162` (reutilizado) | COMPLETED | 241 / 0 |

El portal usa el mismo `job_id` para su trabajo y el del motor, así que ambos se siguen con un solo identificador.

## Lo que se comprobó
- **Carga inicial:** 240 estudiantes procesados y 0 rechazados, en 23 s. El portal mostró los 240.
- **Actualización:** tras subir la segunda versión, el motor devolvió `total: 241` en el triage, `EST-241` aparece en la lista,
  `GET /students/EST-241/ficha-360` responde **200**, y el portal muestra 241 con el nombre «Estudiante ficticio QA 241».
  El portal vuelve a consultar al motor después de `COMPLETED`, sin necesidad de recargar nada a mano.
- **Fallo controlado:** el portal aceptó el envío, el trabajo terminó en `DEAD_LETTER` y el mensaje para el usuario fue
  «estudiantes: faltan columnas obligatorias». Enviado directo al motor, respondió `202` y luego `FAILED` con
  «ValueError: La tabla `estudiantes` debe incluir la columna `codigo` (o `codigo_estudiante`).»
- **Nada se perdió con el fallo:** el motor y el portal siguieron mostrando los **241** de la última carga válida.
- **Reintento:** al restaurar el `estudiantes.csv` correcto, el conjunto quedó idéntico al de la carga 2, así que el portal
  reconoció el mismo contenido y devolvió ese trabajo ya `COMPLETED` (241 / 0) en lugar de reprocesarlo. Esa es su protección
  contra duplicados: el identificador se calcula del contenido de los seis archivos, no de un número de intento. `EST-241` sigue visible.
  Si prefieres que un reintento tras un fallo vuelva a procesar aunque los archivos sean iguales, se puede cambiar; hoy no se repite
  trabajo que ya terminó bien.

## Observación para Wilo
El motor respondió correcto en todo. La única diferencia con el guion es el punto 4: no se generó un quinto `job_id`, porque el
contenido corregido era idéntico al de la carga 2 y el portal no reprocesa lo que ya está hecho.
