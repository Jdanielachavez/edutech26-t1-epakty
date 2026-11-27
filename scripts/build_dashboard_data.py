#!/usr/bin/env python3
"""Build validated Silver/Gold from the official hackathon dataset."""

from __future__ import annotations

import csv
import json
import math
import os
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.reference_model import fit_reference, predict_reference
from backend.production.validation import validate_source
from copy import deepcopy
import logging

SOURCE = Path(os.getenv("PAKTAI_SOURCE_DIR", str(ROOT / "data" / "bronze" / "dataset-ficticio-colegio"))).resolve()
MODEL_PATH = Path(os.getenv("PAKTAI_MODEL_ARTIFACT", str(ROOT / "data" / "models" / "approved-risk-model.json"))).resolve()
SILVER_OUTPUT = ROOT / "data" / "silver" / "silver_estudiantes.json"
GOLD_OUTPUT = ROOT / "data" / "gold" / "gold_estudiantes.json"
FRONTEND_OUTPUT = ROOT / "frontend" / "data" / "dashboard.json"


def read_csv(name: str) -> list[dict[str, str]]:
    source_path = SOURCE / name
    if not source_path.is_file():
        raise RuntimeError(f"Falta fuente escolar real requerida: {source_path}")
    with source_path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_optional_csv(name: str) -> list[dict[str, str]]:
    path = SOURCE / name
    return read_optional_csv_from(path)


