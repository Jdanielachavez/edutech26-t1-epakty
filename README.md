# E-Pakty · Alerta temprana para el ecosistema educativo

**Track 1 · Problemáticas de la educación** · Hackathon EduTech Eight Academy by n8n 2026

| | |
|---|---|
| **Demo en vivo** | https://ed.paktai-ec.com |
| **Documentación del sistema** | https://ed.paktai-ec.com/docs.html |
| **Repositorio** | https://github.com/Jdanielachavez/edutech26-t1-paktai |

> E-Pakty existía antes del hackathon. Lo que ya estaba hecho está declarado en [`PRIOR_WORK.md`](PRIOR_WORK.md) y el uso de inteligencia artificial en [`AI_USAGE.md`](AI_USAGE.md).

---

## Resumen en 30 segundos (para cualquier lector)

- **El problema:** cada año más de **72 mil estudiantes** dejan el sistema educativo en Ecuador. Casi nunca se van de un día para otro: antes faltan, les bajan las notas, decae su bienestar o la familia se atrasa con la pensión. Esas señales existen, pero **están repartidas entre varias personas** y nadie las ve juntas a tiempo.
- **Lo que hace E-Pakty:** **junta los datos que la institución ya tiene** (asistencia, notas, bienestar, pagos), calcula **quién necesita acompañamiento, por qué y qué hacer**, y ayuda a actuar a tiempo. La inteligencia artificial escribe el borrador del mensaje y **una persona siempre lo aprueba** antes de enviarlo.
- **Nuestra mayor fortaleza son los datos:** no pedimos información nueva. Convertimos lo que la institución ya registra todos los días en decisiones concretas.
- **Para quién:** cualquier institución educativa: colegios fiscales, fiscomisionales y particulares, academias, institutos y negocios educativos.

---

## Índice

