#!/usr/bin/env python3
"""Download and normalize public aggregate references for Bronze.

AMIE is aggregated before it enters the application-facing layers. ENEMDU uses
official tabulated estimates, not microdata. INEVAL is retained as a published
aggregate factors-associated report; none of these sources is joined to an
individual student record.
"""

from __future__ import annotations

import csv
import argparse
import hashlib
import io
import json
import unicodedata
import urllib.request
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "data" / "bronze" / "public"
RAW = PUBLIC / "raw"
AMIE_URL = "https://www.datosabiertos.gob.ec/dataset/137ebd87-8998-4c1b-aa3f-ad6daf411b6d/resource/e4a967a3-7bed-44eb-92d7-d23a1f2129d3/download/registro-administrativo-historico_2009-2024-fin.csv"
ENEMDU_URL = "https://www.ecuadorencifras.gob.ec/documentos/web-inec/EMPLEO/2025/anual/ENEMDU_Tabulados_anual_2025-CSV.zip"
PROVINCES = {
    "Azuay", "Bolívar", "Cañar", "Carchi", "Cotopaxi", "Chimborazo", "El Oro",
    "Esmeraldas", "Guayas", "Imbabura", "Loja", "Los Ríos", "Manabí",
    "Morona Santiago", "Napo", "Pastaza", "Pichincha", "Tungurahua",
    "Zamora Chinchipe", "Galápagos", "Sucumbíos", "Orellana",
    "Santo Domingo", "Santa Elena",
}


def normalized(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(char)
    ).strip()


def download(url: str, destination: Path, *, force: bool = False) -> dict:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "PAKTAI-EDU-public-reference-sync/1.0"})
    digest = hashlib.sha256()
    size = 0
    if not force and destination.exists() and destination.stat().st_size > 0:
        with destination.open("rb") as existing:
            while chunk := existing.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
        return {"url": url, "path": str(destination.relative_to(ROOT)), "bytes": size, "sha256": digest.hexdigest(), "cached": True}
    with urllib.request.urlopen(request, timeout=180) as response, destination.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    return {"url": url, "path": str(destination.relative_to(ROOT)), "bytes": size, "sha256": digest.hexdigest()}


