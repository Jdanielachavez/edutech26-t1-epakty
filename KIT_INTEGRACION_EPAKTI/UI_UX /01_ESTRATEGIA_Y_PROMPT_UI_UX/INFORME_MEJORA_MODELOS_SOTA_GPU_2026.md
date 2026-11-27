# Informe Científico y de Auditoría Técnica (v2.4): Mejora SOTA en GPU RTX 5070 y Cierre de Reauditoría — E-Pakti EduTech SaaS

**Fecha:** 25 de noviembre de 2026  
**Hardware verificado:** `NVIDIA GeForce RTX 5070 Laptop GPU (8.151 MiB VRAM, Driver 616.92, CUDA 13.4)` · `CatBoost 1.2.10 (GPU)` · `LightGBM 4.7.0` · `PyTorch 2.15.0` · `scikit-learn 1.9.1`  
**Script 100 % reproducible:** [`validacion_sota_gpu_multinivel.py`](../validacion_sota_gpu_multinivel.py) → [`reporte_benchmark_sota_gpu_multinivel.json`](../motor_saas/reporte_benchmark_sota_gpu_multinivel.json)  
**Suite integral de calidad del motor:** [`reporte_verificacion_integral_15_tests.json`](../motor_saas/reporte_verificacion_integral_15_tests.json) (**`22/22` pruebas aprobadas**)  
**Auditorías cerradas:** [`AUDITORIA_MODELOS_Y_NEGOCIO_2026-11-25.md`](AUDITORIA_MODELOS_Y_NEGOCIO_2026-11-25.md) y [`AUDITORIA_EVOLUCION_EPAKTI_V23_2026-11-25.md`](AUDITORIA_EVOLUCION_EPAKTI_V23_2026-11-25.md)

---

## 1. Respuesta Científica Transparente sobre la Meta de `>= 70 %` de Precisión

### 1.1. Escenario Sintético Demo (`y_falta_en_ambos_meses`, `70 / 240` alumnos)
* Mediante análisis forense de `asistencia.csv` (`44` días pre-corte, `18` en nov., `15` en dic.), comprobamos que los registros sintéticos siguen un proceso Bernoulli estacionario independiente (autocorrelación lag-1 `r = -0,0095`, `p = 0,20`) con tasa latente compartida $\lambda_i \sim \text{Beta}(\alpha = 1,4883,\ \beta = 19,5745)$ y proporción fija de injustificadas `53,77 %`.
* Bajo `M = 2.000` cohortes Monte Carlo simuladas con ese DGP MLE:
  * **Media simulada de un Oráculo que conozca la $\lambda_i$ verdadera exacta:** **`Precisión@40 = 59,6 %`** (`23,8 / 40`, IC 95 %: `42,5 % – 75,0 %`; en `278 / 2.000` realizaciones = `13,9 %` el Oráculo alcanza `>= 28/40` por varianza muestral finita).
  * **Media simulada del Posterior Óptimo de Bayes con 44 días previos:** **`Precisión@40 = 52,2 %`** (`20,9 / 40`, IC 95 %: `37,5 % – 67,5 %`; en `36 / 2.000` realizaciones = `1,8 %` alcanza `>= 28/40`).
* **Interpretación rigurosa (corregida tras reauditoría v2.3):** `59,6 %` y `52,2 %` son las **medias simuladas bajo el DGP ajustado** (no límites deterministas absolutos en una única muestra finita), y explican con transparencia por qué ningún modelo sin fuga ni sobreajuste supera de forma estable el entorno de `55 % – 60 %` a cupo `40` sobre esta etiqueta binaria sintética.
* **Corrección de la regresión Top-40 detectada en v2.3:** Al sustituir `racha_injustificada_historica` por `frac_semanas_ausencia_total` (persistencia semanal de ausencias, `VIF <= 4,10`), incorporar la cabeza analítica **Bivariada Poisson Count-Hazard `TabM_mini-FiLM` (`RobustScaler` + `k=32`)** en [`buro_educativo_preadmision_y_morosidad.py`](../buro_educativo_preadmision_y_morosidad.py) y separar la cola operativa de Permanencia de la cola Académica Q2 en [`simulador_saas_multiterritorio.py`](../simulador_saas_multiterritorio.py):
  * El modelo operativo `TabM_mini-FiLM` saltó de **`19/40 (47,5 %)` → `22/40 (55,0 %)` OOF** (`AUC = 0,7676`, `AP = 0,5548`, `Brier = 0,1725`, `Prec@20 = 65,0 %`).
  * La **cola exportada a n8n (`alertas_priorizadas_360`)** saltó de **`19/40 (47,5 %)` → `23/40 (57,5 %)`** (y `cola_priorizada_academico_q2_top40` se exporta por separado con `39/40 = 97,5 %`), protegidos permanentemente por la compuerta automatizada **`TEST-22`**.
  * En estabilidad sobre las **5 particiones agrupadas por hogar**, `TabM_mini` Count-Hazard alcanza **`23,40 / 40` (`22–25`)** frente a `20,80 / 40` (`20–23`) del Logit histórico de referencia del auditor.

