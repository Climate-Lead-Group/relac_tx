"""Cap TotalTechnologyAnnualActivityUpperLimit using fractions from an xlsx.

The user adds rows to the "Secondary Techs" sheet of A-O_Parametrization.xlsx
with Parameter == params['activity_upper_limit_parameter_label'] (default
"TotalTechnologyAnnualActivityUpperLimit_fraction"). Each year column holds a
fraction in [0, 1] of the per-country electricity demand. This module reads
those fractions, maps each tech to its country-level demand fuel via
OutputActivityRatio, multiplies fraction * demand / OAR to get an absolute
activity cap, and rewrites the TotalTechnologyAnnualActivityUpperLimit block
of an OSeMOSYS GMPL datafile (.txt).

Exposed as an importable module — there is no CLI. B2_Executing_OG_Model.py
calls `apply(...)` directly with paths resolved from the YAML.
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).parent))
from patch_reserve_margin_repair_careful import (  # noqa: E402
    find_param_block,
    fmt_number,
)
from _xlsx_validation_core import (  # noqa: E402
    index_target_sheet,
    is_empty_number,
    norm_str,
)

PARAM_NAME = "TotalTechnologyAnnualActivityUpperLimit"


def _matches_any_prefix(name: str, prefixes) -> bool:
    return any(name.startswith(p) for p in prefixes)


def _derive_demand_fuel(output_fuel: str, demand_fuels: set[str]) -> str | None:
    """Map a tech's output fuel to the country-level demand fuel.

    Convention in this model: PWR* outputs `ELC{country}02` (intermediate); the
    final demand fuel is `ELC{country}03`. Strategy: keep the country segment
    (everything except the last 2 chars of the output fuel) and try common
    suffixes ("03", "04", ...) against the set of demand fuels.
    """
    if output_fuel in demand_fuels:
        return output_fuel
    if len(output_fuel) < 3:
        return None
    stem = output_fuel[:-2]
    for candidate in (f"{stem}03", f"{stem}04", f"{stem}01"):
        if candidate in demand_fuels:
            return candidate
    for fuel in demand_fuels:
        if fuel.startswith(stem):
            return fuel
    return None


def _load_oar(oar_csv: Path, demand_fuel_prefixes) -> dict:
    """Return {tech: [(region, output_fuel, year, mode, oar)]} filtered to
    rows whose output fuel matches one of the demand_fuel_prefixes."""
    out: dict[str, list] = defaultdict(list)
    with open(oar_csv, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fuel = row["FUEL"].strip()
            if not _matches_any_prefix(fuel, demand_fuel_prefixes):
                continue
            try:
                year = int(row["YEAR"])
                oar = float(row["VALUE"])
            except (KeyError, ValueError):
                continue
            out[row["TECHNOLOGY"].strip()].append(
                (row["REGION"].strip(), fuel, year, row.get("MODE_OF_OPERATION", "1").strip(), oar)
            )
    return out


def _load_demand(demand_csv: Path) -> tuple[dict, set[str]]:
    """Return ({(region, fuel, year): value}, set_of_fuels)."""
    demand: dict[tuple[str, str, int], float] = {}
    fuels: set[str] = set()
    with open(demand_csv, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                year = int(row["YEAR"])
                value = float(row["VALUE"])
            except (KeyError, ValueError):
                continue
            region = row["REGION"].strip()
            fuel = row["FUEL"].strip()
            fuels.add(fuel)
            demand[(region, fuel, year)] = value
    return demand, fuels


def _read_fractions_from_xlsx(
    xlsx_path: Path,
    parameter_label: str,
    tech_prefixes,
    exclude_prefixes,
) -> dict:
    """Return {tech_upper: {year: fraction}} from Secondary Techs only."""
    wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=False)
    out: dict[str, dict[int, float]] = {}
    if "Secondary Techs" not in wb.sheetnames:
        wb.close()
        return out
    ws, _cols, ymap, t2r, _dup = index_target_sheet(
        wb, "Secondary Techs", extra_params=(parameter_label,)
    )
    rows = t2r.get(parameter_label, {})
    for tech_upper, row in rows.items():
        if not _matches_any_prefix(tech_upper, tech_prefixes):
            continue
        if exclude_prefixes and _matches_any_prefix(tech_upper, exclude_prefixes):
            continue
        per_year: dict[int, float] = {}
        for year, col in ymap.items():
            v = ws.cell(row, col).value
            if is_empty_number(v):
                continue
            try:
                per_year[int(year)] = float(v)
            except (TypeError, ValueError):
                continue
        if per_year:
            out[tech_upper] = per_year
    wb.close()
    return out


def _compute_caps(
    fractions: dict[str, dict[int, float]],
    oar_by_tech: dict[str, list],
    demand: dict[tuple[str, str, int], float],
    demand_fuels: set[str],
) -> tuple[list[tuple[str, str, int, float]], list[str]]:
    """Return ([(region, tech, year, cap_value)], warnings).

    TotalTechnologyAnnualActivityUpperLimit is indexed by (REGION, TECH, YEAR)
    — there is no MODE dimension. When a tech has multiple OAR rows (e.g.,
    several modes outputting the same demand fuel), we collapse them into a
    single cap by picking the first (region, output_fuel) pair encountered.
    """
    caps: list[tuple[str, str, int, float]] = []
    warnings: list[str] = []
    for tech_upper, year_fractions in fractions.items():
        oar_rows = oar_by_tech.get(tech_upper) or oar_by_tech.get(tech_upper.upper())
        if not oar_rows:
            warnings.append(f"{tech_upper}: no OutputActivityRatio row matching demand fuel prefixes")
            continue
        # One canonical (region, output_fuel) per tech: first encountered wins.
        primary_by_region: dict[str, tuple[str, dict[int, float]]] = {}
        for region, output_fuel, year, _mode, oar in oar_rows:
            slot = primary_by_region.get(region)
            if slot is None:
                primary_by_region[region] = (output_fuel, {year: oar})
            elif slot[0] == output_fuel:
                slot[1][year] = oar
            # else: same region, different output fuel — ignored (first wins).
        for region, (output_fuel, oar_by_year) in primary_by_region.items():
            demand_fuel = _derive_demand_fuel(output_fuel, demand_fuels)
            if demand_fuel is None:
                warnings.append(
                    f"{tech_upper} (region={region}, output_fuel={output_fuel}): "
                    "no SpecifiedAnnualDemand fuel matched country stem"
                )
                continue
            for year, fraction in year_fractions.items():
                demand_value = demand.get((region, demand_fuel, year))
                if demand_value is None:
                    continue
                oar = oar_by_year.get(year, 1.0)
                if oar <= 0:
                    continue
                cap = fraction * demand_value / oar
                caps.append((region, tech_upper, year, cap))
    return caps, warnings


def _patch_param_block(
    lines: list[str],
    caps: list[tuple[str, str, int, float]],
) -> tuple[list[str], int, int]:
    """Rewrite the TotalTechnologyAnnualActivityUpperLimit block.

    Returns (patched_lines, n_overwritten, n_inserted). Pre-existing rows for
    techs NOT in the patch set are preserved verbatim; rows for techs IN the
    patch set are replaced by the new (region, tech, year, value) entries.
    """
    try:
        start, end = find_param_block(lines, PARAM_NAME)
    except ValueError:
        return lines, 0, 0

    header_line = lines[start]
    newline = "\r\n" if header_line.endswith("\r\n") else "\n"

    patched_techs = {tech for (_r, tech, _y, _v) in caps}

    preserved_rows: list[str] = []
    n_dropped = 0
    for raw in lines[start + 1:end]:
        stripped = raw.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) < 2:
            preserved_rows.append(raw if raw.endswith(newline) else raw + newline)
            continue
        tech_token = parts[1]
        if tech_token in patched_techs:
            n_dropped += 1
            continue
        preserved_rows.append(raw if raw.endswith(newline) else raw + newline)

    new_rows = [
        f"{region} {tech} {year} {fmt_number(value)}{newline}"
        for (region, tech, year, value) in caps
    ]
    patched = lines[: start + 1] + preserved_rows + new_rows + lines[end:]
    return patched, n_dropped, len(new_rows)


def apply(
    input_txt: Path,
    output_txt: Path,
    xlsx_path: Path,
    demand_csv: Path,
    oar_csv: Path,
    params: dict,
) -> dict:
    """Apply activity-upper-limit caps. Writes a sibling .txt at output_txt.

    Returns a summary dict with keys: techs_capped, rows_written, rows_replaced,
    rows_skipped_no_demand, warnings.
    """
    input_txt = Path(input_txt)
    output_txt = Path(output_txt)
    xlsx_path = Path(xlsx_path)
    demand_csv = Path(demand_csv)
    oar_csv = Path(oar_csv)

    label = params.get(
        "activity_upper_limit_parameter_label",
        "TotalTechnologyAnnualActivityUpperLimit_fraction",
    )
    tech_prefixes = tuple(params.get("activity_upper_limit_tech_prefixes", ["PWR"]))
    exclude_prefixes = tuple(
        params.get("activity_upper_limit_exclude_prefixes", ["PWRSDS", "PWRLDS", "PWRBCK", "PWRTRN"])
    )
    demand_fuel_prefixes = tuple(params.get("activity_upper_limit_demand_fuel_prefixes", ["ELC"]))

    fractions = _read_fractions_from_xlsx(xlsx_path, label, tech_prefixes, exclude_prefixes)
    if not fractions:
        # Nothing to patch — still emit the output file (a copy) so the chain
        # downstream finds the expected filename.
        output_txt.parent.mkdir(parents=True, exist_ok=True)
        output_txt.write_bytes(input_txt.read_bytes())
        return {
            "techs_capped": 0,
            "rows_written": 0,
            "rows_replaced": 0,
            "rows_skipped_no_demand": 0,
            "warnings": [f"No rows with Parameter == {label!r} found in {xlsx_path.name}"],
        }

    oar_by_tech = _load_oar(oar_csv, demand_fuel_prefixes)
    demand, demand_fuels = _load_demand(demand_csv)
    caps, warnings = _compute_caps(fractions, oar_by_tech, demand, demand_fuels)

    rows_skipped = sum(
        1
        for tech, ys in fractions.items()
        for _y in ys
    ) - len(caps)

    lines = input_txt.read_text(encoding="utf-8").splitlines(keepends=True)
    patched, n_replaced, n_written = _patch_param_block(lines, caps)
    output_txt.parent.mkdir(parents=True, exist_ok=True)
    output_txt.write_text("".join(patched), encoding="utf-8")

    return {
        "techs_capped": len(fractions),
        "rows_written": n_written,
        "rows_replaced": n_replaced,
        "rows_skipped_no_demand": max(rows_skipped, 0),
        "warnings": warnings,
    }
