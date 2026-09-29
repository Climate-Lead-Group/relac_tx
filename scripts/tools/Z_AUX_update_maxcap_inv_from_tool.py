"""Merge TotalAnnualMaxCapacityInvestment from the LAC maxcap tool into Secondary Techs.

Copies TotalAnnualMaxCapacityInvestment into the "Secondary Techs" sheet of
A-O_Parametrization.xlsx for each scenario in SCENARIOS (today only BAU is populated with
data), combining two sources: (A) LAC_maxcap_tool.xlsx, sheet "Export", the "LOGISTIC x
HEADROOM ... saturating cap" table (12 PWRSPV*/PWRWON* techs for BRA/MEX/CHL/ARG/COL/PER);
(B) LAC_maxcap_tool_complementary.xlsx, sheet "Updated" (flat table with every PWR* tech and
its TotalAnnualMaxCapacityInvestment). Merge rule: writes every tech from A (A's values) plus
the techs from B that are NOT in A (B's values); where a tech is in both, A takes precedence
and is never overwritten by B.

Strict scope (nothing else is touched): only technologies present in A or B; only the
TotalAnnualMaxCapacityInvestment parameter; only year cells present in both the source and
the target; Projection.Mode (column G) is copied from the source row only on rows that
received at least one value (mirrors the source, today "User defined") — no other row,
parameter or technology is modified.

The "Export" sheet stacks several tables separated by blank rows; the LOGISTIC table is
selected by its title (contains LOGISTIC + HEADROOM + SATURATING CAP, and NOT
GEOMETRIC/COMPOUNDING), and reading stops at the first row with an empty Tech (double
safeguard against reading the GEOMETRIC table below it).

The source year cells are formulas, but are read via their cached values (`data_only=True`).
If the tool file was edited by code and Excel never recalculated/saved it, the cached values
can be missing: if a year cell comes back as a string (formula text), the script aborts and
asks that the tool be reopened/saved in Excel.

Inputs:
    inputs/data/LAC_maxcap_tool.xlsx (sheet "Export"), LAC_maxcap_tool_complementary.xlsx
        (sheet "Updated")
Outputs:
    A-O_Parametrization.xlsx / Secondary Techs, in place — only with --apply (backup unless
        --no-backup)
Usage:
    python scripts/tools/Z_AUX_update_maxcap_inv_from_tool.py [--dry-run|--apply]
        [--no-backup] [--scenario BAU] [--tool PATH] [--complementary PATH]
    --dry-run previews without writing (default); --apply writes and creates a backup unless
    --no-backup; --scenario restricts to a comma-separated subset of SCENARIOS (default: all).
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

TOOL_XLSX = P.DATA / 'LAC_maxcap_tool.xlsx'
TOOL_COMPLEMENTARY_XLSX = P.DATA / 'LAC_maxcap_tool_complementary.xlsx'
A1_OUTPUTS = P.A1_OUTPUTS

# Escenarios a los que se PUEDE aplicar este script.
SCENARIOS = ['BAU', 'INV', 'OPT', 'VGB']

INPUT_SHEET = 'Export'              # fuente A (tabla LOGISTIC, apilada con titulo)
COMPLEMENTARY_SHEET = 'Updated'     # fuente B (tabla plana, header en su 1a fila)
TARGET_SHEET = 'Secondary Techs'
PARAM = 'TotalAnnualMaxCapacityInvestment'

# Seleccion robusta de la tabla de entrada por su titulo (col A, mayusculas).
TITLE_MUST_CONTAIN = ('LOGISTIC', 'HEADROOM', 'SATURATING CAP')
TITLE_MUST_NOT_CONTAIN = ('GEOMETRIC', 'COMPOUNDING')

# Tecnologias esperadas en la tabla LOGISTIC (solo cross-check informativo; el
# filtro real es "lo que traiga la tabla").
EXPECTED_TECHS = [
    'PWRSPVBRAXX', 'PWRWONBRAXX', 'PWRSPVMEXXX', 'PWRWONMEXXX',
    'PWRSPVCHLXX', 'PWRWONCHLXX', 'PWRSPVARGXX', 'PWRWONARGXX',
    'PWRSPVCOLXX', 'PWRWONCOLXX', 'PWRSPVPERXX', 'PWRWONPERXX',
]

YEAR_MIN, YEAR_MAX = 2000, 2100
VALUE_TOL = 1e-9  # tolerancia para la verificacion de round-trip de floats


def param_path(scenario: str) -> Path:
    """Path to the scenario's A-O_Parametrization.xlsx."""
    return A1_OUTPUTS / f'A1_Outputs_{scenario}' / 'A-O_Parametrization.xlsx'


