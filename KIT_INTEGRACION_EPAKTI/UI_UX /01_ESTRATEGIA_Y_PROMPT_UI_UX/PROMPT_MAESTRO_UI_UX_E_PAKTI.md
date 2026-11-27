# PROMPT MAESTRO DE DISEÑO UI/UX Y ARQUITECTURA FRONTEND — PLATAFORMA SAAS "E-PAKTI" (DUAL-PLANE)

## 1. Rol, Producto y Lógica de Negocio
Actúa como Principal Product Designer (UI/UX) y Staff Frontend Architect especializado en plataformas SaaS B2B Enterprise de analítica predictiva e IA (referentes visuales: Linear, Stripe Dashboard, Datadog/Weights & Biases para el plano MLOps, y Panorama Education / Branching Minds para el plano escolar).

Vamos a diseñar **E-Pakti**, la plataforma SaaS multinivel **100 % autónoma** (no depende ni requiere que el colegio tenga Runachay, Idukay ni ningún ERP de terceros) que predice y previene el ausentismo recurrente, la reprobación académica y el incumplimiento/morosidad de pensiones combinando **datos propios de cada colegio (Nivel Micro: carga directa en Excel/CSV, registro nativo dentro de E-Pakti o conector externo estrictamente opcional solo si el colegio ya usa otro sistema)** con **bases oficiales nacionales de Ecuador vigentes antes del corte (Nivel Macro y Meso: MINEDUC AMIE 2024-2025, INEC Censo 2022, INEC ENEMDU 2024 e INEVAL 2023-2024)** mediante redes neuronales monótonas (`MonotonicSignConstrainedFiLMNet`), explicabilidad individual exacta **SHAP** desde un modelo pedagógico único libre de variables financieras, simulador de sensibilidad *What-If* del puntaje (etiquetado con rigor como escenario ilustrativo, no efecto causal), automatización agéntica en **n8n** y aprendizaje continuo **MLOps Multi-Colegio (Data Flywheel)**.
> **Regla de Negocio Crítica (Autonomía sin ERPs de Terceros):** Ninguna pantalla de onboarding, ingesta ni configuración debe exigir ni asumir que el colegio tiene Runachay, Idukay, Educalinks o Academium. El flujo principal es **Excel/CSV, plantilla E-Pakti o registro nativo**; si el colegio ya usa una aplicación externa, aparece solo como opción secundaria *"Conector externo (opcional)"*.
> **Nota de Desacoplamiento (Protección de IP):** El equipo Frontend/Web/Supabase/n8n desarrolla y prueba contra el **Contract Stub Server local (`05_KIT_INTEGRACION_SIN_EXPONER_MOTOR/epakti_engine_stub_server.py`)** sin necesidad de recibir el código propietario del motor ML (`GEMINI/`). En producción solo se cambia la variable `EPAKTI_ENGINE_BASE_URL`.

## 2. ARQUITECTURA DUAL-PLANE (CRÍTICO — NO MEZCLAR EN UNA SOLA BARRA)
La aplicación tiene **DOS PLANOS TOTALMENTE SEPARADOS** (en el prototipo/demo incluye un switcher de entorno en la esquina superior izquierda para presentar ambos al equipo e inversionistas, pero con separación estricta de rutas y JWT):

1. **PLANO A — Portal del Colegio Cliente (`app.epakti.ec`, Tema Claro Limpio `#F8FAFC`):**
   - Lo usan los colegios suscritos (cada uno aislado en su `school_id`).
   - Switcher de Roles del Colegio: `RECTORADO`, `DOCENTE_TUTOR`, `DECE`, `INSPECCION`, `COLECTURIA`, `ADMISIONES`.
   - **Jamás muestra la consola MLOps interna, el Data Lake multi-colegio, los Feature Flags ni datos de otros colegios.**
2. **PLANO B — Consola Interna de la SaaS E-Pakti (`admin.epakti.ec`, Tema Oscuro / Slate Pro `#0F172A` o Sidebar Técnico Diferenciado):**
   - Lo usa exclusivamente el equipo interno de **E-Pakti** (`EPAKTI_CEO`, `EPAKTI_MLOPS`, `EPAKTI_DATA_SCIENCE`, `EPAKTI_CS`).
   - Permite ver todos los colegios conectados, explorar el Data Lake k-anónimo bajo LOPDP (cero PII), monitorear Data Drift (`PSI`) y Calibración (`ECE`), lanzar re-entrenamientos contrafactuales, aprobar los 5 Candados *Champion vs. Challenger*, gestionar despliegues *Canary* / *Rollback*, activar *Feature Flags* por colegio y monitorear la salud de n8n.