def read_optional_csv_from(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def number(value: str | None, fallback: float = 0.0) -> float:
    try:
        return float(value) if value not in (None, "") else fallback
    except ValueError:
        return fallback


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def std(values: list[float]) -> float:
    if not values:
        return 0.0
    center = mean(values)
    return math.sqrt(sum((value - center) ** 2 for value in values) / len(values))


def zscore(value: float, values: list[float]) -> float:
    deviation = std(values)
    return (value - mean(values)) / deviation if deviation else 0.0


def slope(points: list[tuple[int, float]]) -> float:
    if len(points) < 2:
        return 0.0
    x_bar = mean([x for x, _ in points])
    y_bar = mean([y for _, y in points])
    denominator = sum((x - x_bar) ** 2 for x, _ in points)
    return sum((x - x_bar) * (y - y_bar) for x, y in points) / denominator if denominator else 0.0


def round2(value: float) -> float:
    return round(float(value), 2)


def max_unjustified_streak(rows: list[dict[str, str]]) -> int:
    longest = current = 0
    for row in sorted(rows, key=lambda item: item["fecha"]):
        if row["estado"] == "falta_injustificada":
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def read_public_context(public_dir: Path) -> dict:
    """Expose small aggregate references without attaching them to students."""
    amie = read_optional_csv_from(public_dir / "amie_abandono.csv")
    enemdu = read_optional_csv_from(public_dir / "enemdu_hogar.csv")
    ineval = read_optional_csv_from(public_dir / "ineval_factores.csv")

    latest_amie_period = max((row.get("periodo", "") for row in amie), default="")
    latest_amie = [row for row in amie if row.get("periodo") == latest_amie_period]
    province_totals: defaultdict[str, list[int]] = defaultdict(lambda: [0, 0])
    for row in latest_amie:
        counts = province_totals[row.get("provincia", "")]
        try:
            counts[0] += int(float(row.get("total_matriculados", 0) or 0))
            counts[1] += int(float(row.get("total_abandono", 0) or 0))
        except ValueError:
            continue
    amie_by_province = [
        {
            "provincia": province,
            "matriculados": counts[0],
            "abandono": counts[1],
            "tasa_abandono": round(100 * counts[1] / counts[0], 4) if counts[0] else None,
        }
        for province, counts in sorted(province_totals.items())
    ]

    latest_enemdu_period = max((row.get("periodo", "") for row in enemdu), default="")
    latest_enemdu = [row for row in enemdu if row.get("periodo") == latest_enemdu_period]
    return {
        "scope": "Agregado; referencia contextual, no enlazada a estudiantes individuales",
        "amie": {
            "periodo": latest_amie_period or None,
            "tasa_abandono_nacional": round(
                100 * sum(item[1] for item in province_totals.values()) /
                sum(item[0] for item in province_totals.values()), 4
            ) if sum(item[0] for item in province_totals.values()) else None,
            "por_provincia": amie_by_province,
            "fuente_url": latest_amie[0].get("fuente_url") if latest_amie else None,
            "fecha_extraccion": latest_amie[0].get("fecha_extraccion") if latest_amie else None,
        },
        "enemdu": {
            "periodo": latest_enemdu_period or None,
            "indicadores": latest_enemdu,
        },
        "ineval": {
            "periodo": max((row.get("periodo", "") for row in ineval), default=None),
            "factores": ineval,
        },
    }


def build(source: Path = SOURCE, *, write_outputs: bool = True) -> tuple[dict, dict, dict]:
    # Dataset mode is independent of whether the API is deployed in production.
    tables = validate_source(source)
    source_manifest = {"institution_id": "hackathon-colegio", "source_system": "dataset-ficticio-colegio",
                       "data_mode": "synthetic_official", "imported_at": "2026-01-01",
                       "payment_due_day": 10, "financial_exposure_months": 6}
    def read_csv(name):
        return tables[name.removesuffix('.csv')]
    def read_optional_csv(name):
        return read_optional_csv_from(source / name)
    payment_due_day = source_manifest["payment_due_day"]
    financial_exposure_months = source_manifest["financial_exposure_months"]
    students = read_csv("estudiantes.csv")
    if not students:
        raise RuntimeError("No hay expedientes reales; no se generará Gold vacío ni de demostración")
    attendance = read_csv("asistencia.csv")
    teachers = read_csv("docentes.csv")
    schedules = read_csv("horarios.csv")
    grades = read_csv("notas.csv")
    payments = read_csv("pensiones.csv")
    class_attendance = read_optional_csv("asistencia_clase.csv")
    wellbeing = read_optional_csv("bienestar.csv")
    public_dir = ROOT / "data" / "bronze" / "public"
    public_reference_counts = {
        name: len(read_optional_csv_from(public_dir / name))
        for name in ("amie_abandono.csv", "enemdu_hogar.csv", "ineval_factores.csv")
    }

    # Production schedules must preserve the effective dates of assignments.
    teacher_by_course_subject: dict[tuple[str, str, str], str] = {}
    teacher_ids = {row["codigo"] for row in teachers}
    for row in schedules:
        if row["docente_codigo"] in teacher_ids:
            teacher_by_course_subject[(row["curso"], row["paralelo"], row["materia"])] = row["docente_codigo"]

    attendance_by_student: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in attendance:
        attendance_by_student[row["codigo_estudiante"]].append(row)

    grades_by_student: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in grades:
        grades_by_student[row["codigo_estudiante"]].append(row)

    payments_by_student: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in payments:
        payments_by_student[row["codigo_estudiante"]].append(row)
    class_attendance_by_student: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in class_attendance:
        class_attendance_by_student[row["codigo_estudiante"]].append(row)
    wellbeing_by_student: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in wellbeing:
        wellbeing_by_student[row["codigo_estudiante"]].append(row)

    teacher_grades: defaultdict[str, list[float]] = defaultdict(list)
    for student in students:
        for row in grades_by_student[student["codigo"]]:
            teacher_id = teacher_by_course_subject.get((student["curso"], student["paralelo"], row["materia"]))
            if teacher_id:
                teacher_grades[teacher_id].append(number(row["nota"]))
    teacher_failure_rates = {
        teacher_id: mean([grade < 7 for grade in values])
        for teacher_id, values in teacher_grades.items()
    }
    latest_period = max(
        ((int(row["quimestre"]), int(row["parcial"])) for row in grades),
        default=(0, 0),
    )

    family_members: Counter[str] = Counter(row["representante_codigo"] for row in students)
    family_spend: defaultdict[str, float] = defaultdict(float)
    family_debt: defaultdict[str, float] = defaultdict(float)
    family_payments: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for student_id, rows in payments_by_student.items():
        student = next(item for item in students if item["codigo"] == student_id)
        family_spend[student["representante_codigo"]] += number(rows[0]["valor"] if rows else "0")
        family_debt[student["representante_codigo"]] += sum(
            number(row["valor"]) for row in rows if row["estado"] == "vencido"
        )
        family_payments[student["representante_codigo"]].extend(rows)

    intermediate: list[dict] = []
    for student in students:
        student_id = student["codigo"]
        family = student["representante_codigo"]
        attendance_rows = attendance_by_student[student_id]
        grade_rows = grades_by_student[student_id]
        payment_rows = payments_by_student[student_id]

        total_days = len(attendance_rows)
        unjustified = sum(row["estado"] == "falta_injustificada" for row in attendance_rows)
        justified = sum(row["estado"] == "falta_justificada" for row in attendance_rows)
        late = sum(row["estado"] == "atraso" for row in attendance_rows)
        attendance_pct = 100 * (1 - (unjustified + justified) / total_days) if total_days else 0.0
        absence_pct = 100 * unjustified / total_days if total_days else 0.0
        max_absence_streak = max_unjustified_streak(attendance_rows)
        hourly_rows = class_attendance_by_student[student_id]
        first_hour_rows = [row for row in hourly_rows if row.get("es_primera_hora") == "1"]
        first_hour_absence = (
            round2(100 * mean([row.get("estado") == "falta_injustificada" for row in first_hour_rows]))
            if first_hour_rows else None
        )

        by_period: defaultdict[int, list[float]] = defaultdict(list)
        by_subject: defaultdict[str, list[float]] = defaultdict(list)
        for row in grade_rows:
            period = (int(row["quimestre"]) - 1) * 3 + int(row["parcial"])
            grade = number(row["nota"])
            by_period[period].append(grade)
            by_subject[row["materia"]].append(grade)
        grade_points = sorted((period, mean(values)) for period, values in by_period.items())
        academic_slope = slope(grade_points)
        grade_values = [number(row["nota"]) for row in grade_rows]
        average_grade = mean(grade_values)
        low_grades = sum(value < 7 for value in grade_values)
        math_grades = [number(row["nota"]) for row in grade_rows if row["materia"].casefold() == "matemática"]
        subject_averages = {subject: mean(values) for subject, values in by_subject.items()}
        critical_subject = min(subject_averages, key=subject_averages.get) if subject_averages else "Sin datos"
        latest_cut_rows = [
            row for row in grade_rows
            if (int(row["quimestre"]), int(row["parcial"])) == latest_period
        ]
        expected_subjects = {
            row["materia"] for row in schedules
            if row["curso"] == student["curso"] and row["paralelo"] == student["paralelo"]
        }
        latest_subjects = {row["materia"] for row in latest_cut_rows}
        missing_latest_subject_count = len(expected_subjects - latest_subjects)
        snp = int(not latest_cut_rows)

        assigned_teachers = {
            teacher_by_course_subject[(student["curso"], student["paralelo"], subject)]
            for subject in expected_subjects
            if (student["curso"], student["paralelo"], subject) in teacher_by_course_subject
        }
        student_teacher_fail_rates = [teacher_failure_rates[item] for item in assigned_teachers if item in teacher_failure_rates]
        teacher_failure_context = mean(student_teacher_fail_rates) if student_teacher_fail_rates else None
        wellbeing_rows = sorted(wellbeing_by_student[student_id], key=lambda row: row.get("fecha_corte", ""))
        wellbeing_value = wellbeing_rows[-1].get("score_bienestar", "").strip() if wellbeing_rows else ""
        wellbeing_score = number(wellbeing_value) if wellbeing_value else None
        if wellbeing_score is not None and not 1 <= wellbeing_score <= 5:
            wellbeing_score = None

        overdue = sum(row["estado"] == "vencido" for row in payment_rows)
        late_payments = 0
        payment_delays = []
        for row in payment_rows:
            if row["estado"] == "pagado" and row["fecha_pago"]:
                try:
                    paid_date = date.fromisoformat(row["fecha_pago"])
                    days_late = max(0, (paid_date - date.fromisoformat(row["mes"] + f"-{payment_due_day:02d}")).days)
                    late_payments += int(days_late > 0)
                    payment_delays.append(days_late)
                except ValueError:
                    pass
        monthly_payment = number(payment_rows[0]["valor"] if payment_rows else "0")
        debt = sum(number(row["valor"]) for row in payment_rows if row["estado"] == "vencido")
        billed_total = sum(number(row["valor"]) for row in payment_rows if row["estado"] != "por_vencer")
        paid_total = sum(number(row["valor"]) for row in payment_rows if row["estado"] == "pagado")
        family_payment_rows = [r for r in family_payments[family] if r["estado"] != "por_vencer"]
        family_latest_month = max((row["mes"] for row in family_payment_rows), default=None)
        recent_payments = [row for row in family_payment_rows if row["mes"] == family_latest_month]
        earlier_payments = [row for row in family_payment_rows if row["mes"] != family_latest_month]
        earlier_payment_problem = any(
            row["estado"] == "vencido"
            or (row["estado"] == "pagado" and row["fecha_pago"] and int(row["fecha_pago"][-2:]) > payment_due_day)
            for row in earlier_payments
        )
        payment_shock = int(
            bool(recent_payments)
            and any(row["estado"] == "vencido" for row in recent_payments)
            and not earlier_payment_problem
        )
        december = [row for row in attendance_rows if row["fecha"].startswith("2025-12")]
        previous = [row for row in attendance_rows if not row["fecha"].startswith("2025-12")]
        december_rate = mean([row["estado"] == "falta_injustificada" for row in december])
        previous_rate = mean([row["estado"] == "falta_injustificada" for row in previous])

        has_nee = (student.get("necesidad_educativa", "").strip().casefold() not in ("", "ninguna", "no"))
        expected_age = {"8vo EGB": 12, "9no EGB": 13, "10mo EGB": 14, "1ro BGU": 15, "2do BGU": 16, "3ro BGU": 17}.get(student["curso"], 18)
        intermediate.append(
            {
                "id": student_id,
                "name": student["nombre_ficticio"],
                "rezago_edad": max(0, 2025 - int(student["anio_nacimiento"]) - expected_age - 1),
                "transicion_critica": int(student["curso"] in ("8vo EGB", "1ro BGU")),
                "history_missing": not bool(grade_rows) or not bool(attendance_rows),
                "course": student["curso"],
                "parallel": student["paralelo"],
                "tiene_nee": int(has_nee),
                "scholarship": number(student["beca_porcentaje"]),
                "family": family,
                "attendance": round2(attendance_pct) if total_days else None,
                "unjustifiedAbsence": round2(absence_pct) if total_days else None,
                "racha_faltas_injustificadas": int(max_absence_streak),
                # Daily attendance has no class-period identifier, so first-hour
                # absence cannot be inferred from this source.
                "ausentismo_primera_hora": first_hour_absence,
                "justifiedAbsence": int(justified),
                "late": int(late),
                "decemberAbsenceDelta": round2((december_rate - previous_rate) * 100),
                "average": round2(average_grade) if grade_values else None,
                "gradeSlope": round2(academic_slope),
                "lowGrades": int(low_grades),
                "mathAverage": round2(mean(math_grades)),
                "materia_critica": critical_subject,
                "SNP_i": snp,
                "materias_sin_nota_ultimo_corte": int(missing_latest_subject_count),
                "promedio_z_paralelo": None,
                "tasa_reprobacion_docente_contexto": round2(100 * teacher_failure_context) if teacher_failure_context is not None else None,
                "docentes_contexto": sorted(assigned_teachers),
                "score_bienestar": round2(wellbeing_score) if wellbeing_score is not None else None,
                "overdueMonths": int(overdue),
                "latePayments": int(late_payments),
                "retraso_pago_promedio_dias_desde_dia_10": round2(mean(payment_delays)),
                "proporcion_pensiones_pagadas": round2(100 * paid_total / billed_total) if billed_total else 0.0,
                "dummy_shock_financiero": payment_shock,
                "debt": round2(debt),
                "familyChildren": int(family_members[family]),
                "familySpend": round2(family_spend[family]),
                "familyDebt": round2(family_debt[family]),
                # The household income needed for a real affordability ratio is
                # not in the school CSVs; ENEMDU is not an individual join key.
                "familySpendRatio": None,
                "financialRisk": round2(monthly_payment * financial_exposure_months),
                "isBgu": int("BGU" in student["curso"]),
            }
        )

    by_course: defaultdict[str, list[float]] = defaultdict(list)
    for row in intermediate:
        if row["average"] is not None:
            by_course[(row["course"], row["parallel"])].append(row["average"])
    for row in intermediate:
        course_values = by_course[(row["course"], row["parallel"])]
        deviation = std(course_values)
        row["promedio_z_paralelo"] = round2((row["average"] - mean(course_values)) / deviation) if deviation and row["average"] is not None else None
        row["desvinculacion_critica_proxy"] = int(
            row["racha_faltas_injustificadas"] >= 15
            or (row["SNP_i"] == 1 and (row["unjustifiedAbsence"] or 0) >= 15)
            or (row["overdueMonths"] >= 3 and (row["unjustifiedAbsence"] or 0) >= 15)
        )

    grade_periods = sorted({(int(row["quimestre"]), int(row["parcial"])) for row in grades})
    if len(grade_periods) >= 2:
        previous_period = grade_periods[-2]
        latest_period_rows = [
            row for row in grades
            if (int(row["quimestre"]), int(row["parcial"])) == latest_period
        ]
        previous_period_rows = [
            row for row in grades
            if (int(row["quimestre"]), int(row["parcial"])) == previous_period
        ]
        latest_by_student: defaultdict[str, list[float]] = defaultdict(list)
        previous_by_student: defaultdict[str, list[float]] = defaultdict(list)
        for row in latest_period_rows:
            latest_by_student[row["codigo_estudiante"]].append(number(row["nota"]))
        for row in previous_period_rows:
            previous_by_student[row["codigo_estudiante"]].append(number(row["nota"]))
        for row in intermediate:
            student_id = row["id"]
            row["delta_nota_ultimo_corte"] = round2(
                mean(latest_by_student[student_id]) - mean(previous_by_student[student_id])
            ) if latest_by_student[student_id] and previous_by_student[student_id] else None
    else:
        for row in intermediate:
            row["delta_nota_ultimo_corte"] = None

    feature_coverage = {
        field: {"con_dato": sum(row.get(field) is not None for row in intermediate), "total": len(intermediate)}
        for field in (
            "racha_faltas_injustificadas", "ausentismo_primera_hora", "score_bienestar",
            "tasa_reprobacion_docente_contexto", "delta_nota_ultimo_corte",
        )
    }

    silver_output = {
        "meta": {
            "layer": "silver",
            "product": "PAKTAI EDU",
            "version": "Hackathon · dataset oficial",
            "dataStatus": "synthetic_official",
            "sourceSystem": source_manifest["source_system"],
            "institutionId": source_manifest["institution_id"],
            "publicReferenceRows": public_reference_counts,
            "publicContext": read_public_context(public_dir),
            "featureCoverage": feature_coverage,
            "limitations": [
                "ausentismo_primera_hora nulo si no existe asistencia_clase.csv",
                "score_bienestar nulo si no existe bienestar.csv",
                "familySpendRatio nulo: no existe ingreso familiar individual",
                "desvinculacion_critica_proxy no representa retiro administrativo confirmado",
            ],
            "updatedAt": datetime.now().strftime("%Y-%m-%d"),
        },
        "students": deepcopy(sorted(intermediate, key=lambda row: row["id"])),
    }

    model = fit_reference(intermediate, public_dir / "amie_abandono.csv")
    display_group = {
        "academico": "Académico",
        "socioemocional_conductual": "Conductual",
        "financiero": "Financiero",
    }
    principal_by_group = {
        "academico": "ACADEMICO",
        "socioemocional_conductual": "SOCIOEMOCIONAL_CONDUCTUAL",
        "financiero": "FINANCIERO",
    }
    actions = {
        "academico": ("Tutoría académica", "Refuerzo personalizado y seguimiento semanal."),
        "socioemocional_conductual": ("DECE e inspección", "Contactar al representante y revisar la asistencia."),
        "financiero": ("Colecturía y trabajo social", "Proponer alternativas de apoyo financiero."),
    }
    for row in intermediate:
        probability, group_contributions = predict_reference(model, row)
        driver_group = max(group_contributions, key=group_contributions.get)
        parts = {display_group[key]: value for key, value in group_contributions.items()}
        driver = display_group[driver_group]
        driver_principal = principal_by_group[driver_group]
        positive_total = sum(max(0.0, value) for value in group_contributions.values())
        causas_pct = {
            "academico": round2(100 * max(0.0, group_contributions["academico"]) / positive_total) if positive_total else 0.0,
            "socioemocional_conductual": round2(100 * max(0.0, group_contributions["socioemocional_conductual"]) / positive_total) if positive_total else 0.0,
            "financiero": round2(100 * max(0.0, group_contributions["financiero"]) / positive_total) if positive_total else 0.0,
            "nee": 0.0,
        }
        area, action = actions[driver_group]
        if probability >= model["thresholds"]["critical"]:
            risk = "Crítico"
        elif probability >= model["thresholds"]["moderate"]:
            risk = "Moderado"
        else:
            risk = "Bajo"
        row.update(
            {
                "risk": round2(probability * 100),
                "riskLabel": risk,
                "driver": driver,
                "driver_principal": driver_principal,
                "tiene_nee": row["tiene_nee"],
                "area": area,
                "action": action,
                "components": {key: round2(value) for key, value in parts.items()},
                "causas_pct": causas_pct,
                "value_risk_usd": row["financialRisk"],
                "VRF_i": row["financialRisk"],
            }
        )
        for transient in ("family", "isBgu"):
            row.pop(transient, None)

    risk_order = ["Crítico", "Moderado", "Bajo"]
    risk_counts = {label: sum(row["riskLabel"] == label for row in intermediate) for label in risk_order}
    driver_counts = dict(sorted(Counter(row["driver"] for row in intermediate).items(), key=lambda item: -item[1]))
    course_counts = dict(sorted(Counter(row["course"] for row in intermediate).items()))
    top_students = sorted(intermediate, key=lambda row: row["risk"], reverse=True)[:8]

    output = {
        "meta": {
            "product": "PAKTAI EDU",
            "version": "Hackathon · dataset oficial",
            "dataStatus": "synthetic_official",
            "riskModelStatus": model["status"],
            "riskModel": {"model_id": model["model_id"], "version": model["version"]},
            "riskInterpretation": "puntaje Logit de referencia; no probabilidad individual validada",
            "modelLimitations": model["limitations"],
            "institutionId": source_manifest["institution_id"],
            "sourceImportedAt": source_manifest["imported_at"],
            "modelValidation": model["validation"],
            "trainingOutcomeCounts": model["training"]["outcome_counts"],
            "updatedAt": datetime.now().strftime("%Y-%m-%d"),
            "publicReferenceRows": public_reference_counts,
            "featureCoverage": feature_coverage,
        },
        "contextualIndicators": read_public_context(public_dir),
        "summary": {
            "students": len(intermediate),
            "critical": risk_counts["Crítico"],
            "moderate": risk_counts["Moderado"],
            "low": risk_counts["Bajo"],
            "operationalDisengagementProxy": sum(row["desvinculacion_critica_proxy"] for row in intermediate),
            "averageRisk": round2(mean([row["risk"] for row in intermediate])),
            "debt": round2(sum(row["debt"] for row in intermediate)),
            "riskCounts": risk_counts,
            "driverCounts": driver_counts,
            "courseCounts": course_counts,
            "topStudents": top_students,
        },
        "students": sorted(intermediate, key=lambda row: row["risk"], reverse=True),
    }
    if write_outputs:
        for path, value in ((SILVER_OUTPUT, silver_output), (GOLD_OUTPUT, output), (FRONTEND_OUTPUT, output),
                            (ROOT / 'data/models/reference-logit.json', model)):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    logging.getLogger('paktai').info(json.dumps({'event': 'pipeline_built', 'students': len(intermediate), 'risk_counts': risk_counts}))
    return silver_output, output, model

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    build()