1. [El problema](#1-el-problema)
2. [Por qué los datos son nuestra mayor fortaleza](#2-por-qué-los-datos-son-nuestra-mayor-fortaleza)
3. [Para quién es: todo el ecosistema educativo](#3-para-quién-es-todo-el-ecosistema-educativo)
4. [Qué resuelve E-Pakty y qué no](#4-qué-resuelve-e-pakty-y-qué-no)
5. [Cómo se resuelve (explicación no técnica)](#5-cómo-se-resuelve-explicación-no-técnica)
6. [Cómo funciona por dentro (explicación técnica)](#6-cómo-funciona-por-dentro-explicación-técnica)
7. [Los modelos que usamos](#7-los-modelos-que-usamos)
8. [n8n: en qué momento entra cada flujo](#8-n8n-en-qué-momento-entra-cada-flujo)
9. [Inteligencia artificial: dónde se usa y cómo se controla](#9-inteligencia-artificial-dónde-se-usa-y-cómo-se-controla)
10. [Privacidad y seguridad (LOPDP)](#10-privacidad-y-seguridad-lopdp)
11. [Resultados en la demostración](#11-resultados-en-la-demostración)
12. [Viabilidad](#12-viabilidad)
13. [Cómo ejecutarlo](#13-cómo-ejecutarlo)
14. [Estructura del repositorio](#14-estructura-del-repositorio)
15. [Limitaciones conocidas](#15-limitaciones-conocidas)

---

## 1. El problema

### 1.1 Cuántos estudiantes dejan el sistema en Ecuador

Datos oficiales del **Ministerio de Educación (AMIE, datos abiertos)**, calculados con [`data/bronze/public/amie_abandono.csv`](data/bronze/public/amie_abandono.csv):

| Indicador (período 2023-2024) | Dato |
|---|---|
| Estudiantes que abandonaron el sistema en un año | **72 644** de 4 144 414 matriculados (**1,75 %**) |
| En instituciones fiscales | 60 630 estudiantes (**1,97 %**) |
| En instituciones fiscomisionales | 5 048 estudiantes (**1,99 %**) |
| En instituciones particulares | 6 619 estudiantes (**0,84 %**) |
| Zona rural / urbana | 1,83 % / 1,73 % |
| Provincias con más abandono | Morona Santiago **5,21 %** · Esmeraldas **3,06 %** · Orellana **3,02 %** (Pichincha: 1,44 %) |

### 1.2 Cómo ha cambiado en 15 años

| Período | Abandonaron | Tasa |
|---|---|---|
| 2011-2012 (el peor año) | 229 620 | **5,61 %** |
| 2015-2016 | 120 974 | 2,77 % |
| 2019-2020 | 75 295 | 1,73 % |
| 2021-2022 (rebote después de la pandemia) | 90 016 | 2,11 % |
| 2023-2024 | 72 644 | 1,75 % |

- Entre 2009 y 2024 se registraron **1 929 569 abandonos**.
- La tasa bajó mucho desde 2012, pero **se estancó cerca del 1,8 %** y **volvió a subir después de la pandemia**.
- Cada año siguen siendo **más de 70 mil** estudiantes.

### 1.3 El contexto también pesa

Según la **ENEMDU 2025 del INEC**, el **21,8 %** de la población está en **pobreza por ingresos** y el desempleo es del **3,6 %**. Donde hay más pobreza suele haber más abandono. Por eso E-Pakty ajusta el riesgo según la provincia de la institución.

### 1.4 Por qué las instituciones llegan tarde

Un estudiante casi nunca se va de un día para otro. Antes aparecen señales:

- **Falta seguido sin justificar.** Es la señal más temprana.
- **Le bajan las notas**, sobre todo en las materias clave.
- **Su bienestar empeora**, o tiene una **necesidad educativa especial (NEE)** sin el apoyo adecuado.
- **La familia se atrasa con la pensión.**

**El problema de fondo es que esas señales están repartidas:**

| Señal | Quién la ve hoy |
|---|---|
| Faltas y atrasos | Inspección |
| Notas | Cada docente |
| Bienestar y NEE | DECE |
| Pagos | Colecturía |

Nadie las ve **juntas**, nadie sabe **a quién atender primero**, y cuando la institución se entera, el estudiante ya se fue. Con él se pierden también sus pensiones del resto del año.

### 1.5 Cómo entendimos qué necesita cada persona

- **Quiénes somos.** Los fundadores, **Dani y Wilo, somos economistas**. Leemos los datos oficiales (AMIE, ENEMDU, INEVAL) con criterio, y sabemos que el abandono también pesa en los ingresos de la institución.
- **Investigación profunda.** Revisamos fuentes oficiales y estudios sobre abandono escolar, el rol del DECE, la inclusión de estudiantes con NEE y la morosidad en instituciones particulares.
- **Simulación con 10 agentes de IA distintos.** Con esa investigación armamos una simulación de varios agentes. Cada uno representaba a una persona de la institución: docente tutor, DECE, inspección, vicerrectorado, rectorado, colecturía, admisiones, familia y otros. Así identificamos qué necesita ver y decidir cada uno. De ahí salen las pantallas por rol de la sección 3.
- **Lo declaramos con honestidad:** esa simulación **no reemplaza** a las entrevistas reales. Se usó IA, y está declarado en [`AI_USAGE.md`](AI_USAGE.md).

### 1.6 Lo que todavía no tenemos

- **Entrevistas de campo documentadas** con docentes tutores, DECE y rectores. Por ahora es una demostración; las entrevistas van con el piloto.
- **Validación con retiros reales.** Los modelos se midieron con una institución ficticia de 240 estudiantes. El siguiente paso es un piloto.

---

## 2. Por qué los datos son nuestra mayor fortaleza

**E-Pakty no le pide a la institución información nueva.** Trabaja con lo que la institución ya registra todos los días, y lo convierte en decisiones.

### 2.1 Qué datos usa

| Dato que la institución ya tiene | Qué nos dice |
|---|---|
| **Asistencia diaria** (faltas, justificadas, atrasos, primera hora) | La señal más temprana de que algo está pasando |
| **Notas por parcial y quimestre** | Si el estudiante está por reprobar y en qué materia |
| **Necesidades educativas especiales (NEE)** | Quién necesita una adaptación y en qué área |
| **Bienestar** (si existe el registro) | Señales que no se ven en las notas |
| **Pensiones y pagos** | Qué familias podrían atrasarse, y si eso se junta con otras señales |
| **Horarios y docentes** | Dónde se concentran las faltas y las notas bajas |
| **Datos públicos del país** (AMIE, ENEMDU, INEVAL) | El contexto de la zona: abandono, pobreza y desempleo |

### 2.2 Por qué le sirven los datos a una institución educativa

- **Actuar antes, no después.** Con los datos se ve el problema semanas antes de que el estudiante se vaya.
- **Saber a quién atender primero.** El equipo tiene tiempo limitado: los datos ordenan la lista de más urgente a menos.
- **Saber por qué.** No es lo mismo un estudiante que falta que uno que reprueba: cada caso necesita una acción distinta.
- **Proteger los ingresos.** Cada estudiante que se queda es una pensión que la institución no pierde. Los datos muestran cuánto está en riesgo y cuánto se puede recuperar.
- **Incluir mejor.** Los datos de NEE muestran en qué materia necesita apoyo cada condición (por ejemplo, Matemática en discalculia).
- **Medir si funcionó.** Cada acción queda registrada, y la siguiente carga muestra si el riesgo bajó.
- **Rendir cuentas.** El rectorado tiene un panel con cifras claras para el directorio, las familias o el Ministerio.
- **Mejorar con el tiempo.** Cada carga queda guardada en el historial, y los modelos se pueden volver a entrenar con más datos.

### 2.3 Cómo los cuidamos

- Los datos se usan **sin nombres** (códigos `EST-…`, `REP-…`, `DOC-…`). Los nombres se guardan aparte.
- **Cada persona ve solo lo que le corresponde**: un docente nunca ve pagos, y Colecturía nunca ve notas.
- **Cada carga queda guardada** y se compara con la anterior. Administración puede eliminar una carga de prueba del historial.

---

## 3. Para quién es: todo el ecosistema educativo

E-Pakty sirve para **cualquier entorno educativo que registre asistencia, notas y pagos**:

| Tipo de institución | Para qué le sirve |
|---|---|
| **Colegios fiscales, fiscomisionales y particulares** | Evitar el abandono, acompañar a tiempo y cuidar las pensiones |
| **Academias, institutos y centros de refuerzo o de idiomas** | Detectar a quién le está costando y quién podría dejar el curso |
| **Negocios y comercios educativos** (cursos, programas, plataformas) | Reducir la deserción de sus estudiantes y la morosidad |
| **Redes de instituciones** | Comparar sus sedes con los mismos indicadores |

### Dentro de una institución, cada persona tiene su propia pantalla

| Rol | Qué ve | Qué decide |
|---|---|---|
| **Docente tutor** | *Mi aula*: su paralelo, el calendario de faltas, a quién acompañar y por qué | A quién llamar o citar esta semana |
| **DECE** | Estudiantes con NEE o bienestar bajo y la materia donde más apoyo necesitan | Qué adaptación o acompañamiento dar |
| **Inspección / Vicerrectorado** | Docentes con más notas bajo 7 y faltas por clase | Dónde reforzar |
| **Rectorado** | Panel con pensiones en riesgo, plan de acción y avance del seguimiento | Dónde poner el esfuerzo |
| **Colecturía** | Familias con riesgo de atraso, el motivo y qué hacer (sin datos académicos) | A qué familia ofrecer una intervención de pago |
| **Admisiones** | Evaluación de postulantes desde el día 1 | Qué apoyo preparar antes de que entre |
| **Familia** | Un mensaje claro y humano, aprobado por la institución | — |

Desde administración se puede **ver el portal como cada rol**, para mostrar cómo trabaja cada persona.

---

## 4. Qué resuelve E-Pakty y qué no

**Resuelve:**
- **Junta** en un solo lugar las señales que hoy están repartidas.
- **Prioriza:** Urgente (esta semana), Pronto, Observar o Va bien.
- **Explica** por qué cada estudiante está en la lista, en palabras simples.
- **Recomienda** qué hacer y estima cuánto bajaría el riesgo con cada acción.
- **Automatiza** lo repetitivo: el borrador del mensaje, el aviso al docente, la carga nocturna de datos.
- **Registra** todo el seguimiento, para que no se pierda la historia de cada estudiante.

**No hace:**
- **No decide** por la institución.
- **No reemplaza** al DECE ni al docente: les da información, no un veredicto.
- **No le muestra a la familia** un porcentaje de riesgo.
- **No envía nada** sin que una persona lo apruebe.

---

## 5. Cómo se resuelve (explicación no técnica)

1. **La institución sube sus datos.** Son 6 archivos que ya tiene (estudiantes, asistencia, notas, pensiones, horarios y docentes). Se suben desde el portal o, mejor aún, **n8n los trae solos cada noche** a las 2:00.
2. **E-Pakty revisa y protege los datos.** Comprueba que estén completos y cambia los nombres por códigos.
3. **El motor calcula el riesgo.** Una red neuronal estima, para cada estudiante, qué tan probable es que deje la institución, que repruebe o que la familia se atrase con la pensión, **y por qué**.
4. **Cada persona ve su pantalla.** El tutor ve su aula, el DECE sus casos, el rectorado su panel, Colecturía sus familias.
5. **La IA prepara el mensaje.** Escribe un borrador amable para la familia y una acción para el equipo.
6. **Una persona lo revisa y lo aprueba.** Puede editarlo antes de enviarlo.
7. **n8n lo envía** por correo a la familia o al docente.
8. **Todo queda registrado.** Las acciones y su resultado se guardan, y en la próxima carga se ve si el riesgo bajó.

**Tiempos medidos en las pruebas:**

| Qué | Tiempo |
|---|---|
| Subir los 6 archivos y recalcular todo | **31 segundos** |
| Sincronización nocturna automática con n8n | **19,5 segundos** (repetirla no duplica nada) |
| La IA escribe el borrador de un mensaje | unos **3 segundos** |

---

## 6. Cómo funciona por dentro (explicación técnica)

### 6.1 Arquitectura

```
 ┌─────────────── Fuentes de datos ───────────────┐
 │ Portal: subir 6 CSV  │  n8n: sincronización 2:00 │
 └───────────┬───────────────────────┬────────────┘
             ▼                       ▼
   Portal web (Vercel) ──► API FastAPI (Vercel) ──► Supabase PostgreSQL
   HTML/JS, pantallas        roles y permisos         · seguridad por fila (RLS)
   por rol                   validación               · bronze / silver / gold
                             cola de trabajos          · historial de cargas
                                                       · nombres aparte
             │
             ▼
   Worker ──────────────► Motor E-Pakti · TabM mini‑FiLM v2.4 (AWS, 24 h)
   procesa la cola          PyTorch, 8 modelos, devuelve riesgo + razones
             │
             ▼
   n8n (automatización) ──► Amazon Nova Lite (AWS Bedrock) ──► correo
   9 flujos                  redacta borradores e informes        a familias y docentes
```

### 6.2 Componentes

| Pieza | Tecnología | Qué hace |
|---|---|---|
| **Portal** | HTML + JavaScript, en Vercel | Pantallas por rol, paneles interactivos, informes en PDF |
| **API** | Python, FastAPI, en Vercel | Inicio de sesión, permisos por rol, validación, cola de trabajos |
| **Base de datos** | Supabase (PostgreSQL) con Row Level Security | Guarda las cargas (bronze, silver, gold), casos, seguimiento y auditoría |
| **Worker** | Python | Procesa las cargas, llama al motor y entrega los mensajes a n8n |
| **Motor** | TabM mini‑FiLM v2.4 (PyTorch) en AWS | Calcula el riesgo y sus razones |
| **Modelo explicativo** | Regresión logística propia | Muestra qué factores pesan; respaldo si el motor no responde |
| **Automatización** | n8n | Borradores con IA, envíos de correo, alertas del motor, sincronización nocturna |
| **IA generativa** | Amazon Nova Lite (AWS Bedrock) | Redacta borradores de mensajes e informes en palabras simples |

### 6.3 Las capas de datos

| Capa | Qué guarda |
|---|---|
| **Bronze** | Los archivos tal como llegaron, ya sin nombres. Cada carga queda guardada. |
| **Silver** | Los datos limpios por estudiante, en cada carga |
| **Gold** | El resultado listo para las pantallas (riesgo, prioridad, razones) |
| **Nombres** | Aparte del resto, con fecha de borrado (LOPDP) |

### 6.4 Si algo falla

- Si el motor no responde, la carga queda marcada con un mensaje claro y el portal sigue mostrando la última carga buena.
- Los mensajes pendientes se reintentan solos (patrón *outbox*).
- Subir dos veces los mismos archivos no duplica nada.
- El portal reutiliza los datos 60 segundos para no esperar al servidor en cada clic.

---

## 7. Los modelos que usamos

### 7.1 Motor E-Pakti · TabM mini‑FiLM v2.4

Red neuronal tabular (PyTorch) desarrollada por el equipo antes del hackathon (ver [`PRIOR_WORK.md`](PRIOR_WORK.md)). Corre en la nube las 24 horas. Tiene **8 modelos**, cada uno para anticipar un problema distinto. Su validación **fuera de muestra** (OOF) sobre la cohorte ficticia de 240 estudiantes:

| Qué anticipa | AUC-ROC | Lectura |
|---|---|---|
| Que repruebe el 2.º quimestre (nota menor a 7) | **0,947** | Bueno |
| Admisión: que le cueste en notas | **0,928** | Bueno |
| Que falte seguido a clases | 0,768 | Aceptable |
| Que la familia llegue a deber 2 meses o más | 0,765 | Aceptable |
| Admisión: que la familia llegue a deber 2 meses o más | 0,687 | Débil |
| Que la familia pague tarde 2 veces o más | 0,601 | Débil |
| Admisión: que la familia pague tarde | 0,566 | Débil |

*AUC-ROC: 0,5 es adivinar al azar y 1 es acertar siempre.* El octavo modelo (que deje la institución) da el riesgo de permanencia de cada estudiante.

**El motor pasa 22 de 22 pruebas automáticas**, entre ellas:
- más faltas nunca bajan el riesgo;
- dos hermanos no se mezclan al medir;
- **ningún docente ve datos de pagos** (0 términos financieros en 40 vistas docentes).

En la pantalla de MLOps también se ven la AP, el Brier, la calibración, la precisión y la exhaustividad en los primeros 20, 40 y 60 estudiantes, y una curva de captura por modelo.

### 7.2 Modelo explicativo propio

Regresión logística con 11 factores ([`backend/reference_model.py`](backend/reference_model.py)). Muestra **qué factores pesan** y sirve de respaldo transparente.

### 7.3 Cómo se lee el riesgo

- **Prioridad:** Urgente (actuar esta semana), Pronto, Observar o Va bien. Compara al estudiante con el resto de su institución.
- **Razones:** cada alerta dice por qué, por ejemplo: "falta al menos un día casi todas las semanas, +26 puntos".
- **Qué pasaría si…:** cuánto bajaría el riesgo con cada acción (plan de asistencia, tutoría o ambas).
- **Contexto de la zona:** el riesgo se ajusta con el abandono y la pobreza de la provincia.

---

## 8. n8n: en qué momento entra cada flujo

n8n es la pieza que **conecta todo y hace el trabajo repetitivo**. Los flujos están exportados en [`n8n/`](n8n/). Así entra cada uno, en orden:

| Momento | Flujo | Qué lo activa | Qué hace | ¿Aprobación humana? |
|---|---|---|---|---|
| **1. Cada noche, 2:00** | **Sincronización nocturna** ([json](n8n/epakti_sincronizacion_nocturna.json)) | Un reloj (cron `0 2 * * *`) | Descarga los 6 CSV del sistema de la institución y los envía a E-Pakty | No: solo carga datos |
| **2. Después de cada carga** | **Borrador con Nova Lite** ([json](n8n/paktai_borrador_bedrock_local.json)) | El worker, con los estudiantes más urgentes | Por cada estudiante: reserva el caso, la IA escribe el borrador para la familia y la acción interna, y lo guarda en el caso | **Sí**: queda pendiente de revisión |
| **3. Cuando el motor detecta alertas** | **Alerta 360 del motor** ([json](n8n/epakti_alerta_360_firmado.json)) | El motor en la nube | **Verifica la firma HMAC** (si no es válida responde 401), separa la información por rol (lo pedagógico sin pagos; lo de Colecturía sin NEE), ajusta por NEE con el DECE, la IA prepara el plan según el motivo y registra la intervención en el motor | Sí, antes de enviar a una familia |
| **4. Cuando una persona aprueba** | **Entrega a familia** ([json](n8n/epakti_entrega_correo.json)) | El botón *Aprobar envío* | Envía el mensaje aprobado por correo. WhatsApp está pendiente de configurar | Ya fue aprobado |
| **5. Cuando se avisa al docente** | **Aviso al docente** ([json](n8n/epakti_aviso_docente.json)) | Marcar en Seguimiento "Docente avisado" | Envía al docente un correo con el resumen y qué hacer | Lo decide quien lo marca |
| **6. Cuando alguien pide el informe simple** | **Redactar informe** ([json](n8n/epakti_redactar_informe.json)) | El botón *Explicar en palabras simples (IA)* | La IA reescribe el informe; si inventa una cifra, se descarta | Es solo lectura |
| **7. Cuando se sube un examen** | **Lector de exámenes** ([json](n8n/epakti_examen_ocr.json)) | Fotos de una evaluación | La IA lee las hojas y devuelve las notas **para revisar** | Sí: se revisa antes de guardar |
| **8. Desde la página web** | **Contacto comercial** ([json](n8n/epakti_contacto_lead.json)) | El formulario de contacto | Avisa al equipo de un interesado | No |
| **Siempre** | **Registro de errores** ([json](n8n/epakti_errores.json)) | Cualquier falla de otro flujo | Registra el error y avisa al administrador | No |

**El recorrido de la Alerta 360, paso a paso:**

```
webhook ─► verificar firma HMAC ─► ¿válida? ─ no ─► 401
                                     │ sí ─► 202 (recibido)
                                     ▼
separar alertas ─► vista pedagógica (sin pagos) ─┐
               └─► vista Colecturía (sin NEE)  ──┤
                                                 ▼
ajuste por NEE (DECE) ─► elegir según el motivo ─► Amazon Nova Lite
  ├─ tutor / DECE
  ├─ permanencia / inspección
  └─ Colecturía
          ▼
preparar alerta ─► correo interno de prueba ─► registrar el resultado en el motor
```

**Cómo se protegen estas conexiones:**
- Lo que el motor envía a n8n va **firmado con HMAC-SHA256**; n8n rechaza cualquier firma inválida.
- Lo que la API envía a n8n lleva un **token**.
- n8n solo publica las rutas de los flujos: **el editor no queda expuesto**.
- En modo de prueba, **todos los correos se desvían a una sola dirección del equipo**, para que nunca le llegue nada a una familia por error.

---

## 9. Inteligencia artificial: dónde se usa y cómo se controla

| Dónde | Modelo | Para qué |
|---|---|---|
| Predicción del riesgo | TabM mini‑FiLM v2.4 (red neuronal) | Calcular el riesgo y sus razones |
| Explicación de factores | Regresión logística propia | Mostrar qué pesa, de forma transparente |
| Borrador del mensaje | Amazon Nova Lite | Escribir el mensaje para la familia y la acción interna |
| Informe en palabras simples | Amazon Nova Lite | Reescribir el informe para cualquier lector |
| Lector de exámenes | Amazon Nova Lite | Extraer notas de un examen escaneado |

**Controles:**
- **La IA nunca decide ni envía.** Solo propone; una persona aprueba.
- **La IA nunca ve nombres** ni datos de pagos.
- **Si la IA inventa una cifra** que no estaba en el informe, el texto se descarta.
- Todo el uso de IA, incluida la que usamos para construir, está declarado en [`AI_USAGE.md`](AI_USAGE.md).

---

## 10. Privacidad y seguridad (LOPDP)

- **Solo datos ficticios** en el hackathon.
- **Seudonimización:** los nombres se guardan aparte; todo lo demás usa códigos. El motor nunca recibe nombres.
- **Seguridad por fila** en la base: cada institución solo ve sus datos.
- **Permisos por rol** en la API y en las pantallas.
- **Auditoría:** cada inicio de sesión, aprobación y cambio queda registrado.
- **Retención:** los nombres tienen fecha de borrado.

---

## 11. Resultados en la demostración

Institución ficticia de **240 estudiantes**:

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

## 12. Viabilidad

- **Quién lo usa:** la institución (rectorado, DECE, tutores, inspección, colecturía y admisiones).
- **Quién paga:** la institución, con una **suscripción**. El precio se definirá con el primer piloto.
- **Por qué le conviene:** cada estudiante que se queda es una pensión que no se pierde, y un estudiante que termina sus estudios.
- **Siguiente paso concreto:** un **piloto con una institución real**, con sus datos seudonimizados, para validar los modelos con retiros reales y conectar la sincronización nocturna con su sistema académico.

---

## 13. Cómo ejecutarlo

**Probarlo:** entra a https://ed.paktai-ec.com. Desde la portada se recorre la demostración con datos ficticios, o se inicia sesión con un usuario del equipo.

**En local** (ver [`docs/DESARROLLO_LOCAL.md`](docs/DESARROLLO_LOCAL.md)):

```bash
infra/dev/dev-up.sh
set -a; . ./.env.dev; set +a; .venv/bin/python -m backend.server
cd frontend-v2 && python3 -m http.server 8800 --bind 127.0.0.1
```

Las variables necesarias están en [`.env.example`](.env.example) y en [`env/`](env/).

**Pruebas:** `TEST_DATABASE_URL="$DATABASE_URL" .venv/bin/python -m pytest -q backend/tests`.

**Encender producción completa para una demostración** (n8n, IA, correo, worker y sincronización nocturna):

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

## 14. Estructura del repositorio

| Carpeta | Qué hay |
|---|---|
| [`frontend-v2/`](frontend-v2/) | Portal web: portada, demostración y pantallas por rol |
| [`backend/`](backend/) | API FastAPI (`production/`), modelo explicativo, worker y pruebas (`tests/`) |
| [`engine_stub/`](engine_stub/) | Contrato y simulador del motor para desarrollo local (el código del motor no está en este repositorio) |
| [`sql/`](sql/) | Esquema de la base con seguridad por fila |
| [`n8n/`](n8n/) | Los flujos de n8n exportados |
| [`data/`](data/) | Datos públicos (AMIE, ENEMDU, INEVAL) y la institución ficticia (ver [`data/README.md`](data/README.md)) |
| [`scripts/`](scripts/) | Encender producción, migraciones, túneles y utilidades |
| [`docs/`](docs/) | Desarrollo local, despliegue y webhooks |
| [`env/`](env/), [`infra/`](infra/) | Plantillas de variables e infraestructura |

---

## 15. Limitaciones conocidas

- Los modelos **no están validados con retiros reales**; las cifras son de una cohorte ficticia.
- Los modelos de **pagos aciertan menos** (AUC entre 0,57 y 0,77): hay que usarlos con cuidado.
- Que un factor pese mucho indica **asociación, no causa**.
- El motor corre en la nube (AWS) las 24 horas. En la demostración, **n8n y el worker** todavía corren en una computadora del equipo y n8n se publica con un túnel temporal: **esa computadora debe estar encendida**. En una institución real correrían en un servidor.
- WhatsApp todavía no está configurado; hoy los mensajes salen por correo.

---

## Contacto

paktai_ec@outlook.com · WhatsApp +593 96 271 9099
