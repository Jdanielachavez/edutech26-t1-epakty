# E-Pakty · Alerta temprana de abandono escolar (Ecuador)

**Track 1 · Problemáticas de la educación** · Hackathon EduTech Eight Academy by n8n 2026

| | |
|---|---|
| **Demo en vivo** | https://ed.paktai-ec.com |
| **Documentación completa** | https://ed.paktai-ec.com/docs.html |
| **Repositorio** | https://github.com/Jdanielachavez/edutech26-t1-paktai |

> E-Pakty existía antes del hackathon. Lo que ya estaba hecho está declarado en [`PRIOR_WORK.md`](PRIOR_WORK.md) y el uso de inteligencia artificial en [`AI_USAGE.md`](AI_USAGE.md).

**En una frase:** E-Pakty junta en un solo lugar las señales que anuncian que un estudiante podría dejar el colegio (faltas, notas, bienestar y pagos), dice a quién acompañar primero y por qué, y ayuda al colegio a actuar a tiempo, siempre con una persona aprobando cada mensaje.

---

## 1. El problema

### Cuántos estudiantes dejan el colegio en Ecuador

Datos oficiales del **Ministerio de Educación (AMIE, datos abiertos)**, calculados con [`data/bronze/public/amie_abandono.csv`](data/bronze/public/amie_abandono.csv):

| Indicador (período 2023-2024) | Dato |
|---|---|
| Estudiantes que abandonaron el sistema en un año | **72 644** de 4 144 414 matriculados (**1,75 %**) |
| En colegios fiscales | 60 630 estudiantes (**1,97 %**) |
| En colegios fiscomisionales | 5 048 estudiantes (**1,99 %**) |
| En colegios particulares | 6 619 estudiantes (**0,84 %**) |
| Zona rural / urbana | 1,83 % / 1,73 % |
| Provincias con más abandono | Morona Santiago **5,21 %** · Esmeraldas **3,06 %** · Orellana **3,02 %** (Pichincha: 1,44 %) |

**Cómo ha cambiado en 15 años** (mismo archivo):

| Período | Abandonaron | Tasa |
|---|---|---|
| 2011-2012 (el peor año) | 229 620 | **5,61 %** |
| 2015-2016 | 120 974 | 2,77 % |
| 2019-2020 | 75 295 | 1,73 % |
| 2021-2022 (rebote después de la pandemia) | 90 016 | 2,11 % |
| 2023-2024 | 72 644 | 1,75 % |

Entre 2009 y 2024 se registraron **1 929 569 abandonos**. La tasa bajó mucho desde 2012, pero **se estancó cerca del 1,8 %** y volvió a subir después de la pandemia: cada año siguen siendo más de 70 mil estudiantes.

**El contexto pesa.** Según la **ENEMDU 2025 del INEC**, el **21,8 %** de la población del país está en pobreza por ingresos y el desempleo es de 3,6 %. Las provincias con más pobreza suelen ser las que tienen más abandono, y por eso E-Pakty ajusta el riesgo según la provincia del colegio.

### Por qué los colegios llegan tarde

Un estudiante casi nunca deja el colegio de un día para otro. Antes aparecen señales:

- **Falta seguido sin justificar.** Es la señal más temprana.
- **Le bajan las notas**, sobre todo en las materias clave.
- **Su bienestar empeora**, o tiene una necesidad educativa especial (NEE) sin el apoyo adecuado.
- **La familia se atrasa con la pensión.**

El problema es que **esas señales están repartidas**: las faltas las ve Inspección, las notas el docente, el bienestar el DECE y los pagos Colecturía. Nadie las ve juntas, y nadie sabe a quién atender primero. Cuando el colegio se entera, el estudiante ya se fue y el colegio perdió también sus pensiones del resto del año.

### Lo que todavía no tenemos (con honestidad)

