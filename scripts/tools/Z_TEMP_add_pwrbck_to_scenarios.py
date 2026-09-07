"""
Z_TEMP_add_pwrbck_to_scenarios.py

Upsert PWRBCK* rows en los Excel de los escenarios A1_Outputs_{BAU,INV,OPT},
leyendo valores desde OG_csvs_inputs/. No toca filas no-PWRBCK. Filas nuevas
se agregan al final de cada hoja.

Hojas tocadas:
  A-O_Parametrization.xlsx:
    - Secondary Techs            <- CapitalCost, FixedCost
    - VariableCost               <- VariableCost
    - Fixed Horizon Parameters   <- CapacityToActivityUnit
  A-O_AR_Model_Base_Year.xlsx:
    - Secondary                  <- OutputActivityRatio (FUEL_I = None)
  A-O_AR_Projections.xlsx:
    - Secondary                  <- OutputActivityRatio (Direction = Output)

Si una fila PWRBCK ya existe en la hoja destino, sobrescribe sus valores con
los del CSV. Si no existe, se agrega al final. Projection.Mode se fija en
'User defined' en todas las hojas que tengan esa columna.

Usage:
    python t1_confection/Z_TEMP_add_pwrbck_to_scenarios.py --dry-run
    python t1_confection/Z_TEMP_add_pwrbck_to_scenarios.py --apply
    python t1_confection/Z_TEMP_add_pwrbck_to_scenarios.py --apply --scenarios BAU INV
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from A1_Pre_processing_OG_csvs import (  # noqa: E402
    assign_tech_type,
    parse_fuel_name,
    parse_tech_name,
    remap_pwrbck_output_fuel,
)

CSV_DIR = HERE / "OG_csvs_inputs"
OUT_DIR = HERE / "A1_Outputs"
SCENARIOS_DEFAULT = ["BAU", "INV", "OPT"]
PREFIX = "PWRBCK"

# Override del VariableCost para PWRBCK. El OG trae 999999 (sentinel); sobrescribimos
# por un valor razonable para que las BCK puedan despacharse a un costo finito.
# Ajustable vía CLI con --pwrbck-varcost <valor>.
PWRBCK_VARCOST_DEFAULT = 1750.0

# Parameter IDs (mismos que A1_Pre_processing_OG_csvs.py)
SECONDARY_PARAM_IDS = {
    "CapitalCost": 1,
    "FixedCost": 2,
}
VARCOST_PARAM_ID = 12
CTAU_PARAM_ID = 1  # Fixed Horizon Parameters


# ----------------------------- helpers -----------------------------

def load_pwrbck_csv(name: str) -> pd.DataFrame:
    p = CSV_DIR / f"{name}.csv"
    if not p.exists():
        print(f"  [WARN] CSV no encontrado: {p.name}")
        return pd.DataFrame()
    df = pd.read_csv(p)
    if "TECHNOLOGY" not in df.columns:
        return pd.DataFrame()
    return df[df["TECHNOLOGY"].astype(str).str.startswith(PREFIX)].copy()


def load_full_csv(name: str) -> pd.DataFrame:
    p = CSV_DIR / f"{name}.csv"
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


def build_year_col_map(ws, start_col: int) -> dict[int, int]:
    out: dict[int, int] = {}
    for col_idx, cell in enumerate(ws[1], start=1):
        if col_idx < start_col:
            continue
        v = cell.value
        if isinstance(v, int) and 2000 <= v <= 2100:
            out[v] = col_idx
        elif isinstance(v, str) and v.isdigit() and 2000 <= int(v) <= 2100:
            out[int(v)] = col_idx
    return out


def max_existing_tech_id(tech_ids: dict[str, int]) -> int:
    return max(tech_ids.values(), default=0)


# --------------------- Secondary Techs (Param) ---------------------

def upsert_secondary_techs(ws, csv_dfs: dict[str, pd.DataFrame]) -> tuple[int, int]:
    """A:Tech.ID B:Tech C:Tech.Name D:Parameter.ID E:Parameter
       F:Unit G:Projection.Mode H:Projection.Parameter I..: years"""
    year_cols = build_year_col_map(ws, start_col=9)
    if not year_cols:
        print("  [WARN] Secondary Techs: no se detectaron columnas de año.")
        return 0, 0

    idx: dict[tuple[str, str], int] = {}
    tech_ids: dict[str, int] = {}
    for r in range(2, ws.max_row + 1):
        tech = ws.cell(r, 2).value
        param = ws.cell(r, 5).value
        if isinstance(tech, str) and isinstance(param, str):
            idx[(tech.strip(), param.strip())] = r
            tid = ws.cell(r, 1).value
            if isinstance(tid, (int, float)):
                tech_ids[tech.strip()] = int(tid)

    next_id = max_existing_tech_id(tech_ids) + 1
    upd = ins = 0

    for param, df in csv_dfs.items():
        if df.empty:
            continue
        param_id = SECONDARY_PARAM_IDS[param]
        for tech, group in df.groupby("TECHNOLOGY"):
            tech = str(tech)
            if tech not in tech_ids:
                tech_ids[tech] = next_id
                next_id += 1
            key = (tech, param)
            if key in idx:
                row = idx[key]
                upd += 1
            else:
                row = ws.max_row + 1
                idx[key] = row
                ws.cell(row, 1).value = tech_ids[tech]
                ws.cell(row, 2).value = tech
                ws.cell(row, 3).value = parse_tech_name(tech)
                ws.cell(row, 4).value = param_id
                ws.cell(row, 5).value = param
                ws.cell(row, 8).value = 0
                ins += 1
            year_vals = {int(y): float(v) for y, v in zip(group["YEAR"], group["VALUE"])}
            for y, col in year_cols.items():
                if y in year_vals:
                    ws.cell(row, col).value = year_vals[y]
            ws.cell(row, 7).value = "User defined"
    return upd, ins


# --------------------------- VariableCost --------------------------

def upsert_variable_cost(ws, df: pd.DataFrame) -> tuple[int, int]:
    """A:Mode.Operation B:Tech.ID C:Tech D:Tech.Name E:Parameter.ID F:Parameter
       G:Unit H:Projection.Mode I:Projection.Parameter J..: years"""
    if df.empty:
        return 0, 0
    year_cols = build_year_col_map(ws, start_col=10)
    if not year_cols:
        print("  [WARN] VariableCost: no se detectaron columnas de año.")
        return 0, 0

    idx: dict[tuple[int, str], int] = {}
    tech_ids: dict[str, int] = {}
    for r in range(2, ws.max_row + 1):
        mode = ws.cell(r, 1).value
        tech = ws.cell(r, 3).value
        if isinstance(tech, str) and isinstance(mode, (int, float)):
            idx[(int(mode), tech.strip())] = r
            tid = ws.cell(r, 2).value
            if isinstance(tid, (int, float)):
                tech_ids[tech.strip()] = int(tid)
    next_id = max_existing_tech_id(tech_ids) + 1
    upd = ins = 0

    for (tech, mode), group in df.groupby(["TECHNOLOGY", "MODE_OF_OPERATION"]):
        tech = str(tech)
        mode = int(mode)
        if tech not in tech_ids:
            tech_ids[tech] = next_id
            next_id += 1
        key = (mode, tech)
        if key in idx:
            row = idx[key]
            upd += 1
        else:
            row = ws.max_row + 1
            idx[key] = row
            ws.cell(row, 1).value = mode
            ws.cell(row, 2).value = tech_ids[tech]
            ws.cell(row, 3).value = tech
            ws.cell(row, 4).value = parse_tech_name(tech)
            ws.cell(row, 5).value = VARCOST_PARAM_ID
            ws.cell(row, 6).value = "VariableCost"
            ws.cell(row, 9).value = 0
            ins += 1
        year_vals = {int(y): float(v) for y, v in zip(group["YEAR"], group["VALUE"])}
        for y, col in year_cols.items():
            if y in year_vals:
                ws.cell(row, col).value = year_vals[y]
        ws.cell(row, 8).value = "User defined"
    return upd, ins


# ---------------------- Fixed Horizon Parameters --------------------

def upsert_fixed_horizon(ws, df_ctau: pd.DataFrame) -> tuple[int, int]:
    """A:Tech.Type B:Tech.ID C:Tech D:Tech.Name E:Parameter.ID F:Parameter
       G:Unit H:Value (sin años)"""
    if df_ctau.empty:
        return 0, 0
    idx: dict[tuple[str, str], int] = {}
    tech_ids: dict[str, int] = {}
    for r in range(2, ws.max_row + 1):
        tech = ws.cell(r, 3).value
        param = ws.cell(r, 6).value
        if isinstance(tech, str) and isinstance(param, str):
            idx[(tech.strip(), param.strip())] = r
            tid = ws.cell(r, 2).value
            if isinstance(tid, (int, float)):
                tech_ids[tech.strip()] = int(tid)
    next_id = max_existing_tech_id(tech_ids) + 1
    upd = ins = 0

    param = "CapacityToActivityUnit"
    for _, row in df_ctau.iterrows():
        tech = str(row["TECHNOLOGY"])
        value = float(row["VALUE"])
        if tech not in tech_ids:
            tech_ids[tech] = next_id
            next_id += 1
        key = (tech, param)
        if key in idx:
            r_idx = idx[key]
            upd += 1
        else:
            r_idx = ws.max_row + 1
            idx[key] = r_idx
            ws.cell(r_idx, 1).value = assign_tech_type(tech)
            ws.cell(r_idx, 2).value = tech_ids[tech]
            ws.cell(r_idx, 3).value = tech
            ws.cell(r_idx, 4).value = parse_tech_name(tech)
            ws.cell(r_idx, 5).value = CTAU_PARAM_ID
            ws.cell(r_idx, 6).value = param
            ins += 1
        ws.cell(r_idx, 8).value = value
    return upd, ins


# ------------------ Model Base Year - Secondary --------------------

def upsert_mby_secondary(ws, df_oar: pd.DataFrame) -> tuple[int, int]:
    """A:Mode.Operation B:Fuel.I C:Fuel.I.Name D:Value.Fuel.I E:Unit.Fuel.I
       F:Tech G:Tech.Name H:Fuel.O I:Fuel.O.Name J:Value.Fuel.O K:Unit.Fuel.O"""
    if df_oar.empty:
        return 0, 0
    idx: dict[tuple[int, str], int] = {}
    for r in range(2, ws.max_row + 1):
        mode = ws.cell(r, 1).value
        tech = ws.cell(r, 6).value
        if isinstance(tech, str) and isinstance(mode, (int, float)):
            idx[(int(mode), tech.strip())] = r
    upd = ins = 0

    # Una fila por (TECHNOLOGY, MODE_OF_OPERATION) tomando el FUEL representativo
    grouped = df_oar.groupby(["TECHNOLOGY", "MODE_OF_OPERATION"], as_index=False).first()
    for _, row in grouped.iterrows():
        tech = str(row["TECHNOLOGY"])
        mode = int(row["MODE_OF_OPERATION"])
        fuel_o = row["FUEL"]
        key = (mode, tech)
        if key in idx:
            r_idx = idx[key]
            upd += 1
        else:
            r_idx = ws.max_row + 1
            idx[key] = r_idx
            ws.cell(r_idx, 1).value = mode
            ins += 1
        # PWRBCK no tiene InputActivityRatio: Fuel.I = None
        ws.cell(r_idx, 2).value = None
        ws.cell(r_idx, 3).value = None
        ws.cell(r_idx, 4).value = None
        ws.cell(r_idx, 5).value = None
        ws.cell(r_idx, 6).value = tech
        ws.cell(r_idx, 7).value = parse_tech_name(tech)
        ws.cell(r_idx, 8).value = fuel_o
        ws.cell(r_idx, 9).value = parse_fuel_name(fuel_o)
        ws.cell(r_idx, 10).value = 1
        ws.cell(r_idx, 11).value = None
    return upd, ins


# --------------------- Projections - Secondary ---------------------

def upsert_proj_secondary(ws, df_oar: pd.DataFrame) -> tuple[int, int]:
    """A:Mode.Operation B:Tech C:Tech.Name D:Fuel E:Fuel.Name F:Direction
       G:Projection.Mode H:Projection.Parameter I..: years"""
    if df_oar.empty:
        return 0, 0
    year_cols = build_year_col_map(ws, start_col=9)
    if not year_cols:
        print("  [WARN] Projections Secondary: no se detectaron columnas de año.")
        return 0, 0

    # NOTA: la clave NO incluye FUEL para que un remap de fuel (ej. ELC*01 -> ELC*02)
    # sobrescriba la fila existente en lugar de duplicarla. Asume 1 fuel por (Mode, Tech, Direction).
    idx: dict[tuple[int, str, str], int] = {}
    for r in range(2, ws.max_row + 1):
        mode = ws.cell(r, 1).value
        tech = ws.cell(r, 2).value
        direction = ws.cell(r, 6).value
        if (isinstance(tech, str) and isinstance(mode, (int, float))
                and isinstance(direction, str)):
            idx[(int(mode), tech.strip(), direction.strip())] = r
    upd = ins = 0
    direction = "Output"

    for (tech, mode, fuel), group in df_oar.groupby(["TECHNOLOGY", "MODE_OF_OPERATION", "FUEL"]):
        tech = str(tech)
        mode = int(mode)
        fuel = str(fuel)
        key = (mode, tech, direction)
        if key in idx:
            r_idx = idx[key]
            upd += 1
        else:
            r_idx = ws.max_row + 1
            idx[key] = r_idx
            ws.cell(r_idx, 1).value = mode
            ws.cell(r_idx, 2).value = tech
            ws.cell(r_idx, 3).value = parse_tech_name(tech)
            ws.cell(r_idx, 4).value = fuel
            ws.cell(r_idx, 5).value = parse_fuel_name(fuel)
            ws.cell(r_idx, 6).value = direction
            ws.cell(r_idx, 8).value = 0
            ins += 1
        year_vals = {int(y): float(v) for y, v in zip(group["YEAR"], group["VALUE"])}
        for y, col in year_cols.items():
            if y in year_vals:
                ws.cell(r_idx, col).value = year_vals[y]
        ws.cell(r_idx, 7).value = "User defined"
    return upd, ins


# ----------------------------- driver ------------------------------

def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _save_with_backup(wb, path: Path, ts: str) -> Path:
    backup = path.with_suffix(f".backup-pwrbck-{ts}.xlsx")
    shutil.copy2(path, backup)
    wb.save(path)
    return backup


def process_scenario(label: str, scen_dir: Path, apply_changes: bool, csvs: dict[str, pd.DataFrame]) -> None:
    param_path = scen_dir / "A-O_Parametrization.xlsx"
    mby_path = scen_dir / "A-O_AR_Model_Base_Year.xlsx"
    proj_path = scen_dir / "A-O_AR_Projections.xlsx"

    print(f"\n========== Scenario: {label} ==========")
    print(f"  dir: {scen_dir}")
    if not scen_dir.exists():
        print(f"  [SKIP] no existe {scen_dir}")
        return

    ts = _stamp()

    # --- A-O_Parametrization.xlsx ---
    if param_path.exists():
        wb = load_workbook(param_path)
        total = 0
        if "Secondary Techs" in wb.sheetnames:
            u, i = upsert_secondary_techs(wb["Secondary Techs"], {
                "CapitalCost": csvs["CapitalCost"],
                "FixedCost":   csvs["FixedCost"],
            })
            print(f"  [Secondary Techs]           updated={u}  inserted={i}")
            total += u + i
        else:
            print("  [SKIP] hoja 'Secondary Techs' no encontrada")
        if "VariableCost" in wb.sheetnames:
            u, i = upsert_variable_cost(wb["VariableCost"], csvs["VariableCost"])
            print(f"  [VariableCost]              updated={u}  inserted={i}")
            total += u + i
        else:
            print("  [SKIP] hoja 'VariableCost' no encontrada")
        if "Fixed Horizon Parameters" in wb.sheetnames:
            u, i = upsert_fixed_horizon(wb["Fixed Horizon Parameters"],
                                        csvs["CapacityToActivityUnit"])
            print(f"  [Fixed Horizon Parameters]  updated={u}  inserted={i}")
            total += u + i
        else:
            print("  [SKIP] hoja 'Fixed Horizon Parameters' no encontrada")

        if apply_changes and total > 0:
            backup = _save_with_backup(wb, param_path, ts)
            print(f"  guardado {param_path.name}  (backup: {backup.name})")
        wb.close()
    else:
        print(f"  [SKIP] no existe {param_path.name}")

    # --- A-O_AR_Model_Base_Year.xlsx ---
    if mby_path.exists():
        wb = load_workbook(mby_path)
        total = 0
        if "Secondary" in wb.sheetnames:
            u, i = upsert_mby_secondary(wb["Secondary"], csvs["OutputActivityRatio"])
            print(f"  [MBY/Secondary]             updated={u}  inserted={i}")
            total += u + i
        else:
            print("  [SKIP] hoja 'Secondary' (MBY) no encontrada")
        if apply_changes and total > 0:
            backup = _save_with_backup(wb, mby_path, ts)
            print(f"  guardado {mby_path.name}  (backup: {backup.name})")
        wb.close()
    else:
        print(f"  [SKIP] no existe {mby_path.name}")

    # --- A-O_AR_Projections.xlsx ---
    if proj_path.exists():
        wb = load_workbook(proj_path)
        total = 0
        if "Secondary" in wb.sheetnames:
            u, i = upsert_proj_secondary(wb["Secondary"], csvs["OutputActivityRatio"])
            print(f"  [Proj/Secondary]            updated={u}  inserted={i}")
            total += u + i
        else:
            print("  [SKIP] hoja 'Secondary' (Proj) no encontrada")
        if apply_changes and total > 0:
            backup = _save_with_backup(wb, proj_path, ts)
            print(f"  guardado {proj_path.name}  (backup: {backup.name})")
        wb.close()
    else:
        print(f"  [SKIP] no existe {proj_path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true", help="escribe cambios (crea backup)")
    g.add_argument("--dry-run", action="store_true", help="preview sin escribir (default)")
    parser.add_argument("--scenarios", nargs="+", default=SCENARIOS_DEFAULT,
                        help=f"escenarios short-code, esperan A1_Outputs/A1_Outputs_<X>/ (default: {SCENARIOS_DEFAULT})")
    parser.add_argument("--scen-paths", nargs="+", default=None,
                        help="paths explícitos a carpetas de escenario; si se usa, reemplaza a --scenarios")
    parser.add_argument("--pwrbck-varcost", type=float, default=PWRBCK_VARCOST_DEFAULT,
                        help=f"override VariableCost para PWRBCK (default: {PWRBCK_VARCOST_DEFAULT})")
    args = parser.parse_args()

    apply_changes = args.apply and not args.dry_run
    mode = "APPLY" if apply_changes else "DRY-RUN"
    print(f"Mode: {mode}")
    print(f"CSV dir:    {CSV_DIR}")
    print(f"Output dir: {OUT_DIR}")

    csvs = {
        "CapitalCost":            load_pwrbck_csv("CapitalCost"),
        "FixedCost":              load_pwrbck_csv("FixedCost"),
        "VariableCost":           load_pwrbck_csv("VariableCost"),
        "CapacityToActivityUnit": load_pwrbck_csv("CapacityToActivityUnit"),
        "OutputActivityRatio":    load_pwrbck_csv("OutputActivityRatio"),
    }
    print("\nPWRBCK filas leídas por CSV:")
    for name, df in csvs.items():
        techs = df["TECHNOLOGY"].nunique() if not df.empty else 0
        print(f"  {name:24s} rows={len(df):5d}  techs={techs}")

    # Override del VariableCost para PWRBCK (el OG trae 999999 como sentinel).
    if not csvs["VariableCost"].empty:
        csvs["VariableCost"]["VALUE"] = float(args.pwrbck_varcost)
        print(f"\n[Info] VariableCost PWRBCK sobrescrito a {args.pwrbck_varcost} "
              f"({len(csvs['VariableCost'])} filas).")

    # Aplica remap opcional PWRBCK OutputActivityRatio FUEL ELC*01 -> ELC*02
    # (no-op si pwrbck_output_to_elc02 está en false en Config_region_consolidation.yaml).
    # Se pasa InputActivityRatio completo para validar que ELC*02 exista downstream.
    remap_ctx = {
        "OutputActivityRatio": csvs["OutputActivityRatio"],
        "InputActivityRatio":  load_full_csv("InputActivityRatio"),
    }
    remap_pwrbck_output_fuel(remap_ctx)
    csvs["OutputActivityRatio"] = remap_ctx["OutputActivityRatio"]

    if args.scen_paths:
        targets = [(Path(p).resolve().name, Path(p).resolve()) for p in args.scen_paths]
    else:
        targets = [(scen, OUT_DIR / f"A1_Outputs_{scen}") for scen in args.scenarios]

    for label, scen_dir in targets:
        process_scenario(label, scen_dir, apply_changes, csvs)

    if not apply_changes:
        print("\n[DRY-RUN] no se guardaron cambios. Usar --apply para escribir.")


if __name__ == "__main__":
    main()
