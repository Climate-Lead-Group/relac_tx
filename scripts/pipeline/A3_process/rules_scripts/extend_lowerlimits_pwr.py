# -*- coding: utf-8 -*-
"""
extend_lowerlimits_pwr.py
==========================

Extends TotalTechnologyAnnualActivityLowerLimit for PWR (generation) techs in
A-O_Parametrization.xlsx sheet "Secondary Techs" from BASE_YEAR (2024) through
END_YEAR (2050). The 2024 value is held flat — no growth, no taper.

Without this extension, the 2024 calibration floor expires and the optimizer
is free to dump thermal generation in 2025+, which is undesirable for BAU-style
runs that anchor thermal fleets on observed 2024 dispatch.

USAGE (via A3_process.py orchestrator)
--------------------------------------
A3_process.py invokes this for each scenario as:
    python extend_lowerlimits_pwr.py --input-dir <scenario_dir> [--force-overwrite]

Direct invocation:
    python extend_lowerlimits_pwr.py --input-dir t1_confection/A1_Outputs/A1_Outputs_BAU

Default (no --force-overwrite): only fills empty or zero 2025..2050 cells with
the 2024 value; non-zero pre-existing values are preserved. With
--force-overwrite, every 2025..2050 cell of qualifying rows is set to the 2024
value regardless of prior content.

--include-types restricts the extension to PWR techs whose type code (chars 4-6
of the code, TECHNOLOGY[3:6], e.g. "HYD" in PWRHYDBRAXX) is in the given
comma-separated list. Without it, every PWR row qualifies (original behavior).
Used by A3_process.py to impose the floor on a subset of types per scenario
(e.g. renewables only for OPT, see lowerlimit_scenarios in lid_rule.yaml).

Side effects:
- Modifies A-O_Parametrization.xlsx in place.
- Writes extend_lowerlimits_pwr_changes_<ts>.json next to the xlsx with a
  per-cell audit (row, tech, year, prev, new).
- Whenever a row is touched, its Projection.Mode (col G) is forced to
  "User defined" so the downstream pipeline does not treat populated values as
  placeholders.

Author: Luis / CLG  (refactored for A3_process integration)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import openpyxl

SHEET_NAME = "Secondary Techs"
TARGET_PARAMETER = "TotalTechnologyAnnualActivityLowerLimit"
TECH_PREFIX = "PWR"
BASE_YEAR = 2024
END_YEAR = 2050

# Earliest year this script may write. The 2024 value is still used as the flat
# floor, but only cells from MODIFY_FROM_YEAR onward are written; years before
# it (e.g. 2025) keep their existing value so the historical years stay
# identical across scenarios (see sync_historical_from_bau.py). Override via
# --modify-from-year. Set to BASE_YEAR+1 (2025) to restore the prior behavior.
MODIFY_FROM_YEAR = 2026

# Column layout for "Secondary Techs":
#   B=Tech, E=Parameter, G=Projection.Mode, I=2023, J=2024, ..., AJ=2050.
COL_TECH = 2
COL_PARAMETER = 5
COL_PROJ_MODE = 7
COL_YEAR_2023 = 9  # column for year `y` = COL_YEAR_2023 + (y - 2023)

PARAM_FILENAME = "A-O_Parametrization.xlsx"


def year_to_col(year: int) -> int:
    return COL_YEAR_2023 + (year - 2023)


def _is_empty(val) -> bool:
    if val is None:
        return True
    if isinstance(val, str) and val.strip() == "":
        return True
    if isinstance(val, (int, float)) and val == 0:
        return True
    return False


def run(input_dir: Path, force_overwrite: bool,
        include_types: set[str] | None = None,
        modify_from_year: int = MODIFY_FROM_YEAR) -> dict:
    paramfile = input_dir / PARAM_FILENAME
    if not paramfile.is_file():
        sys.exit(f"ERROR: {PARAM_FILENAME} not found in {input_dir}")

    # First year actually written: never before MODIFY_FROM_YEAR, and never at
    # or before BASE_YEAR (the flat-floor anchor itself is not overwritten).
    start_year = max(modify_from_year, BASE_YEAR + 1)

    wb = openpyxl.load_workbook(paramfile)
    if SHEET_NAME not in wb.sheetnames:
        sys.exit(f"ERROR: sheet '{SHEET_NAME}' not found in {paramfile}")
    ws = wb[SHEET_NAME]

    base_col = year_to_col(BASE_YEAR)

    changes: list[dict] = []
    rows_touched = 0
    rows_skipped_no_base = 0
    rows_skipped_type = 0
    rows_matched = 0

    for row in range(2, ws.max_row + 1):
        tech = ws.cell(row=row, column=COL_TECH).value
        parameter = ws.cell(row=row, column=COL_PARAMETER).value
        if not isinstance(tech, str) or not tech.startswith(TECH_PREFIX):
            continue
        if parameter != TARGET_PARAMETER:
            continue
        rows_matched += 1

        if include_types is not None and tech[3:6] not in include_types:
            rows_skipped_type += 1
            continue

        base_val = ws.cell(row=row, column=base_col).value
        if _is_empty(base_val):
            rows_skipped_no_base += 1
            continue

        row_changes: list[dict] = []
        for year in range(start_year, END_YEAR + 1):
            col = year_to_col(year)
            prev = ws.cell(row=row, column=col).value
            if not force_overwrite and not _is_empty(prev):
                continue
            if prev == base_val:
                continue
            ws.cell(row=row, column=col).value = base_val
            row_changes.append({"year": year, "prev": prev, "new": base_val})

        if row_changes:
            ws.cell(row=row, column=COL_PROJ_MODE).value = "User defined"
            rows_touched += 1
            changes.append({
                "row": row,
                "tech": tech,
                "base_year": BASE_YEAR,
                "base_value": base_val,
                "cells": row_changes,
            })

    wb.save(paramfile)

    stamp = time.strftime("%Y%m%d_%H%M%S")
    log_path = input_dir / f"extend_lowerlimits_pwr_changes_{stamp}.json"
    log = {
        "input_dir": str(input_dir),
        "paramfile": str(paramfile),
        "sheet": SHEET_NAME,
        "parameter": TARGET_PARAMETER,
        "tech_prefix": TECH_PREFIX,
        "base_year": BASE_YEAR,
        "end_year": END_YEAR,
        "modify_from_year": modify_from_year,
        "start_year": start_year,
        "force_overwrite": force_overwrite,
        "include_types": sorted(include_types) if include_types is not None else None,
        "rows_matched": rows_matched,
        "rows_touched": rows_touched,
        "rows_skipped_no_base": rows_skipped_no_base,
        "rows_skipped_type": rows_skipped_type,
        "total_cell_writes": sum(len(c["cells"]) for c in changes),
        "changes": changes,
    }
    log_path.write_text(json.dumps(log, indent=2, default=str))
    log["log_path"] = str(log_path)
    return log


def print_summary(log: dict) -> None:
    print()
    print("=" * 70)
    print(f"  EXTEND LowerLimits for {log['tech_prefix']} technologies")
    print("=" * 70)
    print(f"  paramfile            : {log['paramfile']}")
    print(f"  sheet                : {log['sheet']}")
    print(f"  parameter            : {log['parameter']}")
    print(f"  base_year -> end     : {log['base_year']} -> {log['end_year']}")
    print(f"  modify_from_year     : {log['modify_from_year']} "
          f"(first written year: {log['start_year']})")
    print(f"  force_overwrite      : {log['force_overwrite']}")
    print(f"  include_types        : {log['include_types'] or 'ALL'}")
    print(f"  rows_matched         : {log['rows_matched']}")
    print(f"  rows_skipped_type    : {log['rows_skipped_type']}")
    print(f"  rows_skipped_no_base : {log['rows_skipped_no_base']}")
    print(f"  rows_touched         : {log['rows_touched']}")
    print(f"  total_cell_writes    : {log['total_cell_writes']}")
    print(f"  log                  : {log['log_path']}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        required=True,
        help="Scenario folder containing A-O_Parametrization.xlsx.",
    )
    parser.add_argument(
        "--force-overwrite",
        action="store_true",
        help=(
            "Overwrite non-empty 2025..2050 cells with the 2024 value. "
            "Default preserves any pre-existing positive values."
        ),
    )
    parser.add_argument(
        "--include-types",
        default=None,
        help=(
            "Comma-separated PWR type codes (chars 4-6 of the tech code, "
            "e.g. 'BIO,GEO,SPV'). When given, only PWR techs whose type is in "
            "this list get the floor extended; others are left untouched. "
            "Default: all PWR techs."
        ),
    )
    parser.add_argument(
        "--modify-from-year",
        type=int,
        default=MODIFY_FROM_YEAR,
        help=(
            f"Earliest year to write; years before it keep their value "
            f"(default {MODIFY_FROM_YEAR}). The 2024 flat floor is still the "
            f"source value. Use 2025 to restore the prior behavior."
        ),
    )
    args = parser.parse_args()

    include_types = None
    if args.include_types:
        include_types = {
            t.strip().upper() for t in args.include_types.split(",") if t.strip()
        }

    log = run(args.input_dir, args.force_overwrite, include_types=include_types,
              modify_from_year=args.modify_from_year)
    print_summary(log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