- **Entrevistas documentadas** con docentes tutores, DECE y rectores.
- **Validación con retiros reales.** Los modelos se midieron con un colegio ficticio de 240 estudiantes ([`data/bronze/dataset-ficticio-colegio/`](data/bronze/dataset-ficticio-colegio/)). El siguiente paso es un piloto con un colegio real.

---

## 2. Para quién es

Colegios de Ecuador, y dentro de cada uno:

| Rol | Qué ve en E-Pakty | Qué decide |
|---|---|---|
| **Docente tutor** | *Mi aula*: su paralelo, el calendario de faltas, a quién acompañar y por qué | A quién llamar o citar esta semana |
| **DECE** | Estudiantes con NEE o bienestar bajo y la materia donde más apoyo necesitan | Qué adaptación o acompañamiento dar |
| **Inspección / Vicerrectorado** | Docentes con más notas bajo 7 y faltas por clase | Dónde reforzar |
| **Rectorado** | Panel con pensiones en riesgo, plan de acción y avance del seguimiento | Dónde poner el esfuerzo del colegio |
| **Colecturía** | Familias con riesgo de atraso, el motivo y qué hacer (sin datos académicos) | A qué familia ofrecer una intervención de pago |
| **Admisiones** | Evaluación de postulantes desde el día 1 | Qué apoyo preparar antes de que entre |
| **Familia** | Un mensaje claro y humano, aprobado por el colegio | — |

Cada rol ve **solo lo suyo**: un docente nunca ve datos de pagos, y Colecturía nunca ve notas. Desde administración se puede **ver el portal como cada rol** para mostrar cómo trabaja cada persona.

**Qué no hace E-Pakty:** no decide por el colegio, no reemplaza al DECE ni al docente, y no le muestra a la familia un porcentaje de riesgo.

---

## 3. Cómo funciona

```
 1. El colegio sube 6 archivos CSV (o n8n los trae solo cada noche a las 2:00)
    estudiantes · asistencia · notas · pensiones · horarios · docentes
        │
        ▼
 2. Portal web (Vercel) ──► API FastAPI ──► Base Supabase (PostgreSQL, seguridad por fila)
        │                                     · guarda cada carga y su historial
        │                                     · nombres separados del resto (seudonimización)
        ▼
 3. Worker ──► Motor E-Pakti · TabM mini‑FiLM v2.4 (PyTorch, 8 modelos, en AWS las 24 horas)
        │        └─ devuelve riesgo, prioridad y las razones de cada estudiante
        ▼
 4. Pantallas por rol: semáforo, Mi aula, DECE, Colecturía, Rectoría, informes
        │
        ▼
 5. n8n (automatización)
        ├─ Amazon Nova Lite (IA) redacta el borrador del mensaje y el informe en palabras simples
        ├─ una persona del colegio revisa y APRUEBA
        └─ se envía por correo a la familia o al docente
```

**Lo que medimos en las pruebas:**
- Subir los 6 CSV desde el portal y que todo se recalcule: **31 segundos**.
- La sincronización nocturna automática de n8n: **19,5 segundos**, y repetirla no duplica nada.
- La IA redacta el borrador de un mensaje en unos **3 segundos**.

**Si algo falla:** si el motor no responde, la carga queda marcada con un mensaje claro y el portal sigue mostrando la última carga buena. Los mensajes pendientes se reintentan solos.

---

## 4. Los modelos

### Motor E-Pakti · TabM mini‑FiLM v2.4

Red neuronal tabular (PyTorch), desarrollada por el equipo antes del hackathon (ver [`PRIOR_WORK.md`](PRIOR_WORK.md)). Tiene **8 modelos**, cada uno para anticipar un problema distinto. Esta es su validación **fuera de muestra** (OOF) sobre la cohorte ficticia de 240 estudiantes:

