"""
Process Combined_Inputs_Outputs CSVs and update dashboard_capacity_cost.html directly.

Usage:
    python scripts/dashboard/_process_csv_for_dashboard.py
"""
import csv
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> scripts/
from common import relac_paths as P

# Input files
RELAC_CSV = str(P.OUTPUTS / 'RELAC_TX_Combined_Inputs_Outputs_ReLAC.csv')
SIELAC_CSV = str(P.OUTPUTS / 'RELAC_TX_Combined_Inputs_Outputs_SieLAC.csv')
DASHBOARD_HTML = str(P.FIGURES / 'dashboard_capacity_cost.html')

# Technology type code -> Fuente mapping (for Generación)
TECH_TO_FUENTE = {
    'BIO': 'Biomasa',
    'WON': 'Eólico',
    'WOF': 'Eólico',
    'SPV': 'Fotovoltaica',
    'CSP': 'Fotovoltaica',
    'NGS': 'Gas natural',
    'GEO': 'Geotérmica',
    'HYD': 'Hidroeléctrica',
    'WAV': 'Mareomotriz',
    'WAS': 'Biomasa',
    'COA': 'No Renovable',
    'OIL': 'Térmica no renovable',
    'PET': 'Térmica no renovable',
    'OTH': 'Térmica no renovable',
    'URN': 'Nuclear',
    'COG': 'Térmica no renovable',
    'CCS': 'Térmica no renovable',
    'BCK': 'Térmica no renovable',
}

COUNTRY_NAMES = {
    'ARG': 'Argentina',
    'BOL': 'Bolivia',
    'BRA': 'Brasil',
    'BRB': 'Barbados',
    'CHL': 'Chile',
    'COL': 'Colombia',
    'CRI': 'Costa Rica',
    'DOM': 'Rep. Dominicana',
    'ECU': 'Ecuador',
    'GTM': 'Guatemala',
    'HND': 'Honduras',
    'HTI': 'Haití',
    'MEX': 'México',
    'NIC': 'Nicaragua',
    'PAN': 'Panamá',
    'PER': 'Perú',
    'PRY': 'Paraguay',
    'SLV': 'El Salvador',
    'URY': 'Uruguay',
    'INT': 'Internacional',
}


def classify_tech(tech_code):
    """Returns (tipo, fuente, countries) or None if tech should be excluded.
    countries is a list of 3-letter country codes.
    """
    if tech_code.startswith('MIN') or tech_code.startswith('RNW'):
        return None

    if tech_code.startswith('PWR'):
        sub = tech_code[3:6]
        # Country is at positions 6:9 (e.g., PWRBIOARGXX -> ARG)
        country = tech_code[6:9] if len(tech_code) >= 9 else 'UNK'
        if sub in ('LDS', 'SDS'):
            return ('Almacenamiento', 'No generacion', [country])
        if sub == 'TRN':
            return ('Transmisión', 'No generacion', [country])
        fuente = TECH_TO_FUENTE.get(sub)
        if fuente:
            return ('Generación', fuente, [country])
        print(f"  WARNING: Unknown PWR subtype: {sub} in {tech_code}", file=sys.stderr)
        return None

    if tech_code.startswith('TRN'):
        sub = tech_code[3:6]
        if sub in ('NLI', 'RPO'):
            # TRNNLIARGXX -> country at 6:9
            country = tech_code[6:9] if len(tech_code) >= 9 else 'UNK'
            return ('Transmisión', 'No generacion', [country])
        # Interconnection: TRNARGXXBOLXX -> ARG(3:6), BOL(8:11)
        c1 = tech_code[3:6]
        c2 = tech_code[8:11] if len(tech_code) >= 11 else 'UNK'
        return ('Interconexiones', 'No generacion', [c1, c2])

    print(f"  WARNING: Unknown tech prefix: {tech_code}", file=sys.stderr)
    return None


def parse_num(val):
    val = val.strip()
    if not val:
        return 0.0
    try:
        return float(val)
    except ValueError:
        return 0.0