### 1.2. Dónde E-Pakti Alcanza `>= 70 %` de Precisión (Identificando Siempre la Etiqueta Exacta y sus Límites)

| Dominio y Etiqueta Exacta Validada | Escala y Límite Declarado | Modelo SOTA E-Pakti | Precisión Verificada (`>= 70 %`) | `ROC-AUC` / `Lift vs. Prevalencia` |
| --- | --- | --- | :---: | --- |
| **1. Reprobación Q2 (`nota_media_q2 < 7,0`)** | Demo (`N=240`, `71` pos.; *asume notas Q1 P1–P2 disponibles al corte*) | `TabM_mini-FiLM` / `GatedResNet` | **`Prec@20 = 100,0 %`** · **`Prec@40 = 97,5 % – 100,0 %`** · **`ROJO = 95,3 %`** | `AUC = 0,9466 – 0,9607` · `Lift vs Prev. = 3,22×` |
| **2. Pre-Ingreso Educativo M1 (`y_reprobacion_q2` desde proxy Q1 P1)** | Demo (`N=240`, `71` pos.; *proxy libreta previa*) | `TabM_mini-FiLM` | **`Prec@20 = 100,0 %`** · **`Prec@40 = 97,5 %`** · **`ROJO = 91,7 %`** | `AUC = 0,9283` · `Lift vs Prev. = 3,10×` |
| **3. Ausencia Total en Ambos Meses (justificada + injustificada)** | Demo (`N=240`, `109` pos., prevalencia `45,4 %`; *desenlace distinto a injustificadas*) | `TabM_mini` Count-Hazard (solo asistencia) | **`Prec@10 = 100,0 %`** · **`Prec@20 = 85,0 %`** · **`Prec@40 = 80,0 % (32/40)`** *(Recall `29,4 %`)* | `AUC = 0,7754` · `AP = 0,7444` |
| **4. Ausentismo Crónico (`>=4` ausencias en 33 días ≈ `>=12 %`, estándar US Dept. of Ed. `>=10 %`)** | Demo (`N=240`, `68` pos., prevalencia `28,3 %`) | `TabM_mini` Count-Hazard (solo asistencia) | **`Prec@10 = 70,0 %`** · **`Prec@20 = 70,0 %`** *(Cupo 40: `24/40 = 60,0 %`)* | `AUC = 0,7822` · `AP = 0,5916` |
| **5. Colecturía — Incumplimiento Amplio (`>=1` cuota tardía o impaga Nov–Ene)** | Demo (`204` hogares, `72` pos.; *cuota impaga estricta tiene `AUC = 0,552`*) | `TabM_mini-FiLM` + Household EB | **`ROJO = 71,4 %` (`10/14`, IC Wilson 95 %: `45,4 % – 88,3 %`)** · **`Prec@20 = 70,0 %`** | `Lift vs Prev. = 2,38×` *(Crónica `>=2m`: `AUC = 0,7649`, **`Lift vs Prev. = 3,57×`**, `VERDE = 0/72`, `lift_rojo_vs_verde = null`)* |
| **6. Deserción Universitaria Real (1er Semestre, 10 bloques macro)** | **UCI Portugal (`4.424` alumnos reales, `1.421` retiros)** *(otra población/nivel)* | **Ensamble RTX 5070 (`CatBoost GPU + LightGBM`)** | **`Prec@737 = 88,87 % (655/737)`** *(8 vars)* · **`93,35 % (688/737)`** *(1er sem + matrícula)* · **`Acc@0.5 = 85,44 %`** | `AUC = 0,9015` · `AP = 0,8603` · `Brier = 0,1055` |

---

## 2. Validación Real Multi-País en GPU NVIDIA RTX 5070 con Ablaciones Controladas (Corregidas v2.4)

### 2.1. Ecuador — AMIE Sierra Ordinaria Presencial (`Train 2019–2023`, **`Val 2024 con Pool Ponderado`**, **`Test Reservado 2025`: `6.291` planteles, `1.616.492` estudiantes, `21.103` abandonos**)

Corregido el olvido de pesos en validación 2024 (`catboost.Pool(X_va, y_va, weight=w_va)`) y ejecutada **ablación controlada con el mismo modelo, mismos pesos y mismo cupo (`315` planteles)**:

