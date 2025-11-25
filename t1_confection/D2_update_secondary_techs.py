"""
Update Secondary Techs from Editor Template

This script reads the Secondary_Techs_Editor.xlsx file and applies
the changes to the corresponding A-O_Parametrization.xlsx files.

Usage:
    python t1_confection/D2_update_secondary_techs.py
"""
import openpyxl
import sys
from pathlib import Path
from datetime import datetime
import shutil

# OLADE country name to model country code mapping
# Note: Model uses JAM for Barbados (not standard ISO-3)
OLADE_COUNTRY_MAPPING = {
    'Argentina': 'ARG',
    'Barbados': 'JAM',  # Model convention: JAM represents Barbados
    'Belice': 'BLZ',
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
    'México': 'MEX',
    'Nicaragua': 'NIC',
    'Panamá': 'PAN',
    'Paraguay': 'PRY',
    'Perú': 'PER',
    'República Dominicana': 'DOM',
    'Uruguay': 'URY'
}

# OLADE technology to model tech code (3 chars) mapping
OLADE_TECH_MAPPING = {
    'Nuclear': 'URN',
    'Gas natural': 'CCG',
    'Carbón mineral': 'COA',
    'Hidro': 'HYD',
    'Geotermia': 'GEO',
    'Eólica': 'WON',
    'Solar': 'SPV'
    # Note: BIO is special - sum of 'Biogás' + 'Biomasa sólida'
    # Note: 'Petróleo y derivados' pending confirmation
}


def read_olade_config(editor_path):
    """
    Read OLADE configuration from the editor Excel file

    Returns:
        dict with config: {enabled, petroleum_split_mode, demand_enabled, demand_growth_rates}
    """
    wb = openpyxl.load_workbook(editor_path, data_only=True)

    if 'OLADE_Config' not in wb.sheetnames:
        wb.close()
        return {
            'enabled': False,
            'petroleum_split_mode': 'Split_PET_OIL',
            'demand_enabled': False,
            'demand_growth_rates': {}
        }

    ws = wb['OLADE_Config']

    # Read configuration values
    # Row 5 = ResidualCapacitiesFromOLADE, Row 6 = PetroleumSplitMode, Row 7 = DemandFromOLADE
    enabled = str(ws['B5'].value).upper() == 'YES' if ws['B5'].value else False
    petroleum_split_mode = str(ws['B6'].value) if ws['B6'].value else 'Split_PET_OIL'
    demand_enabled = str(ws['B7'].value).upper() == 'YES' if ws['B7'].value else False

    # Read demand growth rates from Demand_Growth sheet
    demand_growth_rates = {}
    if 'Demand_Growth' in wb.sheetnames:
        ws_demand = wb['Demand_Growth']
        # Data starts at row 5, Column A = country code, Column C = growth rate
        for row_idx in range(5, ws_demand.max_row + 1):
            country_code = ws_demand.cell(row_idx, 1).value
            growth_rate = ws_demand.cell(row_idx, 3).value
            if country_code and growth_rate is not None:
                try:
                    # Convert percentage to decimal (e.g., 2.0 -> 0.02)
                    demand_growth_rates[str(country_code).strip()] = float(growth_rate) / 100.0
                except (ValueError, TypeError):
                    pass

    wb.close()

    return {
        'enabled': enabled,
        'petroleum_split_mode': petroleum_split_mode,
        'demand_enabled': demand_enabled,
        'demand_growth_rates': demand_growth_rates
    }


