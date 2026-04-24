"""
AUX_Z_recalc_shares.py

Back-calculates Diésel / Fuel oil / Búnker shares in Shares_PET_OIL_Split.xlsx
so that D2_update_secondary_techs.py reproduces the ResidualCapacity values from
Old_Inputs parametrization files.

Usage:
    python AUX_Z_recalc_shares.py
"""

import shutil
from pathlib import Path

import openpyxl


SCRIPT_DIR = Path(__file__).parent

# --- Configuration ---

SHARES_FILE = SCRIPT_DIR / "Shares_PET_OIL_Split.xlsx"
OLADE_FILE = SCRIPT_DIR / "OLADE - Capacidad instalada por fuente - Anual.xlsx"

SCENARIO_CONFIG = {
    "SharesBAU": {
        "old_inputs": SCRIPT_DIR / "Old_Inputs" / "A1_Outputs" / "A1_Outputs_BAU" / "A-O_Parametrization.xlsx",
    },
    "SharesNDC": {
        "old_inputs": SCRIPT_DIR / "Old_Inputs" / "A1_Outputs" / "A1_Outputs_NDC" / "A-O_Parametrization.xlsx",
    },
}

# OLADE country name -> ISO3 (row 5 of OLADE file)
OLADE_NAME_TO_ISO3 = {
    "Argentina": "ARG", "Barbados": "JAM", "Bolivia": "BOL", "Brasil": "BRA",
    "Chile": "CHL", "Colombia": "COL", "Costa Rica": "CRI", "Ecuador": "ECU",
    "El Salvador": "SLV", "Guatemala": "GTM", "Haiti": "HTI", "Honduras": "HND",
    "México": "MEX", "Nicaragua": "NIC", "Panamá": "PAN", "Paraguay": "PRY",
    "Perú": "PER", "República Dominicana": "DOM", "Uruguay": "URY",
}

# Countries to add as new blocks (not currently in Shares file)
NEW_COUNTRIES = {"ARG": "Argentina", "BRA": "Brasil", "MEX": "México"}

# Years range for Shares file
SHARES_YEARS = list(range(2023, 2046))  # 2023-2045


def read_olade_petroleum_capacity():
    """Read OLADE petroleum capacity (GW) per country from the OLADE file."""
    wb = openpyxl.load_workbook(OLADE_FILE, data_only=True)
    ws = wb["1.2023"]

    # Row 5 has country names (cols 3+), row 8 has Petroleum values
    capacity = {}
    for c in range(3, ws.max_column + 1):
        country_name = ws.cell(5, c).value
        if country_name and country_name in OLADE_NAME_TO_ISO3:
            iso3 = OLADE_NAME_TO_ISO3[country_name]
            val = ws.cell(8, c).value  # MW
            capacity[iso3] = (float(val) / 1000.0) if val else 0.0  # Convert to GW

    wb.close()
    return capacity


def read_old_inputs_targets(parametrization_path):
    """
    Read target PET and OIL ResidualCapacity from Old_Inputs parametrization file.

    Returns: {iso3: {"PET": {year_str: value}, "OIL": {year_str: value}}}
    """
    wb = openpyxl.load_workbook(parametrization_path, data_only=True)
    ws = wb["Secondary Techs"]

    # Build year -> column map (headers are strings like "2023")
    year_cols = {}
    for c in range(9, ws.max_column + 1):
        h = ws.cell(1, c).value
        if h:
            year_cols[str(h)] = c

    targets = {}

    for r in range(2, ws.max_row + 1):
        tech_id = str(ws.cell(r, 2).value or "")
        param = str(ws.cell(r, 5).value or "")

        if "ResidualCapacity" not in param:
            continue
        if "PET" not in tech_id and "OIL" not in tech_id:
            continue

        # Extract ISO3: PWRPETARGXX01 -> ARG, PWROILMEXXX01 -> MEX
        # Tech IDs are like PWR + PET/OIL + ISO3(3 chars) + XX01
        if "PET" in tech_id:
            tech_type = "PET"
            # Find position of PET and extract next 3 chars
            idx = tech_id.index("PET") + 3
        else:
            tech_type = "OIL"
            idx = tech_id.index("OIL") + 3
        iso3 = tech_id[idx : idx + 3]

        if iso3 not in targets:
            targets[iso3] = {"PET": {}, "OIL": {}}

        for yr_str, col in year_cols.items():
            val = ws.cell(r, col).value
            targets[iso3][tech_type][yr_str] = float(val) if val is not None else 0.0

    wb.close()
    return targets


