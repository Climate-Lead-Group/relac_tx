"""
Set TRN Interconnection Activity Limits from Bilateral Flow Data

Reads estimated bilateral energy flows from flujos_energia_estimados_optimizacion.xlsx
and writes Lower/Upper activity limits into Secondary_Techs_Editor.xlsx.

- LowerLimit = Flujo Total (PJ) * 0.95  (-5%)
- UpperLimit = Flujo Total (PJ) * 1.05  (+5%)
- Years 2023-2025: actual flow data
- Years 2026-2050: flat projection from 2025 value

Usage:
    python scripts/tools/Z_AUX_D1b_set_trn_limits_from_flows.py
"""
import argparse
import openpyxl
import sys
import unicodedata
from openpyxl.formula.translate import Translator
from openpyxl.utils import get_column_letter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> scripts/
from common import relac_paths as P

# ============================================================================
# CONSTANTS
# ============================================================================

GWH_TO_PJ = 0.0036  # 1 GWh = 0.0036 PJ

LOWER_LIMIT_FACTOR = 0.95  # -5%
UPPER_LIMIT_FACTOR = 1.05  # +5%

FLAT_PROJECTION_BASE_YEAR = 2025
EDITOR_FIRST_YEAR = 2023
EDITOR_LAST_YEAR = 2050

