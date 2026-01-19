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
# Barbados uses BRB (ISO-3166 standard code)
OLADE_COUNTRY_MAPPING = {
    'Argentina': 'ARG',
    'Barbados': 'BRB',
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
    'Gas natural': 'NGS',  # NGS is the unified natural gas code (CCG+OCG were merged into NGS)
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
        dict with config: {enabled, petroleum_split_mode, demand_enabled, activity_lower_limit_enabled,
                          activity_upper_limit_enabled, demand_growth_rates, scenarios_demand_adjustments,
                          renewability_targets, technology_weights}
    """
    wb = openpyxl.load_workbook(editor_path, data_only=True)

    if 'OLADE_Config' not in wb.sheetnames:
        wb.close()
        return {
            'enabled': False,
            'petroleum_split_mode': 'Split_PET_OIL',
            'demand_enabled': False,
            'activity_lower_limit_enabled': False,
            'activity_upper_limit_enabled': False,
            'demand_growth_rates': {},
            'scenarios_demand_adjustments': {},
            'renewability_targets': {},
            'technology_weights': {}
        }

    ws = wb['OLADE_Config']

    # Read configuration values
    # Row 5 = ResidualCapacitiesFromOLADE, Row 6 = PetroleumSplitMode, Row 7 = DemandFromOLADE
    # Row 8 = ActivityLowerLimitFromOLADE, Row 9 = ActivityUpperLimitFromOLADE
    enabled = str(ws['B5'].value).upper() == 'YES' if ws['B5'].value else False
    petroleum_split_mode = str(ws['B6'].value) if ws['B6'].value else 'Split_PET_OIL'
    demand_enabled = str(ws['B7'].value).upper() == 'YES' if ws['B7'].value else False
    activity_lower_limit_enabled = str(ws['B8'].value).upper() == 'YES' if ws['B8'].value else False
    activity_upper_limit_enabled = str(ws['B9'].value).upper() == 'YES' if ws['B9'].value else False

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

    # Read renewability targets from Renewability_Targets sheet
    # Structure: {(country, scenario): {'interpolation': str, 'targets': {year: percentage}}}
    renewability_targets = {}
    if 'Renewability_Targets' in wb.sheetnames:
        ws_renew = wb['Renewability_Targets']
        # Get year columns from header (row 5)
        year_cols = {}
        for col_idx in range(4, ws_renew.max_column + 1):
            header = ws_renew.cell(5, col_idx).value
            if header and str(header).isdigit():
                year_cols[int(header)] = col_idx

        # Data starts at row 6
        for row_idx in range(6, ws_renew.max_row + 1):
            country = ws_renew.cell(row_idx, 1).value
            scenario = ws_renew.cell(row_idx, 2).value
            interpolation = ws_renew.cell(row_idx, 3).value

            if not country or not scenario:
                continue

            country_str = str(country).strip().upper()
            scenario_str = str(scenario).strip()
            interpolation_str = str(interpolation).strip().lower() if interpolation else 'flat_step'

            targets = {}
            for year, col_idx in year_cols.items():
                value = ws_renew.cell(row_idx, col_idx).value
                if value is not None:
                    try:
                        # Value might be percentage (0.5) or decimal (50)
                        pct = float(value)
                        if pct > 1:  # Assume it's a percentage like 50 instead of 0.5
                            pct = pct / 100.0
                        targets[year] = pct
                    except (ValueError, TypeError):
                        pass

            if targets:  # Only add if there are any targets defined
                renewability_targets[(country_str, scenario_str)] = {
                    'interpolation': interpolation_str,
                    'targets': targets
                }

    # Read scenario-specific demand growth adjustments from Scenarios_Demand_Growth sheet
    # Structure: {(country, scenario): {year: adjustment_percentage}}
    scenarios_demand_adjustments = {}
    if 'Scenarios_Demand_Growth' in wb.sheetnames:
        ws_scen_demand = wb['Scenarios_Demand_Growth']
        # Get year columns from header (row 5)
        year_cols = {}
        for col_idx in range(3, ws_scen_demand.max_column + 1):
            header = ws_scen_demand.cell(5, col_idx).value
            if header and str(header).isdigit():
                year_cols[int(header)] = col_idx

        # Data starts at row 6
        for row_idx in range(6, ws_scen_demand.max_row + 1):
            country = ws_scen_demand.cell(row_idx, 1).value
            scenario = ws_scen_demand.cell(row_idx, 2).value

            if not country or not scenario:
                continue

            country_str = str(country).strip().upper()
            scenario_str = str(scenario).strip()

            adjustments = {}
            for year, col_idx in year_cols.items():
                value = ws_scen_demand.cell(row_idx, col_idx).value
                if value is not None:
                    try:
                        # Value is stored as percentage (e.g., 0.05 for 5%)
                        # Convert to decimal if needed
                        adj_pct = float(value)
                        # If value > 1, assume it's like 5 instead of 0.05
                        if abs(adj_pct) > 1:
                            adj_pct = adj_pct / 100.0
                        adjustments[year] = adj_pct
                    except (ValueError, TypeError):
                        pass

            if adjustments:  # Only add if there are any adjustments defined
                scenarios_demand_adjustments[(country_str, scenario_str)] = adjustments

    # Read technology weights from Technology_Weights sheet (formerly Renewable_Weights)
    # Structure: {(country, scenario): {'renewable': {'HYD': w, ...}, 'non_renewable': {'COA': w, ...}}}
    technology_weights = {}
    weights_sheet_name = 'Technology_Weights' if 'Technology_Weights' in wb.sheetnames else 'Renewable_Weights'
    if weights_sheet_name in wb.sheetnames:
        ws_weights = wb[weights_sheet_name]

        # Find header row (contains 'Country')
        header_row = None
        for row_idx in range(1, min(15, ws_weights.max_row + 1)):
            if ws_weights.cell(row_idx, 1).value == 'Country':
                header_row = row_idx
                break

        if header_row:
            # Get column indices for each technology from header
            tech_cols = {}
            for col_idx in range(3, ws_weights.max_column + 1):
                header = ws_weights.cell(header_row, col_idx).value
                if header:
                    tech_cols[str(header).strip().upper()] = col_idx

            renewable_techs = ['HYD', 'SPV', 'WND', 'GEO', 'BIO']
            non_renewable_techs = ['COA', 'PET', 'NGS', 'URN', 'OIL']

            # Data starts after header row
            for row_idx in range(header_row + 1, ws_weights.max_row + 1):
                country = ws_weights.cell(row_idx, 1).value
                scenario = ws_weights.cell(row_idx, 2).value

                if not country or not scenario:
                    continue

                country_str = str(country).strip().upper()
                scenario_str = str(scenario).strip()

                renewable_weights = {}
                non_renewable_weights = {}
                has_weights = False

                for tech, col_idx in tech_cols.items():
                    value = ws_weights.cell(row_idx, col_idx).value
                    if value is not None:
                        try:
                            weight = float(value)
                            if tech in renewable_techs:
                                renewable_weights[tech] = weight
                            elif tech in non_renewable_techs:
                                non_renewable_weights[tech] = weight
                            has_weights = True
                        except (ValueError, TypeError):
                            pass

                if has_weights:
                    technology_weights[(country_str, scenario_str)] = {
                        'renewable': renewable_weights,
                        'non_renewable': non_renewable_weights
                    }

    wb.close()

    return {
        'enabled': enabled,
        'petroleum_split_mode': petroleum_split_mode,
        'demand_enabled': demand_enabled,
        'activity_lower_limit_enabled': activity_lower_limit_enabled,
        'activity_upper_limit_enabled': activity_upper_limit_enabled,
        'demand_growth_rates': demand_growth_rates,
        'scenarios_demand_adjustments': scenarios_demand_adjustments,
        'renewability_targets': renewability_targets,
        'technology_weights': technology_weights
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
        'Barbados': 'BRB',
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
            },
            'tech_shares': {
                country_iso3: {
                    tech_code: share_value
                }
            }
        }
    """
    if not generation_file_path.exists():
        raise FileNotFoundError(f"OLADE generation file not found: {generation_file_path}")

    wb = openpyxl.load_workbook(generation_file_path, data_only=True)
    ws = wb['1.2023']

    ref_year = 2023  # Reference year

    # Technology row mapping (OLADE row -> model tech code)
    # Row 6: Nuclear
    # Row 8: Petróleo y derivados (will be mapped to OIL+PET combined as 'PETROLEUM')
    # Row 9: Gas natural
    # Row 10: Carbón mineral
    # Row 13: Biogás
    # Row 14: Biomasa sólida
    # Row 15: Biocombustibles líquidos
    # Row 17: Hidro
    # Row 18: Geotermia
    # Row 19: Eólica
    # Row 20: Solar
    # Row 21: Total

    tech_row_mapping = {
        6: 'URN',      # Nuclear
        8: 'PETROLEUM', # Petróleo y derivados (combined PET+OIL)
        9: 'NGS',      # Gas natural
        10: 'COA',     # Carbón mineral
        13: 'BIO',     # Biogás (will be summed with biomass)
        14: 'BIO',     # Biomasa sólida
        15: 'BIO',     # Biocombustibles líquidos
        17: 'HYD',     # Hidro
        18: 'GEO',     # Geotermia
        19: 'WON',     # Eólica
        20: 'SPV',     # Solar
    }

    # Get country columns from row 5 (starting at column 3)
    country_columns = {}
    for col_idx in range(3, ws.max_column + 1):
        country_name = ws.cell(5, col_idx).value
        if country_name and str(country_name) in OLADE_COUNTRY_MAPPING:
            iso3_code = OLADE_COUNTRY_MAPPING[str(country_name)]
            country_columns[col_idx] = iso3_code

    # Read Total generation from row 21 and individual technologies
    data = {}
    tech_shares = {}

    for col_idx, country_iso3 in country_columns.items():
        total_gwh = ws.cell(21, col_idx).value  # Row 21 = "Total"

        if total_gwh is not None and total_gwh != '':
            try:
                generation_gwh = float(total_gwh)
                # Convert from GWh to PJ (1 GWh = 0.0036 PJ)
                generation_pj = generation_gwh * 0.0036
                data[country_iso3] = generation_pj

                # Calculate technology shares for this country
                tech_generation = {}
                for row_idx, tech_code in tech_row_mapping.items():
                    tech_gwh = ws.cell(row_idx, col_idx).value
                    if tech_gwh is not None and tech_gwh != '':
                        try:
                            tech_gwh_float = float(tech_gwh)
                            # Accumulate for technologies that are summed (e.g., BIO)
                            if tech_code in tech_generation:
                                tech_generation[tech_code] += tech_gwh_float
                            else:
                                tech_generation[tech_code] = tech_gwh_float
                        except (ValueError, TypeError):
                            pass

                # Calculate shares (percentage of total generation)
                tech_shares[country_iso3] = {}
                if generation_gwh > 0:
                    for tech_code, tech_gwh_value in tech_generation.items():
                        share = tech_gwh_value / generation_gwh
                        tech_shares[country_iso3][tech_code] = share

            except ValueError:
                pass

    wb.close()

    return {
        'reference_year': ref_year,
        'data': data,
        'tech_shares': tech_shares
    }


def read_shares_total_data(shares_total_path):
    """
    Read Shares_Total.xlsx file to get technology shares by scenario, country, technology, and year

    The file has a structure where countries are followed by their technology rows.
    Technologies in Shares_Total are mapped to model tech codes:
    - Biomasa → BIO
    - Búnker + Fuel oil → OIL
    - Carbón → COA
    - Diésel → PET
    - Eólica → WON
    - Gas natural → NGS (not CCG, since NGS is the generic natural gas code)
    - Geotérmica → GEO
    - Hidroeléctrica → HYD
    - Nuclear → URN
    - Solar (GD) + Solar (gran escala) → SPV

    Returns:
        dict: {
            scenario: {
                country_iso3: {
                    tech_code: {
                        year: share_value
                    }
                }
            }
        }
    """
    if not shares_total_path.exists():
        raise FileNotFoundError(f"Shares_Total file not found: {shares_total_path}")

    wb = openpyxl.load_workbook(shares_total_path, data_only=True)

    shares_data = {}

    # Map sheet names to scenario codes
    sheet_scenario_map = {
        'SharesBAU': 'BAU',
        'SharesNDC': 'NDC',
        'SharesNDC_NoRPO': 'NDC_NoRPO',
        'SharesNDC+ELC': 'NDC+ELC'
    }

    # Map country names from Shares_Total to model ISO3 codes
    shares_country_to_iso3 = {
        'Barbados': 'BRB',
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

    # Map Shares_Total technology names to model tech codes
    # Note: Some technologies are combined (e.g., Búnker + Fuel oil → OIL)
    shares_tech_to_code = {
        'Biomasa': 'BIO',
        'Búnker': 'OIL',      # Combined with Fuel oil
        'Carbón': 'COA',
        'Diésel': 'PET',
        'Eólica': 'WON',
        'Fuel oil': 'OIL',    # Combined with Búnker
        'Gas natural': 'NGS',
        'Geotérmica': 'GEO',
        'Hidroeléctrica': 'HYD',
        'Nuclear': 'URN',
        'Solar (GD)': 'SPV',        # Combined with Solar (gran escala)
        'Solar (gran escala)': 'SPV'  # Combined with Solar (GD)
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

            # If we have a current country, check for technology rows
            if current_country_iso3 and cell_str in shares_tech_to_code:
                tech_code = shares_tech_to_code[cell_str]

                # Initialize tech_code dict if not exists
                if tech_code not in shares_data[scenario_code][current_country_iso3]:
                    shares_data[scenario_code][current_country_iso3][tech_code] = {}

                # Read shares for all years
                for col_idx, year in years:
                    share_value = ws.cell(row_idx, col_idx).value

                    if share_value is not None:
                        try:
                            share_float = float(share_value)
                            # For combined techs (OIL, SPV), sum the values
                            if year in shares_data[scenario_code][current_country_iso3][tech_code]:
                                shares_data[scenario_code][current_country_iso3][tech_code][year] += share_float
                            else:
                                shares_data[scenario_code][current_country_iso3][tech_code][year] = share_float
                        except (ValueError, TypeError):
                            if year not in shares_data[scenario_code][current_country_iso3][tech_code]:
                                shares_data[scenario_code][current_country_iso3][tech_code][year] = 0.0
                    else:
                        if year not in shares_data[scenario_code][current_country_iso3][tech_code]:
                            shares_data[scenario_code][current_country_iso3][tech_code][year] = 0.0

            row_idx += 1

    wb.close()
    return shares_data


class SecondaryTechsUpdater:
    def __init__(self, editor_path, base_path, olade_file_path=None, shares_file_path=None, generation_file_path=None, shares_total_file_path=None):
        self.editor_path = editor_path
        self.base_path = base_path
        self.olade_file_path = olade_file_path
        self.shares_file_path = shares_file_path
        self.generation_file_path = generation_file_path
        self.shares_total_file_path = shares_total_file_path
        self.scenarios = ["BAU", "NDC", "NDC+ELC", "NDC_NoRPO"]
        self.log_lines = []
        self.changes_applied = 0
        self.rows_failed = 0
        self.olade_config = None
        self.olade_data = None
        self.shares_data = None
        self.generation_data = None
        self.shares_total_data = None

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
        max_capacity_rows = {}  # {full_tech_code: row_idx} for TotalAnnualMaxCapacity

        for row_idx in range(2, ws.max_row + 1):
            row_tech = ws.cell(row_idx, 2).value  # Column 2: Tech
            row_param = ws.cell(row_idx, 5).value  # Column 5: Parameter

            if not row_tech or not row_param:
                continue

            row_tech_str = str(row_tech).strip()
            row_param_str = str(row_param).strip()

            # Track TotalAnnualMaxCapacity rows for constraint checking
            if row_param_str == 'TotalAnnualMaxCapacity':
                max_capacity_rows[row_tech_str.upper()] = row_idx

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
                        target_rows.append((row_idx, row_tech_str.upper()))
            else:
                # Exact match for manual instructions
                if row_tech_str == tech:
                    target_rows.append((row_idx, row_tech_str.upper()))

        if not target_rows:
            tech_desc = f"Tech type='{tech}' Country='{country}'" if is_olade else f"Tech='{tech}'"
            return False, f"No matching row found for {tech_desc} and Parameter='{parameter}'", 0

        # Update year values for all matching rows
        total_values_updated = 0
        rows_updated = []
        capped_count = 0

        for target_row, full_tech_code in target_rows:
            values_updated = 0

            # For ResidualCapacity, check against TotalAnnualMaxCapacity constraint
            max_cap_row = max_capacity_rows.get(full_tech_code) if parameter == 'ResidualCapacity' else None

            for year, value in year_values.items():
                if year in year_col_map:
                    col_idx = year_col_map[year]
                    final_value = value

                    # Check ResidualCapacity <= TotalAnnualMaxCapacity constraint
                    if max_cap_row and parameter == 'ResidualCapacity':
                        max_cap_value = ws.cell(max_cap_row, col_idx).value
                        if max_cap_value is not None:
                            try:
                                max_cap = float(max_cap_value)
                                if value > max_cap:
                                    # Cap ResidualCapacity to TotalAnnualMaxCapacity
                                    final_value = max_cap
                                    capped_count += 1
                            except (ValueError, TypeError):
                                pass

                    ws.cell(target_row, col_idx, final_value)
                    values_updated += 1

            # Set Projection.Mode to "User defined" if column exists
            if projection_mode_col:
                current_value = ws.cell(target_row, projection_mode_col).value
                if current_value != "User defined":
                    ws.cell(target_row, projection_mode_col, "User defined")

            total_values_updated += values_updated
            rows_updated.append(target_row)

        capped_msg = f" ({capped_count} capped to MaxCapacity)" if capped_count > 0 else ""
        if len(rows_updated) > 1:
            return True, f"Rows {rows_updated} updated with {total_values_updated} total year values{capped_msg}", total_values_updated
        else:
            return True, f"Row {rows_updated[0]} updated with {total_values_updated} year values{capped_msg}", total_values_updated

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

                # Store initial row count for validation
                initial_row_count = ws.max_row

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

                # Validate row count before saving
                final_row_count = ws.max_row
                if final_row_count != initial_row_count:
                    self.log(f"  ⚠ WARNING: Row count changed from {initial_row_count} to {final_row_count}!", "WARNING")

                # Save ONCE after all instructions
                self.log(f"  Saving {scenario}...")
                wb.save(scenario_path)
                wb.close()
                self.log(f"  ✓ {scenario} saved successfully (rows: {final_row_count})")

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
                            # Flat value for all years (6 decimals to preserve small values)
                            oil_year_values = {year: round(base_capacity, 6) for year in all_years}

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

                                # Use 6 decimals to preserve small capacity values
                                pet_year_values[year] = round(pet_capacity, 6)
                                oil_year_values[year] = round(oil_capacity, 6)

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
                    # Flat capacity value for all years (6 decimals to preserve small values)
                    year_values = {year: round(base_capacity, 6) for year in all_years}

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

                # Find existing ELC*XX02 country codes and their row indices
                # Format: ELC + country(3) + XX02 = 10 characters (e.g., ELCARGXX02)
                existing_countries = {}  # {country_code: row_idx}
                for row_idx in range(2, ws.max_row + 1):
                    fuel_code = ws.cell(row_idx, 2).value
                    if fuel_code:
                        fuel_str = str(fuel_code).strip().upper()
                        if fuel_str.startswith('ELC') and fuel_str.endswith('XX02') and len(fuel_str) == 10:
                            country_code = fuel_str[3:6]
                            existing_countries[country_code] = row_idx

                # Update existing ELC*XX02 rows with generation data
                for country_code, row_idx in existing_countries.items():
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

                            # Apply scenario-specific demand adjustment if defined
                            # Formula: Demand(scenario, year) = Base_Demand(year) × (1 + adjustment_percentage)
                            adjustments_dict = self.olade_config.get('scenarios_demand_adjustments', {})
                            adjustment_key = (country_code, scenario)
                            if adjustment_key in adjustments_dict:
                                year_adjustments = adjustments_dict[adjustment_key]
                                if year in year_adjustments:
                                    adjustment_pct = year_adjustments[year]
                                    demand_year = demand_year * (1 + adjustment_pct)

                            demand_year = round(demand_year, 2)

                            ws.cell(row_idx, year_col_map[year], demand_year)
                            demand_changes += 1

                # Add missing countries that have generation data but aren't in the sheet
                missing_countries = set(self.generation_data['data'].keys()) - set(existing_countries.keys())
                if missing_countries:
                    self.log(f"  Adding missing countries: {', '.join(sorted(missing_countries))}")

                    # Get column positions for fixed columns
                    # Headers: Demand/Share, Fuel/Tech, Name, Ref.Cap.BY, Ref.OAR.BY, Ref.km.BY, Projection.Mode, Projection.Parameter, [years...]
                    fixed_col_map = {}
                    for col_idx in range(1, ws.max_column + 1):
                        header = ws.cell(1, col_idx).value
                        if header:
                            fixed_col_map[str(header)] = col_idx

                    # Add a row for each missing country
                    for country_code in sorted(missing_countries):
                        base_demand_pj = self.generation_data['data'][country_code]
                        growth_rate = growth_rates.get(country_code, 0.02)

                        # Find country name from OLADE mapping
                        country_name = None
                        for name, code in OLADE_COUNTRY_MAPPING.items():
                            if code == country_code:
                                country_name = name
                                break

                        # Create new row
                        new_row = ws.max_row + 1
                        fuel_code = f"ELC{country_code}XX02"

                        ws.cell(new_row, fixed_col_map.get('Demand/Share', 1), 'Demand')
                        ws.cell(new_row, fixed_col_map.get('Fuel/Tech', 2), fuel_code)
                        ws.cell(new_row, fixed_col_map.get('Name', 3), f"Output demand of transmission lines in {country_name or country_code}")
                        ws.cell(new_row, fixed_col_map.get('Ref.Cap.BY', 4), 'not needed')
                        ws.cell(new_row, fixed_col_map.get('Ref.OAR.BY', 5), 'not needed')
                        ws.cell(new_row, fixed_col_map.get('Ref.km.BY', 6), 'not needed')
                        ws.cell(new_row, fixed_col_map.get('Projection.Mode', 7), 'User defined')
                        ws.cell(new_row, fixed_col_map.get('Projection.Parameter', 8), 0)

                        self.log(f"  + {country_code}: Base={base_demand_pj:.2f} PJ, Growth={growth_rate*100:.1f}%")

                        # Add year values
                        for year in all_years:
                            if year in year_col_map:
                                years_diff = year - ref_year
                                demand_year = base_demand_pj * (1 + growth_rate * years_diff)

                                # Apply scenario-specific demand adjustment if defined
                                adjustments_dict = self.olade_config.get('scenarios_demand_adjustments', {})
                                adjustment_key = (country_code, scenario)
                                if adjustment_key in adjustments_dict:
                                    year_adjustments = adjustments_dict[adjustment_key]
                                    if year in year_adjustments:
                                        adjustment_pct = year_adjustments[year]
                                        demand_year = demand_year * (1 + adjustment_pct)

                                demand_year = round(demand_year, 2)

                                ws.cell(new_row, year_col_map[year], demand_year)
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

    def calculate_technology_shares(self, country_code, scenario, all_years):
        """
        Calculate technology shares for each year based on renewability targets.

        Uses OLADE base year data and interpolates to reach renewability targets.
        Renewable techs: HYD, SPV, WND, GEO, BIO
        Non-renewable techs: COA, NGS, OIL, PET, URN

        Args:
            country_code: ISO3 country code
            scenario: Scenario name (BAU, NDC, etc.)
            all_years: list of years

        Returns:
            dict: {tech_type: {year: share}} for all technologies
        """
        renewable_techs = ['HYD', 'SPV', 'WND', 'GEO', 'BIO']
        non_renewable_techs = ['COA', 'NGS', 'OIL', 'PET', 'URN']

        # Get renewability target configuration for this country/scenario
        target_key = (country_code, scenario)
        target_config = self.olade_config.get('renewability_targets', {}).get(target_key)

        # Get custom weights if defined (new structure: {'renewable': {...}, 'non_renewable': {...}})
        custom_weights = self.olade_config.get('technology_weights', {}).get(target_key)

        # Get base year shares from OLADE (via shares_total_data)
        if scenario not in self.shares_total_data or country_code not in self.shares_total_data[scenario]:
            return {}

        base_shares = self.shares_total_data[scenario][country_code]

        # If no renewability targets defined, use original shares_total_data
        if not target_config:
            return base_shares

        # Get target years and values
        targets = target_config['targets']  # {year: renewable_percentage}
        interpolation = target_config['interpolation']  # 'linear' or 'flat_step'

        # Find base year (first year in all_years that has OLADE data)
        ref_year = self.generation_data['reference_year']
        base_year = min(all_years) if all_years else ref_year

        # Get base year shares from OLADE direct calculations (tech_shares)
        # These are the actual percentages calculated from OLADE generation data for 2023
        olade_tech_shares = {}
        if 'tech_shares' in self.generation_data and country_code in self.generation_data['tech_shares']:
            olade_tech_shares = self.generation_data['tech_shares'][country_code]

        # Calculate base renewable share from OLADE direct data
        # Note: OLADE uses 'PETROLEUM' (combined PET+OIL), so we need to handle this
        if olade_tech_shares:
            # Use OLADE direct shares for base year
            base_renewable_share = 0.0
            for tech in renewable_techs:
                base_renewable_share += olade_tech_shares.get(tech, 0.0)

            base_non_renewable_share = 1.0 - base_renewable_share
        else:
            # Fallback to Shares_Total if OLADE data not available
            base_renewable_share = sum(base_shares.get(tech, {}).get(base_year, 0.0) for tech in renewable_techs)
            base_non_renewable_share = 1.0 - base_renewable_share

        # Calculate renewable tech proportions (for distributing renewable target)
        if custom_weights and custom_weights.get('renewable'):
            # Use custom renewable weights
            renewable_proportions = custom_weights['renewable']
            # Normalize if needed
            total_weight = sum(renewable_proportions.values())
            if total_weight > 0 and abs(total_weight - 1.0) > 0.001:
                renewable_proportions = {k: v / total_weight for k, v in renewable_proportions.items()}
        else:
            # Use proportional distribution based on OLADE direct data
            if olade_tech_shares:
                total_renewable = sum(olade_tech_shares.get(tech, 0.0) for tech in renewable_techs)
                if total_renewable > 0:
                    renewable_proportions = {
                        tech: olade_tech_shares.get(tech, 0.0) / total_renewable
                        for tech in renewable_techs
                    }
                else:
                    # Default equal distribution if no renewable data
                    renewable_proportions = {tech: 1.0 / len(renewable_techs) for tech in renewable_techs}
            else:
                # Fallback to Shares_Total
                total_renewable = sum(base_shares.get(tech, {}).get(base_year, 0.0) for tech in renewable_techs)
                if total_renewable > 0:
                    renewable_proportions = {
                        tech: base_shares.get(tech, {}).get(base_year, 0.0) / total_renewable
                        for tech in renewable_techs
                    }
                else:
                    # Default equal distribution if no renewable data
                    renewable_proportions = {tech: 1.0 / len(renewable_techs) for tech in renewable_techs}

        # Calculate non-renewable tech proportions (for distributing non-renewable portion)
        if custom_weights and custom_weights.get('non_renewable'):
            # Use custom non-renewable weights
            non_renewable_proportions = custom_weights['non_renewable']
            # Normalize if needed
            total_weight = sum(non_renewable_proportions.values())
            if total_weight > 0 and abs(total_weight - 1.0) > 0.001:
                non_renewable_proportions = {k: v / total_weight for k, v in non_renewable_proportions.items()}
        else:
            # Use proportional distribution based on OLADE direct data
            # Note: OLADE has 'PETROLEUM' instead of separate 'PET' and 'OIL'
            # We need to handle this specially
            if olade_tech_shares:
                # Build non-renewable shares, handling PETROLEUM specially
                non_renewable_shares = {}
                for tech in non_renewable_techs:
                    if tech in ['PET', 'OIL']:
                        # Split PETROLEUM between PET and OIL
                        # Use Shares_Total.xlsx to get the split ratio for base year
                        petroleum_share = olade_tech_shares.get('PETROLEUM', 0.0)
                        if petroleum_share > 0:
                            # Get PET and OIL shares from Shares_Total for the split ratio
                            pet_share_total = base_shares.get('PET', {}).get(base_year, 0.0)
                            oil_share_total = base_shares.get('OIL', {}).get(base_year, 0.0)
                            total_petroleum_shares = pet_share_total + oil_share_total

                            if total_petroleum_shares > 0:
                                # Split proportionally based on Shares_Total
                                if tech == 'PET':
                                    non_renewable_shares[tech] = petroleum_share * (pet_share_total / total_petroleum_shares)
                                else:  # OIL
                                    non_renewable_shares[tech] = petroleum_share * (oil_share_total / total_petroleum_shares)
                            else:
                                # Default 50/50 split
                                non_renewable_shares[tech] = petroleum_share * 0.5
                        else:
                            non_renewable_shares[tech] = 0.0
                    else:
                        non_renewable_shares[tech] = olade_tech_shares.get(tech, 0.0)

                total_non_renewable = sum(non_renewable_shares.values())
                if total_non_renewable > 0:
                    non_renewable_proportions = {
                        tech: non_renewable_shares[tech] / total_non_renewable
                        for tech in non_renewable_techs
                    }
                else:
                    # Default equal distribution if no non-renewable data
                    non_renewable_proportions = {tech: 1.0 / len(non_renewable_techs) for tech in non_renewable_techs}
            else:
                # Fallback to Shares_Total
                total_non_renewable = sum(base_shares.get(tech, {}).get(base_year, 0.0) for tech in non_renewable_techs)
                if total_non_renewable > 0:
                    non_renewable_proportions = {
                        tech: base_shares.get(tech, {}).get(base_year, 0.0) / total_non_renewable
                        for tech in non_renewable_techs
                    }
                else:
                    # Default equal distribution if no non-renewable data
                    non_renewable_proportions = {tech: 1.0 / len(non_renewable_techs) for tech in non_renewable_techs}

        # Sort target years
        sorted_target_years = sorted(targets.keys())

        # Build the interpolated shares for each year
        result = {tech: {} for tech in renewable_techs + non_renewable_techs}

        for year in all_years:
            # Determine renewable percentage for this year
            if year <= base_year:
                # Use base year values
                renewable_pct = base_renewable_share
            elif not sorted_target_years:
                # No targets, use base
                renewable_pct = base_renewable_share
            else:
                # Find where this year falls relative to targets
                if year >= sorted_target_years[-1]:
                    # Beyond last target, use last target value
                    renewable_pct = targets[sorted_target_years[-1]]
                else:
                    # Find the surrounding target years
                    prev_year = base_year
                    prev_pct = base_renewable_share
                    next_year = None
                    next_pct = None

                    for ty in sorted_target_years:
                        if ty <= year:
                            prev_year = ty
                            prev_pct = targets[ty]
                        else:
                            next_year = ty
                            next_pct = targets[ty]
                            break

                    if next_year is None:
                        renewable_pct = prev_pct
                    elif interpolation == 'linear':
                        # Linear interpolation
                        if next_year != prev_year:
                            ratio = (year - prev_year) / (next_year - prev_year)
                            renewable_pct = prev_pct + ratio * (next_pct - prev_pct)
                        else:
                            renewable_pct = prev_pct
                    else:  # flat_step
                        # Keep flat until target year, then step
                        renewable_pct = prev_pct

            # Distribute renewable percentage among renewable techs
            for tech in renewable_techs:
                tech_share = renewable_pct * renewable_proportions.get(tech, 0.0)
                result[tech][year] = tech_share

            # Distribute non-renewable percentage among non-renewable techs
            non_renewable_pct = 1.0 - renewable_pct
            for tech in non_renewable_techs:
                tech_share = non_renewable_pct * non_renewable_proportions.get(tech, 0.0)
                result[tech][year] = tech_share

        return result

    def update_activity_limits(self, all_years):
        """
        Update TotalTechnologyAnnualActivityLowerLimit and/or TotalTechnologyAnnualActivityUpperLimit
        in A-O_Parametrization.xlsx files.

        Uses renewability targets from Renewability_Targets sheet to calculate shares.
        Formula: Generation_OLADE × (1 + growth_rate × (year - ref_year)) × Share_technology
        UpperLimit = LowerLimit + 0.1

        IMPORTANT: LowerLimit is capped to ensure it doesn't exceed what the MaxCapacity can produce.
        MaxPossibleActivity = MaxCapacity × CapacityToActivityUnit × AvailabilityFactor × sum(CapacityFactor × YearSplit)

        Args:
            all_years: list of years to populate
        """
        update_lower = self.olade_config.get('activity_lower_limit_enabled', False)
        update_upper = self.olade_config.get('activity_upper_limit_enabled', False)

        if not update_lower and not update_upper:
            return

        if not self.generation_data:
            self.log("Cannot update Activity Limits: Missing generation data", "WARNING")
            return

        self.log("")
        self.log("=" * 80)
        self.log("UPDATING ACTIVITY LIMITS")
        self.log("=" * 80)

        ref_year = self.generation_data['reference_year']
        growth_rates = self.olade_config.get('demand_growth_rates', {})
        renewability_targets = self.olade_config.get('renewability_targets', {})

        self.log(f"Reference year: {ref_year}")
        self.log(f"Update LowerLimit: {'YES' if update_lower else 'NO'}")
        self.log(f"Update UpperLimit: {'YES' if update_upper else 'NO'}")
        self.log(f"Renewability targets defined for: {len(renewability_targets)} country/scenario combinations")
        self.log("LowerLimit will be capped based on MaxCapacity constraints")
        self.log("")

        activity_changes = 0
        capped_values = 0

        for scenario in self.scenarios:
            param_path = self.base_path / f"A1_Outputs_{scenario}" / "A-O_Parametrization.xlsx"

            if not param_path.exists():
                self.log(f"  ✗ Parametrization file not found: {param_path}", "WARNING")
                continue

            self.log(f"Processing {scenario}...")

            # Create backup before modifying
            backup_path = self.create_backup(param_path)
            self.log(f"  Backup created: {backup_path.name}")

            try:
                wb = openpyxl.load_workbook(param_path)

                if 'Secondary Techs' not in wb.sheetnames:
                    wb.close()
                    self.log(f"  ✗ 'Secondary Techs' sheet not found", "ERROR")
                    continue

                ws = wb['Secondary Techs']

                # Store initial row count for validation
                initial_row_count = ws.max_row
                self.log(f"  Initial row count: {initial_row_count}")

                # Build year column map from headers
                year_col_map = {}
                projection_mode_col = None
                headers = [cell.value for cell in ws[1]]

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

                # Build index of rows by tech and parameter
                lower_limit_rows = {}  # {tech_code: row_idx}
                upper_limit_rows = {}  # {tech_code: row_idx}
                max_capacity_rows = {}  # {tech_code: row_idx}
                residual_capacity_rows = {}  # {tech_code: row_idx}
                availability_rows = {}  # {tech_code: row_idx}

                for row_idx in range(2, ws.max_row + 1):
                    tech_code = ws.cell(row_idx, 2).value
                    parameter = ws.cell(row_idx, 5).value
                    if tech_code and parameter:
                        tech_str = str(tech_code).strip().upper()
                        param_str = str(parameter).strip()
                        if param_str == 'TotalTechnologyAnnualActivityLowerLimit':
                            lower_limit_rows[tech_str] = row_idx
                        elif param_str == 'TotalTechnologyAnnualActivityUpperLimit':
                            upper_limit_rows[tech_str] = row_idx
                        elif param_str == 'TotalAnnualMaxCapacity':
                            max_capacity_rows[tech_str] = row_idx
                        elif param_str == 'ResidualCapacity':
                            residual_capacity_rows[tech_str] = row_idx
                        elif param_str == 'AvailabilityFactor':
                            availability_rows[tech_str] = row_idx

                # Read CapacityToActivityUnit from Fixed Horizon Parameters
                capacity_to_activity = {}  # {tech_code: value}
                if 'Fixed Horizon Parameters' in wb.sheetnames:
                    ws_fixed = wb['Fixed Horizon Parameters']
                    for row_idx in range(2, ws_fixed.max_row + 1):
                        tech_code = ws_fixed.cell(row_idx, 2).value  # Column B: Tech
                        parameter = ws_fixed.cell(row_idx, 6).value  # Column F: Parameter
                        value = ws_fixed.cell(row_idx, 8).value      # Column H: Value
                        if tech_code and parameter and value:
                            tech_str = str(tech_code).strip().upper()
                            param_str = str(parameter).strip()
                            if param_str == 'CapacityToActivityUnit':
                                try:
                                    capacity_to_activity[tech_str] = float(value)
                                except (ValueError, TypeError):
                                    pass

                # Get unique countries from the technology codes
                countries_in_sheet = set()
                for tech_str in set(lower_limit_rows.keys()) | set(upper_limit_rows.keys()):
                    if tech_str.startswith('PWR') and len(tech_str) >= 9:
                        country_code = tech_str[6:9]
                        countries_in_sheet.add(country_code)

                # Process each country
                for country_code in countries_in_sheet:
                    # Check if we have generation data for this country
                    if country_code not in self.generation_data['data']:
                        continue

                    base_generation_pj = self.generation_data['data'][country_code]
                    growth_rate = growth_rates.get(country_code, 0.02)

                    # Calculate technology shares using renewability targets
                    tech_shares = self.calculate_technology_shares(country_code, scenario, all_years)

                    if not tech_shares:
                        # Fall back to shares_total_data if available
                        if self.shares_total_data and scenario in self.shares_total_data:
                            tech_shares = self.shares_total_data[scenario].get(country_code, {})

                    if not tech_shares:
                        continue

                    # Update each technology
                    for tech_type, year_shares in tech_shares.items():
                        tech_str = f"PWR{tech_type}{country_code}XX"

                        lower_row = lower_limit_rows.get(tech_str)
                        upper_row = upper_limit_rows.get(tech_str)
                        max_cap_row = max_capacity_rows.get(tech_str)
                        residual_cap_row = residual_capacity_rows.get(tech_str)
                        avail_row = availability_rows.get(tech_str)

                        if not lower_row and not upper_row:
                            continue

                        # Get CapacityToActivityUnit for this tech (default 31.536 for power plants)
                        c2a = capacity_to_activity.get(tech_str, 31.536)

                        values_updated = 0
                        tech_capped = 0
                        for year in all_years:
                            if year not in year_col_map:
                                continue

                            share = year_shares.get(year, 0.0)
                            if share <= 0:
                                continue

                            # Calculate: Generation × (1 + rate × years_diff) × Share
                            years_diff = year - ref_year
                            generation_year = base_generation_pj * (1 + growth_rate * years_diff)
                            limit_value = generation_year * share

                            # Calculate maximum possible activity based on available capacity
                            # We need to consider BOTH MaxCapacity AND ResidualCapacity constraints
                            # The actual available capacity is limited by:
                            # 1. TotalAnnualMaxCapacity (absolute maximum allowed)
                            # 2. ResidualCapacity (what's actually built/available from past)
                            # Since we can't easily calculate accumulated investments here,
                            # we use ResidualCapacity as the realistic constraint for activity limits

                            max_possible_activity = None
                            capacity_source = None

                            # Get availability factor (needed for both calculations)
                            avail = None
                            if avail_row:
                                avail_value = ws.cell(avail_row, year_col_map[year]).value
                                if avail_value is not None:
                                    try:
                                        avail = float(avail_value)
                                    except (ValueError, TypeError):
                                        pass

                            if avail is not None:
                                # CapacityFactor varies by technology (using 0.28 as conservative)
                                capacity_factor = 0.28

                                # Calculate activity from MaxCapacity
                                max_cap_activity = None
                                if max_cap_row:
                                    max_cap_value = ws.cell(max_cap_row, year_col_map[year]).value
                                    if max_cap_value is not None:
                                        try:
                                            max_cap = float(max_cap_value)
                                            max_cap_activity = max_cap * c2a * avail * capacity_factor
                                        except (ValueError, TypeError):
                                            pass

                                # Calculate activity from ResidualCapacity
                                residual_cap_activity = None
                                if residual_cap_row:
                                    residual_cap_value = ws.cell(residual_cap_row, year_col_map[year]).value
                                    if residual_cap_value is not None:
                                        try:
                                            residual_cap = float(residual_cap_value)
                                            residual_cap_activity = residual_cap * c2a * avail * capacity_factor
                                        except (ValueError, TypeError):
                                            pass

                                # Use the MORE RESTRICTIVE of the two constraints
                                # ResidualCapacity represents what's actually available
                                # MaxCapacity represents what's allowed (but may require investment)
                                if max_cap_activity is not None and residual_cap_activity is not None:
                                    # Both exist: use the minimum (most restrictive)
                                    if residual_cap_activity < max_cap_activity:
                                        max_possible_activity = residual_cap_activity
                                        capacity_source = 'ResidualCapacity'
                                    else:
                                        max_possible_activity = max_cap_activity
                                        capacity_source = 'MaxCapacity'
                                elif max_cap_activity is not None:
                                    max_possible_activity = max_cap_activity
                                    capacity_source = 'MaxCapacity'
                                elif residual_cap_activity is not None:
                                    max_possible_activity = residual_cap_activity
                                    capacity_source = 'ResidualCapacity'

                            # Cap the limit_value if it exceeds max_possible_activity
                            # Also set to 0 if MaxCapacity is 0 (no capacity allowed)
                            if max_possible_activity is not None:
                                if max_possible_activity <= 0:
                                    # MaxCapacity is 0, so LowerLimit must also be 0
                                    if limit_value > 0:
                                        limit_value = 0
                                        tech_capped += 1
                                        capped_values += 1
                                else:
                                    # Leave a small margin (0.05 PJ) below the maximum
                                    max_allowed = max_possible_activity - 0.05
                                    if limit_value > max_allowed:
                                        limit_value = max(0, max_allowed)
                                        tech_capped += 1
                                        capped_values += 1

                            limit_value = round(limit_value, 4)

                            # Update LowerLimit
                            if update_lower and lower_row:
                                ws.cell(lower_row, year_col_map[year], limit_value)
                                activity_changes += 1
                                values_updated += 1

                            # Update UpperLimit = value + 0.1
                            if update_upper and upper_row:
                                upper_value = round(limit_value + 0.1, 4)
                                ws.cell(upper_row, year_col_map[year], upper_value)
                                activity_changes += 1

                        # Set Projection.Mode to "User defined"
                        if values_updated > 0 and projection_mode_col:
                            if update_lower and lower_row:
                                ws.cell(lower_row, projection_mode_col, "User defined")
                            if update_upper and upper_row:
                                ws.cell(upper_row, projection_mode_col, "User defined")
                            capped_msg = f" ({tech_capped} capped)" if tech_capped > 0 else ""
                            self.log(f"  {country_code}-{tech_type}: Updated {values_updated} years{capped_msg}")

                # ============================================================
                # UNIVERSAL VALIDATION: RE-ENABLED
                # Check power technologies with LowerLimit
                # This ensures no technology has LowerLimit > available capacity
                # ONLY applies to the 10 main PWR generation technologies from OLADE:
                # URN, NGS, COA, HYD, GEO, WON, SPV, BIO, PET, OIL
                # Excludes storage (PWRSDS, PWRLDS), backup (PWRBCK), and transmission (TRN)
                # ============================================================
                if True:
                    universal_capped = 0

                    # Only validate these specific technology types
                    validated_tech_types = ['URN', 'NGS', 'COA', 'HYD', 'GEO', 'WON', 'SPV', 'BIO', 'PET', 'OIL']

                    for tech_str, lower_row in lower_limit_rows.items():
                        # Only process PWR technologies (power generation)
                        if not tech_str.startswith('PWR'):
                            continue

                        # Only validate the 10 main generation technologies
                        # Format: PWR{TYPE}{COUNTRY}XX (e.g., PWRHYDARGXX)
                        if len(tech_str) >= 6:
                            tech_type = tech_str[3:6]  # e.g., 'HYD', 'SPV', 'BIO'
                            if tech_type not in validated_tech_types:
                                # Skip storage (SDS, LDS), backup (BCK), and any other tech
                                continue

                        max_cap_row = max_capacity_rows.get(tech_str)
                        residual_cap_row = residual_capacity_rows.get(tech_str)
                        avail_row = availability_rows.get(tech_str)
                        c2a = capacity_to_activity.get(tech_str, 31.536)

                        # Skip if no AvailabilityFactor row (shouldn't happen for non-SDS/STO techs)
                        if not avail_row:
                            continue

                        for year in all_years:
                            if year not in year_col_map:
                                continue

                            col_idx = year_col_map[year]
                            current_limit = ws.cell(lower_row, col_idx).value
                            if current_limit is None:
                                continue
                            try:
                                current_limit = float(current_limit)
                            except (ValueError, TypeError):
                                continue

                            if current_limit <= 0:
                                continue

                            # Get availability
                            avail_value = ws.cell(avail_row, col_idx).value
                            if avail_value is None:
                                continue
                            try:
                                avail = float(avail_value)
                            except (ValueError, TypeError):
                                continue

                            capacity_factor = 0.28

                            # Calculate max possible activity from both capacity sources
                            max_cap_activity = None
                            if max_cap_row:
                                max_cap_value = ws.cell(max_cap_row, col_idx).value
                                if max_cap_value is not None:
                                    try:
                                        max_cap_activity = float(max_cap_value) * c2a * avail * capacity_factor
                                    except (ValueError, TypeError):
                                        pass

                            residual_cap_activity = None
                            if residual_cap_row:
                                residual_cap_value = ws.cell(residual_cap_row, col_idx).value
                                if residual_cap_value is not None:
                                    try:
                                        residual_cap_activity = float(residual_cap_value) * c2a * avail * capacity_factor
                                    except (ValueError, TypeError):
                                        pass

                            # Use the most restrictive constraint
                            max_possible = None
                            if max_cap_activity is not None and residual_cap_activity is not None:
                                max_possible = min(max_cap_activity, residual_cap_activity)
                            elif max_cap_activity is not None:
                                max_possible = max_cap_activity
                            elif residual_cap_activity is not None:
                                max_possible = residual_cap_activity
                            else:
                                # No capacity defined at all (neither MaxCapacity nor ResidualCapacity)
                                # This means the technology has no available capacity
                                max_possible = 0

                            # Cap if needed
                            if max_possible <= 0:
                                if current_limit > 0:
                                    ws.cell(lower_row, col_idx, 0)
                                    universal_capped += 1
                                    # Also update UpperLimit if exists
                                    upper_row = upper_limit_rows.get(tech_str)
                                    if upper_row:
                                        ws.cell(upper_row, col_idx, 0.1)
                            else:
                                max_allowed = max_possible - 0.05
                                if current_limit > max_allowed:
                                    new_limit = max(0, max_allowed)
                                    ws.cell(lower_row, col_idx, round(new_limit, 4))
                                    universal_capped += 1
                                    # Also update UpperLimit if exists
                                    upper_row = upper_limit_rows.get(tech_str)
                                    if upper_row:
                                        ws.cell(upper_row, col_idx, round(new_limit + 0.1, 4))

                    if universal_capped > 0:
                        self.log(f"  Universal validation: {universal_capped} values capped across all technologies")
                        capped_values += universal_capped

                # Validate row count before saving
                final_row_count = ws.max_row
                if final_row_count != initial_row_count:
                    self.log(f"  ⚠ WARNING: Row count changed from {initial_row_count} to {final_row_count}!", "WARNING")

                # Save
                wb.save(param_path)
                wb.close()
                self.log(f"  ✓ {scenario} activity limits updated (rows: {final_row_count})")

            except Exception as e:
                self.log(f"  ✗ Error updating {scenario}: {e}", "ERROR")
                import traceback
                traceback.print_exc()
                try:
                    wb.close()
                except:
                    pass

        self.log("")
        self.log(f"Activity limits updates completed: {activity_changes} values written")
        if capped_values > 0:
            self.log(f"  Note: {capped_values} values were capped due to MaxCapacity constraints")

    def update_activity_lower_limit(self, all_years):
        """Legacy wrapper - calls update_activity_limits"""
        self.update_activity_limits(all_years)

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

            # Check Demand integration (also needed for ActivityLowerLimit)
            demand_or_activity_enabled = (self.olade_config.get('demand_enabled') or
                                          self.olade_config.get('activity_lower_limit_enabled'))
            if demand_or_activity_enabled:
                self.log("")
                self.log("Demand/ActivityLowerLimit integration: ENABLED")
                if self.generation_file_path and self.generation_file_path.exists():
                    self.log(f"Generation file: {self.generation_file_path}")
                    try:
                        self.generation_data = read_olade_generation_data(self.generation_file_path)
                        self.log(f"Generation data loaded: {len(self.generation_data['data'])} countries")
                        self.log(f"Growth rates configured: {len(self.olade_config.get('demand_growth_rates', {}))} countries")
                    except Exception as e:
                        self.log(f"ERROR loading generation data: {e}", "ERROR")
                        self.log("Continuing without demand/activity update...", "WARNING")
                        self.olade_config['demand_enabled'] = False
                        self.olade_config['activity_lower_limit_enabled'] = False
                else:
                    self.log(f"WARNING: Generation file not found: {self.generation_file_path}", "WARNING")
                    self.log("Continuing without demand/activity update...", "WARNING")
                    self.olade_config['demand_enabled'] = False
                    self.olade_config['activity_lower_limit_enabled'] = False
            else:
                self.log("")
                self.log("Demand integration: DISABLED")

            # Check Activity Limits integration - needs Shares_Total.xlsx
            lower_enabled = self.olade_config.get('activity_lower_limit_enabled')
            upper_enabled = self.olade_config.get('activity_upper_limit_enabled')

            if lower_enabled or upper_enabled:
                self.log("")
                self.log(f"ActivityLowerLimit integration: {'ENABLED' if lower_enabled else 'DISABLED'}")
                self.log(f"ActivityUpperLimit integration: {'ENABLED' if upper_enabled else 'DISABLED'}")

                # Log renewability targets info
                renewability_targets = self.olade_config.get('renewability_targets', {})
                technology_weights = self.olade_config.get('technology_weights', {})
                if renewability_targets:
                    self.log(f"Renewability targets: {len(renewability_targets)} country/scenario combinations")
                if technology_weights:
                    self.log(f"Custom technology weights: {len(technology_weights)} country/scenario combinations")

                if self.shares_total_file_path and self.shares_total_file_path.exists():
                    self.log(f"Shares_Total file: {self.shares_total_file_path}")
                    try:
                        self.shares_total_data = read_shares_total_data(self.shares_total_file_path)
                        self.log(f"Shares_Total data loaded: {len(self.shares_total_data)} scenarios")
                    except Exception as e:
                        self.log(f"ERROR loading Shares_Total data: {e}", "ERROR")
                        self.log("Continuing without activity limits update...", "WARNING")
                        self.olade_config['activity_lower_limit_enabled'] = False
                        self.olade_config['activity_upper_limit_enabled'] = False
                else:
                    self.log(f"WARNING: Shares_Total file not found: {self.shares_total_file_path}", "WARNING")
                    self.log("Continuing without activity limits update...", "WARNING")
                    self.olade_config['activity_lower_limit_enabled'] = False
                    self.olade_config['activity_upper_limit_enabled'] = False
            else:
                self.log("")
                self.log("Activity Limits integration: DISABLED")

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

            # Apply instructions in batch mode (one file open per scenario) if any
            if instructions:
                self.apply_instructions_batch(instructions)
            else:
                self.log("No manual instructions to process.")

            # Update demand files if enabled
            if self.olade_config.get('demand_enabled') and self.generation_data:
                self.update_demand_files(sorted(all_years))

            # Update activity limits if enabled (LowerLimit and/or UpperLimit)
            if (self.olade_config.get('activity_lower_limit_enabled') or
                self.olade_config.get('activity_upper_limit_enabled')) and self.generation_data:
                self.update_activity_limits(sorted(all_years))

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
        shares_total_file_path = script_dir / "Shares_Total.xlsx"

        # Create updater and run
        updater = SecondaryTechsUpdater(editor_path, base_path, olade_file_path, shares_file_path, generation_file_path, shares_total_file_path)
        return updater.run()

    except Exception as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