def read_current_shares(wb, sheet_name):
    """
    Read current shares from the Shares file.

    Returns: {iso3: {"Diésel": {year: val}, "Fuel oil": {year: val}, "Búnker": {year: val}}}
    Also returns structure info: {iso3: {"country_row": row, "fuel_rows": {"Diésel": row, ...}}}
    """
    if sheet_name not in wb.sheetnames:
        return {}, {}

    ws = wb[sheet_name]

    # Read years from row 1
    years = {}
    for c in range(2, ws.max_column + 1):
        v = ws.cell(1, c).value
        if v is not None:
            try:
                years[int(float(v))] = c
            except (ValueError, TypeError):
                pass

    shares = {}
    structure = {}
    current_iso3 = None
    row = 2

    while row <= ws.max_row:
        cell = ws.cell(row, 1).value
        if not cell:
            row += 1
            continue

        cell_str = str(cell).strip()

        if cell_str in OLADE_NAME_TO_ISO3:
            current_iso3 = OLADE_NAME_TO_ISO3[cell_str]
            structure[current_iso3] = {"country_row": row, "fuel_rows": {}}
            shares[current_iso3] = {"Diésel": {}, "Fuel oil": {}, "Búnker": {}}
            row += 1
            continue

        if current_iso3 and cell_str in ("Diésel", "Fuel oil", "Búnker"):
            structure[current_iso3]["fuel_rows"][cell_str] = row
            for yr, col in years.items():
                val = ws.cell(row, col).value
                shares[current_iso3][cell_str][yr] = float(val) if val is not None else 0.0

        row += 1

    return shares, structure


def compute_new_shares(targets, current_shares, olade_cap):
    """
    Compute new normalized shares for all years.

    Returns: {iso3: {"Diésel": {year: val}, "Fuel oil": {year: val}, "Búnker": {year: val}}}
    """
    new_shares = {}

    all_iso3 = set(targets.keys())

    for iso3 in sorted(all_iso3):
        if iso3 not in olade_cap or olade_cap[iso3] == 0:
            print(f"  SKIP {iso3}: no OLADE petroleum capacity")
            continue

        pet_data = targets[iso3].get("PET", {})
        oil_data = targets[iso3].get("OIL", {})

        new_shares[iso3] = {"Diésel": {}, "Fuel oil": {}, "Búnker": {}}

        for year in SHARES_YEARS:
            yr_str = str(year)
            target_pet = pet_data.get(yr_str, 0.0)
            target_oil = oil_data.get(yr_str, 0.0)
            total_target = target_pet + target_oil

            if total_target > 0:
                diesel_share = target_pet / total_target
                oil_share = target_oil / total_target
            else:
                diesel_share = 0.0
                oil_share = 0.0

            # Split oil_share between Fuel oil and Búnker using existing ratio
            if iso3 in current_shares:
                existing_fo = current_shares[iso3].get("Fuel oil", {}).get(year, 0.0)
                existing_bk = current_shares[iso3].get("Búnker", {}).get(year, 0.0)
            else:
                existing_fo = 0.0
                existing_bk = 0.0

            oil_sum = existing_fo + existing_bk
            if oil_sum > 0:
                fo_ratio = existing_fo / oil_sum
            elif oil_share > 0:
                # New country with no existing ratio: 100% Fuel oil
                fo_ratio = 1.0
            else:
                fo_ratio = 0.5

            new_shares[iso3]["Diésel"][year] = diesel_share
            new_shares[iso3]["Fuel oil"][year] = oil_share * fo_ratio
            new_shares[iso3]["Búnker"][year] = oil_share * (1.0 - fo_ratio)

        # Log 2023 values
        d23 = new_shares[iso3]["Diésel"].get(2023, 0)
        f23 = new_shares[iso3]["Fuel oil"].get(2023, 0)
        b23 = new_shares[iso3]["Búnker"].get(2023, 0)
        pet23 = pet_data.get("2023", 0)
        oil23 = oil_data.get("2023", 0)
        cap = olade_cap[iso3]
        print(
            f"  {iso3}: D={d23:.4f} FO={f23:.4f} BK={b23:.4f} "
            f"(sum={d23+f23+b23:.4f}) | "
            f"target PET={pet23:.4f} OIL={oil23:.4f} total={pet23+oil23:.4f} | "
            f"OLADE={cap:.4f}"
        )

    return new_shares