## 3. Reglas Éticas, Legales (LOPDP / LOEI Ecuador) y Sistema Semafórico — OBLIGATORIAS
1. **PROHIBIDO usar letras bancarias (`AAA`, `AA`, `A`, `B`, `C`) o scores tipo buró crediticio para estudiantes.** Usa únicamente el **Sistema de Semaforización Escolar Calibrada de 4 Niveles**:
   - `VERDE` (`#1B9E77`, bg `#E8F8F5`, border `#A3E4D7`): "Acompañamiento Regular / Trayectoria Lograda / Pago Regular"
   - `AMARILLO` (`#D4AC0D`, bg `#FEF9E7`, border `#F9E79F`): "Observación Preventiva en Aula / Seguimiento de Fecha"
   - `NARANJA` (`#D95F02`, bg `#FDF2E9`, border `#F5CBA7`): "Apoyo Focalizado (Tutoría + DECE / Fecha Flexible Día 15-20)"
   - `ROJO` (`#C0392B`, bg `#FDEDEC`, border `#F5B7B1`): "Intervención Prioritaria Inmediata (Mesa Integral / Convenio)"
2. **Aislamiento Visual RBAC en Plano A (Colegio):**
   - Los roles `DOCENTE_TUTOR`, `DECE` e `INSPECCION` tienen **PROHIBIDO ver cualquier campo de deuda, cuotas vencidas, pagos tardíos o semáforo de Colecturía**.
   - El rol `COLECTURIA` ve únicamente el Semáforo de Pagos por representante/hogar, la tipología financiera y el porqué SHAP financiero, sin acceder a expedientes clínicos confidenciales del DECE.
   - El **Semáforo Docente Integrado** usa la **Regla del Peor Caso Pedagógico** (`max(Permanencia, Académico)`) y muestra el chip de foco (`Foco: Permanencia`, `Foco: Aprendizaje` o `Doble Foco`), nunca un promedio engañoso.

## 4. Stack Visual Recomendado
- **Frontend:** Next.js 14+ (App Router, TypeScript) + Tailwind CSS + `shadcn/ui` + `Lucide Icons` + `Recharts` (Waterfall SHAP, curvas Data Flywheel, PSI Drift, Heatmaps).
- **Tipografía:** `Plus Jakarta Sans` o `Inter` para interfaz; `JetBrains Mono` para códigos (`EST-089`, `REP-131`, `DPA 010150`, `AMIE 01H00123`), probabilidades calibradas (`90,1 %`), deltas (`-32,8 pp`) y métricas MLOps (`PSI 0,036`, `ECE 2,27 pp`).

## 5. PLANO A — Las 6 Pantallas del Portal Colegio Cliente (`app.epakti.ec`)

### Pantalla A1: Rectorado, Contexto Territorial y Escenario Financiero Ilustrativo (`GET /api/v1/dashboard/rectorado/kpis-roi` + `POST /api/v1/tenants/onboard` + `POST /api/v1/public/contact-lead`)
- **Banner Macro-Meso Vinculado:** Muestra código AMIE, parroquia oficial Censo 2022 (`DPA 010150 Cuenca` / `010162 Ricaurte` / `010169 Turi`), NBI (`8,5 %–38,1 %`), internet fijo, pobreza ENEMDU 2024 (`12,7 %`) y abandono AMIE, con un **Simulador de 7 Territorios Reales de Ecuador** (*Cuenca Urbano, Turi, Quito Urbano, Pomasqui, Guayaquil, Calpi, Esmeraldas*) demostrando el sesgo evitado frente a modelos solo-micro.
- **4 KPI Cards Ejecutivas (escenario ilustrativo de sensibilidad, no ROI causal garantizado):**
  1. Colegiatura Restante del Ciclo (8 meses): **`$321.086,00`** (`240` alumnos, `204` familias).
  2. Cartera Expuesta en Alertas 360° (`124` alumnos Rojo/Naranja): **`$167.684,00`**.
  3. Pérdida Esperada Ilustrativa sin Intervención: **`$102.693,07`**.
  4. **Ahorro / Ingreso Retenido Ilustrativo (Escenario Intervención 360°):** **`$35.751,10` en el plantel** (`$13.933,66` en Top 40), con tooltip visible indicando que deriva de supuestos de eficacia a validar en piloto controlado.