| Modelo AMIE 2025 (`Pool` Ponderado en Train y Val 2024, Cupo `315` Planteles) | `ROC-AUC` | `AP` | `Brier` | Abandonos Top 5 % (`315` planteles) | Aporte Neto |
| --- | :---: | :---: | :---: | :---: | --- |
| Referencia previa (`oro/amie_temporal` `logit_aditivo`) | `0,7100` | `0,0401` | `0,012747` | `8.434` (`39,97 %`) | Referencia |
| **Ablación A: `CatBoost GPU` Solo Historial Plantel (`15` vars, `best_it=202`)** | `0,7146` | `0,0412` | `0,012772` | `8.746` (`41,44 %`) | `+0,46 pp AUC` |
| **Ablación B: `CatBoost GPU` Historial + Contexto Censo/ENEMDU (`25` vars, `best_it=351`)** | **`0,7322`** | **`0,0440`** | **`0,012730`** | **`8.792` (`41,66 %`)** | **`+1,76 pp AUC` · `+6,8 % AP` · `+46` abandonos puro aporte contextual!** |
| **Ensamble RTX 5070 (`CatBoost GPU + LightGBM`)** | **`0,7360`** | `0,0439` | **`0,012720`** | `8.740` (`41,42 %`) | **`+2,60 pp AUC` sobre baseline logit** |

*(Nota: en `motor_nacional_amie_censo.py` el mismo experimento entrega `AUC = 0,7153 → 0,7312` (`+1,59 pp`) y ensamble `0,7354`, con variación mínima debida al ordenamiento paralelo determinista en GPU.)*

### 2.2. Chile — MINEDUC K-12 Longitudinal (`Train 2024: 1.290.840` → **`Test Reservado 2025: 1.299.423`, `42.500` sin matrícula**)

Corregida la escala de asistencia a `[0, 1]` (`1.0 - asistencia_mar_abr`), igualado el **cupo exacto a `64.971` alertas** (idéntico al baseline `oro/validacion_chile_temprana`), y ejecutada **ablación controlada en 4 pasos con hiperparámetros idénticos (`CatBoost GPU iter=1000, depth=7, lr=0.04, l2=10, seed=5147`)**:

| Paso de Ablación Controlada (Mismo Modelo GPU y Cupo Exacto `64.971`) | `ROC-AUC` | `AP` | `Brier` | Deserciones Capturadas (`64.971` alertas) | Precisión Top 1 % | Ganancia Incremental |
| --- | :---: | :---: | :---: | :---: | :---: | --- |
| Referencia previa (`oro/validacion_chile_temprana` `lightgbm_junio`) | `0,7824` | `0,1908` | `0,028840` | `10.562` | — | Referencia |
| **Paso 0: Solo Micro Base (`15` vars exactas del baseline)** | `0,7889` | `0,1995` | `0,028663` | `10.756` | `39,77 %` | `+0,65 pp AUC` · `+194` |
| **Paso 1: + Demografía / Región / Doble Riesgo (`18` vars)** | `0,8027` | `0,2058` | `0,028556` | `10.910` | `40,50 %` | `+1,38 pp AUC` · `+154` |
| **Paso 2: + Pobreza Comunal Residencia y Plantel (`21` vars)** | `0,8125` | `0,2119` | `0,028432` | `10.955` | `40,64 %` | `+0,98 pp AUC` · `+45` |
| **Paso 3: + E-Pakti Meso Plantel EB + Posición Relativa (`27` vars)** | **`0,8319`** | **`0,2231`** | **`0,028178`** | **`11.031`** | **`41,40 %`** | **`+1,94 pp AUC` · `+76` puro aporte Meso Plantel!** |
| **Ensamble RTX 5070 (`CatBoost GPU + LightGBM`, cupo `64.971`)** | **`0,8335`** | **`0,2259`** | **`0,028133`** | **`11.067`** | **`41,85 %`** | **`+5,11 pp AUC` · `+505` deserciones a igual cupo!** |

---

## 3. Matriz Completa de Cierre de la Reauditoría v2.3 (`22/22` Tests + `15/15` Probes Stub)

