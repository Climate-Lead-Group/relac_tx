"""
Z_AUX_update_maxcap_inv_from_tool.py

Copia TotalAnnualMaxCapacityInvestment hacia la hoja 'Secondary Techs' de
A-O_Parametrization.xlsx de cada escenario listado en SCENARIOS (de momento solo
BAU), combinando DOS fuentes:

    A) LAC_maxcap_tool.xlsx, hoja 'Export', tabla "LOGISTIC x HEADROOM ...
       saturating cap" (12 techs PWRSPV*/PWRWON* de BRA/MEX/CHL/ARG/COL/PER).
    B) LAC_maxcap_tool_complementary.xlsx, hoja 'Updated' (tabla plana con todas
       las techs PWR* y su TotalAnnualMaxCapacityInvestment).

Merge: se escriben las techs de A (con sus valores) MAS las techs de B que NO
estan en A (con valores de B). En las techs presentes en ambas, A tiene
precedencia (no se sobreescriben con B).

Alcance estricto (NO se toca nada mas):
    - Solo las tecnologias presentes en A o en B.
    - Solo el parametro 'TotalAnnualMaxCapacityInvestment'.
    - Solo las celdas de año presentes tanto en la entrada como en la salida.
    - Projection.Mode (col G) se copia desde la fila de entrada SOLO en las
      filas que recibieron al menos un valor (replica la fuente: hoy "User
      defined"). Ninguna otra fila, parametro o tecnologia se modifica.

La hoja 'Export' tiene varias tablas apiladas separadas por filas en blanco; se
selecciona la tabla LOGISTIC por su titulo (contiene LOGISTIC + HEADROOM +
SATURATING CAP, y NO GEOMETRIC/COMPOUNDING) y la lectura se detiene en la primera
fila con Tech vacio (doble defensa para no leer la tabla GEOMETRIC de abajo).

Las celdas de año de la entrada son formulas, pero se leen sus VALORES CACHEADOS
con data_only=True. Si el archivo se edito por codigo y Excel no recalculo/guardo,
los valores cacheados pueden faltar: si una celda de año llega como string (texto
de formula) el script aborta pidiendo reabrir/guardar el tool en Excel.

Usage:
    python t1_confection/Z_AUX_update_maxcap_inv_from_tool.py            # dry-run (default)
    python t1_confection/Z_AUX_update_maxcap_inv_from_tool.py --apply    # escribe (con backup)
    python t1_confection/Z_AUX_update_maxcap_inv_from_tool.py --apply --no-backup
    python t1_confection/Z_AUX_update_maxcap_inv_from_tool.py --scenario BAU
"""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

import openpyxl


HERE = Path(__file__).resolve().parent
TOOL_XLSX = HERE / 'LAC_maxcap_tool.xlsx'
TOOL_COMPLEMENTARY_XLSX = HERE / 'LAC_maxcap_tool_complementary.xlsx'
A1_OUTPUTS = HERE / 'A1_Outputs'

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
    """Ruta al A-O_Parametrization.xlsx del escenario."""
    return A1_OUTPUTS / f'A1_Outputs_{scenario}' / 'A-O_Parametrization.xlsx'


def header_map(ws, header_row: int) -> dict[str, int]:
    """{encabezado_stripped: col} para celdas no vacias de `header_row`."""
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
    """{año: col} para los encabezados que son años (int o str-digito) en rango."""
    year_cols: dict[int, int] = {}
    for col in range(1, ws.max_column + 1):
        v = ws.cell(header_row, col).value
        if isinstance(v, int) and YEAR_MIN <= v <= YEAR_MAX:
            year_cols[v] = col
        elif isinstance(v, str) and v.strip().isdigit() and YEAR_MIN <= int(v.strip()) <= YEAR_MAX:
            year_cols[int(v.strip())] = col
    return year_cols


def locate_cols(ws, header_row: int) -> dict[str, int]:
    """Columnas de Tech / Parameter / Projection.Mode por nombre de encabezado."""
    hmap = header_map(ws, header_row)
    missing = [h for h in ('Tech', 'Parameter', 'Projection.Mode') if h not in hmap]
    if missing:
        raise ValueError(
            f'Encabezados faltantes en fila {header_row}: {missing}. '
            f'Encabezados hallados: {sorted(hmap)}')
    return {'tech': hmap['Tech'], 'param': hmap['Parameter'], 'proj_mode': hmap['Projection.Mode']}


def build_row_index(ws, tech_col: int, param_col: int, header_row: int = 1):
    """{(tech, param): fila} en una pasada. Devuelve (index, duplicados)."""
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
    """Localiza la tabla LOGISTIC. Devuelve (title_row, header_row).

    Busca en la col A un titulo que contenga TODOS los tokens de
    TITLE_MUST_CONTAIN y NINGUNO de TITLE_MUST_NOT_CONTAIN (mayusculas,
    substring -> tolera el espaciado irregular y el em-dash). El header es la
    primera fila siguiente cuya col A == 'Tech.ID'.
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
    """Lee filas con Parameter == PARAM desde header_row+1. Devuelve (table, year_cols).

        table = {tech: {'proj_mode': valor_colG, 'years': {año: float}}}

    stop_at_blank=True  -> corta en la primera fila con Tech vacio (tablas
                           apiladas; tabla LOGISTIC de la fuente A).
    stop_at_blank=False -> recorre toda la hoja saltando filas con Tech vacio o
                           Parameter != PARAM (hoja dedicada de la fuente B).
    Celdas de año vacias se omiten; una celda de año string (formula no
    cacheada) -> error.
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
    """Fuente A: tabla LOGISTIC de la hoja 'Export'. Devuelve (table, title_row, header_row, years)."""
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
    """Primera fila (<= max_scan) cuya col A == 'Tech.ID' (header de tabla plana)."""
    for r in range(1, min(max_scan, ws.max_row) + 1):
        if str(ws.cell(r, 1).value).strip() == 'Tech.ID':
            return r
    raise RuntimeError('No se encontro fila de encabezado (col A == "Tech.ID").')


def read_complementary_table(path: Path, sheet: str = COMPLEMENTARY_SHEET):
    """Fuente B: tabla plana de la hoja `sheet`. Devuelve (table, header_row, years)."""
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
    """Reabre con data_only=True y verifica valores + Projection.Mode escritos."""
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
    """Normaliza para comparar Projection.Mode (None/'' equivalentes)."""
    if v is None:
        return ''
    return str(v).strip()


def write_scenario(scenario: str, table: dict, apply_changes: bool,
                   do_backup: bool = True) -> tuple[int, int, int]:
    """Escribe (o previsualiza) los valores de la tabla en el escenario.

    Devuelve (techs_actualizadas, celdas_escritas, violaciones_verificacion).
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