def header_map(ws, header_row: int) -> dict[str, int]:
    """{stripped_header: col} for the non-empty cells of `header_row`."""
    hmap: dict[str, int] = {}
    for col in range(1, ws.max_column + 1):
        v = ws.cell(header_row, col).value
        if v is None:
            continue
        key = str(v).strip()
        if key and key not in hmap:
            hmap[key] = col
    return hmap


def year_cols_from_header(ws, header_row: int) -> dict[int, int]:
    """{year: col} for headers that are years (int or digit-string) within range."""
    year_cols: dict[int, int] = {}
    for col in range(1, ws.max_column + 1):
        v = ws.cell(header_row, col).value
        if isinstance(v, int) and YEAR_MIN <= v <= YEAR_MAX:
            year_cols[v] = col
        elif isinstance(v, str) and v.strip().isdigit() and YEAR_MIN <= int(v.strip()) <= YEAR_MAX:
            year_cols[int(v.strip())] = col
    return year_cols


def locate_cols(ws, header_row: int) -> dict[str, int]:
    """Tech / Parameter / Projection.Mode columns by header name."""
    hmap = header_map(ws, header_row)
    missing = [h for h in ('Tech', 'Parameter', 'Projection.Mode') if h not in hmap]
    if missing:
        raise ValueError(
            f'Encabezados faltantes en fila {header_row}: {missing}. '
            f'Encabezados hallados: {sorted(hmap)}')
    return {'tech': hmap['Tech'], 'param': hmap['Parameter'], 'proj_mode': hmap['Projection.Mode']}


def build_row_index(ws, tech_col: int, param_col: int, header_row: int = 1):
    """{(tech, param): row} in a single pass. Returns (index, duplicates)."""
    index: dict[tuple[str, str], int] = {}
    dups: list[tuple[str, str]] = []
    for r in range(header_row + 1, ws.max_row + 1):
        tech = ws.cell(r, tech_col).value
        param = ws.cell(r, param_col).value
        if isinstance(tech, str) and isinstance(param, str):
            key = (tech.strip(), param.strip())
            if key in index:
                dups.append(key)
            else:
                index[key] = r
    return index, dups


def find_logistic_table(ws) -> tuple[int, int]:
    """Locate the LOGISTIC table. Returns (title_row, header_row).

    Searches col A for a title that contains ALL tokens of TITLE_MUST_CONTAIN
    and NONE of TITLE_MUST_NOT_CONTAIN (uppercased substring match -> tolerates
    irregular spacing and the em-dash). The header is the first following row
    whose col A == 'Tech.ID'.
    """
    title_row = None
    for r in range(1, ws.max_row + 1):
        v = ws.cell(r, 1).value
        if not isinstance(v, str):
            continue
        upper = v.upper()
        if all(tok in upper for tok in TITLE_MUST_CONTAIN) and \
                not any(bad in upper for bad in TITLE_MUST_NOT_CONTAIN):
            title_row = r
            break
    if title_row is None:
        raise RuntimeError(
            f'No se encontro titulo con {TITLE_MUST_CONTAIN} '
            f'(excluyendo {TITLE_MUST_NOT_CONTAIN}) en la col A de {INPUT_SHEET!r}.')
    header_row = None
    for r in range(title_row + 1, min(title_row + 6, ws.max_row + 1)):
        if str(ws.cell(r, 1).value).strip() == 'Tech.ID':
            header_row = r
            break
    if header_row is None:
        raise RuntimeError(
            f'No se encontro la fila de encabezado (col A == "Tech.ID") '
            f'despues del titulo en fila {title_row}.')
    return title_row, header_row


