"""
D4_load_dsptrn_max_cap_inv.py

Escribe TotalAnnualMaxCapacityInvestment (GW) para las tecnologias de TRANSMISION
que inyectan en el nodo 02 (no para el sumador DSPTRN) en la hoja 'Demand Techs'
de A-O_Parametrization.xlsx del escenario INV.

Motivacion:
    El sumador DSPTRN{ISO3}XX tiene capacidad residual 9999 y costo cero, asi que
    cualquier tope sobre el NUNCA es vinculante (BAU e INV daban la misma inversion
    en transmision). En su lugar, topamos directamente las tecnologias de transmision
    reales, usando como cuota lo que BAU ya construyo (NewCapacity), escalado por un
    factor < 1. Como el respaldo PWRBCK inyecta en el mismo nodo 02, cubre la diferencia:
    menos transmision, mas respaldo -> el contraste INV vs BAU que se busca, manteniendo
    factibilidad.

Regla por tech/ano Y (dos bloques):

    2023..2030  ->  celda VACIA (None): INV igual a BAU (sin tope). BAU no se topa a
                    si mismo, asi que dejar la celda sin valor hace que INV reproduzca
                    a BAU en esos anos -> PWRBCK no entra a producir temprano. Se LIMPIA
                    cualquier valor que corridas anteriores hubieran dejado.

    2031..2050  ->  cap = NewCapacity_BAU[tech, Y] * factor(Y)     [GW]
                    factor(Y) decrece linealmente de 0.90 (2031) a 0.50 (2050).
                    Donde BAU construyo 0 (o no hay dato) se escribe 0 -> prohibe
                    inversion ese ano; el respaldo PWRBCK (mismo nodo 02) cubre.

Solo se toca TotalAnnualMaxCapacityInvestment; el piso TotalAnnualMinCapacityInvestment
NO se escribe.

NewCapacity de BAU se lee de RELAC_TX_Combined_Inputs_Outputs.csv (formato largo;
columnas Scenario, YEAR, TECHNOLOGY, NewCapacity). Ese CSV contiene BAU/INV/OPT;
aqui filtramos Scenario == 'BAU'.

Usage:
    python t1_confection/D4_load_dsptrn_max_cap_inv.py --dry-run
    python t1_confection/D4_load_dsptrn_max_cap_inv.py --apply
"""
from __future__ import annotations

import argparse
import csv
import shutil
from datetime import datetime
from pathlib import Path

import openpyxl


HERE = Path(__file__).resolve().parent
COMBINED_CSV = HERE / 'RELAC_TX_Combined_Inputs_Outputs.csv'
SCENARIO_DIR = HERE / 'A1_Outputs' / 'A1_Outputs_INV'
PARAM_PATH = SCENARIO_DIR / 'A-O_Parametrization.xlsx'

SHEET = 'Demand Techs'
PARAM = 'TotalAnnualMaxCapacityInvestment'

# --- Configuracion ---------------------------------------------------------
# Bloque "igual a BAU": anos <= este quedan SIN tope (celda vacia).
EQUAL_THROUGH_YEAR = 2030

# Bloque con tope decreciente: factor lineal de CAP_START_FACTOR a CAP_END_FACTOR.
CAP_START_YEAR, CAP_START_FACTOR = 2031, 0.90
CAP_END_YEAR, CAP_END_FACTOR = 2050, 0.50

# Escenario de referencia dentro del CSV combinado.
BAU_SCENARIO = 'BAU'

# Familias de transmision que inyectan en el nodo 02 (19 paises c/u = 114 techs).
TRN_PREFIXES = ('PWRTRN', 'TRNNLI', 'TRNRPO', 'RNWTRN', 'RNWRPO', 'RNWNLI')

# Se recorren todos los anos del horizonte; 2023-2030 se vacian, 2031-2050 se topan.
YEARS = list(range(2023, 2051))
# ---------------------------------------------------------------------------


def factor_for_year(year: int) -> float:
    """Factor de tope para anos del bloque con cap (2031..2050): lineal 0.90 -> 0.50."""
    span = CAP_END_YEAR - CAP_START_YEAR
    frac = (year - CAP_START_YEAR) / span
    return CAP_START_FACTOR + (CAP_END_FACTOR - CAP_START_FACTOR) * frac