- **Heatmap Curso × Paralelo** (`8vo EGB` a `3ro BGU`, paralelos `A/B`) por porcentaje de alumnos en Rojo/Naranja.

### Pantalla A2: Matriz Triage Docente e Inspección — CERO Datos Financieros (`GET /api/v1/dashboard/docente-tutor/triage`)
- **Píldoras de Filtro Rápido con Conteos Reales Auditados:** `ROJO (93)`, `NARANJA (8)`, `AMARILLO (60)`, `VERDE (79)` (el semáforo de Permanencia usa 3 niveles calibrados `Verde / Amarillo / Rojo` con `ECE = 2,15 pp`, y el Académico Q2 usa 4 niveles con `ECE = 0,71 pp`) + filtros de Curso, Paralelo, Foco Pedagógico y NEE.
- **Tabla Triage:** Código/Alumno, Curso/Paralelo, Badge NEE + Sobreedad, Semáforo Docente + Chip de Foco, Semáforo Permanencia (`%` operativo y OOF + racha faltas), Semáforo Académico Q2 (`%` + materias `< 7` sobre 7 materias + Materia Crítica), Palanca Pedagógica Óptima y botón `"Ficha 360° & Simular"`.

### Pantalla A3: Drawer Lateral — Ficha 360° del Estudiante, Cascada SHAP y Simulador de Sensibilidad *What-If* (`GET /api/v1/students/{codigo}/ficha-360` + `POST /api/v1/n8n/dispatch-alerts` + `POST /api/v1/interventions/log-outcome`)
- Ejemplo real verificado desde el **modelo pedagógico único sin variables financieras** (`EST-089 · Gabriel Quiroga Andrade · 10 EGB A · NEE: discalculia`):
  1. **Cascada SHAP Exacta en puntos porcentuales (`0,00 pp` de cierre exacto con el color y `%`):** Base `24,58 %` → Riesgo operativo `78,47 %` (OOF auditoría `79,01 %`, `MAE = 1,25 pp`): `Micro Asistencia (+39,28 pp)`, `Micro Académico/NEE (+5,95 pp)`, `Sinergia Ausentismo×Notas<7 (+4,59 pp)`, `Contexto Macro/Meso (+4,07 pp)` + Top 3 factores en lenguaje natural.
  2. **Simulador de Sensibilidad *What-If* del Puntaje (3 toggles interactivos, etiquetado como sensibilidad del score, no efecto causal):** Plan de Asistencia (`-10,23 pp`), Tutoría + Adaptación DECE (`-26,44 pp`, palanca sugerida), Combinación 360° (**`-38,33 pp`**, moviendo el puntaje de `91,48 %` a **`53,2 %`**).
  3. **Panel Agéntico n8n (*Human-in-the-Loop*):** Destinatarios (`Tutor`, `Inspección`, `DECE`), borrador editable redactado por IA (`prompt_ia_pedagogico`, cero menciones financieras) y botón `"Aprobar, Enviar vía n8n y Registrar Intervención"` (dispara `EP-10` y callback `EP-11`).

### Pantalla A4: Bandeja Psicopedagógica DECE e Inclusión NEE (`GET /api/v1/dashboard/dece/inclusion-nee`)
- **92 alumnos con NEE (`38,3 %`):** `32` Prioridad Alta, `16` Media, `44` Preventiva.
- **Heatmap Condición NEE × 7 Materias** (`discalculia → Matemática 7,32`; `TEA → Inglés 7,03 y Lengua 7,12`; `TDAH → 4,13 faltas vs 2,76`) + generador de plan de adaptación curricular de 3 pasos y bitácora MTSS.