def _read_param_rows(ws, header_row: int, stop_at_blank: bool, source: str):
    """Read rows with Parameter == PARAM from header_row+1. Returns (table, year_cols).

        table = {tech: {'proj_mode': col-G value, 'years': {year: float}}}

    stop_at_blank=True  -> stops at the first row with an empty Tech (stacked
                           tables; source A's LOGISTIC table).
    stop_at_blank=False -> scans the whole sheet, skipping rows with an empty
                           Tech or Parameter != PARAM (source B's dedicated sheet).
    Empty year cells are skipped; a string year cell (uncached formula) ->
    error.
    """
    cols = locate_cols(ws, header_row)
    year_cols = year_cols_from_header(ws, header_row)
    if not year_cols:
        raise ValueError(f'[{source}] Sin columnas de año en el header (fila {header_row}).')

    table: dict[str, dict] = {}
    for r in range(header_row + 1, ws.max_row + 1):
        raw_tech = ws.cell(r, cols['tech']).value
        if raw_tech is None or str(raw_tech).strip() == '':
            if stop_at_blank:
                break  # primera fila con Tech vacio termina la tabla
            continue
        tech = str(raw_tech).strip()
        param = ws.cell(r, cols['param']).value
        if param is None or str(param).strip() != PARAM:
            continue
        proj_mode = ws.cell(r, cols['proj_mode']).value
        years: dict[int, float] = {}
        for y, c in year_cols.items():
            v = ws.cell(r, c).value
            if v is None or (isinstance(v, str) and v.strip() == ''):
                continue  # celda vacia -> no se escribe
            if isinstance(v, str):
                raise ValueError(
                    f'[{source}] Celda de año no cacheada: {tech} {y} = {v!r} (texto '
                    f'de formula). Abre el archivo en Excel, recalcula y guarda.')
            years[y] = float(v)
        if tech in table:
            raise ValueError(f'[{source}] Tech duplicada: {tech}.')
        table[tech] = {'proj_mode': proj_mode, 'years': years}
    return table, year_cols


def read_input_table(path: Path):
    """Source A: LOGISTIC table from the 'Export' sheet.

    Returns (table, title_row, header_row, years).
    """
    if not path.exists():
        raise FileNotFoundError(f'No existe el tool de entrada: {path}')
    wb = openpyxl.load_workbook(path, data_only=True)
    try:
        if INPUT_SHEET not in wb.sheetnames:
            raise KeyError(f'Hoja {INPUT_SHEET!r} no encontrada. Hojas: {wb.sheetnames}')
        ws = wb[INPUT_SHEET]
        title_row, header_row = find_logistic_table(ws)
        table, year_cols = _read_param_rows(ws, header_row, stop_at_blank=True, source='A/LOGISTIC')
        if not table:
            raise ValueError(f'La tabla LOGISTIC no produjo filas con Parameter == {PARAM!r}.')
        return table, title_row, header_row, sorted(year_cols)
    finally:
        wb.close()


def find_flat_header_row(ws, max_scan: int = 10) -> int:
    """First row (<= max_scan) whose col A == 'Tech.ID' (flat table header)."""
    for r in range(1, min(max_scan, ws.max_row) + 1):
        if str(ws.cell(r, 1).value).strip() == 'Tech.ID':
            return r
    raise RuntimeError('No se encontro fila de encabezado (col A == "Tech.ID").')


def read_complementary_table(path: Path, sheet: str = COMPLEMENTARY_SHEET):
    """Source B: flat table from sheet `sheet`. Returns (table, header_row, years)."""
    if not path.exists():
        raise FileNotFoundError(f'No existe el complementario: {path}')
    wb = openpyxl.load_workbook(path, data_only=True)
    try:
        if sheet not in wb.sheetnames:
            raise KeyError(f'Hoja {sheet!r} no encontrada. Hojas: {wb.sheetnames}')
        ws = wb[sheet]
        header_row = find_flat_header_row(ws)
        table, year_cols = _read_param_rows(ws, header_row, stop_at_blank=False, source=f'B/{sheet}')
        if not table:
            raise ValueError(f'La hoja {sheet!r} no produjo filas con Parameter == {PARAM!r}.')
        return table, header_row, sorted(year_cols)
    finally:
        wb.close()