def write_shares_to_excel(wb, sheet_name, new_shares, structure):
    """Write new shares into the workbook sheet, adding new countries if needed."""
    ws = wb[sheet_name]

    # Read year -> column map from row 1
    years_cols = {}
    for c in range(2, ws.max_column + 1):
        v = ws.cell(1, c).value
        if v is not None:
            try:
                years_cols[int(float(v))] = c
            except (ValueError, TypeError):
                pass

    # Update existing countries
    for iso3, fuels in new_shares.items():
        if iso3 in structure:
            for fuel_name in ("Diésel", "Fuel oil", "Búnker"):
                row = structure[iso3]["fuel_rows"].get(fuel_name)
                if row is None:
                    continue
                for year, col in years_cols.items():
                    if year in fuels[fuel_name]:
                        ws.cell(row, col, value=fuels[fuel_name][year])

    # Add new countries at the end
    next_row = ws.max_row + 2  # Leave a blank row
    for iso3 in sorted(NEW_COUNTRIES.keys()):
        if iso3 not in new_shares:
            continue
        if iso3 in structure:
            continue  # Already exists

        country_name = NEW_COUNTRIES[iso3]
        # Write country name
        ws.cell(next_row, 1, value=country_name)
        next_row += 1

        # Write fuel rows
        for fuel_name in ("Diésel", "Fuel oil", "Búnker"):
            ws.cell(next_row, 1, value=fuel_name)
            for year, col in years_cols.items():
                if year in new_shares[iso3][fuel_name]:
                    ws.cell(next_row, col, value=new_shares[iso3][fuel_name][year])
            next_row += 1


def main():
    print("=" * 70)
    print("AUX_Z_recalc_shares: Recalculating PET/OIL shares")
    print("=" * 70)

    # Step 1: Read OLADE petroleum capacity
    print("\n[1] Reading OLADE petroleum capacity...")
    olade_cap = read_olade_petroleum_capacity()
    for iso3 in sorted(olade_cap):
        print(f"  {iso3}: {olade_cap[iso3]:.6f} GW")

    # Backup shares file
    backup_path = SHARES_FILE.with_suffix(".xlsx.bak")
    shutil.copy2(SHARES_FILE, backup_path)
    print(f"\nBackup saved to: {backup_path}")

    # Open shares workbook (preserving structure, NOT data_only)
    wb = openpyxl.load_workbook(SHARES_FILE)

    for sheet_name, config in SCENARIO_CONFIG.items():
        print(f"\n{'='*50}")
        print(f"[2] Processing sheet: {sheet_name}")
        print(f"{'='*50}")

        # Read current shares
        current_shares, structure = read_current_shares(wb, sheet_name)
        print(f"  Existing countries: {sorted(structure.keys())}")

        # Read target values from Old_Inputs
        old_inputs_path = config["old_inputs"]
        if not old_inputs_path.exists():
            print(f"  WARNING: Old_Inputs not found: {old_inputs_path}")
            continue

        print(f"  Reading targets from: {old_inputs_path.name}")
        targets = read_old_inputs_targets(old_inputs_path)

        # Compute new shares
        print(f"\n  Computing new shares (normalized to 1.0):")
        new_shares = compute_new_shares(targets, current_shares, olade_cap)

        # Write to Excel
        write_shares_to_excel(wb, sheet_name, new_shares, structure)
        print(f"  Written {len(new_shares)} countries to {sheet_name}")

    # Save
    wb.save(SHARES_FILE)
    wb.close()
    print(f"\nSaved updated shares to: {SHARES_FILE}")
    print("Done.")


if __name__ == "__main__":
    main()