| Qué anticipa | AUC-ROC | Lectura |
|---|---|---|
| Que repruebe el 2.º quimestre (nota menor a 7) | **0,947** | Bueno |
| Admisión: que le cueste en notas | **0,928** | Bueno |
| Que falte seguido a clases | 0,768 | Aceptable |
| Que la familia llegue a deber 2 meses o más | 0,765 | Aceptable |
| Admisión: que la familia llegue a deber 2 meses o más | 0,687 | Débil |
| Que la familia pague tarde 2 veces o más | 0,601 | Débil |
| Admisión: que la familia pague tarde | 0,566 | Débil |

*AUC-ROC: 0,5 es adivinar al azar y 1 es acertar siempre.* El motor además **pasa 22 de 22 pruebas automáticas**. Entre ellas: que más faltas nunca bajen el riesgo, que dos hermanos no se mezclen al medir y que **ningún docente vea datos de pagos** (0 términos financieros en 40 vistas docentes).

En la pantalla de MLOps están también la AP, el Brier, la calibración, la precisión y exhaustividad en los primeros 20, 40 y 60 estudiantes, y una curva de captura por modelo.

### Modelo explicativo propio

Una regresión logística con 11 factores ([`backend/reference_model.py`](backend/reference_model.py)) que muestra **qué factores pesan** y sirve de respaldo transparente si el motor no está disponible.

### Cómo se lee el riesgo

- Cada estudiante recibe una **prioridad**: **Urgente** (actuar esta semana), **Pronto**, **Observar** o **Va bien**.
- La prioridad compara al estudiante **con el resto de su colegio**.
- Cada alerta trae **las razones** (por ejemplo, "falta al menos un día casi todas las semanas, +26 puntos") y **cuánto bajaría el riesgo con cada acción**.

---

## 5. Automatización e inteligencia artificial

**9 flujos de n8n**, exportados en [`n8n/`](n8n/):

| Flujo | Qué hace |
|---|---|
| Borrador con Nova Lite | La IA escribe el mensaje para la familia y la acción interna para el colegio |
| Redactar informe en palabras simples | La IA reescribe el informe del estudiante para cualquier lector |
| Lector de exámenes | La IA extrae notas de un examen escaneado |
| Entrega a familia | Envía por correo el mensaje **ya aprobado** |
| Aviso al docente | Avisa por correo al docente que tiene un estudiante a acompañar |
| Alerta 360 del motor | Recibe las alertas del motor **verificando su firma HMAC** |
| Sincronización nocturna | Cada noche a las 2:00 trae los 6 CSV del colegio y los carga |
| Contacto y errores | Formulario comercial y registro de fallas |

**Qué verificamos y qué pasa si falla:**
- **Ningún mensaje sale sin aprobación humana.** La IA solo propone el borrador.
- **Si la IA inventa una cifra** que no estaba en el informe, el texto se descarta y se muestra el informe normal.
- **La IA nunca ve nombres** ni datos de pagos.
- **En modo de prueba**, todos los correos se desvían a una sola dirección del equipo, para que nunca le llegue nada a una familia por error.
- **Las alertas del motor van firmadas** (HMAC-SHA256); n8n rechaza las que no traen una firma válida.

---

## 6. Privacidad (LOPDP)

- **Solo datos ficticios** en el hackathon. Nada de datos reales de estudiantes, familias o docentes.
- **Seudonimización:** los nombres se guardan aparte; todo lo demás usa códigos (`EST-…`, `REP-…`, `DOC-…`). El motor nunca recibe nombres.
- **Seguridad por fila** en la base (Row Level Security): cada colegio solo ve sus datos.
- **Permisos por rol** en la API y en las pantallas.
- **Auditoría:** cada inicio de sesión, aprobación y cambio queda registrado.

---

## 7. Resultados en la demostración (colegio ficticio, 240 estudiantes)

| Indicador | Dato |
|---|---|
| Prioridad de los estudiantes | **95** urgentes · **10** pronto · **56** observar · **79** van bien |
| Estudiantes con NEE | 92 |
| Pensiones por cobrar (8 meses) | $321 086 |
| Ingresos de estudiantes en alerta | $142 524 |
| Recuperable si se interviene (estimación del modelo) | $41 109 |
| Pérdida estimada si no se actúa (estimación del modelo) | $130 311 |