def read_shares_data(shares_file_path):
    """
    Read Shares.xlsx file to get Diésel, Fuel oil, and Búnker shares by scenario, country, and year

    The file should be normalized so that Diésel + Fuel oil + Búnker = 1.0

    Returns:
        dict: {
            scenario: {
                country_iso3: {
                    year: {
                        'Diésel': share_value,
                        'Fuel oil': share_value,
                        'Búnker': share_value
                    }
                }
            }
        }
    """
    if not shares_file_path.exists():
        raise FileNotFoundError(f"Shares file not found: {shares_file_path}")

    wb = openpyxl.load_workbook(shares_file_path, data_only=True)

    shares_data = {}

    # Map sheet names to scenario codes
    sheet_scenario_map = {
        'SharesBAU': 'BAU',
        'SharesNDC': 'NDC',
        'SharesNDC_NoRPO': 'NDC_NoRPO',
        'SharesNDC+ELC': 'NDC+ELC'
    }

    # Map country names from Shares to ISO3 codes
    shares_country_to_iso3 = {
        'Barbados': 'JAM',  # Model convention
        'Bolivia': 'BOL',
        'Chile': 'CHL',
        'Colombia': 'COL',
        'Costa Rica': 'CRI',
        'Ecuador': 'ECU',
        'El Salvador': 'SLV',
        'Guatemala': 'GTM',
        'Haiti': 'HTI',
        'Honduras': 'HND',
        'Nicaragua': 'NIC',
        'Panamá': 'PAN',
        'Paraguay': 'PRY',
        'Perú': 'PER',
        'República Dominicana': 'DOM',
        'Uruguay': 'URY'
    }

    for sheet_name, scenario_code in sheet_scenario_map.items():
        if sheet_name not in wb.sheetnames:
            continue

        ws = wb[sheet_name]
        shares_data[scenario_code] = {}

        # Read years from row 1 (starting from column 2)
        years = []
        for col_idx in range(2, ws.max_column + 1):
            year_val = ws.cell(1, col_idx).value
            if year_val:
                try:
                    year = int(float(year_val))
                    years.append((col_idx, year))
                except:
                    pass

        # Process rows: each country has a block of rows
        current_country_iso3 = None
        row_idx = 2

        while row_idx <= ws.max_row:
            # First column: could be country name or fuel name
            cell_value = ws.cell(row_idx, 1).value

            if not cell_value:
                row_idx += 1
                continue

            cell_str = str(cell_value).strip()

            # Check if this is a country row
            if cell_str in shares_country_to_iso3:
                current_country_iso3 = shares_country_to_iso3[cell_str]
                shares_data[scenario_code][current_country_iso3] = {}
                row_idx += 1
                continue

            # If we have a current country, check for fuel types
            if current_country_iso3 and cell_str in ['Diésel', 'Fuel oil', 'Búnker']:
                fuel_name = cell_str

                # Read shares for all years
                for col_idx, year in years:
                    share_value = ws.cell(row_idx, col_idx).value

                    if year not in shares_data[scenario_code][current_country_iso3]:
                        shares_data[scenario_code][current_country_iso3][year] = {}

                    if share_value is not None:
                        try:
                            shares_data[scenario_code][current_country_iso3][year][fuel_name] = float(share_value)
                        except (ValueError, TypeError):
                            shares_data[scenario_code][current_country_iso3][year][fuel_name] = 0.0
                    else:
                        shares_data[scenario_code][current_country_iso3][year][fuel_name] = 0.0

            row_idx += 1

    wb.close()
    return shares_data


def read_olade_data(olade_file_path):
    """
    Read OLADE capacity data from Excel file

    Note: OLADE data is in MW, but is converted to GW for the model (1 GW = 1000 MW)

    Returns:
        dict: {
            'reference_year': int,
            'data': {
                country_iso3: {
                    tech_code: capacity_gw
                }
            }
        }
    """
    if not olade_file_path.exists():
        raise FileNotFoundError(f"OLADE file not found: {olade_file_path}")

    wb = openpyxl.load_workbook(olade_file_path, data_only=True)
    ws = wb['1.2023']

    # Extract reference year from A4
    ref_year_cell = ws['A4'].value
    ref_year = 2023  # Default
    if ref_year_cell and str(ref_year_cell).startswith('2023'):
        ref_year = 2023

    # Get country columns from row 5 (starting at column 3)
    country_columns = {}
    for col_idx in range(3, ws.max_column + 1):
        country_name = ws.cell(5, col_idx).value
        if country_name and str(country_name) in OLADE_COUNTRY_MAPPING:
            iso3_code = OLADE_COUNTRY_MAPPING[str(country_name)]
            country_columns[col_idx] = iso3_code

    # Read technology data (rows 6-20)
    data = {}

    # Process each technology
    for row_idx in range(6, 21):
        tech_name = ws.cell(row_idx, 1).value
        if not tech_name:
            continue

        tech_name_str = str(tech_name).strip()

        # Skip non-applicable technologies
        if tech_name_str in ['Térmica no renovable (combustión)', 'Otras fuentes',
                             'Térmica renovable (combustión)', 'Fuentes renovable (no combustión)',
                             'Biocombustibles líquidos', 'Total']:
            continue

        # Map OLADE tech name to model tech code
        tech_code = None
        if tech_name_str in OLADE_TECH_MAPPING:
            tech_code = OLADE_TECH_MAPPING[tech_name_str]

        # Special handling for BIO (sum of Biogás and Biomasa sólida)
        if tech_name_str == 'Biogás':
            tech_code = 'BIO'
        elif tech_name_str == 'Biomasa sólida':
            tech_code = 'BIO'

        # Special handling for Petróleo y derivados (will be split into PET and OIL later)
        elif tech_name_str == 'Petróleo y derivados':
            tech_code = 'PETROLEUM'  # Temporary code, will be split later

        if not tech_code:
            continue

        # Read capacity values for each country
        for col_idx, country_iso3 in country_columns.items():
            capacity = ws.cell(row_idx, col_idx).value

            if capacity is not None and capacity != '':
                try:
                    capacity_mw = float(capacity)

                    # Convert from MW to GW (1 GW = 1000 MW)
                    capacity_gw = capacity_mw / 1000.0

                    # Initialize country if not exists
                    if country_iso3 not in data:
                        data[country_iso3] = {}

                    # For BIO, sum Biogás + Biomasa sólida
                    if tech_code == 'BIO':
                        if tech_code in data[country_iso3]:
                            data[country_iso3][tech_code] += capacity_gw
                        else:
                            data[country_iso3][tech_code] = capacity_gw
                    else:
                        data[country_iso3][tech_code] = capacity_gw

                except ValueError:
                    pass

    wb.close()

    return {
        'reference_year': ref_year,
        'data': data
    }


