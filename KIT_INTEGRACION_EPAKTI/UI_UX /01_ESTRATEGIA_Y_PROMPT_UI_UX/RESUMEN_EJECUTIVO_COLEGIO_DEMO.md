# Informe Ejecutivo Multinivel de Alertas Tempranas y Barreras Educativas (GEMINI)

## 1. Respuesta a la Pregunta Guía: ¿Qué impide aprender, permanecer o sentirse bien?

El sistema integra **tres niveles de evidencia** (Macro nacional, Meso territorial/institucional y Micro escolar):

| Dimensión | Evidencia Macro/Meso en Ecuador (INEVAL, PISA 2025, ENEMDU, AMIE) | Señal Micro en el Colegio (240 alumnos, 204 familias) | Actor Responsable |
| --- | --- | --- | --- |
| **Sentirse bien** (Bienestar e inclusión) | Bullying/burlas (+11.4 pp baja integración en INEVAL; +15,8 pp soledad en PISA) y relación/apoyo docente (+0.0 a +15.4 pp). | **92 alumnos con NEE (38,3 %)**: TDAH y discalculia tienen mayor inasistencia (4,13 y 3,42 faltas vs. 2,76) y brechas en materias críticas (Matemática 7,32 en discalculia; Inglés 7,03 y Lengua 7,12 en TEA). | **DECE y Tutores de Paralelo** |
| **Permanecer** (Asistencia y continuidad) | Pobreza (+6.0 pp no asistencia en ENEMDU), ruralidad (+7.4 pp), trabajo adolescente (+16,1 pp) y poca conversación familiar (+0.0 pp ausentismo en PISA). | **70 alumnos (29,2 %)** presentan ausentismo injustificado recurrente en nov-dic; **74 alumnos** tienen sobreedad (+1 año) y **56 familias** acumulan 74 cuotas vencidas. | **Inspección, Colecturía y Rectorado** |
| **Aprender** (Desempeño académico) | Brecha socioeconómica ESCS (−15,1 pts Matemática en PISA; −8,0 pts dentro del mismo plantel) y baja conversación familiar (−5,7 pts intra-plantel). | **71 alumnos (29,6 %)** reprueban el promedio del Quimestre 2 (< 7,0); la correlación entre asistencia y promedio general es **r = 0,314**. | **Vicerrectorado Académico y Docentes** |

---

## 2. Resultados del Torneo de Modelos e Interacciones (Validación Anidada por Hogar)

### A. Alerta Temprana de Ausentismo Injustificado Recurrente (`y_falta_en_ambos_meses`, 70 casos / 240)

| Modelo | AP (Precisión Promedio) | ROC-AUC | Brier | Casos Detectados (Cupo 40) | Precisión (Cupo 40) | Recall (Cupo 40) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `01_Benchmark_Logit_Asistencia_Previo` | 0.5258 | 0.7563 | 0.1761 | **23 / 70** | 57.5% | 32.9% |
| `02_Logit_Contexto_Aleatorio_Previo` | 0.5006 | 0.7412 | 0.1795 | **20 / 70** | 50.0% | 28.6% |
| `03_Logit_Micro_Enriquecido_Notas_NEE_Mora` | 0.5754 | 0.7734 | 0.1673 | **23 / 70** | 57.5% | 32.9% |
| `04_Logit_Multinivel_Interacciones_Macro_Micro` | 0.5764 | 0.7701 | 0.1687 | **24 / 70** | 60.0% | 34.3% |
| `05_Logit_Multinivel_Geografia_Coherente` | 0.5773 | 0.7692 | 0.1682 | **25 / 70** | 62.5% | 35.7% |
| `06_RandomForest_Multinivel` | 0.5128 | 0.7534 | 0.1755 | **22 / 70** | 55.0% | 31.4% |
| `07_LightGBM_Multinivel` | 0.4659 | 0.7271 | 0.1804 | **20 / 70** | 50.0% | 28.6% |
| `08_CatBoost_Multinivel` | 0.4846 | 0.7381 | 0.1847 | **20 / 70** | 50.0% | 28.6% |
| `09_PyTorch_MLP_Scratch` | 0.4979 | 0.7448 | 0.1920 | **20 / 70** | 50.0% | 28.6% |
| `10_PyTorch_GatedResNet_Scratch` | 0.5723 | 0.7684 | 0.1691 | **24 / 70** | 60.0% | 34.3% |
| `11_PyTorch_MultiTask_NN_Scratch` | 0.4943 | 0.7250 | 0.1928 | **19 / 70** | 47.5% | 27.1% |
| `12_PyTorch_GatedResNet_Geo_Coherente` | 0.5747 | 0.7671 | 0.1685 | **25 / 70** | 62.5% | 35.7% |
| `13_Ensamble_Neuro_Estadistico_Multinivel` | 0.5508 | 0.7621 | 0.1730 | **24 / 70** | 60.0% | 34.3% |
| `14_Ensamble_Neuro_Estadistico_Geo_Coherente` | 0.5547 | 0.7606 | 0.1720 | **23 / 70** | 57.5% | 32.9% |