def verify_scenario(pth: Path, table: dict) -> int:
    """Reopen with data_only=True and verify the written values + Projection.Mode."""
    wb = openpyxl.load_workbook(pth, data_only=True)
    try:
        ws = wb[TARGET_SHEET]
        cols = locate_cols(ws, 1)
        year_cols = year_cols_from_header(ws, 1)
        row_index, _ = build_row_index(ws, cols['tech'], cols['param'])
        violations = 0
        for tech, payload in table.items():
            row = row_index.get((tech, PARAM))
            if row is None:
                continue
            got_pm = ws.cell(row, cols['proj_mode']).value
            want_pm = payload['proj_mode']
            if _norm(got_pm) != _norm(want_pm):
                print(f'  PROJMODE {tech}: got {got_pm!r} want {want_pm!r}')
                violations += 1
            for y, v in payload['years'].items():
                got = ws.cell(row, year_cols[y]).value
                if not isinstance(got, (int, float)) or abs(got - v) > VALUE_TOL * max(1.0, abs(v)):
                    print(f'  VALUE {tech} {y}: got {got!r} want {v}')
                    violations += 1
        return violations
    finally:
        wb.close()


def _norm(v):
    """Normalize for Projection.Mode comparison (None/'' are equivalent)."""
    if v is None:
        return ''
    return str(v).strip()


def write_scenario(scenario: str, table: dict, apply_changes: bool,
                   do_backup: bool = True) -> tuple[int, int, int]:
    """Write (or preview) the table's values into the scenario.

    Returns (techs_updated, cells_written, verification_violations).
    """
    pth = param_path(scenario)
    print(f'\n========== ESCENARIO {scenario} ==========')
    print(f'Target: {pth}')
    if not pth.exists():
        raise FileNotFoundError(f'No existe: {pth}')

    wb = openpyxl.load_workbook(pth)  # SIN data_only -> preserva formato/formulas
    try:
        if TARGET_SHEET not in wb.sheetnames:
            raise KeyError(f'Hoja {TARGET_SHEET!r} no encontrada. Hojas: {wb.sheetnames}')
        ws = wb[TARGET_SHEET]
        cols = locate_cols(ws, 1)
        year_cols = year_cols_from_header(ws, 1)
        row_index, dups = build_row_index(ws, cols['tech'], cols['param'])
        if dups:
            print(f'  [WARN] filas duplicadas (tech,param) en {TARGET_SHEET}: {sorted(set(dups))}')

        techs_updated = 0
        cells_updated = 0
        for tech in sorted(table):
            row = row_index.get((tech, PARAM))
            if row is None:
                print(f'  [WARN] {tech} {PARAM} no esta en {scenario}/{TARGET_SHEET}; omitida.')
                continue
            wrote = 0
            for y, v in table[tech]['years'].items():
                col = year_cols.get(y)
                if col is None:
                    print(f'  [WARN] año {y} ausente del header de salida; omitido para {tech}.')
                    continue
                ws.cell(row, col).value = v
                wrote += 1
            if wrote:
                ws.cell(row, cols['proj_mode']).value = table[tech]['proj_mode']
                techs_updated += 1
                cells_updated += wrote
                print(f"  {tech} (fila {row}): {wrote} celdas | "
                      f"Projection.Mode='{table[tech]['proj_mode']}'")

        print(f'\nTechs actualizadas: {techs_updated} | celdas escritas: {cells_updated}')

        if not apply_changes:
            print(f'[DRY-RUN] {scenario}: no se guardaron cambios.')
            return techs_updated, cells_updated, 0

        if do_backup:
            ts = datetime.now().strftime('%Y%m%d-%H%M%S')
            backup = pth.with_suffix(f'.backup-lacmaxcap-{ts}.xlsx')
            shutil.copy2(pth, backup)
            print(f'Backup: {backup.name}')
        wb.save(pth)
    finally:
        wb.close()

    if not apply_changes:
        return techs_updated, cells_updated, 0

    print(f'Guardado: {pth}')
    print('=== VERIFICATION ===')
    violations = verify_scenario(pth, table)
    print(f'Verificadas {techs_updated} techs. Violations: {violations}')
    return techs_updated, cells_updated, violations


