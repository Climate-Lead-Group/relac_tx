"""
Set TRN Interconnection Activity Limits from Bilateral Flow Data

Reads estimated bilateral energy flows from flujos_energia_estimados_optimizacion.xlsx
and writes Lower/Upper activity limits into Secondary_Techs_Editor.xlsx.

- LowerLimit = Flujo Total (PJ) * 0.95  (-5%)
- UpperLimit = Flujo Total (PJ) * 1.05  (+5%)
- Years 2023-2025: actual flow data
- Years 2026-2050: flat projection from 2025 value

Usage:
    python t1_confection/D1b_set_trn_limits_from_flows.py
"""
import argparse
import openpyxl
import unicodedata
from pathlib import Path

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


def fill_editor(editor_path, flow_data, scenarios=None):
    """
    Create Lower/Upper activity limit rows for TRN interconnections in the Editor sheet.

    Idempotent: on each call, rows previously written by this function are cleared
    (rows where column D contains a plain TRN code, i.e. not a VLOOKUP formula) and
    rebuilt from flow_data.

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

    # --- Pass 1: Read _TechMapping and Editor year columns (resolving formulas) ---
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
    wb_read.close()

    print(f"  Year columns: {min(year_col_map)} to {max(year_col_map)} ({len(year_col_map)} years)")
    print(f"  TRN tech mappings loaded: {len(pair_to_tech)}")

    # --- Pass 2: Open writable, clear previous rows, create new rows ---
    wb_write = openpyxl.load_workbook(editor_path)
    ws_write = wb_write['Editor']
    max_col = ws_write.max_column

    # Determine end of VLOOKUP template (last row with a formula in column D).
    # Our rows are appended *beyond* the template so users' manual-entry
    # template rows (where D has =IFERROR(VLOOKUP(...))) are preserved.
    template_end = 1
    for row_idx in range(2, ws_write.max_row + 1):
        d_val = ws_write.cell(row_idx, 4).value
        if d_val and str(d_val).startswith('='):
            template_end = row_idx

    # Step A: Clear previously-written fill_editor rows (beyond the template)
    rows_cleared = 0
    for row_idx in range(template_end + 1, ws_write.max_row + 1):
        d_val = ws_write.cell(row_idx, 4).value
        if d_val is None:
            continue
        if str(d_val).strip().upper().startswith('TRN'):
            for col in range(1, max_col + 1):
                ws_write.cell(row_idx, col).value = None
            rows_cleared += 1

    # Step B: Create rows per scenario × pair × parameter starting after template
    PARAMS = [
        ('TotalTechnologyAnnualActivityLowerLimit', LOWER_LIMIT_FACTOR, 'Lower'),
        ('TotalTechnologyAnnualActivityUpperLimit', UPPER_LIMIT_FACTOR, 'Upper'),
    ]
    rows_created = 0
    unmatched_pairs = []
    next_row = template_end + 1

    for pair, pair_flows in sorted(flow_data.items(), key=lambda kv: sorted(kv[0])):
        if pair not in pair_to_tech:
            unmatched_pairs.append(sorted(pair))
            continue
        tech_code, tech_name, origin_country = pair_to_tech[pair]
        base_year = max(pair_flows.keys())
        base_gwh = pair_flows[base_year]

        for scenario in scenarios:
            for parameter, factor, limit_type in PARAMS:
                ws_write.cell(next_row, 1).value = scenario
                ws_write.cell(next_row, 2).value = origin_country
                ws_write.cell(next_row, 3).value = tech_name
                ws_write.cell(next_row, 4).value = tech_code
                ws_write.cell(next_row, 5).value = parameter
                for year in range(EDITOR_FIRST_YEAR, EDITOR_LAST_YEAR + 1):
                    if year not in year_col_map:
                        continue
                    gwh = pair_flows.get(year, base_gwh)
                    limit_value = round(gwh * GWH_TO_PJ * factor, 6)
                    ws_write.cell(next_row, year_col_map[year]).value = limit_value
                rows_created += 1
                next_row += 1

    wb_write.save(editor_path)
    wb_write.close()

    print(f"  Template ends at row {template_end} (preserved)")
    print(f"  Cleared {rows_cleared} previously-written TRN rows")
    print(f"  Created {rows_created} rows "
          f"({len(flow_data) - len(unmatched_pairs)} pairs × {len(scenarios)} scenarios × {len(PARAMS)} params)")
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

    script_dir = Path(__file__).parent

    flow_file = script_dir / "Matriz Balance energético" / "flujos_energia_estimados_optimizacion.xlsx"
    editor_file = script_dir / "Secondary_Techs_Editor.xlsx"

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