Son estimaciones sobre datos ficticios: sirven para mostrar cómo razona el sistema, no como promesa de resultados.

---

## 8. Viabilidad

- **Quién lo usa:** el colegio (rectorado, DECE, tutores, inspección y colecturía).
- **Quién paga:** el colegio, con una **suscripción por colegio**. El precio se definirá con el primer piloto.
- **Por qué le conviene:** cada estudiante que se queda es una pensión que el colegio no pierde, y un estudiante que termina sus estudios.
- **Siguiente paso concreto:** un **piloto con un colegio**, con sus datos seudonimizados, para validar los modelos con retiros reales y conectar la sincronización nocturna con su sistema académico.

---

## 9. Cómo ejecutarlo

**Probarlo:** entra a https://ed.paktai-ec.com. Desde la portada se recorre la demostración con datos ficticios, o se inicia sesión con un usuario del equipo.

**En local** (ver [`docs/DESARROLLO_LOCAL.md`](docs/DESARROLLO_LOCAL.md)):

```bash
infra/dev/dev-up.sh
set -a; . ./.env.dev; set +a; .venv/bin/python -m backend.server
cd frontend-v2 && python3 -m http.server 8800 --bind 127.0.0.1
```

Las variables necesarias están en [`.env.example`](.env.example) y en [`env/`](env/).

**Pruebas:** `TEST_DATABASE_URL="$DATABASE_URL" .venv/bin/python -m pytest -q backend/tests` (77 pruebas).

**Encender producción completa para una demostración** (n8n, IA, correo, worker y sincronización):

```bash
./scripts/encender_produccion.sh
```

| Otras tareas | Comando |
|---|---|
| Reiniciar la API y el worker locales | `./scripts/reiniciar_local.sh` |
| API contra Supabase | `./scripts/dev_supabase.sh 8011` |
| Importar los flujos en n8n | `./scripts/n8n_import_all.sh epakty-n8n` |
| Cambiar la dirección del motor en producción | `./scripts/vercel_motor.sh <url>` |

---

## 10. Estructura del repositorio

| Carpeta | Qué hay |
|---|---|
| [`frontend-v2/`](frontend-v2/) | Portal web: portada, demostración y pantallas por rol |
| [`backend/`](backend/) | API FastAPI (`production/`), modelo explicativo, worker y pruebas (`tests/`) |
| [`engine_stub/`](engine_stub/) | Contrato y simulador del motor para desarrollo local (el código del motor no está en este repositorio) |
| [`sql/`](sql/) | Esquema de la base con seguridad por fila |
| [`n8n/`](n8n/) | Los flujos de n8n exportados |
| [`data/`](data/) | Datos públicos (AMIE, ENEMDU, INEVAL) y el colegio ficticio (ver [`data/README.md`](data/README.md)) |
| [`scripts/`](scripts/) | Encender producción, migraciones, túneles y utilidades |
| [`docs/`](docs/) | Desarrollo local, despliegue y webhooks |
| [`env/`](env/), [`infra/`](infra/) | Plantillas de variables e infraestructura |

---

## 11. Limitaciones conocidas

- Los modelos **no están validados con retiros reales**; las cifras son de una cohorte ficticia.
- Los modelos de **pagos aciertan menos** (AUC entre 0,57 y 0,77): hay que usarlos con cuidado.
- Que un factor pese mucho indica **asociación, no causa**.
- El motor ya corre en la nube (AWS) las 24 horas, con dirección fija. En la demostración, **n8n y el worker** todavía corren en una computadora del equipo y n8n se publica con un túnel temporal: **esa computadora debe estar encendida**. En un colegio real correrían en un servidor.
- WhatsApp todavía no está configurado; hoy los mensajes salen por correo.

---

## Contacto

paktai_ec@outlook.com · WhatsApp +593 96 271 9099
