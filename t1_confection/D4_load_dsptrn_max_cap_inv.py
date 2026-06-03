"""
D4_load_dsptrn_max_cap_inv.py

Carga TotalAnnualMaxCapacityInvestment (GW) para los 19 DSPTRN{ISO3}XX
en la hoja 'Demand Techs' de A-O_Parametrization.xlsx (escenario INV).

Formula por ano Y (2026..2050):
    budget(Y)         = 3.0                              [billones USD, flat]
    capacity(Y, pais) = budget(Y) / unit_cost[pais]     [GW]

El presupuesto quedo PLANO en 3.0 billones (3000 millones) para todos los anos,
sin incremento anual. Ademas solo se escriben los anos 2026..2050: los anos
historicos 2023-2025 se dejan intactos (iguales a BAU, ver
sync_historical_from_bau.py).

unit_cost[pais] se lee de CAPEX.xlsx (hoja Hoja1, col A=Pais, col B=CAPEX
en MUSD/GW, segun especificacion del usuario).

Tras escribir los valores, fija la columna Projection.Mode (col G) en
'User defined' (antes estaba en 'EMPTY').

Usage:
    python t1_confection/D4_load_dsptrn_max_cap_inv.py --dry-run
    python t1_confection/D4_load_dsptrn_max_cap_inv.py --apply
"""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

import openpyxl


HERE = Path(__file__).resolve().parent
SCENARIO_DIR = HERE / 'A1_Outputs' / 'A1_Outputs_INV'
PARAM_PATH = SCENARIO_DIR / 'A-O_Parametrization.xlsx'
CAPEX_PATH = SCENARIO_DIR / 'CAPEX.xlsx'

SHEET = 'Demand Techs'
PARAM = 'TotalAnnualMaxCapacityInvestment'

BASE_YEAR = 2022          # ano base fuera del horizonte
BASE_BUDGET = 3.0         # billones USD, presupuesto PLANO (antes 3.3)
ANNUAL_INCREMENT = 0.0    # billones USD/ano — sin incremento (antes 0.1)
# Solo se escriben 2026..2050; 2023-2025 quedan iguales a BAU (regla historica).
YEARS = list(range(2026, 2051))

# Mapeo nombre (como aparece en CAPEX.xlsx col A) -> ISO-3
COUNTRY_TO_ISO3 = {
    'Bolivia': 'BOL',
    'Colombia': 'COL',
    'Panamá': 'PAN',
    'Paraguay': 'PRY',
    'RD': 'DOM',
    'Chile': 'CHL',
    'CR': 'CRI',
    'El Salvador': 'SLV',
    'Honduras': 'HND',
    'Perú': 'PER',
    'Barbados': 'BRB',
    'Ecuador': 'ECU',
    'Guatemala': 'GTM',
    'Haití': 'HTI',
    'Nicaragua': 'NIC',
    'Uruguay': 'URY',
    'Brasil': 'BRA',
    'Argentina': 'ARG',
    'México': 'MEX',
}


def budget_for_year(year: int) -> float:
    return BASE_BUDGET + ANNUAL_INCREMENT * (year - BASE_YEAR)


def load_unit_costs(path: Path) -> dict[str, float]:
    """Lee col A (Pais) y col B (CAPEX) de CAPEX.xlsx y devuelve dict iso3 -> MUSD/GW."""
    if not path.exists():
        raise FileNotFoundError(f'No existe: {path}')

    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb['Hoja1']

    costs: dict[str, float] = {}
    unknown_names: list[str] = []
    for r in range(2, ws.max_row + 1):
        name = ws.cell(r, 1).value
        val = ws.cell(r, 2).value
        if not isinstance(name, str) or not isinstance(val, (int, float)):
            continue
        name = name.strip()
        iso3 = COUNTRY_TO_ISO3.get(name)
        if iso3 is None:
            unknown_names.append(name)
            continue
        costs[iso3] = float(val)
    wb.close()

    if unknown_names:
        print(f'  [WARN] nombres en CAPEX.xlsx sin mapeo ISO-3: {unknown_names}')
    missing = [iso3 for iso3 in COUNTRY_TO_ISO3.values() if iso3 not in costs]
    if missing:
        raise ValueError(f'Paises sin costo unitario en CAPEX.xlsx: {missing}')
    return costs


def build_year_col_map(ws) -> dict[int, int]:
    year_cols: dict[int, int] = {}
    for col_idx, cell in enumerate(ws[1], start=1):
        v = cell.value
        if isinstance(v, int) and 2000 <= v <= 2100:
            year_cols[v] = col_idx
        elif isinstance(v, str) and v.isdigit() and 2000 <= int(v) <= 2100:
            year_cols[int(v)] = col_idx
    return year_cols