def load_amie(path: Path) -> tuple[list[dict], int]:
    grouped: defaultdict[tuple[str, ...], list[int]] = defaultdict(lambda: [0, 0])
    records = 0
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        required = {"Anio_lectivo", "Provincia", "Sostenimiento", "Tipo_Educacion", "area", "Regimen_Escolar", "Total_Estudiantes", "Abandono"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError("El CSV AMIE no contiene el esquema esperado")
        for row in reader:
            records += 1
            # This publication uses dots as thousands separators (e.g. 1.010).
            # Strip punctuation only after validating that the value is numeric.
            def parse_count(raw: str) -> int:
                value = (raw or "0").strip().replace(".", "").replace(",", "")
                return int(value) if value.isdigit() else 0

            total = parse_count(row["Total_Estudiantes"])
            abandoned = parse_count(row["Abandono"])
            if total < 0 or abandoned < 0 or abandoned > total:
                continue
            key = (
                row["Anio_lectivo"].strip(), row["Provincia"].strip().title(),
                row["Sostenimiento"].strip(), row["Tipo_Educacion"].strip(),
                row["area"].strip(), row["Regimen_Escolar"].strip(),
            )
            grouped[key][0] += total
            grouped[key][1] += abandoned
    rows = []
    for key, counts in sorted(grouped.items()):
        total, abandoned = counts
        if total == 0:
            continue
        rows.append({
            "periodo": key[0], "provincia": key[1], "sostenimiento": key[2],
            "tipo_educacion": key[3], "area": key[4], "regimen": key[5],
            "total_matriculados": total, "total_abandono": abandoned,
            "tasa_abandono": round(100 * abandoned / total, 4), "fuente_url": AMIE_URL,
            "fecha_extraccion": datetime.now(timezone.utc).date().isoformat(),
        })
    return rows, records


def parse_percent(value: str) -> float | None:
    value = value.strip().replace("%", "").replace(" ", "")
    if not value:
        return None
    try:
        if "," in value:
            return float(value.replace(".", "").replace(",", "."))
        return float(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return None


def parse_enemdu_table(data: bytes, source_file: str, indicator_filter: set[str]) -> list[dict]:
    with io.TextIOWrapper(io.BytesIO(data), encoding="cp1252", newline="") as handle:
        table = list(csv.reader(handle, delimiter=";"))
    header_idx = next((index for index, row in enumerate(table) if row and normalized(row[0]) in {"periodo", "período"}), None)
    if header_idx is None:
        raise ValueError(f"No se encontró encabezado territorial en {source_file}")
    # ENEMDU territory tables use a two-row header: the first row describes
    # the groups (Nacional/Área/Ciudades/Provincias), the next row contains
    # actual area and province names. Take those leaf labels for each column.
    labels = table[header_idx + 1] if header_idx + 1 < len(table) else table[header_idx]
    rows = []
    for row in table[header_idx + 1:]:
        if len(row) < 3:
            continue
        period, indicator = row[0].strip(), row[1].strip()
        if normalized(indicator) not in indicator_filter:
            continue
        for index, label in enumerate(labels[2:], start=2):
            if index >= len(row) or not label.strip():
                continue
            normalized_label = normalized(label)
            if normalized_label in {"total", "urbano", "rural"}:
                province, area = "Nacional", label.strip()
            elif label.strip() in PROVINCES or normalized_label in {normalized(item) for item in PROVINCES}:
                province, area = label.strip().title(), "Total"
            else:
                continue
            value = parse_percent(row[index])
            if value is None:
                continue
            rows.append({
                "periodo": period, "provincia": province, "area": area,
                "indicador": indicator, "valor": value, "unidad": "porcentaje",
                "fuente_url": ENEMDU_URL,
                "fecha_extraccion": datetime.now(timezone.utc).date().isoformat(),
            })
    return rows


def load_enemdu(path: Path) -> list[dict]:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        employment_path = next(
            name for name in names
            if "Mercado_Laboral_CSV" in name and name.endswith("2. Territorio.csv")
        )
        poverty_path = next(
            name for name in names
            if "Pobreza_Desigualdad_CSV" in name and name.endswith("2. Territorio.csv")
        )
        employment = archive.read(employment_path)
        poverty = archive.read(poverty_path)
    rows = parse_enemdu_table(employment, employment_path, {"tasa de desempleo"})
    rows.extend(parse_enemdu_table(poverty, poverty_path, {"pobreza por ingresos"}))
    return rows


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sincroniza referencias públicas AMIE y ENEMDU")
    parser.add_argument("--force", action="store_true", help="descarga nuevamente aunque exista copia en cache")
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    amie_file = RAW / "amie_registro_historico_2009_2024_fin.csv"
    enemdu_file = RAW / "enemdu_tabulados_anual_2025_csv.zip"
    files = [
        download(AMIE_URL, amie_file, force=args.force),
        download(ENEMDU_URL, enemdu_file, force=args.force),
    ]
    amie_rows, amie_source_records = load_amie(amie_file)
    enemdu_rows = load_enemdu(enemdu_file)
    write_csv(PUBLIC / "amie_abandono.csv", amie_rows, [
        "periodo", "provincia", "sostenimiento", "tipo_educacion", "area", "regimen",
        "total_matriculados", "total_abandono", "tasa_abandono", "fuente_url", "fecha_extraccion",
    ])
    write_csv(PUBLIC / "enemdu_hogar.csv", enemdu_rows, [
        "periodo", "provincia", "area", "indicador", "valor", "unidad", "fuente_url", "fecha_extraccion",
    ])
    manifest = {
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": files,
        "amie_source_records": amie_source_records,
        "amie_aggregate_rows": len(amie_rows),
        "enemdu_aggregate_rows": len(enemdu_rows),
        "ineval_context_rows": sum(1 for _ in (PUBLIC / "ineval_factores.csv").open(encoding="utf-8")) - 1,
        "linkage_policy": "AMIE, ENEMDU e INEVAL son agregados/contexto y no se enlazan a estudiantes individuales.",
    }
    (RAW / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"AMIE {amie_source_records} registros -> {len(amie_rows)} agregados")
    print(f"ENEMDU -> {len(enemdu_rows)} agregados")
    print("INEVAL -> extracto agregado preservado con referencia al boletín oficial")


if __name__ == "__main__":
    main()