### Pantalla A5: Colecturía Exclusiva — Semáforo de Pagos por Hogar y Porqué SHAP (`GET /api/v1/dashboard/colecturia/cartera-hogares`)
- Banner superior de confidencialidad RBAC (`Acceso exclusivo Colecturía y Rectorado`).
- Toggle *Vista por Hogar (204 familias, 56 con mora, 74 cuotas vencidas)* vs *Vista por Estudiante (240 alumnos)* con píldoras `ROJO (22)`, `NARANJA (24)`, `AMARILLO (106)`, `VERDE (88)`.
- Muestra `Representante`, `Hermanos`, `Beca %`, `Carga Mensual USD`, `Cuotas Vencidas Sep-Oct`, **`Pagos Tardíos > Día 10`**, `Día Medio de Pago`, `Prob. Incumplimiento %` (**`ROJO = 71,4 %`, `10/14`**), `Prob. Morosidad Crónica >=2m %` (`ROC-AUC = 0,7649`, `Lift vs. Prevalencia = 3,57×`, `Verde = 0/72`), `Tipología`, **`Porqué SHAP`** y botón de acción contextual vía n8n (*"Proponer cambio de fecha al día 15-20"* o *"Enviar convenio fraccionado"*).

### Pantalla A6: Admisiones Pre-Ingreso ($N=1$) & Control Docente/Horarios (`POST /api/v1/admissions/evaluate-applicant` + `GET /api/v1/dashboard/vicerrectorado/docentes-horarios`)
- **Tab 1 (Admisiones $N=1$):** Formulario en vivo para evaluar a 1 postulante nuevo; devuelve dos semáforos calibrados independientes: *Semáforo Educativo Día 1* (`ROC-AUC = 0,9272`, `ECE = 1,57 pp`) y *Semáforo Financiero Matrícula* en 3 colores (`ROJO: 34`, `AMARILLO: 137`, `VERDE: 69`, `Lift = 12,18×`).
- **Tab 2 (Vicerrectorado):** Tabla de los 14 docentes (`30 bloques/sem`, `efecto_fijo_docente`, `DOC-02 36,5 % < 7` vs `DOC-01 30,6 %`) y gráfico de faltas en primer bloque (`viernes 4,14 %`, `jueves 4,04 %`).

## 6. PLANO B — Las 5 Pantallas de la Consola Interna de **E-Pakti** (`admin.epakti.ec` — CEO, Data Science & MLOps)

### Pantalla B1: Centro de Comando CEO & Gestión Multi-Tenant (`GET /api/v1/admin/tenants` + `POST /api/v1/tenants/onboard`)
- **4 KPI Cards de Negocio SaaS:** Total Colegios Activos (`25`), Estudiantes Monitoreados en Red (`6.000+`), MRR/ARR Mensual (`$7.250 MRR`) y Salud de Ingesta de Datos (`99,4 %` completitud).
- **Mapa Interactivo de Ecuador + Tabla Multi-Tenant:** Lista cada colegio (`school_id`, `AMIE`, provincia/parroquia `DPA`, modo de ingesta —*Excel/CSV, Nativo E-Pakti o Conector externo opcional*—, estado de carga/sync, $\lambda_k$ de *Empirical Bayes*, `PSI` local y escenario de retención) + botón `"Alta Rápida de Nuevo Colegio"` (sin requerir ningún ERP de terceros) y `"Impersonar Vista Soporte (Auditado)"`.

### Pantalla B2: Explorador del Data Lake K-Anónimo LOPDP & Fuentes Oficiales (`GET /api/v1/admin/data-lake/anonymized-explorer`)
- **Banner Permanente de Gobernanza:** Sello verde `"ENTORNO K-ANÓNIMO AUDITADO · CERO PII (SIN NOMBRES NI CÉDULAS) · LOPDP ECUADOR"`.
- **Tarjetas de Fuentes Nacionales Macro-Meso con Botón de Actualización Anual:** `MINEDUC AMIE 2024-2025` (`30.559` cohortes), `INEC Censo 2022` (`99,96 %` homologación DPA), `INEC ENEMDU` (`24` provincias), `INEVAL + PISA 2025`.
- **Auditoría Global de Variables:** Tabla interactiva de las `39` variables con su `VIF` ($\le 5,19$), correlación global, peso monótono y badge `"100 % Coherencia Teórica"`.