def read_olade_generation_data(generation_file_path):
    """
    Read OLADE electricity generation data from Excel file

    Note: OLADE data is in GWh, converted to PJ for the model (1 GWh = 0.0036 PJ)

    Returns:
        dict: {
            'reference_year': int,
            'data': {
                country_iso3: generation_pj
            }
        }
    """
    if not generation_file_path.exists():
        raise FileNotFoundError(f"OLADE generation file not found: {generation_file_path}")

    wb = openpyxl.load_workbook(generation_file_path, data_only=True)
    ws = wb['1.2023']

    ref_year = 2023  # Reference year

    # Get country columns from row 5 (starting at column 3)
    country_columns = {}
    for col_idx in range(3, ws.max_column + 1):
        country_name = ws.cell(5, col_idx).value
        if country_name and str(country_name) in OLADE_COUNTRY_MAPPING:
            iso3_code = OLADE_COUNTRY_MAPPING[str(country_name)]
            country_columns[col_idx] = iso3_code

    # Read Total generation from row 21
    data = {}
    for col_idx, country_iso3 in country_columns.items():
        total_gwh = ws.cell(21, col_idx).value  # Row 21 = "Total"

        if total_gwh is not None and total_gwh != '':
            try:
                generation_gwh = float(total_gwh)
                # Convert from GWh to PJ (1 GWh = 0.0036 PJ)
                generation_pj = generation_gwh * 0.0036
                data[country_iso3] = generation_pj
            except ValueError:
                pass

    wb.close()

    return {
        'reference_year': ref_year,
        'data': data
    }