# Country name mapping (Spanish names with accents → 3-letter model codes)
# Same as D2_update_secondary_techs.py lines 19-40
COUNTRY_NAME_TO_CODE = {
    'Argentina': 'ARG',
    'Bolivia': 'BOL',
    'Brasil': 'BRA',
    'Chile': 'CHL',
    'Colombia': 'COL',
    'Costa Rica': 'CRI',
    'Ecuador': 'ECU',
    'El Salvador': 'SLV',
    'Guatemala': 'GTM',
    'Haiti': 'HTI',
    'Honduras': 'HND',
    'Mexico': 'MEX',
    'Nicaragua': 'NIC',
    'Panama': 'PAN',
    'Paraguay': 'PRY',
    'Peru': 'PER',
    'Republica Dominicana': 'DOM',
    'Uruguay': 'URY',
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def strip_accents(text):
    """Remove accents from text (e.g., 'México' → 'Mexico')"""
    nfkd = unicodedata.normalize('NFKD', str(text))
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def read_flow_data(flow_file_path):
    """
    Read bilateral energy flow data from the source Excel.

    Returns:
        dict: {frozenset({code_a, code_b}): {year: flujo_total_gwh}}
    """
    print(f"Reading flow data from: {flow_file_path.name}")

    wb = openpyxl.load_workbook(flow_file_path, data_only=True)

    # Find the sheet (handle accent in name)
    target_sheet = None
    for name in wb.sheetnames:
        if strip_accents(name) == 'Flujos por Interconexion':
            target_sheet = name
            break

    if not target_sheet:
        wb.close()
        raise ValueError(f"Sheet 'Flujos por Interconexión' not found. Available: {wb.sheetnames}")

    ws = wb[target_sheet]

    # Parse header row to find column indices
    headers = {}
    for col_idx in range(1, ws.max_column + 1):
        header = ws.cell(1, col_idx).value
        if header:
            headers[strip_accents(str(header).strip())] = col_idx

    year_col = headers.get('Ano')
    pais_a_col = headers.get('Pais A')
    pais_b_col = headers.get('Pais B')
    flujo_total_col = headers.get('Flujo Total (GWh)')

    if not all([year_col, pais_a_col, pais_b_col, flujo_total_col]):
        wb.close()
        raise ValueError(f"Missing required columns. Found headers: {list(headers.keys())}")

    # Read flow data
    flow_data = {}  # {frozenset({code_a, code_b}): {year: flujo_gwh}}

    for row_idx in range(2, ws.max_row + 1):
        year_val = ws.cell(row_idx, year_col).value
        pais_a = ws.cell(row_idx, pais_a_col).value
        pais_b = ws.cell(row_idx, pais_b_col).value
        flujo = ws.cell(row_idx, flujo_total_col).value

        if year_val is None or flujo is None or pais_a is None or pais_b is None:
            continue

        pais_a_clean = strip_accents(str(pais_a).strip())
        pais_b_clean = strip_accents(str(pais_b).strip())

        code_a = COUNTRY_NAME_TO_CODE.get(pais_a_clean)
        code_b = COUNTRY_NAME_TO_CODE.get(pais_b_clean)

        if not code_a:
            print(f"  WARNING: Unknown country '{pais_a}' (cleaned: '{pais_a_clean}')")
            continue
        if not code_b:
            print(f"  WARNING: Unknown country '{pais_b}' (cleaned: '{pais_b_clean}')")
            continue

        pair = frozenset({code_a, code_b})
        if pair not in flow_data:
            flow_data[pair] = {}
        flow_data[pair][int(year_val)] = float(flujo)

    wb.close()

    print(f"  Found {len(flow_data)} country pairs")
    for pair, years in sorted(flow_data.items(), key=lambda x: sorted(x[0])):
        codes = sorted(pair)
        available_years = sorted(years.keys())
        print(f"  {codes[0]}-{codes[1]}: years {available_years[0]}-{available_years[-1]}, "
              f"2025 flow = {years.get(2025, 'N/A')} GWh")

    return flow_data


def _build_pair_to_tech_map(wb):
    """Build {frozenset({code_a, code_b}): (tech_code, tech_name, origin)} from _TechMapping."""
    if '_TechMapping' not in wb.sheetnames:
        raise ValueError("'_TechMapping' sheet not found in Editor workbook")
    ws = wb['_TechMapping']
    pair_to_tech = {}
    for row_idx in range(2, ws.max_row + 1):
        tech_name = ws.cell(row_idx, 1).value
        tech_code = ws.cell(row_idx, 2).value
        if not tech_code or not tech_name:
            continue
        tc = str(tech_code).strip().upper()
        if tc.startswith('TRN') and len(tc) >= 13:
            origin = tc[3:6]
            dest = tc[8:11]
            pair_to_tech[frozenset({origin, dest})] = (tc, str(tech_name).strip(), origin)
    return pair_to_tech


PARAMS = [
    ('TotalTechnologyAnnualActivityLowerLimit', LOWER_LIMIT_FACTOR, 'Lower'),
    ('TotalTechnologyAnnualActivityUpperLimit', UPPER_LIMIT_FACTOR, 'Upper'),
]


def _identity_key(scenario, country, tech_name, tech_code, parameter):
    """Normalized identity tuple for detecting existing Editor rows."""
    return (
        str(scenario).strip().upper() if scenario else '',
        str(country).strip().upper() if country else '',
        str(tech_name).strip() if tech_name else '',
        str(tech_code).strip().upper() if tech_code else '',
        str(parameter).strip() if parameter else '',
    )


def fill_editor(editor_path, flow_data, scenarios=None):
    """
    Upsert TRN interconnection activity limit rows into the Editor sheet.

    For each (scenario, pair, parameter) combination:
      - If a row with matching identity (columns A-E: Scenario, Country, Tech.Name,
        Tech, Parameter) already exists, the year values are updated in place.
        A VLOOKUP formula in column D is preserved.
      - Otherwise, the new row is inserted at the top of the sheet (row 2) and
        all existing rows are shifted down. VLOOKUP formulas in shifted cells
        are rewritten via openpyxl's formula Translator so relative references
        stay pointed at their own row.

    Args:
        editor_path: Path to Secondary_Techs_Editor.xlsx
        flow_data: {frozenset({code_a, code_b}): {year: flujo_gwh}}
        scenarios: None | str | list[str]
            - None (default): write each row with Scenario="ALL"
            - str or list: write one row per specified scenario (e.g. "BAU" or ["BAU","NDC"])
    """
    # Normalize scenarios argument
    if scenarios is None:
        scenarios = ["ALL"]
    elif isinstance(scenarios, str):
        scenarios = [s.strip() for s in scenarios.split(',') if s.strip()] or ["ALL"]
    else:
        scenarios = [str(s).strip() for s in scenarios if str(s).strip()]

    print(f"\nProcessing Editor: {editor_path.name}")
    print(f"  Target scenarios: {scenarios}")

    # --- Pass 1: Read _TechMapping, year columns, and existing identity index ---
    wb_read = openpyxl.load_workbook(editor_path, data_only=True)
    pair_to_tech = _build_pair_to_tech_map(wb_read)

    ws_read = wb_read['Editor']
    year_col_map = {}
    for col_idx in range(1, ws_read.max_column + 1):
        header = ws_read.cell(1, col_idx).value
        if header and str(header).strip().isdigit():
            year = int(str(header).strip())
            if EDITOR_FIRST_YEAR <= year <= EDITOR_LAST_YEAR:
                year_col_map[year] = col_idx

    # Build identity → row_idx map from existing rows (D resolved via VLOOKUP)
    identity_to_row = {}
    for row_idx in range(2, ws_read.max_row + 1):
        a = ws_read.cell(row_idx, 1).value
        b = ws_read.cell(row_idx, 2).value
        c = ws_read.cell(row_idx, 3).value
        d = ws_read.cell(row_idx, 4).value
        e = ws_read.cell(row_idx, 5).value
        if not (a and d and e):
            continue
        key = _identity_key(a, b, c, d, e)
        identity_to_row.setdefault(key, row_idx)
    wb_read.close()

    print(f"  Year columns: {min(year_col_map)} to {max(year_col_map)} ({len(year_col_map)} years)")
    print(f"  TRN tech mappings loaded: {len(pair_to_tech)}")
    print(f"  Existing rows indexed: {len(identity_to_row)}")

    # --- Pass 2: Build proposed rows and classify into update / insert ---
    unmatched_pairs = []
    to_update = []  # list of (row_idx, proposed_dict)
    to_insert = []  # list of proposed_dict

    for pair, pair_flows in sorted(flow_data.items(), key=lambda kv: sorted(kv[0])):
        if pair not in pair_to_tech:
            unmatched_pairs.append(sorted(pair))
            continue
        tech_code, tech_name, origin_country = pair_to_tech[pair]
        base_year = max(pair_flows.keys())
        base_gwh = pair_flows[base_year]

        for scenario in scenarios:
            for parameter, factor, _ in PARAMS:
                year_values = {}
                for year in range(EDITOR_FIRST_YEAR, EDITOR_LAST_YEAR + 1):
                    if year not in year_col_map:
                        continue
                    gwh = pair_flows.get(year, base_gwh)
                    year_values[year] = round(gwh * GWH_TO_PJ * factor, 6)
                proposed = {
                    'scenario': scenario,
                    'country': origin_country,
                    'tech_name': tech_name,
                    'tech_code': tech_code,
                    'parameter': parameter,
                    'year_values': year_values,
                }
                key = _identity_key(scenario, origin_country, tech_name, tech_code, parameter)
                if key in identity_to_row:
                    to_update.append((identity_to_row[key], proposed))
                else:
                    to_insert.append(proposed)

    # --- Pass 3: Open writable ---
    wb_write = openpyxl.load_workbook(editor_path)
    ws_write = wb_write['Editor']
    max_col = ws_write.max_column

    # Step A: Apply updates in place (preserve VLOOKUP in D if present)
    updates_applied = 0
    for row_idx, pr in to_update:
        ws_write.cell(row_idx, 1).value = pr['scenario']
        ws_write.cell(row_idx, 2).value = pr['country']
        ws_write.cell(row_idx, 3).value = pr['tech_name']
        existing_d = ws_write.cell(row_idx, 4).value
        if not (isinstance(existing_d, str) and existing_d.startswith('=')):
            ws_write.cell(row_idx, 4).value = pr['tech_code']
        ws_write.cell(row_idx, 5).value = pr['parameter']
        for year, value in pr['year_values'].items():
            ws_write.cell(row_idx, year_col_map[year]).value = value
        updates_applied += 1

    # Step B: Insert new rows at the top with manual shift
    rows_inserted = 0
    rows_shifted = 0
    formulas_rewritten = 0
    if to_insert:
        N = len(to_insert)

        # Snapshot existing rows 2..max_row (values + formulas)
        original_max_row = ws_write.max_row
        snapshot = []  # list of (row_idx, [cell_value_or_formula, ...])
        for r in range(2, original_max_row + 1):
            row_cells = [ws_write.cell(r, c).value for c in range(1, max_col + 1)]
            if any(v is not None for v in row_cells):
                snapshot.append((r, row_cells))

        # Clear existing data range (rows 2 to original_max_row, all columns up to max_col)
        for r in range(2, original_max_row + 1):
            for c in range(1, max_col + 1):
                ws_write.cell(r, c).value = None

        # Write new inserted rows at rows 2..N+1
        for i, pr in enumerate(to_insert):
            new_row = 2 + i
            ws_write.cell(new_row, 1).value = pr['scenario']
            ws_write.cell(new_row, 2).value = pr['country']
            ws_write.cell(new_row, 3).value = pr['tech_name']
            ws_write.cell(new_row, 4).value = pr['tech_code']
            ws_write.cell(new_row, 5).value = pr['parameter']
            for year, value in pr['year_values'].items():
                ws_write.cell(new_row, year_col_map[year]).value = value
            rows_inserted += 1

        # Write shifted existing rows (each originally at row r_old → now at r_old + N)
        for r_old, row_cells in snapshot:
            r_new = r_old + N
            for c, value in enumerate(row_cells, start=1):
                if value is None:
                    continue
                if isinstance(value, str) and value.startswith('='):
                    col_letter = get_column_letter(c)
                    orig_coord = f'{col_letter}{r_old}'
                    new_coord = f'{col_letter}{r_new}'
                    value = Translator(value, origin=orig_coord).translate_formula(new_coord)
                    formulas_rewritten += 1
                ws_write.cell(r_new, c).value = value
            rows_shifted += 1

    wb_write.save(editor_path)
    wb_write.close()

    print(f"  Updates in place: {updates_applied}")
    print(f"  Inserted at top: {rows_inserted}")
    print(f"  Shifted existing rows: {rows_shifted} ({formulas_rewritten} formulas rewritten)")
    if unmatched_pairs:
        print(f"  WARNING: {len(unmatched_pairs)} pair(s) without matching _TechMapping entry:")
        for p in unmatched_pairs:
            print(f"    - {'-'.join(p)}")


def fill_trn_sheet(editor_path, flow_data, scenarios=None, sheet_name='TRN_Flow_Limits'):
    """
    Write TRN activity limits to a DEDICATED sheet (not the Editor sheet).

    Column layout matches the Editor sheet so D2's read_editor_file() can
    process it identically:
        Scenario | Country | Tech.Name | Tech | Parameter | 2023 | ... | 2050

    For each country pair in flow_data, writes rows for both directions
    (A->B and B->A) × 2 parameters (Lower/Upper) × N scenarios.

    On each run, the sheet's data rows (rows 2+) are cleared and rewritten,
    so the Editor sheet's manual edits are never touched.

    Args:
        editor_path: Path to Secondary_Techs_Editor.xlsx
        flow_data: {frozenset({code_a, code_b}): {year: gwh}} (from read_flow_data)
        scenarios: None | str | list[str]
            - None (default): one row per pair/param with Scenario="ALL"
            - str or list: one row per specified scenario
        sheet_name: Target sheet name (default 'TRN_Flow_Limits')
    """
    # Normalize scenarios argument
    if scenarios is None:
        scenarios = ["ALL"]
    elif isinstance(scenarios, str):
        scenarios = [s.strip() for s in scenarios.split(',') if s.strip()] or ["ALL"]
    else:
        scenarios = [str(s).strip() for s in scenarios if str(s).strip()]

    print(f"\nWriting TRN limits to sheet '{sheet_name}' in: {editor_path.name}")
    print(f"  Target scenarios: {scenarios}")

    wb = openpyxl.load_workbook(editor_path)

    # Build TRN pair → tech mapping from _TechMapping (reuses existing helper)
    try:
        pair_to_tech = _build_pair_to_tech_map(wb)
    except ValueError as e:
        wb.close()
        raise

    # Create or reset the target sheet
    if sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        # Clear all data rows (keep header for inspection but we'll rewrite it)
        if ws.max_row > 1:
            ws.delete_rows(1, ws.max_row)
    else:
        ws = wb.create_sheet(sheet_name)

    # Write header row (same layout as Editor sheet)
    headers = ['Scenario', 'Country', 'Tech.Name', 'Tech', 'Parameter'] + \
              [str(y) for y in range(EDITOR_FIRST_YEAR, EDITOR_LAST_YEAR + 1)]
    for col_idx, header in enumerate(headers, 1):
        ws.cell(1, col_idx, header)

    # Build year column map (relative to this sheet's header)
    year_col_map = {
        year: 6 + (year - EDITOR_FIRST_YEAR)
        for year in range(EDITOR_FIRST_YEAR, EDITOR_LAST_YEAR + 1)
    }

    # Write data rows
    unmatched_pairs = []
    row_idx = 2
    rows_written = 0

    for pair, pair_flows in sorted(flow_data.items(), key=lambda kv: sorted(kv[0])):
        if pair not in pair_to_tech:
            unmatched_pairs.append(sorted(pair))
            continue
        tech_code, tech_name, origin_country = pair_to_tech[pair]
        base_year = max(pair_flows.keys())
        base_gwh = pair_flows[base_year]

        for scenario in scenarios:
            for parameter, factor, _ in PARAMS:
                ws.cell(row_idx, 1, scenario)
                ws.cell(row_idx, 2, origin_country)
                ws.cell(row_idx, 3, tech_name)
                ws.cell(row_idx, 4, tech_code)
                ws.cell(row_idx, 5, parameter)

                for year in range(EDITOR_FIRST_YEAR, EDITOR_LAST_YEAR + 1):
                    gwh = pair_flows.get(year, base_gwh)
                    limit_value = round(gwh * GWH_TO_PJ * factor, 6)
                    ws.cell(row_idx, year_col_map[year], limit_value)

                row_idx += 1
                rows_written += 1

    wb.save(editor_path)
    wb.close()

    print(f"  Wrote {rows_written} rows to '{sheet_name}' (Editor sheet untouched)")
    if unmatched_pairs:
        print(f"  WARNING: {len(unmatched_pairs)} pair(s) without matching _TechMapping entry:")
        for p in unmatched_pairs:
            print(f"    - {'-'.join(p)}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Pre-populate TRN interconnection activity limits in Secondary_Techs_Editor.xlsx from bilateral flow data."
    )
    parser.add_argument(
        '--scenarios',
        default='ALL',
        help='Comma-separated list of scenarios to write rows for (default: "ALL" = applies to all scenarios). '
             'Example: --scenarios BAU,NDC'
    )
    args = parser.parse_args()

    scenarios = [s.strip() for s in args.scenarios.split(',') if s.strip()] or ["ALL"]

    flow_file = P.MATRIZ_BALANCE / "flujos_energia_estimados_optimizacion.xlsx"
    editor_file = P.DATA / "Secondary_Techs_Editor.xlsx"

    # Validate files exist
    if not flow_file.exists():
        print(f"ERROR: Flow data file not found: {flow_file}")
        return
    if not editor_file.exists():
        print(f"ERROR: Editor file not found: {editor_file}")
        return

    print("=" * 80)
    print("D1b: Set TRN Interconnection Activity Limits from Flow Data")
    print("=" * 80)
    print(f"  Source: {flow_file.name}")
    print(f"  Target: {editor_file.name}")
    print(f"  Scenarios: {scenarios}")
    print(f"  Conversion: GWh × {GWH_TO_PJ} = PJ")
    print(f"  Lower factor: {LOWER_LIMIT_FACTOR} (-5%)")
    print(f"  Upper factor: {UPPER_LIMIT_FACTOR} (+5%)")
    print(f"  Flat projection from: {FLAT_PROJECTION_BASE_YEAR}")
    print()

    # Step 1: Read flow data
    flow_data = read_flow_data(flow_file)

    # Step 2 & 3: Fill editor with limits
    fill_editor(editor_file, flow_data, scenarios=scenarios)

    print("\nDone!")


if __name__ == '__main__':
    main()