### Pantalla B3: MLOps Studio, *Model Registry* y Candados *Champion vs. Challenger* (`GET /api/v1/admin/mlops/overview-and-drift` + `POST /api/v1/admin/mlops/retrain` + `POST /api/v1/admin/mlops/models/{version}/promote`)
- **Gráfico Estrella — Curva del Data Flywheel Multi-Colegio (`1 → 3 → 5 → 10 → 15 → 25` colegios, evaluada estrictamente sobre 900 alumnos holdout):** Muestra en doble eje cómo sube el `ROC-AUC` (`0,840 → 0,862`) y cae **5 veces** el error de calibración `ECE` (`11,39 pp → 2,27 pp`, y `2,35 pp` con Empirical Bayes).
- **Tabla *Model Registry*:** Versiones (`v2.1.0 CHAMPION`, `v2.2.0 CHALLENGER`, `v2.0.0 ARCHIVED`) por cada familia (`Ausentismo FiLM`, `Académico Q2`, `Morosidad Crónica`, `Pre-Ingreso M1`).
- **Panel Visual de los 5 Candados Automáticos (Checklist bloqueante antes de promover):**
  1. Coherencia de Signos `100 %` y `VIF <= 5,50` (`PASS`)
  2. Mejora *Out-of-School* en `AUC / AP / Brier` (`PASS`)
  3. Monotonicidad de Semáforos + `ECE < 5,0 pp` (`PASS`)
  4. Equidad Urbano/Rural y NEE `< 4,0 pp` (`PASS`)
  5. Prueba Unitaria `N = 1` + Prueba Cero Fuga RBAC (`PASS`)
- **Botones de Control MLOps:** `"Lanzar Re-entrenamiento Contrafactual"`, `"Desplegar Canary (20 % Colegios)"`, `"Promover a 100 % Champion"` y `"Rollback Instantáneo"` (rojo destructivo con confirmación).

### Pantalla B4: Monitor de Drift (`PSI` / `ECE`), Auditoría de *Feedback Loops* y Observabilidad n8n (`GET /api/v1/admin/mlops/overview-and-drift` + `GET /api/v1/admin/n8n/observability`)
- **Monitor de Data Drift (`PSI`) por Colegio:** Semáforo técnico (`< 0,10` Verde estable, `0,10–0,20` Amarillo vigilar, `> 0,20` Rojo disparar re-entrenamiento).
- **Tarjeta Crítica — Escudo contra Profecía Autocumplida (*Feedback Loop*):** Compara visualmente la calibración actual protegiendo las intervenciones registradas (`ECE = 2,22 pp`, Top 20 % `95,2 %` vs real `97,1 %`) frente a lo que ocurriría con un re-entrenamiento ingenuo (`ECE = 23,56 pp`, Top 20 % `55,6 %`).
- **Panel de Observabilidad n8n:** Alertas despachadas (`1.480` en 30 días), tasa de entrega WhatsApp (`98,7 %`), callbacks a bitácora MLOps (`96,2 %`), latencia media de Agentes IA (`2,4 s`) y cola de webhooks fallidos con botón `"Reintentar"`.

### Pantalla B5: Gestión de Planes Comerciales, *Feature Flags* y *Canary Releases* (`PATCH /api/v1/admin/tenants/{school_id}/feature-flags`)
- **Matriz Interactiva `Colegio × Módulos / Feature Flags`:** Switches en tiempo real para asignar plan (`Básico / Pro / Enterprise`), activar o pausar funciones por colegio (`modulo_preingreso_m1`, `simulador_contrafactual_what_if`, `agentes_whatsapp_n8n`, `modelo_canary_v2_2`, `encuesta_bienestar_whatsapp_beta`), controlar cupos de mensajes WhatsApp y visualizar historial de auditoría de cambios.

## 7. Entregables Esperados del Equipo UI/UX e Integración Sin Motor ML
1. Design System completo en Figma (Tokens de color Semafóricos, tema claro Plano A Colegio + tema técnico Plano B E-Pakti Admin, tipografía y librería de componentes).
2. Prototipo interactivo clickeable de las **11 pantallas** (6 del Portal Colegio + 5 de la Consola Interna E-Pakti) + formulario público de contacto (`EP-19`) + estado de carga asíncrono de ingesta (`EP-02` + `EP-02B`) respetando al 100 % los campos JSON de los **20 endpoints** (`EP-01` a `EP-19` + `EP-02B`) validados contra el **Contract Stub Server** (`05_KIT_INTEGRACION_SIN_EXPONER_MOTOR/epakti_engine_stub_server.py`).
3. Estados vacíos (*empty states*), estados de carga (*skeletons*), polling de jobs asíncronos (`202 Accepted`), confirmaciones *Human-in-the-Loop* para envíos n8n y confirmación de doble paso para promociones/rollbacks MLOps.