### B. Alerta Temprana de Riesgo Académico en Quimestre 2 (`y_reprobacion_q2`, 71 casos / 240)

| Modelo | AP (Precisión Promedio) | ROC-AUC | Brier | Casos Detectados (Cupo 40) | Precisión (Cupo 40) | Recall (Cupo 40) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Acad_01_Logit_Solo_Promedio_Corte` | 0.9408 | 0.9690 | 0.0953 | **40 / 71** | 100.0% | 56.3% |
| `Acad_02_Logit_Multinivel_Acad_Asist_NEE` | 0.9195 | 0.9566 | 0.0811 | **39 / 71** | 97.5% | 54.9% |
| `Acad_03_CatBoost_Multinivel_Acad` | 0.9140 | 0.9582 | 0.0772 | **38 / 71** | 95.0% | 53.5% |
| `Acad_04_PyTorch_GatedResNet_Acad_Scratch` | 0.9255 | 0.9607 | 0.0731 | **40 / 71** | 100.0% | 56.3% |
| `Acad_05_Ensamble_Neuro_Logit_Acad` | 0.9240 | 0.9596 | 0.0748 | **39 / 71** | 97.5% | 54.9% |

---

## 3. Top 15 Estudiantes con Prioridad Integral Multinivel (Acción Inmediata)

| Código | Estudiante | Curso | NEE | Prom. Corte | Faltas Injust. | Mora Hogar | Prob. Ausentismo | Prob. Riesgo Acad. | Diagnóstico Multinivel de Barreras |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `EST-089` | Gabriel Quiroga Andrade | 10 EGB A | discalculia | 5.38 | 6.8% | 0 ($0) | 93.5% | 98.1% | PERMANENCIA: Alto riesgo de ausentismo recurrente + APRENDIZAJE: 7 materias < 7 al corte + INCLUSIÓN/DECE: NEE (discalculia) + TRAYECTORIA: Sobreedad (+1 año) |
| `EST-153` | Sebastián Torres Paredes | 1 BGU B | dislexia | 4.95 | 9.1% | 0 ($0) | 80.2% | 98.6% | PERMANENCIA: Alto riesgo de ausentismo recurrente + APRENDIZAJE: 7 materias < 7 al corte + INCLUSIÓN/DECE: NEE (dislexia) + ECONOMÍA FAMILIAR: Fricción de liquidez (2 pagos tardíos > día 10) |
| `EST-117` | Valentina Flores Herrera | 10 EGB B | discalculia | 6.12 | 6.8% | 1 ($139) | 59.8% | 95.2% | PERMANENCIA: Alto riesgo de ausentismo recurrente + APRENDIZAJE: 7 materias < 7 al corte + INCLUSIÓN/DECE: NEE (discalculia) + ECONOMÍA FAMILIAR: Mora hogar (1 cuotas vencidas, $139) + TRAYECTORIA: Sobreedad (+1 año) |
| `EST-124` | Valentina Torres Rivadeneira | 1 BGU A | ninguna | 5.83 | 9.1% | 1 ($185) | 73.3% | 94.0% | PERMANENCIA: Alto riesgo de ausentismo recurrente + APRENDIZAJE: 7 materias < 7 al corte + ECONOMÍA FAMILIAR: Mora hogar (1 cuotas vencidas, $185) |
| `EST-064` | Paula León Torres | 9 EGB B | ninguna | 6.51 | 15.9% | 0 ($0) | 94.8% | 84.3% | PERMANENCIA: Alto riesgo de ausentismo recurrente + APRENDIZAJE: 6 materias < 7 al corte |
| `EST-235` | Daniela Andrade Torres | 3 BGU B | TDAH | 5.95 | 4.5% | 0 ($0) | 64.5% | 93.6% | PERMANENCIA: Alto riesgo de ausentismo recurrente + APRENDIZAJE: 7 materias < 7 al corte + INCLUSIÓN/DECE: NEE (TDAH) + TRAYECTORIA: Sobreedad (+1 año) |
| `EST-068` | Mateo Torres Guerrero | 9 EGB B | discapacidad visual | 5.66 | 2.3% | 0 ($0) | 59.3% | 97.6% | PERMANENCIA: Alto riesgo de ausentismo recurrente + APRENDIZAJE: 7 materias < 7 al corte + INCLUSIÓN/DECE: NEE (discapacidad visual) |
| `EST-114` | Luciana Jaramillo Ordóñez | 10 EGB B | discalculia | 6.57 | 2.3% | 1 ($185) | 44.5% | 86.3% | PERMANENCIA: Alto riesgo de ausentismo recurrente + APRENDIZAJE: 5 materias < 7 al corte + INCLUSIÓN/DECE: NEE (discalculia) + ECONOMÍA FAMILIAR: Mora hogar (1 cuotas vencidas, $185) |
| `EST-161` | Tomás Flores Ordóñez | 2 BGU A | ninguna | 6.37 | 6.8% | 0 ($0) | 85.6% | 90.0% | PERMANENCIA: Alto riesgo de ausentismo recurrente + APRENDIZAJE: 6 materias < 7 al corte + TRAYECTORIA: Sobreedad (+1 año) |
| `EST-127` | Camila Guerrero Flores | 1 BGU A | ninguna | 4.95 | 11.4% | 0 ($0) | 71.7% | 99.0% | PERMANENCIA: Alto riesgo de ausentismo recurrente + APRENDIZAJE: 7 materias < 7 al corte |
| `EST-182` | Daniela Jaramillo Delgado | 2 BGU B | ninguna | 6.06 | 9.1% | 0 ($0) | 78.2% | 88.8% | PERMANENCIA: Alto riesgo de ausentismo recurrente + APRENDIZAJE: 6 materias < 7 al corte + TRAYECTORIA: Sobreedad (+1 año) |
| `EST-175` | Nicolás Ordóñez Cárdenas | 2 BGU A | TDAH | 6.67 | 4.5% | 1 ($166) | 41.6% | 76.3% | PERMANENCIA: Alto riesgo de ausentismo recurrente + APRENDIZAJE: 4 materias < 7 al corte + INCLUSIÓN/DECE: NEE (TDAH) + ECONOMÍA FAMILIAR: Mora hogar (1 cuotas vencidas, $166) |
| `EST-093` | Martín Navarrete Paredes | 10 EGB A | TDAH | 6.98 | 13.6% | 0 ($0) | 82.5% | 52.2% | PERMANENCIA: Alto riesgo de ausentismo recurrente + APRENDIZAJE: 5 materias < 7 al corte + INCLUSIÓN/DECE: NEE (TDAH) |
| `EST-209` | Nicolás Jaramillo Espinoza | 3 BGU A | TDAH | 6.18 | 6.8% | 0 ($0) | 50.1% | 93.6% | PERMANENCIA: Alto riesgo de ausentismo recurrente + APRENDIZAJE: 6 materias < 7 al corte + INCLUSIÓN/DECE: NEE (TDAH) |
| `EST-099` | Martín Navarrete Delgado | 10 EGB A | ninguna | 4.60 | 4.5% | 0 ($0) | 63.5% | 99.2% | PERMANENCIA: Alto riesgo de ausentismo recurrente + APRENDIZAJE: 7 materias < 7 al corte |

---

## 4. Resumen de Control por Área Institucional

1. **DECE y Apoyo a Necesidades Educativas (`tablero_dece_nee.csv`):** Se identificaron **32 estudiantes con NEE en Prioridad Alta** y **16 en Prioridad Media**, con foco específico en Matemática para discalculia (media 7,32) y Lengua/Inglés para TEA (7,12 y 7,03).
2. **Semaforización Docente Separada por Rol (`semaforo_docente_permanencia_y_aprendizaje.csv`):** Los profesores, tutores y el DECE reciben un semáforo de 4 niveles (`Verde / Amarillo / Naranja / Rojo`) calibrado fuera de muestra para **Permanencia** (`12,4 % → 55,6 %`, `ECE = 3,76 pp`) y **Desempeño Académico Q2** (`4,3 % → 93,9 %`, `ECE = 1,89 pp`), **sin exposición de datos financieros familiares (cumplimiento LOEI/LOPDP)**.
3. **Colecturía, Semáforo Financiero Exclusivo + SHAP (`indicador_morosidad_estudiantes_y_porque_shap.csv` y `seguimiento_mora_familiar.csv`):** De los 204 representantes, **56 familias concentran las 74 cuotas vencidas** (`REP-102`: 4 cuotas / $555; `REP-131`: 2 hijos en mora). El semáforo financiero separa morosidad crónica de `2,3 %` (Verde) a `40,9 %` (Rojo, `Lift = 18,0×`, `AUC = 0,7516`) y explica el porqué individual con SHAP.
4. **Pre-Ingreso / Admisión M1 (`semaforo_preingreso_admision_240_estudiantes.csv`):** Dos semáforos independientes calibrados fuera de muestra sin fuga temporal: Educativo Día 1 (`5,2 % → 93,9 %`, `AUC = 0,9272`) y Financiero Matrícula Mes 1 en 3 colores (`2,9 % → 35,3 %` morosidad crónica, `Lift = 12,2×`).
5. **Vicerrectorado e Inspección (`diagnostico_carga_y_desempeno_docente.csv` y `diagnostico_horarios_primer_bloque.csv`):** Los 14 docentes tienen carga simétrica de 30 bloques semanales, pero existen brechas de reprobación entre paralelos (ej. `DOC-02` en Matemática con 36,5 % de notas < 7 vs. `DOC-01` con 30,6 %; `DOC-05` en Ciencias Naturales con 34,7 % vs. `DOC-06` con 32,5 %). En asistencia, **viernes (4,14 %) y jueves (4,04 %)** concentran la mayor tasa de faltas injustificadas.