def build_row_index(ws) -> dict[tuple[str, str], int]:
    index: dict[tuple[str, str], int] = {}
    for r in range(2, ws.max_row + 1):
        tech = ws.cell(r, 2).value
        param = ws.cell(r, 5).value
        if isinstance(tech, str) and isinstance(param, str):
            index[(tech.strip(), param.strip())] = r
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--apply', action='store_true', help='escribe cambios (crea backup)')
    group.add_argument('--dry-run', action='store_true', help='preview sin escribir (default)')
    args = parser.parse_args()

    apply_changes = args.apply and not args.dry_run
    mode = 'APPLY' if apply_changes else 'DRY-RUN'
    print(f'Mode: {mode}')
    print(f'Target:     {PARAM_PATH}')
    print(f'Unit costs: {CAPEX_PATH}')

    unit_costs = load_unit_costs(CAPEX_PATH)
    print(f'\nUnit costs leidos ({len(unit_costs)} paises):')
    for iso3 in sorted(unit_costs):
        print(f'  {iso3}: {unit_costs[iso3]:.4f}')

    if not PARAM_PATH.exists():
        raise FileNotFoundError(f'No existe: {PARAM_PATH}')

    wb = openpyxl.load_workbook(PARAM_PATH)
    if SHEET not in wb.sheetnames:
        raise KeyError(f'Hoja {SHEET!r} no encontrada. Hojas: {wb.sheetnames}')
    ws = wb[SHEET]

    year_cols = build_year_col_map(ws)
    missing_yrs = [y for y in YEARS if y not in year_cols]
    if missing_yrs:
        raise ValueError(f'Anos faltantes en header de {SHEET}: {missing_yrs}')

    row_idx = build_row_index(ws)
    missing_rows = []
    for iso3 in unit_costs:
        tech_code = f'DSPTRN{iso3}XX'
        if (tech_code, PARAM) not in row_idx:
            missing_rows.append(tech_code)
    if missing_rows:
        raise ValueError(
            f'Faltan filas {PARAM} en {SHEET} para: {missing_rows}. '
            f'Corre Z_TEMP_add_max_cap_inv_to_demand_techs.py --apply primero.'
        )

    # Escribir valores
    print(f'\n=== WRITES ({PARAM}) ===')
    for iso3 in sorted(unit_costs):
        tech_code = f'DSPTRN{iso3}XX'
        row = row_idx[(tech_code, PARAM)]
        uc = unit_costs[iso3]
        row_vals = []
        for y in YEARS:
            col = year_cols[y]
            cap_gw = budget_for_year(y) / uc
            ws.cell(row, col).value = cap_gw
            row_vals.append(cap_gw)
        # Projection.Mode -> 'User defined' (col G)
        ws.cell(row, 7).value = 'User defined'
        sample = f'{row_vals[0]:.4g} ({YEARS[0]}) .. {row_vals[-1]:.4g} ({YEARS[-1]})'
        print(f'  {tech_code} (uc={uc:.4f}): {sample}')

    if not apply_changes:
        print('\n[DRY-RUN] no se guardaron cambios.')
        wb.close()
        return

    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = PARAM_PATH.with_suffix(f'.backup-dsptrn-maxinv-{ts}.xlsx')
    shutil.copy2(PARAM_PATH, backup)
    print(f'\nBackup: {backup.name}')
    wb.save(PARAM_PATH)
    wb.close()
    print(f'Guardado: {PARAM_PATH}')

    # Verificacion
    print('\n=== VERIFICATION ===')
    wb2 = openpyxl.load_workbook(PARAM_PATH, data_only=True)
    ws2 = wb2[SHEET]
    yc2 = build_year_col_map(ws2)
    ri2 = build_row_index(ws2)
    violations = 0
    for iso3 in unit_costs:
        tech_code = f'DSPTRN{iso3}XX'
        r = ri2[(tech_code, PARAM)]
        for y in YEARS:
            v = ws2.cell(r, yc2[y]).value
            if not isinstance(v, (int, float)):
                print(f'  MISSING {tech_code} {y}: {v!r}')
                violations += 1
        pm = ws2.cell(r, 7).value
        if pm != 'User defined':
            print(f'  MODE {tech_code}: {pm!r} (esperado User defined)')
            violations += 1
    wb2.close()
    total_checked = len(unit_costs) * (len(YEARS) + 1)
    print(f'Checked {total_checked} celdas. Violations: {violations}')


if __name__ == '__main__':
    main()