def process_file(filepath, model_name):
    """Process a Combined_Inputs_Outputs CSV and return aggregated rows."""
    # Key: (scenario, tipo, fuente, country, year) -> values
    agg = defaultdict(lambda: {'capInv': 0.0, 'fixCost': 0.0, 'capacity': 0.0, 'varCost': 0.0})

    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)

        col_map = {name: idx for idx, name in enumerate(header)}
        COL_SCENARIO = col_map['Scenario']
        COL_YEAR = col_map['YEAR']
        COL_TECH = col_map['TECHNOLOGY']
        COL_CAP_INV = col_map['CapitalInvestment']
        COL_FIX_COST = col_map['AnnualFixedOperatingCost']
        COL_CAPACITY = col_map['TotalCapacityAnnual']
        COL_VAR_COST = col_map['AnnualVariableOperatingCost']
        min_cols = max(COL_SCENARIO, COL_YEAR, COL_TECH, COL_CAP_INV,
                       COL_FIX_COST, COL_CAPACITY, COL_VAR_COST) + 1

        for row in reader:
            if len(row) < min_cols:
                continue

            scenario = row[COL_SCENARIO].strip()
            tech = row[COL_TECH].strip()
            year_str = row[COL_YEAR].strip()

            if not scenario or not tech or not year_str:
                continue

            classification = classify_tech(tech)
            if classification is None:
                continue

            tipo, fuente, countries = classification

            try:
                year = int(float(year_str))
            except ValueError:
                continue

            cap_inv = parse_num(row[COL_CAP_INV])
            fix_cost = parse_num(row[COL_FIX_COST])
            capacity = parse_num(row[COL_CAPACITY])
            var_cost = parse_num(row[COL_VAR_COST])

            if cap_inv or fix_cost or capacity or var_cost:
                # For interconnections with 2 countries, store under both
                for country in countries:
                    key = (scenario, tipo, fuente, country, year)
                    agg[key]['capInv'] += cap_inv
                    agg[key]['fixCost'] += fix_cost
                    agg[key]['capacity'] += capacity
                    agg[key]['varCost'] += var_cost

    rows = []
    for (scenario, tipo, fuente, country, year), vals in sorted(agg.items()):
        rows.append({
            'model': model_name,
            'scenario': scenario,
            'tipo': tipo,
            'fuente': fuente,
            'country': country,
            'year': year,
            'capInv': vals['capInv'],
            'fixCost': vals['fixCost'],
            'capacity': vals['capacity'],
            'varCost': vals['varCost'],
        })
    return rows


def format_num(val):
    if val == 0.0:
        return ''
    return str(val)


def build_csv_text(all_rows):
    """Build the semicolon-separated CSV text for embedding."""
    header = 'Model;Scenario1;Technology Tipo (grupos);Technology Tipo de Fuente;Country;Años;Capital Investment;Fixed Cost;Total Capacity Annual;Variable Cost'
    lines = [header]
    for r in all_rows:
        lines.append(';'.join([
            r['model'], r['scenario'], r['tipo'], r['fuente'], r['country'],
            str(r['year']),
            format_num(r['capInv']), format_num(r['fixCost']),
            format_num(r['capacity']), format_num(r['varCost']),
        ]))
    return '\n'.join(lines)


def build_scenario_options(scenarios):
    """Build the <option> tags for the scenario selector."""
    return ''.join(f'<option value="{s}">{s}</option>' for s in scenarios)


def update_dashboard(all_rows):
    """Update the dashboard HTML file with new embedded data and scenarios."""
    with open(DASHBOARD_HTML, 'r', encoding='utf-8') as f:
        html = f.read()

    csv_text = build_csv_text(all_rows)

    # Replace the EMBEDDED_CSV block
    pattern = r'const EMBEDDED_CSV = `[^`]*`;'
    replacement = f'const EMBEDDED_CSV = `{csv_text}`;'
    new_html, count = re.subn(pattern, replacement, html, count=1, flags=re.DOTALL)
    if count == 0:
        print("ERROR: Could not find EMBEDDED_CSV block in dashboard HTML!", file=sys.stderr)
        sys.exit(1)

    # Update scenario dropdown options
    scenarios = sorted(set(r['scenario'] for r in all_rows))
    options_html = build_scenario_options(scenarios)
    new_html = re.sub(
        r'(<select id="selScenario">).*?(</select>)',
        rf'\1{options_html}\2',
        new_html
    )

    with open(DASHBOARD_HTML, 'w', encoding='utf-8') as f:
        f.write(new_html)

    return scenarios


if __name__ == '__main__':
    print("=== Updating dashboard_capacity_cost.html ===\n", file=sys.stderr)

    print(f"Processing {os.path.basename(RELAC_CSV)}...", file=sys.stderr)
    relac_rows = process_file(RELAC_CSV, 'ReLAC')
    print(f"  -> {len(relac_rows)} aggregated rows", file=sys.stderr)

    print(f"Processing {os.path.basename(SIELAC_CSV)}...", file=sys.stderr)
    sielac_rows = process_file(SIELAC_CSV, 'SieLAC')
    print(f"  -> {len(sielac_rows)} aggregated rows", file=sys.stderr)

    all_rows = relac_rows + sielac_rows

    scenarios = sorted(set(r['scenario'] for r in all_rows))
    tipos = sorted(set(r['tipo'] for r in all_rows))
    fuentes = sorted(set(r['fuente'] for r in all_rows))
    countries = sorted(set(r['country'] for r in all_rows))
    years = sorted(set(r['year'] for r in all_rows))

    print(f"\n  Scenarios:  {scenarios}", file=sys.stderr)
    print(f"  Tipos:      {tipos}", file=sys.stderr)
    print(f"  Fuentes:    {fuentes}", file=sys.stderr)
    print(f"  Countries:  {countries}", file=sys.stderr)
    print(f"  Years:      {years[0]}-{years[-1]}", file=sys.stderr)
    print(f"  Total:      {len(all_rows)} rows\n", file=sys.stderr)

    scenarios = update_dashboard(all_rows)
    print(f"Dashboard updated: {DASHBOARD_HTML}", file=sys.stderr)
    print("Done!", file=sys.stderr)