def load_bau_new_capacity(csv_path: Path) -> dict[tuple[str, int], float]:
    """Lee NewCapacity de BAU para las familias TRN del CSV combinado.

    Devuelve {(tech, year) -> new_capacity_GW} solo para valores > 0. Si hay
    filas repetidas para un (tech, year) se queda con el maximo no nulo
    (NewCapacity no se reparte entre modos/timeslices).
    """
    if not csv_path.exists():
        raise FileNotFoundError(f'No existe: {csv_path}')

    bau: dict[tuple[str, int], float] = {}
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('Scenario') != BAU_SCENARIO:
                continue
            tech = (row.get('TECHNOLOGY') or '').strip()
            if not tech.startswith(TRN_PREFIXES):
                continue
            raw_nc = (row.get('NewCapacity') or '').strip()
            if not raw_nc:
                continue
            try:
                nc = float(raw_nc)
                year = int(float(row['YEAR']))
            except (ValueError, TypeError, KeyError):
                continue
            if nc <= 0:
                continue
            key = (tech, year)
            prev = bau.get(key)
            if prev is None or nc > prev:
                bau[key] = nc
    return bau


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
    print(f'Target:    {PARAM_PATH}')
    print(f'BAU CSV:   {COMBINED_CSV}')
    print(f'Regla:     2023-{EQUAL_THROUGH_YEAR} sin tope (=BAU); '
          f'{CAP_START_YEAR}-{CAP_END_YEAR} cap = NewCapacity_BAU x factor '
          f'({CAP_START_FACTOR:.2f} -> {CAP_END_FACTOR:.2f})')

    bau = load_bau_new_capacity(COMBINED_CSV)
    techs_in_bau = sorted({t for (t, _y) in bau})
    print(f'\nNewCapacity BAU leida: {len(bau)} celdas (tech,ano) > 0 '
          f'sobre {len(techs_in_bau)} techs de transmision.')

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
    trn_rows = sorted(
        tech for (tech, param) in row_idx
        if param == PARAM and tech.startswith(TRN_PREFIXES)
    )
    if not trn_rows:
        raise ValueError(
            f'No se hallaron filas {PARAM} para prefijos {TRN_PREFIXES} en {SHEET}.'
        )

    # Aviso si BAU tiene techs que no estan en el xlsx (mapeo por string completo).
    not_in_xlsx = sorted(set(techs_in_bau) - set(trn_rows))
    if not_in_xlsx:
        print(f'  [WARN] techs con NewCapacity en BAU pero sin fila {PARAM} en xlsx: {not_in_xlsx}')

    # Escritura: 2023-2030 -> vacio (=BAU); 2031-2050 -> cap = bau * factor(y)
    print(f'\n=== WRITES ({PARAM}) ===')
    cells_cleared = 0
    cells_capped = 0
    techs_touched = 0
    sum_bau = 0.0
    sum_cap = 0.0
    for tech in trn_rows:
        row = row_idx[(tech, PARAM)]
        years_with_quota: list[int] = []  # anos 2031-2050 con NewCapacity_BAU > 0
        for y in YEARS:
            if y <= EQUAL_THROUGH_YEAR:
                ws.cell(row, year_cols[y]).value = None  # igual a BAU: sin tope
                cells_cleared += 1
                continue
            nc = bau.get((tech, y))
            cap_gw = nc * factor_for_year(y) if nc is not None else 0.0  # BAU=0 -> 0
            ws.cell(row, year_cols[y]).value = cap_gw
            cells_capped += 1
            if nc is not None:
                years_with_quota.append(y)
                sum_bau += nc
                sum_cap += cap_gw
        ws.cell(row, 7).value = 'User defined'   # Projection.Mode (col G)
        techs_touched += 1
        if years_with_quota:
            first_y, last_y = years_with_quota[0], years_with_quota[-1]
            first_v = bau[(tech, first_y)] * factor_for_year(first_y)
            last_v = bau[(tech, last_y)] * factor_for_year(last_y)
            print(f'  {tech}: {len(years_with_quota)} anos con cuota en 2031-2050 '
                  f'(resto=0) | {first_v:.4g} ({first_y}) .. {last_v:.4g} ({last_y})')
        else:
            print(f'  {tech}: sin cuota en 2031-2050 -> todos 0')

    print(f'\nTechs tocadas: {techs_touched} | celdas vaciadas (2023-{EQUAL_THROUGH_YEAR}): '
          f'{cells_cleared} | celdas con tope ({CAP_START_YEAR}-{CAP_END_YEAR}): {cells_capped}')
    print(f'Sanity (bloque con tope): suma cap = {sum_cap:.4f} GW  vs  '
          f'suma NewCapacity BAU = {sum_bau:.4f} GW '
          f'(ratio {sum_cap / sum_bau if sum_bau else 0:.4f})')

    if not apply_changes:
        print('\n[DRY-RUN] no se guardaron cambios.')
        wb.close()
        return

    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = PARAM_PATH.with_suffix(f'.backup-trn-maxinv-{ts}.xlsx')
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
    for tech in trn_rows:
        r = ri2[(tech, PARAM)]
        for y in YEARS:
            v = ws2.cell(r, yc2[y]).value
            if y <= EQUAL_THROUGH_YEAR:
                # debe quedar VACIO (=BAU, sin tope)
                if v is not None:
                    print(f'  NOTEMPTY {tech} {y}: got {v!r}, esperado vacio')
                    violations += 1
                continue
            nc = bau.get((tech, y))
            expected = nc * factor_for_year(y) if nc is not None else 0.0
            if not isinstance(v, (int, float)) or abs(v - expected) > 1e-6 * max(1.0, abs(expected)):
                print(f'  VALUE {tech} {y}: got {v!r}, expected {expected:.6f}')
                violations += 1
    wb2.close()
    print(f'Verificadas {len(trn_rows)} techs. Violations: {violations}')


if __name__ == '__main__':
    main()