def main() -> None:
    """Parse CLI args, read sources A and B, merge them and write each target scenario.

    Reads source A (LOGISTIC table, precedence on ties) and source B (Updated table, only its
    techs missing from A), merges them, then calls write_scenario() for each scenario in
    --scenario. Raises SystemExit if an unknown scenario is requested, or if --apply left any
    post-write verification violation.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--apply', action='store_true', help='escribe cambios (crea backup)')
    group.add_argument('--dry-run', action='store_true', help='preview sin escribir (default)')
    parser.add_argument(
        '--scenario', default=','.join(SCENARIOS),
        help=f'escenario(s) destino, separados por coma. Permitidos: '
             f'{",".join(SCENARIOS)}. Default: {",".join(SCENARIOS)}.')
    parser.add_argument('--no-backup', action='store_true',
                        help='no crear backup al --apply')
    parser.add_argument('--tool', type=Path, default=None,
                        help=f'ruta alterna al tool A (default: {TOOL_XLSX.name})')
    parser.add_argument('--complementary', type=Path, default=None,
                        help=f'ruta alterna al complementario B (default: {TOOL_COMPLEMENTARY_XLSX.name})')
    args = parser.parse_args()

    apply_changes = args.apply and not args.dry_run
    mode = 'APPLY' if apply_changes else 'DRY-RUN'
    scenarios = [s.strip() for s in args.scenario.split(',') if s.strip()]
    unknown = [s for s in scenarios if s not in SCENARIOS]
    if unknown:
        raise SystemExit(
            f'ERROR: escenario(s) no permitido(s): {unknown}. Permitidos: {SCENARIOS}.')

    tool = args.tool if args.tool is not None else TOOL_XLSX
    complementary = args.complementary if args.complementary is not None else TOOL_COMPLEMENTARY_XLSX
    print(f'Mode: {mode}')
    print(f'Tool A: {tool}')
    print(f'Tool B: {complementary}')
    print(f'Escenarios: {scenarios}')

    # Fuente A (LOGISTIC) -- precedencia en las coincidentes.
    table_a, title_row, header_row_a, years_a = read_input_table(tool)
    print(f'Fuente A (LOGISTIC): titulo fila {title_row}, header fila {header_row_a} | '
          f'{len(table_a)} techs | años {years_a[0]}..{years_a[-1]}.')
    missing = sorted(set(EXPECTED_TECHS) - set(table_a))
    extra = sorted(set(table_a) - set(EXPECTED_TECHS))
    if missing:
        print(f'  [WARN] techs esperadas ausentes en la fuente A: {missing}')
    if extra:
        print(f'  [WARN] techs en la fuente A no listadas como esperadas: {extra}')

    # Fuente B (Updated) -- solo se agregan las techs que NO estan en A.
    table_b, header_row_b, years_b = read_complementary_table(complementary, COMPLEMENTARY_SHEET)
    new_from_b = sorted(t for t in table_b if t not in table_a)
    print(f'Fuente B ({COMPLEMENTARY_SHEET}): header fila {header_row_b} | {len(table_b)} techs | '
          f'años {years_b[0]}..{years_b[-1]} | nuevas (no en A): {len(new_from_b)}.')

    # Merge: A entero + (B \ A). A prevalece en las coincidentes.
    merged = dict(table_a)
    for tech in new_from_b:
        merged[tech] = table_b[tech]
    print(f'Total a escribir: {len(merged)} techs ({len(table_a)} de A + {len(new_from_b)} de B).')

    total_violations = 0
    for scen in scenarios:
        _, _, v = write_scenario(scen, merged, apply_changes, do_backup=not args.no_backup)
        total_violations += v

    if apply_changes and total_violations:
        raise SystemExit(f'\nERROR: {total_violations} violaciones en verificacion.')


if __name__ == '__main__':
    main()
