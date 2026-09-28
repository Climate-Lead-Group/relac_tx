"""Copy BAU's early-year cell values into other scenarios' A-O_Parametrization.xlsx.

Copies the values of the first years from the BAU scenario into the other scenarios (INV,
OPT, VGB, ...) in A-O_Parametrization.xlsx. The year WINDOW to copy is passed via --years:
A3_process.py sets it PER SCENARIO from `historical_sync_through` in lid_rule.yaml
(INV->2030, OPT->2026, VGB->2030). The DEFAULT_* constants below only apply to manual runs
without --scenarios/--years.

Motivation:
    Historical/observed years (2023-2025) must be identical across all scenarios, and some
    scenarios must also mirror BAU beyond the historical years so they do not diverge too
    early (OPT through 2026; INV/VGB through 2030, where D4 starts capping INV's
    transmission). This script guarantees that common starting point: for every sheet with
    year columns, it copies BAU's cells into each target scenario within the given window.
    Deliberate divergences are preserved via --protect-params and the built-in TX
    protection (see below).

Scope:
    - A-O_Parametrization.xlsx only (does not touch Demand, Projections, etc.).
    - Every sheet with year columns (int header 2023 or string header "2023"). Sheets
      without year columns (e.g. 'Fixed Horizon Parameters') are skipped automatically.
    - Only the years in --years (default 2023,2024,2025 for manual runs; in the chain, A3
      passes the per-scenario window from `historical_sync_through`).
    - EXCEPTION: on the 'Demand Techs' sheet, TotalAnnualMaxCapacityInvestment rows for
      transmission technologies (TRN*) are NOT copied for years >= TX_DIVERGE_YEAR (2027).
      There, the cap written by D4_load_dsptrn_max_cap_inv.py governs (INV's transmission
      diverges from BAU starting 2027). Years <= 2026 are still copied (every scenario
      equals BAU through 2026, including TX). This TX protection is turned off per run with
      --no-protect-tx, for scenarios D4 does not cap and that should equal BAU in TX for
      their whole window (e.g. OPT).
    - GENERIC EXCEPTION (--protect-params): parameters named in --protect-params are NOT
      copied for years >= PROTECT_PARAMS_FROM_YEAR (2027), on any sheet. This lets a
      scenario deliberately diverge from BAU in a parameter starting 2027, without the sync
      overwriting that divergence within the synced window. Years <= 2026 are still copied
      (equal to BAU). E.g. VGB protects TotalTechnologyAnnualActivityLowerLimit (renewables
      floor) and TotalAnnualMinCapacityInvestment (PEGs = OPT).
    - Projection.Mode is not copied by this script: only columns matching a year header are
      touched, and Projection.Mode is not a year column.

Safety:
    - The BAU/INV/OPT workbooks have the same number of rows per sheet, so the copy is
      POSITIONAL. Before copying, this script verifies that (a) the sheet exists in both
      workbooks, (b) the row count and header row match, and (c) the 'Parameter' column
      matches row by row (guards against misalignment). If anything does not match, the
      script aborts without writing.
    - --apply makes a timestamped backup of each target xlsx before writing.

Inputs:
    inputs/A1_Outputs/A1_Outputs_BAU/A-O_Parametrization.xlsx (source)
    inputs/A1_Outputs/A1_Outputs_<scenario>/A-O_Parametrization.xlsx (per --scenarios target)
Outputs:
    Target scenarios' A-O_Parametrization.xlsx, in place (timestamped backup first), when
        --apply is passed.
Usage:
    python scripts/pipeline/sync_historical_from_bau.py --dry-run     # preview (default)
    python scripts/pipeline/sync_historical_from_bau.py --apply
    python scripts/pipeline/sync_historical_from_bau.py --apply --scenarios INV
    python scripts/pipeline/sync_historical_from_bau.py --years 2023,2024,2025
Notes:
    - Called by A3_process.py's final harmonization step, once for all scenarios, per
      `historical_sync_through` in lid_rule.yaml.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> scripts/
from common import relac_paths as P

HERE = Path(__file__).resolve().parent
A1_OUTPUTS = P.A1_OUTPUTS
PARAM_FILENAME = "A-O_Parametrization.xlsx"
SOURCE_SCENARIO = "BAU"
# Defaults SOLO para corridas manuales sin --scenarios/--years. En la cadena,
# A3_process.py invoca este script por escenario con la ventana explicita que
# define historical_sync_through en lid_rule.yaml (INV->2030, OPT->2026,
# VGB->2030); esas corridas NO usan estos defaults.
DEFAULT_TARGET_SCENARIOS = ["INV", "OPT"]
DEFAULT_YEARS = [2023, 2024, 2025]

# Transmission MaxCapInv divergence. D4_load_dsptrn_max_cap_inv.py escribe el
# tope anual de transmision para INV desde TX_DIVERGE_YEAR en adelante (cap =
# NewCapacity_BAU * factor). Esas celdas NO deben volver a BAU por este sync, o
# INV perderia su tope de transmision. Por eso, para anos >= TX_DIVERGE_YEAR se
# saltan las filas de transmision (TX_PARAM sobre techs TX_PREFIXES) de la hoja
# TX_SHEET. Los anos < TX_DIVERGE_YEAR si se copian. Boundary = 2027 (2026-06-16):
# TODOS los escenarios igualan a BAU hasta 2026 (incluida TX); la TX de INV
# diverge (tope D4) desde 2027. Debe ir alineado con D4.EQUAL_THROUGH_YEAR=2026.
# Esta proteccion es el DEFAULT; --no-protect-tx la desactiva para escenarios que
# D4 NO topa y que igualan a BAU en TX en toda su ventana (p.ej. OPT).
TX_DIVERGE_YEAR = 2027
TX_SHEET = "Demand Techs"
TX_PARAM = "TotalAnnualMaxCapacityInvestment"
TX_PREFIXES = ("PWRTRN", "TRNNLI", "TRNRPO", "RNWTRN", "RNWRPO", "RNWNLI")

# Generic per-parameter protection (--protect-params). Rows whose 'Parameter'
# is in the protect set are NOT copied from BAU for years >= this boundary, on
# ANY sheet. Same divergence boundary as transmission (2027): years <= 2026 are
# pinned to BAU and always synced (VGB PEGs/LowerLimit diverge only from 2027).
PROTECT_PARAMS_FROM_YEAR = TX_DIVERGE_YEAR


def param_path(scenario: str) -> Path:
    return A1_OUTPUTS / f"A1_Outputs_{scenario}" / PARAM_FILENAME


def year_columns(ws, years: set[int]) -> dict[int, int]:
    """Return {year: column_index_1based} for headers in row 1 matching `years`.

    Accepts both integer headers (2023) and string-digit headers ("2023"),
    since some sheets (Capacities, Yearsplit, DaySplit) store year headers as
    strings while others (Secondary Techs, ...) store them as ints.
    """
    found: dict[int, int] = {}
    for col_idx, cell in enumerate(next(ws.iter_rows(min_row=1, max_row=1)), start=1):
        v = cell.value
        y = None
        if isinstance(v, int):
            y = v
        elif isinstance(v, str) and v.strip().isdigit():
            y = int(v.strip())
        if y is not None and y in years:
            found[y] = col_idx
    return found


def header_row(ws) -> list:
    return [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]


def find_param_col(header: list) -> int | None:
    """1-based index of the 'Parameter' column in the header, or None."""
    for i, h in enumerate(header, start=1):
        if isinstance(h, str) and h.strip() == "Parameter":
            return i
    return None


def find_tech_col(header: list) -> int | None:
    """1-based index of the 'Tech' column in the header, or None."""
    for i, h in enumerate(header, start=1):
        if isinstance(h, str) and h.strip() == "Tech":
            return i
    return None


def sync_scenario(src_ws_map, src_wb, tgt_path: Path, years: set[int],
                  apply_changes: bool, protect_params: set[str] | None = None,
                  protect_tx_rows: bool = True) -> dict:
    """Copy year cells from BAU into one target scenario workbook.

    `src_ws_map` is {sheet_name: source_worksheet}. `protect_params` is a set of
    Parameter names whose rows are NOT copied for years >= PROTECT_PARAMS_FROM_YEAR
    (on any sheet); historical years are still synced. `protect_tx_rows` (default
    True) is the built-in transmission protection: when True, TX MaxCapInv rows
    are NOT copied for years >= TX_DIVERGE_YEAR; set False (via --no-protect-tx)
    to fully sync TX to BAU for scenarios D4 does not cap. Returns a summary dict.
    Raises ValueError on any structural mismatch (caller aborts the run).
    """
    protect_params = protect_params or set()
    tgt_wb = openpyxl.load_workbook(tgt_path)
    summary = {"path": str(tgt_path), "sheets": [], "total_cells": 0}

    try:
        for sheet in src_wb.sheetnames:
            if sheet not in tgt_wb.sheetnames:
                raise ValueError(
                    f"{tgt_path.name}: sheet '{sheet}' present in BAU but missing here."
                )
            src_ws = src_ws_map[sheet]
            tgt_ws = tgt_wb[sheet]

            src_cols = year_columns(src_ws, years)
            tgt_cols = year_columns(tgt_ws, years)
            if not src_cols:
                summary["sheets"].append({"sheet": sheet, "skipped": "no year columns"})
                continue
            if src_cols != tgt_cols:
                raise ValueError(
                    f"{tgt_path.name}/{sheet}: year-column layout differs from BAU "
                    f"(BAU={src_cols}, target={tgt_cols})."
                )
            if src_ws.max_row != tgt_ws.max_row:
                raise ValueError(
                    f"{tgt_path.name}/{sheet}: row count differs from BAU "
                    f"(BAU={src_ws.max_row}, target={tgt_ws.max_row})."
                )
            if header_row(src_ws) != header_row(tgt_ws):
                raise ValueError(
                    f"{tgt_path.name}/{sheet}: header row differs from BAU."
                )

            param_col = find_param_col(header_row(src_ws))
            tech_col = find_tech_col(header_row(src_ws))
            is_tx_sheet = sheet == TX_SHEET
            cells_changed = 0
            cells_protected = 0
            for row in range(2, src_ws.max_row + 1):
                # Guard against row misalignment: the Parameter column (when
                # present) must match between BAU and target for this row.
                if param_col is not None:
                    sp = src_ws.cell(row=row, column=param_col).value
                    tp = tgt_ws.cell(row=row, column=param_col).value
                    if sp != tp:
                        raise ValueError(
                            f"{tgt_path.name}/{sheet} row {row}: Parameter mismatch "
                            f"(BAU={sp!r}, target={tp!r}); aborting to avoid "
                            f"misaligned copy."
                        )
                # Protect D4's transmission MaxCapInv cap from being snapped back
                # to BAU in 2026+. Only the TX_PARAM rows of TX_PREFIXES techs on
                # the TX_SHEET are shielded, and only for years >= TX_DIVERGE_YEAR.
                protect_tx = False
                if protect_tx_rows and is_tx_sheet and tech_col is not None and param_col is not None:
                    tv = src_ws.cell(row=row, column=tech_col).value
                    pv = src_ws.cell(row=row, column=param_col).value
                    if (isinstance(tv, str) and tv.strip().startswith(TX_PREFIXES)
                            and isinstance(pv, str) and pv.strip() == TX_PARAM):
                        protect_tx = True
                # Generic parameter protection: shield deliberately-diverged
                # parameters (e.g. VGB's LowerLimit / PEGs) from 2026 onward.
                protect_param = False
                if protect_params and param_col is not None:
                    pv2 = src_ws.cell(row=row, column=param_col).value
                    if isinstance(pv2, str) and pv2.strip() in protect_params:
                        protect_param = True
                for y, col in src_cols.items():
                    if protect_tx and y >= TX_DIVERGE_YEAR:
                        cells_protected += 1
                        continue
                    if protect_param and y >= PROTECT_PARAMS_FROM_YEAR:
                        cells_protected += 1
                        continue
                    sv = src_ws.cell(row=row, column=col).value
                    tc = tgt_ws.cell(row=row, column=col)
                    if tc.value != sv:
                        tc.value = sv
                        cells_changed += 1

            summary["sheets"].append({
                "sheet": sheet,
                "years": sorted(src_cols),
                "cells_changed": cells_changed,
                "cells_protected": cells_protected,
            })
            summary["total_cells"] += cells_changed

        if apply_changes:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = tgt_path.with_name(
                f"{tgt_path.stem}.backup_pre_sync_hist_{ts}{tgt_path.suffix}"
            )
            shutil.copy2(tgt_path, backup)
            summary["backup"] = backup.name
            tgt_wb.save(tgt_path)
    finally:
        tgt_wb.close()

    return summary


def main() -> int:
    """Parse CLI args, sync each target scenario from BAU, and print a per-sheet summary.

    Returns:
        0 on completion (aborts via `sys.exit` if a source/target workbook is missing, or
        via a propagated `ValueError` from `sync_scenario` on any structural mismatch).

    Side effects:
        For each target scenario, writes its A-O_Parametrization.xlsx in place (after a
        timestamped backup) when `--apply` is passed; otherwise previews without writing.
    """
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--apply", action="store_true", help="escribe cambios (crea backup)")
    grp.add_argument("--dry-run", action="store_true", help="preview sin escribir (default)")
    ap.add_argument(
        "--scenarios", default=",".join(DEFAULT_TARGET_SCENARIOS),
        help=f"escenarios destino, separados por coma (default: "
             f"{','.join(DEFAULT_TARGET_SCENARIOS)})",
    )
    ap.add_argument(
        "--years", default=",".join(str(y) for y in DEFAULT_YEARS),
        help=f"anos a copiar, separados por coma (default: "
             f"{','.join(str(y) for y in DEFAULT_YEARS)})",
    )
    ap.add_argument(
        "--protect-params", default="",
        help="parametros (separados por coma) que NO se copian desde BAU para "
             f"anos >= {PROTECT_PARAMS_FROM_YEAR}, en cualquier hoja. Los anos "
             "historicos (<= 2025) siempre se copian.",
    )
    ap.add_argument(
        "--no-protect-tx", action="store_true",
        help="desactiva la proteccion TX incorporada: las filas de "
             f"{TX_PARAM} de techs de transmision (TRN*) SI se copian desde BAU "
             f"para anos >= {TX_DIVERGE_YEAR}. Usar para escenarios que D4 NO "
             "topa y que deben igualar a BAU tambien en transmision (p.ej. OPT).",
    )
    args = ap.parse_args()

    apply_changes = args.apply and not args.dry_run
    mode = "APPLY" if apply_changes else "DRY-RUN"
    targets = [s.strip() for s in args.scenarios.split(",") if s.strip()]
    years = {int(y.strip()) for y in args.years.split(",") if y.strip()}
    protect_params = {p.strip() for p in args.protect_params.split(",") if p.strip()}
    protect_tx_rows = not args.no_protect_tx

    print(f"Mode      : {mode}")
    print(f"Source    : {SOURCE_SCENARIO}")
    print(f"Targets   : {targets}")
    print(f"Years     : {sorted(years)}")
    print(f"Protect TX: {'ON' if protect_tx_rows else 'OFF (TX synced to BAU)'} "
          f"(TRN* {TX_PARAM} for years >= {TX_DIVERGE_YEAR})")
    if protect_params:
        print(f"Protect   : {sorted(protect_params)} (not synced for years "
              f">= {PROTECT_PARAMS_FROM_YEAR})")

    src_path = param_path(SOURCE_SCENARIO)
    if not src_path.exists():
        sys.exit(f"ERROR: no existe source {src_path}")
    src_wb = openpyxl.load_workbook(src_path, data_only=False)
    src_ws_map = {sh: src_wb[sh] for sh in src_wb.sheetnames}

    try:
        grand_total = 0
        for scen in targets:
            tgt_path = param_path(scen)
            if not tgt_path.exists():
                sys.exit(f"ERROR: no existe target {tgt_path}")
            print(f"\n=== {scen} <- {SOURCE_SCENARIO} ===")
            summary = sync_scenario(src_ws_map, src_wb, tgt_path, years,
                                     apply_changes, protect_params,
                                     protect_tx_rows)
            for s in summary["sheets"]:
                if "skipped" in s:
                    print(f"  [skip] {s['sheet']:28s} ({s['skipped']})")
                else:
                    prot = s.get("cells_protected", 0)
                    prot_str = f" protected={prot}" if prot else ""
                    print(f"  {s['sheet']:28s} years={s['years']} "
                          f"cells_changed={s['cells_changed']}{prot_str}")
            print(f"  TOTAL cells changed: {summary['total_cells']}")
            if apply_changes and "backup" in summary:
                print(f"  Backup: {summary['backup']}")
            grand_total += summary["total_cells"]

        print(f"\nGran total de celdas {'escritas' if apply_changes else 'a escribir'}: "
              f"{grand_total}")
        if not apply_changes:
            print("[DRY-RUN] no se guardaron cambios. Usa --apply para escribir.")
    finally:
        src_wb.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
