"""
Test de Z_AUX_update_maxcap_inv_from_tool.py

Prueba, sobre una COPIA en sandbox del A-O_Parametrization.xlsx real de BAU (no
toca los archivos reales), que el script:
  (a) escribe en cada una de las 12 techs los valores de
      TotalAnnualMaxCapacityInvestment que realmente trae la tabla LOGISTIC,
  (b) copia Projection.Mode (col G) desde la entrada en esas filas,
  (c) NO modifica ninguna otra celda de la hoja 'Secondary Techs'
      (diff celda-a-celda antes/despues; las unicas celdas que pueden cambiar
       son (fila_tech, col_año) y (fila_tech, Projection.Mode) de las 12 techs),
  (d) encuentra las 12 techs esperadas en la salida.

Ademas valida el READER del script: lo que read_input_table() extrae coincide
con un escaneo INDEPENDIENTE del tool hecho aqui (asi un bug del reader no puede
auto-enmascararse).

Usage:
    python t1_confection/test_Z_AUX_update_maxcap_inv_from_tool.py
"""
import shutil
import sys
import tempfile
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import Z_AUX_update_maxcap_inv_from_tool as mod  # noqa: E402

TOOL = HERE / 'LAC_maxcap_tool.xlsx'
REAL_BAU = mod.A1_OUTPUTS / 'A1_Outputs_BAU' / 'A-O_Parametrization.xlsx'
TOL = 1e-9


# --------------------------------------------------------------------------- #
# Helpers independientes (no usan el reader del script)                        #
# --------------------------------------------------------------------------- #
def independent_read_tool(path):
    """Escaneo propio de la tabla LOGISTIC del tool -> {tech: {proj_mode, years}}."""
    wb = openpyxl.load_workbook(path, data_only=True)
    try:
        ws = wb['Export']
        # localizar titulo LOGISTIC (no GEOMETRIC) en col A
        title_row = None
        for r in range(1, ws.max_row + 1):
            v = ws.cell(r, 1).value
            if isinstance(v, str):
                u = v.upper()
                if 'LOGISTIC' in u and 'HEADROOM' in u and 'SATURATING CAP' in u \
                        and 'GEOMETRIC' not in u and 'COMPOUNDING' not in u:
                    title_row = r
                    break
        assert title_row is not None, 'no se hallo el titulo LOGISTIC en el tool'
        # header = primera fila con A == 'Tech.ID'
        header_row = next(
            r for r in range(title_row + 1, title_row + 6)
            if str(ws.cell(r, 1).value).strip() == 'Tech.ID')
        # columnas de año
        year_cols = {}
        for c in range(1, ws.max_column + 1):
            v = ws.cell(header_row, c).value
            if isinstance(v, int) and 2000 <= v <= 2100:
                year_cols[v] = c
        # mapear Tech / Parameter / Projection.Mode por nombre
        hdr = {str(ws.cell(header_row, c).value).strip(): c
               for c in range(1, ws.max_column + 1)
               if ws.cell(header_row, c).value is not None}
        tcol, pcol, gcol = hdr['Tech'], hdr['Parameter'], hdr['Projection.Mode']

        table = {}
        for r in range(header_row + 1, ws.max_row + 1):
            t = ws.cell(r, tcol).value
            if t is None or str(t).strip() == '':
                break
            if str(ws.cell(r, pcol).value).strip() != mod.PARAM:
                continue
            years = {}
            for y, c in year_cols.items():
                val = ws.cell(r, c).value
                if val is None or (isinstance(val, str) and val.strip() == ''):
                    continue
                assert not isinstance(val, str), f'celda de año no cacheada: {t} {y} = {val!r}'
                years[y] = float(val)
            table[str(t).strip()] = {'proj_mode': ws.cell(r, gcol).value, 'years': years}
        return table
    finally:
        wb.close()


def secondary_row_index(path):
    """{(tech, param): fila} de la hoja Secondary Techs (cols B=2, E=5)."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb['Secondary Techs']
        idx = {}
        for r, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            tech = row[1] if len(row) > 1 else None
            param = row[4] if len(row) > 4 else None
            if isinstance(tech, str) and isinstance(param, str):
                idx[(tech.strip(), param.strip())] = r
        return idx
    finally:
        wb.close()


def year_cols_secondary(path):
    """{año: col(1-based)} del header de Secondary Techs."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb['Secondary Techs']
        header = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
        year_cols = {}
        for c, v in enumerate(header, start=1):
            if isinstance(v, int) and 2000 <= v <= 2100:
                year_cols[v] = c
            elif isinstance(v, str) and v.strip().isdigit() and 2000 <= int(v.strip()) <= 2100:
                year_cols[int(v.strip())] = c
        return year_cols
    finally:
        wb.close()