class SecondaryTechsUpdater:
    def __init__(self, editor_path, base_path, olade_file_path=None, shares_file_path=None, generation_file_path=None):
        self.editor_path = editor_path
        self.base_path = base_path
        self.olade_file_path = olade_file_path
        self.shares_file_path = shares_file_path
        self.generation_file_path = generation_file_path
        self.scenarios = ["BAU", "NDC", "NDC+ELC", "NDC_NoRPO"]
        self.log_lines = []
        self.changes_applied = 0
        self.rows_failed = 0
        self.olade_config = None
        self.olade_data = None
        self.shares_data = None
        self.generation_data = None

    def log(self, message, level="INFO"):
        """Add message to log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_line = f"[{timestamp}] {level}: {message}"
        self.log_lines.append(log_line)
        print(log_line)

    def read_editor_file(self):
        """
        Read and parse the editor Excel file

        Returns:
            list of dicts with editing instructions
        """
        self.log("Reading editor file...")

        if not self.editor_path.exists():
            raise FileNotFoundError(f"Editor file not found: {self.editor_path}")

        wb = openpyxl.load_workbook(self.editor_path, data_only=True)

        if 'Editor' not in wb.sheetnames:
            raise ValueError("'Editor' sheet not found in template file")

        ws = wb['Editor']

        # Read header to get year columns
        headers = []
        for cell in ws[1]:
            if cell.value:
                headers.append(str(cell.value))
            else:
                break

        # Identify year columns (after Scenario, Country, Tech.Name, Tech, Parameter)
        # Years start from column 6 (F)
        year_columns = []
        for idx, header in enumerate(headers[5:], 6):  # Start from column 6 (F)
            if header.isdigit():
                year_columns.append((idx, int(header)))

        self.log(f"Found {len(year_columns)} year columns: {year_columns[0][1]} to {year_columns[-1][1]}")

        # Read data rows
        # Columns: 1=Scenario, 2=Country, 3=Tech.Name, 4=Tech, 5=Parameter
        edit_instructions = []
        for row_idx in range(2, ws.max_row + 1):
            scenario = ws.cell(row_idx, 1).value
            country = ws.cell(row_idx, 2).value
            tech_name = ws.cell(row_idx, 3).value
            tech = ws.cell(row_idx, 4).value  # This is the Tech code (auto-filled from Tech.Name)
            parameter = ws.cell(row_idx, 5).value

            # Skip empty rows
            if not scenario and not country and not tech and not parameter:
                continue

            # Read year values
            year_values = {}
            for col_idx, year in year_columns:
                value = ws.cell(row_idx, col_idx).value
                if value is not None and value != "":
                    year_values[year] = value

            # Only add if we have at least one year value
            if year_values:
                edit_instructions.append({
                    'row': row_idx,
                    'scenario': str(scenario).strip() if scenario else None,
                    'country': str(country).strip() if country else None,
                    'tech_name': str(tech_name).strip() if tech_name else None,  # Keep for logging
                    'tech': str(tech).strip() if tech else None,  # This is what we'll use for matching
                    'parameter': str(parameter).strip() if parameter else None,
                    'year_values': year_values
                })

        wb.close()

        self.log(f"Found {len(edit_instructions)} rows with data to process")
        return edit_instructions

    def validate_instruction(self, instruction):
        """
        Validate an edit instruction

        Returns:
            (is_valid, error_message)
        """
        if not instruction['scenario']:
            return False, "Scenario is empty"

        if not instruction['country']:
            return False, "Country is empty"

        if not instruction['tech']:
            return False, "Tech is empty"

        if not instruction['parameter']:
            return False, "Parameter is empty"

        if not instruction['year_values']:
            return False, "No year values provided"

        # Validate scenario
        valid_scenarios = self.scenarios + ['ALL']
        if instruction['scenario'] not in valid_scenarios:
            return False, f"Invalid scenario '{instruction['scenario']}'. Must be one of: {valid_scenarios}"

        # Skip tech validation for OLADE instructions (they use 3-char codes)
        if instruction.get('is_olade'):
            return True, None

        # Validate that tech contains country code (for PWR technologies: PWRTRNARGXX -> ARG is at position 6-8)
        tech = instruction['tech'].upper()
        country = instruction['country'].upper()

        if tech.startswith('PWR'):
            # For PWR technologies, country code is at positions 6-8
            if len(tech) >= 9:
                tech_country = tech[6:9]
                if tech_country != country:
                    return False, f"Tech '{instruction['tech']}' contains country code '{tech_country}', but '{country}' was specified"
            else:
                return False, f"Tech '{instruction['tech']}' has invalid format (too short for PWR technology)"
        else:
            # For non-PWR technologies, country code might be at the beginning or elsewhere
            # We'll just issue a warning but allow it
            pass

        return True, None

    def create_backup(self, file_path):
        """Create backup of file before modifying"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = file_path.with_name(f"{file_path.stem}_backup_{timestamp}{file_path.suffix}")
        shutil.copy2(file_path, backup_path)
        return backup_path

    def find_and_update_row(self, ws, tech, parameter, year_values, year_col_map, projection_mode_col, is_olade=False, country=None):
        """
        Find the row matching tech and parameter, and update year values

        Args:
            is_olade: If True, tech is a 3-char code and we need to match PWR technologies by first 9 chars
            country: Country code (needed for OLADE matching)

        Returns:
            (success, message, values_updated)
        """
        # Search for matching row
        # Columns in Secondary Techs: 1=Tech.Id, 2=Tech, 3=Tech.Name, 5=Parameter
        target_rows = []

        for row_idx in range(2, ws.max_row + 1):
            row_tech = ws.cell(row_idx, 2).value  # Column 2: Tech
            row_param = ws.cell(row_idx, 5).value  # Column 5: Parameter

            if not row_tech or not row_param:
                continue

            row_tech_str = str(row_tech).strip()
            row_param_str = str(row_param).strip()

            # Check parameter match
            if row_param_str != parameter:
                continue

            # Check tech match
            if is_olade:
                # For OLADE: match PWR technologies by first 9 chars (PWR + 3 chars + country code)
                # Example: Looking for tech_code='URN' country='ARG' should match 'PWRURNARGXX'
                if row_tech_str.upper().startswith('PWR') and len(row_tech_str) >= 9:
                    # Extract positions 4-6 (tech type) and 7-9 (country)
                    row_tech_type = row_tech_str[3:6].upper()
                    row_country = row_tech_str[6:9].upper()

                    if row_tech_type == tech.upper() and row_country == country.upper():
                        target_rows.append(row_idx)
            else:
                # Exact match for manual instructions
                if row_tech_str == tech:
                    target_rows.append(row_idx)

        if not target_rows:
            tech_desc = f"Tech type='{tech}' Country='{country}'" if is_olade else f"Tech='{tech}'"
            return False, f"No matching row found for {tech_desc} and Parameter='{parameter}'", 0

        # Update year values for all matching rows
        total_values_updated = 0
        rows_updated = []

        for target_row in target_rows:
            values_updated = 0
            for year, value in year_values.items():
                if year in year_col_map:
                    col_idx = year_col_map[year]
                    ws.cell(target_row, col_idx, value)
                    values_updated += 1

            # Set Projection.Mode to "User defined" if column exists
            if projection_mode_col:
                current_value = ws.cell(target_row, projection_mode_col).value
                if current_value != "User defined":
                    ws.cell(target_row, projection_mode_col, "User defined")

            total_values_updated += values_updated
            rows_updated.append(target_row)

        if len(rows_updated) > 1:
            return True, f"Rows {rows_updated} updated with {total_values_updated} total year values", total_values_updated
        else:
            return True, f"Row {rows_updated[0]} updated with {total_values_updated} year values", total_values_updated

    def apply_instruction_to_scenario(self, instruction, scenario, ws, year_col_map, projection_mode_col):
        """
        Apply a single edit instruction to an already-open worksheet

        Args:
            instruction: instruction dict
            scenario: scenario name
            ws: openpyxl worksheet (already open)
            year_col_map: dict mapping years to column indices
            projection_mode_col: column index for Projection.Mode

        Returns:
            (success, message)
        """
        try:
            # Apply update
            is_olade = instruction.get('is_olade', False)
            country = instruction.get('country')

            success, message, values_updated = self.find_and_update_row(
                ws,
                instruction['tech'],
                instruction['parameter'],
                instruction['year_values'],
                year_col_map,
                projection_mode_col,
                is_olade=is_olade,
                country=country
            )

            if success:
                self.changes_applied += 1
                return True, f"{scenario}: {message}"
            else:
                return False, f"{scenario}: {message}"

        except Exception as e:
            return False, f"{scenario}: Error - {str(e)}"

    def apply_instructions_batch(self, instructions):
        """
        Apply all instructions grouped by scenario (batch processing)
        This opens each workbook only once, creates one backup, and saves only once.
        """
        # Group instructions by scenario
        from collections import defaultdict
        scenario_instructions = defaultdict(list)

        for instruction in instructions:
            # Validate first
            is_valid, error_msg = self.validate_instruction(instruction)
            if not is_valid:
                row_num = instruction['row']
                self.log(f"\nRow {row_num} FAILED: {error_msg}", "ERROR")
                self.rows_failed += 1
                continue

            # Determine target scenarios
            if instruction['scenario'] == 'ALL':
                target_scenarios = self.scenarios
            else:
                target_scenarios = [instruction['scenario']]

            # Add to each target scenario's list
            for scenario in target_scenarios:
                scenario_instructions[scenario].append(instruction)

        # Process each scenario
        for scenario in self.scenarios:
            if scenario not in scenario_instructions:
                self.log(f"\nScenario {scenario}: No instructions to apply")
                continue

            instructions_for_scenario = scenario_instructions[scenario]
            self.log(f"\nProcessing scenario {scenario}: {len(instructions_for_scenario)} instructions")

            scenario_path = self.base_path / f"A1_Outputs_{scenario}" / "A-O_Parametrization.xlsx"

            if not scenario_path.exists():
                self.log(f"  ✗ File not found: {scenario_path}", "ERROR")
                self.rows_failed += len(instructions_for_scenario)
                continue

            # Create backup ONCE for this scenario
            backup_path = self.create_backup(scenario_path)
            self.log(f"  Backup created: {backup_path.name}")

            try:
                # Open workbook ONCE
                wb = openpyxl.load_workbook(scenario_path)

                if 'Secondary Techs' not in wb.sheetnames:
                    wb.close()
                    self.log(f"  ✗ 'Secondary Techs' sheet not found", "ERROR")
                    self.rows_failed += len(instructions_for_scenario)
                    continue

                ws = wb['Secondary Techs']

                # Build year column map and find Projection.Mode column ONCE
                headers = [cell.value for cell in ws[1]]
                year_col_map = {}
                projection_mode_col = None

                for col_idx, header in enumerate(headers, 1):
                    if header:
                        if str(header).isdigit():
                            try:
                                year = int(header)
                                if 2000 <= year <= 2100:
                                    year_col_map[year] = col_idx
                            except:
                                pass
                        elif str(header).strip() == "Projection.Mode":
                            projection_mode_col = col_idx

                # Apply all instructions for this scenario
                for instruction in instructions_for_scenario:
                    row_num = instruction['row']
                    country = instruction.get('country', 'N/A')
                    self.log(f"  Row {row_num} [{country}]: {instruction['tech']} - {instruction['parameter']}")

                    success, message = self.apply_instruction_to_scenario(
                        instruction, scenario, ws, year_col_map, projection_mode_col
                    )

                    if success:
                        self.log(f"    ✓ {message}", "SUCCESS")
                    else:
                        self.log(f"    ✗ {message}", "ERROR")
                        self.rows_failed += 1

                # Save ONCE after all instructions
                self.log(f"  Saving {scenario}...")
                wb.save(scenario_path)
                wb.close()
                self.log(f"  ✓ {scenario} saved successfully")

            except Exception as e:
                self.log(f"  ✗ Error processing {scenario}: {e}", "ERROR")
                self.rows_failed += len(instructions_for_scenario)
                try:
                    wb.close()
                except:
                    pass

    def generate_olade_instructions(self, all_years):
        """
        Generate instructions from OLADE data

        Uses flat capacity values (same for all years, no growth applied).

        For PETROLEUM:
        - PET = Petroleum × Diésel share
        - OIL = Petroleum × (Fuel oil + Búnker) share

        Args:
            all_years: list of years from Secondary Techs

        Returns:
            list of instruction dicts
        """
        if not self.olade_config['enabled']:
            return []

        self.log("")
        self.log("=" * 80)
        self.log("PROCESSING OLADE DATA")
        self.log("=" * 80)
        self.log(f"Reference year: {self.olade_data['reference_year']}")
        self.log(f"Petroleum split mode: {self.olade_config.get('petroleum_split_mode', 'Split_PET_OIL')}")
        self.log("Using FLAT capacity values (same for all years)")
        self.log("")

        instructions = []

        # Generate instructions for each country and technology
        for country_iso3, techs in self.olade_data['data'].items():
            self.log(f"Processing country: {country_iso3}")
            for tech_code, base_capacity in techs.items():

                # Special handling for PETROLEUM
                if tech_code == 'PETROLEUM':
                    # Check split mode
                    split_mode = self.olade_config.get('petroleum_split_mode', 'Split_PET_OIL')

                    if split_mode == 'OIL_only':
                        # Option 1: Assign all petroleum to OIL only
                        for scenario in self.scenarios:
                            # Flat value for all years
                            oil_year_values = {year: round(base_capacity, 2) for year in all_years}

                            instruction_oil = {
                                'row': 'OLADE',
                                'scenario': scenario,
                                'country': country_iso3,
                                'tech_name': 'PWR-OIL',
                                'tech': 'OIL',
                                'parameter': 'ResidualCapacity',
                                'year_values': oil_year_values,
                                'is_olade': True
                            }
                            instructions.append(instruction_oil)

                    else:
                        # Option 2: Split petroleum into PET and OIL using shares
                        # PET = Petroleum × Diésel
                        # OIL = Petroleum × (Fuel oil + Búnker)
                        for scenario in self.scenarios:
                            pet_year_values = {}
                            oil_year_values = {}

                            for year in all_years:
                                # Get shares from shares_data
                                diesel_share = 0.0
                                fuel_oil_share = 0.0
                                bunker_share = 0.0

                                if (self.shares_data and
                                    scenario in self.shares_data and
                                    country_iso3 in self.shares_data[scenario] and
                                    year in self.shares_data[scenario][country_iso3]):

                                    year_shares = self.shares_data[scenario][country_iso3][year]
                                    diesel_share = year_shares.get('Diésel', 0.0)
                                    fuel_oil_share = year_shares.get('Fuel oil', 0.0)
                                    bunker_share = year_shares.get('Búnker', 0.0)

                                # Shares should already be normalized (sum to 1.0)
                                # PET = Petroleum × Diésel
                                # OIL = Petroleum × (Fuel oil + Búnker)
                                pet_capacity = base_capacity * diesel_share
                                oil_capacity = base_capacity * (fuel_oil_share + bunker_share)

                                pet_year_values[year] = round(pet_capacity, 2)
                                oil_year_values[year] = round(oil_capacity, 2)

                            # Create instruction for PET (Diésel)
                            instruction_pet = {
                                'row': 'OLADE',
                                'scenario': scenario,
                                'country': country_iso3,
                                'tech_name': 'PWR-PET',
                                'tech': 'PET',
                                'parameter': 'ResidualCapacity',
                                'year_values': pet_year_values,
                                'is_olade': True
                            }
                            instructions.append(instruction_pet)

                            # Create instruction for OIL (Fuel oil + Búnker)
                            instruction_oil = {
                                'row': 'OLADE',
                                'scenario': scenario,
                                'country': country_iso3,
                                'tech_name': 'PWR-OIL',
                                'tech': 'OIL',
                                'parameter': 'ResidualCapacity',
                                'year_values': oil_year_values,
                                'is_olade': True
                            }
                            instructions.append(instruction_oil)

                else:
                    # Normal handling for other technologies
                    # Flat capacity value for all years
                    year_values = {year: round(base_capacity, 2) for year in all_years}

                    # Create instruction for each scenario
                    for scenario in self.scenarios:
                        instruction = {
                            'row': 'OLADE',
                            'scenario': scenario,
                            'country': country_iso3,
                            'tech_name': f'PWR-{tech_code}',
                            'tech': tech_code,  # This will be used to match PWR technologies
                            'parameter': 'ResidualCapacity',
                            'year_values': year_values,
                            'is_olade': True
                        }
                        instructions.append(instruction)

        self.log(f"Generated {len(instructions)} OLADE instructions")
        self.log("")

        return instructions

    def save_log(self, log_path):
        """Save log to file"""
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(self.log_lines))

    def update_demand_files(self, all_years):
        """
        Update A-O_Demand.xlsx files with electricity demand from OLADE generation data

        Applies linear growth: Demand(year) = Demand(2023) × (1 + rate × (year - 2023))

        Args:
            all_years: list of years to populate
        """
        if not self.olade_config.get('demand_enabled') or not self.generation_data:
            return

        self.log("")
        self.log("=" * 80)
        self.log("UPDATING ELECTRICITY DEMAND")
        self.log("=" * 80)

        ref_year = self.generation_data['reference_year']
        growth_rates = self.olade_config.get('demand_growth_rates', {})

        self.log(f"Reference year: {ref_year}")
        self.log(f"Growth type: Linear")
        self.log("")

        demand_changes = 0

        for scenario in self.scenarios:
            demand_path = self.base_path / f"A1_Outputs_{scenario}" / "A-O_Demand.xlsx"

            if not demand_path.exists():
                self.log(f"  ✗ Demand file not found: {demand_path}", "WARNING")
                continue

            self.log(f"Processing {scenario}...")

            # Create backup
            backup_path = self.create_backup(demand_path)
            self.log(f"  Backup created: {backup_path.name}")

            try:
                wb = openpyxl.load_workbook(demand_path)

                if 'Demand_Projection' not in wb.sheetnames:
                    wb.close()
                    self.log(f"  ✗ 'Demand_Projection' sheet not found", "ERROR")
                    continue

                ws = wb['Demand_Projection']

                # Build year column map from headers
                year_col_map = {}
                for col_idx in range(1, ws.max_column + 1):
                    header = ws.cell(1, col_idx).value
                    if header and str(header).isdigit():
                        try:
                            year = int(header)
                            if 2000 <= year <= 2100:
                                year_col_map[year] = col_idx
                        except:
                            pass

                # Find and update ELC*XX02 rows
                for row_idx in range(2, ws.max_row + 1):
                    fuel_code = ws.cell(row_idx, 2).value  # Column B: Fuel/Tech

                    if not fuel_code:
                        continue

                    fuel_str = str(fuel_code).strip().upper()

                    # Check if this is an electricity demand row (ELC*XX02)
                    if fuel_str.startswith('ELC') and fuel_str.endswith('XX02') and len(fuel_str) == 11:
                        # Extract country code (positions 3-5)
                        country_code = fuel_str[3:6]

                        # Check if we have generation data for this country
                        if country_code not in self.generation_data['data']:
                            continue

                        base_demand_pj = self.generation_data['data'][country_code]
                        growth_rate = growth_rates.get(country_code, 0.02)  # Default 2%

                        self.log(f"  {country_code}: Base={base_demand_pj:.2f} PJ, Growth={growth_rate*100:.1f}%")

                        # Update each year with linear growth
                        for year in all_years:
                            if year in year_col_map:
                                # Linear growth: Demand(year) = Demand(ref_year) × (1 + rate × (year - ref_year))
                                years_diff = year - ref_year
                                demand_year = base_demand_pj * (1 + growth_rate * years_diff)
                                demand_year = round(demand_year, 2)

                                ws.cell(row_idx, year_col_map[year], demand_year)
                                demand_changes += 1

                # Save
                wb.save(demand_path)
                wb.close()
                self.log(f"  ✓ {scenario} demand updated")

            except Exception as e:
                self.log(f"  ✗ Error updating {scenario}: {e}", "ERROR")
                try:
                    wb.close()
                except:
                    pass

        self.log("")
        self.log(f"Demand updates completed: {demand_changes} values written")

    def run(self):
        """Main execution"""
        self.log("=" * 80)
        self.log("SECONDARY TECHS UPDATER")
        self.log("=" * 80)
        self.log(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.log(f"Editor file: {self.editor_path}")
        self.log("")

        try:
            # Read OLADE configuration
            self.olade_config = read_olade_config(self.editor_path)

            if self.olade_config['enabled']:
                self.log("OLADE integration: ENABLED")
                if self.olade_file_path and self.olade_file_path.exists():
                    self.log(f"OLADE file: {self.olade_file_path}")
                    try:
                        self.olade_data = read_olade_data(self.olade_file_path)
                        self.log(f"OLADE data loaded: {len(self.olade_data['data'])} countries")

                        # Load Shares data for petroleum split
                        if self.shares_file_path and self.shares_file_path.exists():
                            self.log(f"Shares file: {self.shares_file_path}")
                            try:
                                self.shares_data = read_shares_data(self.shares_file_path)
                                self.log(f"Shares data loaded: {len(self.shares_data)} scenarios")
                            except Exception as e:
                                self.log(f"ERROR loading Shares data: {e}", "ERROR")
                                self.log("Petroleum will be split 50/50 between PET and OIL", "WARNING")
                                self.shares_data = None
                        else:
                            self.log(f"WARNING: Shares file not found: {self.shares_file_path}", "WARNING")
                            self.log("Petroleum will be split 50/50 between PET and OIL", "WARNING")
                            self.shares_data = None

                    except Exception as e:
                        self.log(f"ERROR loading OLADE data: {e}", "ERROR")
                        self.log("Continuing without OLADE data...", "WARNING")
                        self.olade_config['enabled'] = False
                else:
                    self.log(f"WARNING: OLADE file not found: {self.olade_file_path}", "WARNING")
                    self.log("Continuing without OLADE data...", "WARNING")
                    self.olade_config['enabled'] = False
            else:
                self.log("OLADE integration: DISABLED")

            # Check Demand integration
            if self.olade_config.get('demand_enabled'):
                self.log("")
                self.log("Demand integration: ENABLED")
                if self.generation_file_path and self.generation_file_path.exists():
                    self.log(f"Generation file: {self.generation_file_path}")
                    try:
                        self.generation_data = read_olade_generation_data(self.generation_file_path)
                        self.log(f"Generation data loaded: {len(self.generation_data['data'])} countries")
                        self.log(f"Growth rates configured: {len(self.olade_config.get('demand_growth_rates', {}))} countries")
                    except Exception as e:
                        self.log(f"ERROR loading generation data: {e}", "ERROR")
                        self.log("Continuing without demand update...", "WARNING")
                        self.olade_config['demand_enabled'] = False
                else:
                    self.log(f"WARNING: Generation file not found: {self.generation_file_path}", "WARNING")
                    self.log("Continuing without demand update...", "WARNING")
                    self.olade_config['demand_enabled'] = False
            else:
                self.log("")
                self.log("Demand integration: DISABLED")

            self.log("")

            # Read editor file
            instructions = self.read_editor_file()

            # Get all years from first scenario to determine year range
            all_years = set()
            scenario_path = self.base_path / "A1_Outputs_BAU" / "A-O_Parametrization.xlsx"
            if scenario_path.exists():
                wb = openpyxl.load_workbook(scenario_path, data_only=True)
                if 'Secondary Techs' in wb.sheetnames:
                    ws = wb['Secondary Techs']
                    headers = [cell.value for cell in ws[1]]
                    for header in headers:
                        if header and str(header).isdigit():
                            try:
                                year = int(header)
                                if 2000 <= year <= 2100:
                                    all_years.add(year)
                            except:
                                pass
                wb.close()

            # Generate OLADE instructions if enabled
            olade_instructions = []
            if self.olade_config['enabled'] and self.olade_data:
                olade_instructions = self.generate_olade_instructions(sorted(all_years))

            # Combine instructions: OLADE takes priority for ResidualCapacity
            # Filter out manual ResidualCapacity instructions for PWR techs if OLADE is enabled
            if olade_instructions:
                filtered_instructions = []
                for instr in instructions:
                    # Check if this is a ResidualCapacity instruction for a PWR tech
                    if (instr.get('parameter') == 'ResidualCapacity' and
                        instr.get('tech') and str(instr.get('tech')).upper().startswith('PWR')):
                        # Skip it - OLADE will handle it
                        self.log(f"Skipping manual ResidualCapacity for {instr['tech']} - using OLADE data", "DEBUG")
                        continue
                    filtered_instructions.append(instr)
                instructions = filtered_instructions + olade_instructions
            else:
                # No OLADE, use manual instructions as-is
                pass

            if not instructions:
                self.log("No data found to process. Nothing to update.", "WARNING")
                return 0

            # Apply instructions in batch mode (one file open per scenario)
            self.apply_instructions_batch(instructions)

            # Update demand files if enabled
            if self.olade_config.get('demand_enabled') and self.generation_data:
                self.update_demand_files(sorted(all_years))

            # Summary
            self.log("")
            self.log("=" * 80)
            self.log("SUMMARY")
            self.log("=" * 80)
            self.log(f"Total instructions processed: {len(instructions)}")
            self.log(f"Changes applied: {self.changes_applied}")
            self.log(f"Rows failed: {self.rows_failed}")

            # Save log
            log_path = self.base_path / f"secondary_techs_update_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            self.save_log(log_path)
            self.log(f"\nLog saved: {log_path}")

            if self.rows_failed > 0:
                self.log("\n⚠ Some rows failed. Please review the log.", "WARNING")
                return 1
            else:
                self.log("\n✓ All changes applied successfully!", "SUCCESS")
                return 0

        except Exception as e:
            self.log(f"\nFATAL ERROR: {e}", "ERROR")
            import traceback
            traceback.print_exc()
            return 1


def main():
    try:
        # Paths
        script_dir = Path(__file__).parent
        editor_path = script_dir / "Secondary_Techs_Editor.xlsx"
        base_path = script_dir / "A1_Outputs"
        olade_file_path = script_dir / "Capacidad instalada por fuente - Anual - OLADE.xlsx"
        shares_file_path = script_dir / "Shares.xlsx"
        generation_file_path = script_dir / "Generación eléctrica por fuente - Anual - OLADE.xlsx"

        # Create updater and run
        updater = SecondaryTechsUpdater(editor_path, base_path, olade_file_path, shares_file_path, generation_file_path)
        return updater.run()

    except Exception as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
