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

Regla por tech/ano Y (2026..2050):
    cap(tech, Y) = NewCapacity_BAU[tech, Y] * SCALE_FACTOR     [GW]

    - Solo se escribe donde NewCapacity_BAU > 0. Donde BAU construyo 0 (o no hay dato)
      la celda se deja VACIA -> sin tope (default ilimitado en OSeMOSYS).
    - Solo se escriben los anos 2026..2050. Las columnas historicas 2023-2025 NUNCA
      se tocan (ni valores ni Projection.Mode), quedan iguales a BAU.

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
# Perilla a calibrar: fraccion de la NewCapacity de BAU que se permite en INV.
SCALE_FACTOR = 0.5

# Escenario de referencia dentro del CSV combinado.
BAU_SCENARIO = 'BAU'

# Familias de transmision que inyectan en el nodo 02 (19 paises c/u = 114 techs).
TRN_PREFIXES = ('PWRTRN', 'TRNNLI', 'TRNRPO', 'RNWTRN', 'RNWRPO', 'RNWNLI')

# Solo se escriben 2026..2050; 2023-2025 quedan intactos (regla historica).
YEARS = list(range(2026, 2051))
# ---------------------------------------------------------------------------


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
    print(f'Factor:    {SCALE_FACTOR}  (cap = NewCapacity_BAU x {SCALE_FACTOR})')

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

    # Escritura (solo 2026..2050; NUNCA se tocan columnas 2023-2025)
    print(f'\n=== WRITES ({PARAM}) ===')
    cells_written = 0
    techs_touched = 0
    sum_bau = 0.0
    sum_cap = 0.0
    for tech in trn_rows:
        row = row_idx[(tech, PARAM)]
        wrote_any = False
        years_with_val: list[int] = []
        for y in YEARS:
            nc = bau.get((tech, y))
            if nc is None:  # BAU = 0 o sin dato -> dejar celda VACIA (sin tope)
                continue
            cap_gw = nc * SCALE_FACTOR
            ws.cell(row, year_cols[y]).value = cap_gw
            cells_written += 1
            wrote_any = True
            years_with_val.append(y)
            sum_bau += nc
            sum_cap += cap_gw
        if wrote_any:
            ws.cell(row, 7).value = 'User defined'   # Projection.Mode (col G)
            techs_touched += 1
            first_y, last_y = years_with_val[0], years_with_val[-1]
            first_v = bau[(tech, first_y)] * SCALE_FACTOR
            last_v = bau[(tech, last_y)] * SCALE_FACTOR
            print(f'  {tech}: {len(years_with_val)} anos | '
                  f'{first_v:.4g} ({first_y}) .. {last_v:.4g} ({last_y})')

    print(f'\nTechs tocadas: {techs_touched} | celdas escritas: {cells_written}')
    print(f'Sanity: suma cap = {sum_cap:.4f} GW  vs  suma NewCapacity BAU = {sum_bau:.4f} GW '
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
    wb_bak = openpyxl.load_workbook(backup, data_only=True)
    ws_bak = wb_bak[SHEET]
    yc_bak = build_year_col_map(ws_bak)
    ri_bak = build_row_index(ws_bak)

    violations = 0
    hist_years = (2023, 2024, 2025)
    for tech in trn_rows:
        r = ri2[(tech, PARAM)]
        # 1) valores escritos coinciden con bau * factor
        for y in YEARS:
            nc = bau.get((tech, y))
            v = ws2.cell(r, yc2[y]).value
            if nc is None:
                continue  # deberia seguir vacio; no exigimos None estricto
            expected = nc * SCALE_FACTOR
            if not isinstance(v, (int, float)) or abs(v - expected) > 1e-6 * max(1.0, abs(expected)):
                print(f'  VALUE {tech} {y}: got {v!r}, expected {expected:.6f}')
                violations += 1
        # 2) columnas historicas 2023-2025 intactas respecto al backup
        r_bak = ri_bak[(tech, PARAM)]
        for y in hist_years:
            if y not in yc2:
                continue
            now = ws2.cell(r, yc2[y]).value
            before = ws_bak.cell(r_bak, yc_bak[y]).value
            if now != before:
                print(f'  HIST {tech} {y}: cambio {before!r} -> {now!r} (NO debio cambiar)')
                violations += 1
    wb2.close()
    wb_bak.close()
    print(f'Verificadas {len(trn_rows)} techs. Violations: {violations}')


if __name__ == '__main__':
    main()