def proj_mode_col_secondary(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb['Secondary Techs']
        header = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
        for c, v in enumerate(header, start=1):
            if v is not None and str(v).strip() == 'Projection.Mode':
                return c
        raise AssertionError('no se hallo columna Projection.Mode en Secondary Techs')
    finally:
        wb.close()


def snapshot_sheet(path):
    """{(fila, col): valor} de toda la hoja Secondary Techs."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb['Secondary Techs']
        snap = {}
        for r, row in enumerate(ws.iter_rows(values_only=True), start=1):
            for c, val in enumerate(row, start=1):
                snap[(r, c)] = val
        return snap
    finally:
        wb.close()


def is_empty(v):
    return v is None or (isinstance(v, str) and v.strip() == '')


def vals_equal(a, b):
    if is_empty(a) and is_empty(b):
        return True
    if is_empty(a) != is_empty(b):
        return False
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= TOL * max(1.0, abs(a), abs(b))
    return a == b


# --------------------------------------------------------------------------- #
# Test                                                                         #
# --------------------------------------------------------------------------- #
def run_tests():
    if not TOOL.exists():
        print(f'SKIP: no existe el tool {TOOL}')
        return 0
    if not REAL_BAU.exists():
        print(f'SKIP: no existe el BAU real {REAL_BAU}')
        return 0

    failures = []
    tmp = Path(tempfile.mkdtemp(prefix='zaux_maxcap_'))
    try:
        # 1) sandbox: copia del BAU real
        sandbox_bau = tmp / 'A1_Outputs' / 'A1_Outputs_BAU' / 'A-O_Parametrization.xlsx'
        sandbox_bau.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REAL_BAU, sandbox_bau)

        # 2) redirigir el script al sandbox
        mod.A1_OUTPUTS = tmp / 'A1_Outputs'

        # 3) expectativas INDEPENDIENTES desde el tool
        expected = independent_read_tool(TOOL)
        print(f'[info] tabla independiente: {len(expected)} techs, '
              f'{sum(len(v["years"]) for v in expected.values())} celdas de año.')

        # 4) TEST del reader del script: debe coincidir con el escaneo independiente
        reader_table, _, _, _ = mod.read_input_table(TOOL)
        if set(reader_table) != set(expected):
            failures.append(f'reader techs {sorted(set(reader_table) ^ set(expected))} difieren')
        for tech in set(reader_table) & set(expected):
            if mod._norm(reader_table[tech]['proj_mode']) != mod._norm(expected[tech]['proj_mode']):
                failures.append(f'reader proj_mode {tech}')
            if set(reader_table[tech]['years']) != set(expected[tech]['years']):
                failures.append(f'reader años {tech}')
            for y, v in expected[tech]['years'].items():
                gv = reader_table[tech]['years'].get(y)
                if gv is None or abs(gv - v) > TOL * max(1.0, abs(v)):
                    failures.append(f'reader valor {tech} {y}: got {gv!r} want {v}')

        # mapas de la hoja de salida (independientes del script)
        row_idx = secondary_row_index(sandbox_bau)
        ycols = year_cols_secondary(sandbox_bau)
        pmcol = proj_mode_col_secondary(sandbox_bau)

        # 5) snapshot ANTES
        before = snapshot_sheet(sandbox_bau)

        # 6) ejecutar el writer (lo que produce el script), sin backup
        mod.write_scenario('BAU', reader_table, apply_changes=True, do_backup=False)

        # 7) snapshot DESPUES
        after = snapshot_sheet(sandbox_bau)

        # 8a) cobertura: 12 techs presentes en la salida
        missing_rows = [t for t in expected if (t, mod.PARAM) not in row_idx]
        if missing_rows:
            failures.append(f'(d) techs sin fila en salida: {missing_rows}')

        # construir conjunto de celdas que SI pueden cambiar
        allowed = set()
        for tech, payload in expected.items():
            row = row_idx.get((tech, mod.PARAM))
            if row is None:
                continue
            allowed.add((row, pmcol))
            for y in payload['years']:
                if y in ycols:
                    allowed.add((row, ycols[y]))

        # 8b) valores correctos en las celdas escritas
        for tech, payload in expected.items():
            row = row_idx.get((tech, mod.PARAM))
            if row is None:
                continue
            for y, v in payload['years'].items():
                if y not in ycols:
                    continue
                got = after[(row, ycols[y])]
                if not isinstance(got, (int, float)) or abs(got - v) > TOL * max(1.0, abs(v)):
                    failures.append(f'(a) valor {tech} {y}: got {got!r} want {v}')
            # 8c) Projection.Mode copiado
            got_pm = after[(row, pmcol)]
            if mod._norm(got_pm) != mod._norm(payload['proj_mode']):
                failures.append(f'(b) proj_mode {tech}: got {got_pm!r} want {payload["proj_mode"]!r}')

        # 8d) NO interferencia: ninguna otra celda cambio
        changed_outside = 0
        for key in set(before) | set(after):
            if key in allowed:
                continue
            if not vals_equal(before.get(key), after.get(key)):
                changed_outside += 1
                if changed_outside <= 20:
                    failures.append(
                        f'(c) celda {key} cambio: {before.get(key)!r} -> {after.get(key)!r}')
        if changed_outside:
            failures.append(f'(c) TOTAL celdas cambiadas fuera del set permitido: {changed_outside}')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print('\n' + '=' * 60)
    if failures:
        print(f'TESTS FAILED: {len(failures)} problema(s):')
        for f in failures:
            print(f'  - {f}')
        return 1
    print('ALL TESTS PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(run_tests())