| # | Hallazgo de [`AUDITORIA_EVOLUCION_EPAKTI_V23_2026-11-25.md`](AUDITORIA_EVOLUCION_EPAKTI_V23_2026-11-25.md) | Corrección Implementada en v2.4 | Verificación Automatizada |
| :---: | --- | --- | --- |
| **1** | Regresión de cola operativa y FiLM OOF de `22/40` a `19/40` | `TabM_mini-FiLM` bivariado Poisson + `frac_semanas_ausencia_total` (`VIF<=4,10`) + separación de colas Permanencia vs. Q2 → **`22/40` OOF y `23/40` cola exportada** | **`TEST-22`** (`OOF=22/40, Cola=23/40`) |
| **2** | 20 combinaciones únicas Q2 + 1 duplicado pasaban como 21 notas / 100 % cobertura | Deduplicación por `(codigo_estudiante, parcial, materia)` y verificación exacta del producto cartesiano `{1,2,3} × materias` (`21` claves únicas) | **`TEST-21`** (`q2_20claves_1dup_na=True`) |
| **3** | `lift_rojo_vs_verde` usaba piso arbitrario `0,005` cuando Verde tenía `0` casos (`71,4×`) | Agregado `lift_rojo_vs_prevalencia` (siempre definido: `3,57×` en Crónica) y `lift_rojo_vs_verde = null` cuando Verde = `0` | [`auditoria_calibracion_semaforos.csv`](../resultados/auditoria_calibracion_semaforos.csv) |
| **4** | AMIE 2024 omitía pesos en `eval_set` y faltaba ablación con mismo modelo/pesos | `catboost.Pool(X, y, weight=w)` en Train y Val 2024 + ablación controlada mismo modelo/pesos/cupo `315` (`+1,76 pp AUC`, `+46` abandonos por contexto) | [`validacion_motor_nacional_amie_censo_enemdu.json`](../motor_saas/validacion_motor_nacional_amie_censo_enemdu.json) |
| **5** | Chile mezclaba cambios, usaba `100 - asistencia` sobre escala `[0,1]` y cupo `65.239` vs `64.971` | Corregida escala `1.0 - asistencia_mar_abr`, igualado cupo exacto `64.971` y ablación controlada en 4 pasos idénticos (`+505` deserciones al mismo cupo!) | [`reporte_benchmark_sota_gpu_multinivel.json`](../motor_saas/reporte_benchmark_sota_gpu_multinivel.json) |
| **6** | Stub `EP-02` regresaba a `240` con `archivos_cargados` OpenAPI; `EP-03` ignoraba JSON anidado y confundía `1` vs `2` materias (`59,9 %` vs `16,8 %`) | Soporte completo OpenAPI anidado en `EP-03`, separación estricta proporción vs. conteo (`1/7 < 2/7`), y `0` + `METADATOS_ARCHIVO_SIN_REGISTROS_ADJUNTOS` en `EP-02` sin inventar `240` | **Probes 12, 13, 14** (`15/15` Stub probes PASS) |
| **7** | `workflow_n8n_epakti_360.json` buscaba alertas en raíz (no `body`), usaba esquema IF v1 y faltaban `ai_languageModel` y `jsonBody` | Actualizado a **13 nodos / 12 conexiones**: `body.alertas_priorizadas_360`, esquema oficial `IfV2`, nodo `AWS Bedrock Chat Model` conectado por `ai_languageModel` a los 3 agentes, y `jsonBody` real en WhatsApp y callback MLOps | **`TEST-17` & `TEST-21`** (`nodes=13, conns=12, split_body=True, if_v2=True, llm_3agentes=True, wa_body=True`) |

---

## 4. Bibliografía Peer-Reviewed Verificada (2023–2026)

* Gorishniy, Y., Kotelnikov, A., & Babenko, A. (2025). *TabM: Advancing Tabular Deep Learning with Parameter-Efficient Ensembling*. **ICLR 2025** (`arXiv:2410.24210`).
* Holzmüller, D., Grinsztajn, L., & Steinwart, I. (2024). *Better by Default: Strong Pre-Tuned MLPs and Boosted Trees on Tabular Data (RealMLP & GBDT-TD)*. **NeurIPS 2024** (`arXiv:2407.04491`).
* Hollmann, N., et al. (2025). *Accurate predictions on small data with a tabular foundation model (TabPFN v2)*. **Nature**, 637, 319–326 (`doi:10.1038/s41586-024-08328-6`).
* Erickson, N., et al. (2025). *TabArena: A Living Benchmark for Machine Learning on Tabular Data*. **NeurIPS 2025** (`arXiv:2506.16791`).
* Qu, J., et al. (2026). *TabICLv2: A better, faster, scalable, and open tabular foundation model*. **ICML 2026** (`arXiv:2602.11139`).
* Wu, S., et al. (2026). *Post-hoc probability calibration in small-sample clinical risk models*. **iScience** (`doi:10.1016/j.isci.2026.115654`).
* Wu, Y., & Weiland, C. (2026). *Early Warning Systems for Chronic Absenteeism*. **EEPA** (`doi:10.3102/01623737261419046`).
* Marcolino, M., et al. (2025). *Longitudinal Student Dropout Prediction with Person-Period Survival Modeling*. **Scientific Reports** (`doi:10.1038/s41598-025-93918-1`).
* Gazmuri Barker, A., & Siddiqui, N. (2026). *School-level and contextual predictors of K-12 dropout*. **IJED** (`doi:10.1016/j.ijedudev.2026.103585`).
* Realinho, V., Machado, J., Baptista, L., & Martins, M. V. (2022). *Predicting Student Dropout and Academic Success (UCI)*. (`doi:10.24432/C5MC89`).
