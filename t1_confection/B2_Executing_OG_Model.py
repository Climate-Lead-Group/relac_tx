# -*- coding: utf-8 -*-
"""
Created on 2025

@author: ClimateLeadGroup, Andrey Salazar-Vargas
"""

import os
import pandas as pd
import yaml
import subprocess
import sys
import platform  
import shutil
import time
from datetime import date, datetime
import multiprocessing as mp
import math
from typing import List, Any
from pathlib import Path
import numpy as np

########################################################################################
def sort_csv_files_in_folder(folder_path):
    if not os.path.isdir(folder_path):
        print(f"The path is invalid: {folder_path}")
        return
    print('################################################################')
    print('Sort csv files.')
    for filename in sorted(os.listdir(folder_path)):
        if filename.endswith(".csv"):
            file_path = os.path.join(folder_path, filename)
            print(f"Processing: {filename}")
            try:
                # Read the CSV preserving the header
                df = pd.read_csv(file_path)

                # Sort using all columns
                df_sorted = df.sort_values(by=list(df.columns))

                # Overwrite the original file
                df_sorted.to_csv(file_path, index=False)
            except Exception as e:
                print(f"Error processing {filename}: {e}")

    print("✅ All files were sort.")
    print('################################################################\n')

def process_scenario_folder(base_input_path, template_path, base_output_path, scenario_name):
    """
    Processes a scenario folder: reads its CSV files, aligns with template structure,
    maps 'Value' to 'VALUE', excludes specific columns, and saves the results to output.
    Also ensures VALUE is int() for certain template files.
    """

    # Step 1: Define scenario input path
    scenario_input_path = os.path.join(base_input_path, scenario_name)

    # Step 2: Skip if not a directory or is 'Default'
    if not os.path.isdir(scenario_input_path) or scenario_name == 'Default':
        return

    # Step 3: Read and clean scenario CSVs
    scenario_files = {}
    for f in sorted(os.listdir(scenario_input_path)):
        if f.endswith('.csv'):
            df = pd.read_csv(os.path.join(scenario_input_path, f))

            # Remove unwanted columns
            df = df.drop(columns=[col for col in ['PARAMETERT', 'Scenario'] if col in df.columns])
            df = df.dropna(axis=1, how='all')

            # Rename 'Value' to 'VALUE'
            if 'Value' in df.columns:
                df = df.rename(columns={'Value': 'VALUE'})

            scenario_files[f] = df

    # Step 4: Read template files
    template_files = {
        f: pd.read_csv(os.path.join(template_path, f))
        for f in sorted(os.listdir(template_path))
        if f.endswith('.csv')
    }

    # Step 5: Create output path
    scenario_output_path = os.path.join(base_output_path, scenario_name)
    os.makedirs(scenario_output_path, exist_ok=True)
    
    # Step 6: Fill templates with scenario data
    for template_name, template_df in template_files.items():
        output_file_path = os.path.join(scenario_output_path, template_name)
        
        if template_name in scenario_files:
            input_df = scenario_files[template_name]
            common_columns = [col for col in template_df.columns if col in input_df.columns]
            filled_df = template_df.copy()
            filled_df[common_columns] = input_df[common_columns]

            # Step 7: Convert VALUE to int if required
            if template_name in [
                'DAYTYPE.csv', 'DAILYTIMEBRACKET.csv', 'SEASON.csv',
                'MODE_OF_OPERATION.csv', 'YEAR.csv', 'EMISSION.csv',
                'FUEL.csv', 'REGION.csv', 'STORAGE.csv', 'TECHNOLOGY.csv',
                'TIMESLICE.csv', 'Conversionls.csv'
            ]:
                if 'VALUE' in filled_df.columns:
                    # Drop rows with NaN or empty string (including whitespace-only)
                    filled_df = filled_df[filled_df['VALUE'].notna() & (filled_df['VALUE'].astype(str).str.strip() != '')]
            
                    # Convert to int if required
                    if template_name in [
                        'DAYTYPE.csv', 'DAILYTIMEBRACKET.csv', 'SEASON.csv',
                        'MODE_OF_OPERATION.csv', 'YEAR.csv'
                    ]:
                        filled_df['VALUE'] = filled_df['VALUE'].astype(int)

            filled_df.to_csv(output_file_path, index=False)
        else:
            template_df.to_csv(output_file_path, index=False)
            
    folder_to_sort = os.path.join(base_output_path,scenario_name)
    sort_csv_files_in_folder(folder_to_sort)

    print(f"✅ Scenario '{scenario_name}': templates filled and saved successfully.\n")
    print('#------------------------------------------------------------------------------#')

def run_otoole_conversion(base_output_path, scenario_name, params):
    """
    Runs the corrected 'otoole convert csv datafile' command for a given scenario.

    Parameters:
        base_output_path (str): Path where the scenario's filled CSV files are stored.
        scenario_name (str): The name of the scenario.
        params (dict): Dictionary loaded from the YAML file with required paths.
    """
    # Step 1: Define paths
    input_folder = os.path.join(base_output_path, scenario_name)
    scenario_exec_dir = os.path.join(HERE, params['executables'], scenario_name + '_0')
    output_file = os.path.join(scenario_exec_dir, f"{scenario_name}_0.txt")
    config_file = os.path.join(HERE, params['Miscellaneous'], params['otoole_config'])

    # Step 2: Ensure the scenario's executable folder exists
    os.makedirs(scenario_exec_dir, exist_ok=True)

    # Step 3: Construct the command
    command = [
        'otoole', 'convert', 'csv', 'datafile',
        input_folder,
        output_file,
        config_file
    ]

    print(f"Running command: {' '.join(command)}")

    # Step 4: Execute the command
    result = subprocess.run(command, capture_output=True, text=True)

    # Step 5: Handle output
    if result.returncode != 0:
        print(f"❌ Error while converting scenario '{scenario_name}':\n{result.stderr}")
        print('#------------------------------------------------------------------------------#')
        return False
    else:
        print(f"✅ Scenario '{scenario_name}' converted successfully.\n{result.stdout}")
        print('#------------------------------------------------------------------------------#')
        return True

def run_days_in_day_type_patcher(params, scenario_name):
    """
    Runs inject_DaysInDayType.py against the preprocessed datafile to fix
    the empty DaysInDayType block (which would otherwise default to 7,
    breaking storage cycling vs energy balance scaling).
    Must run AFTER run_preprocessing_script, BEFORE the solve.
    """
    # Anchor to B2's own directory so it works regardless of how B2 is invoked
    script_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'inject_DaysInDayType.py',
    )
    target_file = os.path.join(
        params['executables'],
        scenario_name + '_0',
        f"{params['preprocess_data_name']}{scenario_name}_0.txt",
    )
    command = [sys.executable, script_path, target_file]
    print(f"Patching DaysInDayType for '{scenario_name}_0':")
    print(' '.join(command))
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ DaysInDayType patcher failed for '{scenario_name}':\n{result.stderr}")
    else:
        print(result.stdout)
    print('#------------------------------------------------------------------------------#')

def run_strip_storage_patcher(params, scenario_name):
    """
    OPTIONAL diagnostic step: strips selected storage facilities (and their
    feeding PWR techs) from the preprocessed datafile, writing a SIBLING file
    (e.g. Pre_processed_BAU_0_NoStorage.txt). Original .txt is never modified.

    Controlled by params['strip_storage_active'] (default False = no-op).

    YAML keys consumed:
        strip_storage_active:  bool   -- master switch (default False)
        strip_storage_mode:    str    -- "tech" | "class" | "all"  (default "all")
        strip_storage_targets: list   -- facility names (tech) or prefixes (class)
        strip_storage_suffix:  str    -- filename suffix (default "NoStorage")

    When active, main_executer redirects data_file/output_file to use the
    suffixed sibling, so the solver builds and solves the patched LP and
    writes outputs alongside the originals.
    """
    if not params.get('strip_storage_active', False):
        return  # No-op when disabled

    mode = params.get('strip_storage_mode', 'all')
    targets = params.get('strip_storage_targets') or []
    suffix = params.get('strip_storage_suffix', 'NoStorage')

    # Anchor strip_storage.py to B2's own directory (same pattern as DaysInDayType).
    script_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'strip_storage.py',
    )

    base = f"{params['preprocess_data_name']}{scenario_name}_0"
    in_file = os.path.join(params['executables'], scenario_name + '_0', f"{base}.txt")
    out_file = os.path.join(params['executables'], scenario_name + '_0', f"{base}_{suffix}.txt")

    command = [sys.executable, script_path, in_file, '-o', out_file, '--mode', mode]
    if mode != 'all' and targets:
        command += ['--targets'] + list(targets)

    print(f"Stripping storage for '{scenario_name}_0' (mode={mode}, suffix={suffix}):")
    print(' '.join(command))
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ strip_storage patcher failed for '{scenario_name}':\n{result.stderr}")
    else:
        print(result.stdout)
    print('#------------------------------------------------------------------------------#')

def run_storage_delay_patcher(params, scenario_name):
    """
    OPTIONAL storage-delay step: keeps storage in the model but blocks storage
    builds for the first N model years, then reopens the linked PWRLDS*/PWRSDS*
    caps in later years. Writes SIBLING files (datafile + patched OSeMOSYS
    model); originals are never modified.

    Controlled by params['storage_delay_active'] (default False = no-op).

    YAML keys consumed:
        storage_delay_active:           bool  -- master switch (default False)
        storage_delay_first_n_years:    int   -- years to block (default 5)
        storage_delay_storage_prefixes: list  -- e.g. ["SDS", "LDS"]
        storage_delay_storages:         list  -- exact storage names (optional, overrides prefixes)
        storage_delay_allowed_value:    str   -- PWR cap value in open years (default "-1")
        storage_delay_suffix:           str   -- chained filename suffix (default "StorageDelayN5")
        storage_delay_model_input:      str   -- source OSeMOSYS model file (default params['osemosys_model'])
        storage_delay_model_output:     str   -- patched model file written next to B2 (default "osemosys_fast_preprocessed_storage_delay.txt")

    Mutually exclusive with strip_storage. When storage_delay_active is True,
    main_executer's __main__ already disables strip_storage and switches the
    solver model to the patched output produced here.
    """
    if not params.get('storage_delay_active', False):
        return  # No-op when disabled

    suffix = params.get('storage_delay_suffix', 'StorageDelayN5')
    first_n_years = params.get('storage_delay_first_n_years', 5)
    allowed_value = params.get('storage_delay_allowed_value', '-1')
    storage_prefixes = params.get('storage_delay_storage_prefixes', ['SDS', 'LDS'])
    exact_storages = params.get('storage_delay_storages', [])

    here = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(here, 'patch_storage_delay.py')

    base = f"{params['preprocess_data_name']}{scenario_name}_0"
    in_file = os.path.join(params['executables'], scenario_name + '_0', f"{base}.txt")
    out_file = os.path.join(params['executables'], scenario_name + '_0', f"{base}_{suffix}.txt")

    def _b2_local_path(value):
        path = Path(value)
        return str(path if path.is_absolute() else Path(here) / path)

    model_input = _b2_local_path(
        params.get('storage_delay_model_input', params['osemosys_model'])
    )
    model_output = _b2_local_path(
        params.get('storage_delay_model_output', 'osemosys_fast_preprocessed_storage_delay.txt')
    )

    command = [
        sys.executable,
        script_path,
        in_file,
        '-o',
        out_file,
        '--model-input',
        model_input,
        '--model-output',
        model_output,
        '--first-n-years',
        str(first_n_years),
        '--allowed-value',
        str(allowed_value),
    ]
    if exact_storages:
        command += ['--storages'] + list(exact_storages)
    elif storage_prefixes:
        command += ['--storage-prefixes'] + list(storage_prefixes)

    print(f"Applying storage-delay patch for '{scenario_name}_0' (N={first_n_years}, suffix={suffix}):")
    print(' '.join(command))
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ERROR] storage_delay patcher failed for '{scenario_name}':\n{result.stderr}")
        raise RuntimeError(f"storage_delay patcher failed for '{scenario_name}'")
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    print('#------------------------------------------------------------------------------#')

def run_open_pwrbck_patcher(params, scenario_name):
    """
    OPTIONAL diagnostic step: opens PWRBCK* (backstop) caps in
    TotalAnnualMaxCapacity and TotalAnnualMaxCapacityInvestment by rewriting
    any 0-value cells to params['open_pwrbck_value'] (default 9999). Reads
    from the strip_storage output if that step is active, otherwise from the
    vanilla preprocessed datafile. Writes a sibling file with the OpenBCK
    suffix chained on; original is never modified.

    Controlled by params['open_pwrbck_active'] (default False = no-op).

    YAML keys consumed:
        open_pwrbck_active:  bool  -- master switch (default False)
        open_pwrbck_value:   int   -- replacement for 0 cells (default 9999)
        open_pwrbck_pattern: str   -- tech-name substring (default "PWRBCK")
        open_pwrbck_suffix:  str   -- filename suffix to chain (default "OpenBCK")

    When active, main_executer chains OpenBCK on top of any active strip
    suffix, so the solver builds and solves the patched LP and writes outputs
    alongside the originals.
    """
    if not params.get('open_pwrbck_active', False):
        return  # No-op when disabled

    value   = params.get('open_pwrbck_value',   9999)
    pattern = params.get('open_pwrbck_pattern', 'PWRBCK')
    suffix  = params.get('open_pwrbck_suffix',  'OpenBCK')

    # Anchor open_pwrbck_caps.py to B2's own directory (same pattern as the
    # strip and DaysInDayType patchers).
    script_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'open_pwrbck_caps.py',
    )

    base = f"{params['preprocess_data_name']}{scenario_name}_0"
    # Input is the previous patcher's output (storage_delay or strip) if active;
    # otherwise the vanilla file.
    _chain = []
    if params.get('storage_delay_active', False):
        _chain.append(params.get('storage_delay_suffix', 'StorageDelayN5'))
    if params.get('strip_storage_active', False):
        _chain.append(params.get('strip_storage_suffix', 'NoStorage'))
    in_base = f"{base}_{'_'.join(_chain)}" if _chain else base
    out_base = f"{in_base}_{suffix}"

    in_file  = os.path.join(params['executables'], scenario_name + '_0', f"{in_base}.txt")
    out_file = os.path.join(params['executables'], scenario_name + '_0', f"{out_base}.txt")

    command = [sys.executable, script_path, in_file, '-o', out_file,
               '--pattern', pattern, '--value', str(value)]

    print(f"Opening PWRBCK caps for '{scenario_name}_0' (pattern={pattern}, value={value}):")
    print(' '.join(command))
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ open_pwrbck patcher failed for '{scenario_name}':\n{result.stderr}")
    else:
        print(result.stdout)
    print('#------------------------------------------------------------------------------#')

def run_reserve_margin_repair_patcher(params, scenario_name):
    """
    OPTIONAL diagnostic/final-ish step: patches ReserveMarginTagTechnology and
    opens selected firm capacity caps in the preprocessed datafile.

    Controlled by params['reserve_margin_repair_active'] (default False = no-op).

    YAML keys consumed:
        reserve_margin_repair_active: bool  -- master switch (default False)
        reserve_margin_repair_suffix: str   -- chained filename suffix (default "RMRepair")
        reserve_margin_backstop_credit: num -- PWRBCK reserve credit (default 1.0)
        reserve_margin_ccs_credit: num      -- PWRCCS reserve credit (default 0.9)
        reserve_margin_open_capacity_value: num -- cap value for selected techs (default 9999)
        reserve_margin_open_capacity_prefixes: list -- default ["PWRPET", "PWROIL", "PWRNGS"]
        reserve_margin_patch_backstop: bool -- set PWRBCK tags (default True)
        reserve_margin_patch_ccs: bool      -- set PWRCCS tags (default True)
        reserve_margin_open_capacity: bool  -- open selected caps (default True)

    This chains after strip_storage/open_pwrbck when those patchers are active.
    """
    if not params.get('reserve_margin_repair_active', False):
        return  # No-op when disabled

    suffix = params.get('reserve_margin_repair_suffix', 'RMRepair')
    script_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'patch_reserve_margin_repair.py',
    )

    base = f"{params['preprocess_data_name']}{scenario_name}_0"
    chain_parts = []
    if params.get('storage_delay_active', False):
        chain_parts.append(params.get('storage_delay_suffix', 'StorageDelayN5'))
    if params.get('strip_storage_active', False):
        chain_parts.append(params.get('strip_storage_suffix', 'NoStorage'))
    if params.get('open_pwrbck_active', False):
        chain_parts.append(params.get('open_pwrbck_suffix', 'OpenBCK'))

    in_base = f"{base}_{'_'.join(chain_parts)}" if chain_parts else base
    out_base = f"{in_base}_{suffix}"

    in_file = os.path.join(params['executables'], scenario_name + '_0', f"{in_base}.txt")
    out_file = os.path.join(params['executables'], scenario_name + '_0', f"{out_base}.txt")

    command = [
        sys.executable,
        script_path,
        in_file,
        '-o',
        out_file,
        '--backstop-credit',
        str(params.get('reserve_margin_backstop_credit', 1.0)),
        '--ccs-credit',
        str(params.get('reserve_margin_ccs_credit', 0.9)),
        '--open-capacity-value',
        str(params.get('reserve_margin_open_capacity_value', 9999)),
    ]

    open_prefixes = params.get(
        'reserve_margin_open_capacity_prefixes',
        ['PWRPET', 'PWROIL', 'PWRNGS'],
    )
    command += ['--open-capacity-prefixes'] + list(open_prefixes)

    if not params.get('reserve_margin_patch_backstop', True):
        command.append('--skip-backstop-credit')
    if not params.get('reserve_margin_patch_ccs', True):
        command.append('--skip-ccs-credit')
    if not params.get('reserve_margin_open_capacity', True):
        command.append('--skip-capacity-opening')

    print(f"Repairing reserve margin data for '{scenario_name}_0' (suffix={suffix}):")
    print(' '.join(command))
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ERROR] reserve_margin_repair patcher failed for '{scenario_name}':\n{result.stderr}")
    else:
        print(result.stdout)
    print('#------------------------------------------------------------------------------#')

def run_reserve_margin_xlsx_patcher(params, scenario_name):
    """
    OPTIONAL careful reserve-margin repair step using an XLSX fallback workbook.

    Controlled by params['reserve_margin_xlsx_active'] (default False = no-op).

    YAML keys consumed:
        reserve_margin_xlsx_active: bool  -- master switch (default False)
        reserve_margin_xlsx_suffix: str   -- chained suffix (default "RMCarefulXLSX")
        reserve_margin_xlsx_workbook: str -- workbook path, relative to this B2 file if not absolute
        reserve_margin_xlsx_sheet: str    -- optional worksheet name
        reserve_margin_xlsx_backstop_credit: num -- PWRBCK reserve credit (default 1.0)
        reserve_margin_xlsx_ccs_credit: num      -- PWRCCS reserve credit (default 0.9)
        reserve_margin_xlsx_target_prefixes: list -- default ["PWRPET", "PWROIL", "PWRNGS"]
        reserve_margin_xlsx_sentinel_values: list -- default [0, 9999]

    This chains after strip_storage/open_pwrbck and also after the older
    reserve_margin_repair patch if that older patch is active.
    """
    if not params.get('reserve_margin_xlsx_active', False):
        return

    suffix = params.get('reserve_margin_xlsx_suffix', 'RMCarefulXLSX')
    here = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(here, 'patch_reserve_margin_repair_careful_xlsx.py')

    workbook = params.get(
        'reserve_margin_xlsx_workbook',
        'firm_capacity_fallbacks_by_cr.xlsx',
    )
    if not os.path.isabs(workbook):
        workbook = os.path.join(here, workbook)

    base = f"{params['preprocess_data_name']}{scenario_name}_0"
    chain_parts = []
    if params.get('storage_delay_active', False):
        chain_parts.append(params.get('storage_delay_suffix', 'StorageDelayN5'))
    if params.get('strip_storage_active', False):
        chain_parts.append(params.get('strip_storage_suffix', 'NoStorage'))
    if params.get('open_pwrbck_active', False):
        chain_parts.append(params.get('open_pwrbck_suffix', 'OpenBCK'))
    if params.get('reserve_margin_repair_active', False):
        chain_parts.append(params.get('reserve_margin_repair_suffix', 'RMRepair'))

    in_base = f"{base}_{'_'.join(chain_parts)}" if chain_parts else base
    out_base = f"{in_base}_{suffix}"

    in_file = os.path.join(params['executables'], scenario_name + '_0', f"{in_base}.txt")
    out_file = os.path.join(params['executables'], scenario_name + '_0', f"{out_base}.txt")
    warnings_file = os.path.join(params['executables'], scenario_name + '_0', f"{out_base}.warnings.txt")

    command = [
        sys.executable,
        script_path,
        in_file,
        '-o',
        out_file,
        '--fallback-xlsx',
        workbook,
        '--backstop-credit',
        str(params.get('reserve_margin_xlsx_backstop_credit', 1.0)),
        '--ccs-credit',
        str(params.get('reserve_margin_xlsx_ccs_credit', 0.9)),
        '--warnings-file',
        warnings_file,
    ]

    xlsx_sheet = params.get('reserve_margin_xlsx_sheet')
    if xlsx_sheet:
        command += ['--xlsx-sheet', str(xlsx_sheet)]

    target_prefixes = params.get(
        'reserve_margin_xlsx_target_prefixes',
        ['PWRPET', 'PWROIL', 'PWRNGS'],
    )
    command += ['--target-prefixes'] + list(target_prefixes)

    sentinel_values = params.get('reserve_margin_xlsx_sentinel_values', [0, 9999])
    command += ['--sentinel-values'] + [str(value) for value in sentinel_values]

    if not params.get('reserve_margin_xlsx_patch_backstop', True):
        command.append('--skip-backstop-credit')
    if not params.get('reserve_margin_xlsx_patch_ccs', True):
        command.append('--skip-ccs-credit')

    rm_value = params.get('reserve_margin_xlsx_global_value')
    if rm_value is not None:
        command += ['--reserve-margin-value', str(rm_value)]

    print(f"Repairing reserve margin data from XLSX for '{scenario_name}_0' (suffix={suffix}):")
    print(' '.join(command))
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ERROR] reserve_margin_xlsx patcher failed for '{scenario_name}':\n{result.stderr}")
    else:
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
    print('#------------------------------------------------------------------------------#')

def run_activity_upper_limit_patcher(params, scenario_name):
    """
    Cap TotalTechnologyAnnualActivityUpperLimit using fractions from the
    scenario's A-O_Parametrization.xlsx. Imported and called directly (no
    subprocess); see patch_activity_upper_limit.apply.

    YAML keys consumed:
        activity_upper_limit_active: bool
        activity_upper_limit_scenarios: list[str]  -- scenarios to apply to
        activity_upper_limit_parameter_label: str
        activity_upper_limit_demand_fuel_prefixes: list[str]
        activity_upper_limit_tech_prefixes: list[str]
        activity_upper_limit_exclude_prefixes: list[str]
        activity_upper_limit_suffix: str
    """
    if not params.get('activity_upper_limit_active', False):
        return
    scenarios = params.get('activity_upper_limit_scenarios', [])
    if scenarios and scenario_name not in scenarios:
        return

    suffix = params.get('activity_upper_limit_suffix', 'ActUpLim')
    here = os.path.dirname(os.path.abspath(__file__))

    base = f"{params['preprocess_data_name']}{scenario_name}_0"
    chain_parts = []
    if params.get('storage_delay_active', False):
        chain_parts.append(params.get('storage_delay_suffix', 'StorageDelayN5'))
    if params.get('strip_storage_active', False):
        chain_parts.append(params.get('strip_storage_suffix', 'NoStorage'))
    if params.get('open_pwrbck_active', False):
        chain_parts.append(params.get('open_pwrbck_suffix', 'OpenBCK'))
    if params.get('reserve_margin_repair_active', False):
        chain_parts.append(params.get('reserve_margin_repair_suffix', 'RMRepair'))
    if params.get('reserve_margin_xlsx_active', False):
        chain_parts.append(params.get('reserve_margin_xlsx_suffix', 'RMCarefulXLSX'))

    in_base = f"{base}_{'_'.join(chain_parts)}" if chain_parts else base
    out_base = f"{in_base}_{suffix}"
    scenario_exec = os.path.join(params['executables'], scenario_name + '_0')
    in_file = os.path.join(scenario_exec, f"{in_base}.txt")
    out_file = os.path.join(scenario_exec, f"{out_base}.txt")

    xlsx_path = os.path.join(
        here, 'A1_Outputs', f'A1_Outputs_{scenario_name}', 'A-O_Parametrization.xlsx'
    )
    a2_root = os.path.join(here, params.get('A2_output_otoole', 'A2_Outputs_Params_otoole'), scenario_name)
    demand_csv = os.path.join(a2_root, 'SpecifiedAnnualDemand.csv')
    oar_csv = os.path.join(a2_root, 'OutputActivityRatio.csv')

    missing = [p for p in (in_file, xlsx_path, demand_csv, oar_csv) if not os.path.exists(p)]
    if missing:
        print(f"[ERROR] activity_upper_limit patcher missing inputs for '{scenario_name}':")
        for path in missing:
            print(f"   - {path}")
        print('#------------------------------------------------------------------------------#')
        return

    sys.path.insert(0, here)
    import patch_activity_upper_limit  # noqa: E402

    print(f"Activity upper-limit patcher for '{scenario_name}_0' (suffix={suffix}):")
    print(f"  input : {os.path.basename(in_file)}")
    print(f"  output: {os.path.basename(out_file)}")
    print(f"  xlsx  : {xlsx_path}")
    try:
        summary = patch_activity_upper_limit.apply(
            Path(in_file), Path(out_file),
            Path(xlsx_path), Path(demand_csv), Path(oar_csv),
            params,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] activity_upper_limit patcher failed for '{scenario_name}': {exc}")
        print('#------------------------------------------------------------------------------#')
        return

    # The solver path downstream is built without the ActUpLim suffix, so it
    # reads in_file. Mirror the capped output back onto in_file to ensure the
    # caps reach the LP.
    shutil.copy2(out_file, in_file)

    print(
        f"  techs_capped={summary['techs_capped']}  "
        f"rows_written={summary['rows_written']}  "
        f"rows_replaced={summary['rows_replaced']}  "
        f"rows_skipped_no_demand={summary['rows_skipped_no_demand']}"
    )
    for warning in summary.get('warnings', [])[:10]:
        print(f"  [WARN] {warning}")
    remaining = len(summary.get('warnings', [])) - 10
    if remaining > 0:
        print(f"  ... and {remaining} more warning(s)")
    print('#------------------------------------------------------------------------------#')


def run_sync_patched_csvs(params, scenario_name, base_output_path, patched_base_output_path):
    """
    Mirror the A2 otoole input CSV folder into a sibling `_patched` folder and
    overlay parameter values from the final patched .txt datafile. The original
    folder is never modified.

    Returns the path to be used as input_folder by generate_combined_input_file:
      - The mirror (patched) folder when sync_patched_csvs_active and at least
        one patcher is active.
      - The original A2 CSV folder otherwise.

    YAML keys consumed:
        sync_patched_csvs_active: bool  -- master switch (default False)
        sync_patched_csvs_params: list  -- parameter names to extract from the
            patched .txt and write back into matching CSVs. Default covers the
            params touched by the storage_delay / open_pwrbck / reserve-margin
            patchers.
    """
    original_folder = os.path.join(base_output_path, scenario_name)

    if not params.get('sync_patched_csvs_active', False):
        return original_folder

    chain_parts = []
    if params.get('storage_delay_active', False):
        chain_parts.append(params.get('storage_delay_suffix', 'StorageDelayN5'))
    if params.get('strip_storage_active', False):
        chain_parts.append(params.get('strip_storage_suffix', 'NoStorage'))
    if params.get('open_pwrbck_active', False):
        chain_parts.append(params.get('open_pwrbck_suffix', 'OpenBCK'))
    if params.get('reserve_margin_repair_active', False):
        chain_parts.append(params.get('reserve_margin_repair_suffix', 'RMRepair'))
    if params.get('reserve_margin_xlsx_active', False):
        chain_parts.append(params.get('reserve_margin_xlsx_suffix', 'RMCarefulXLSX'))
    if params.get('activity_upper_limit_active', False) and (
        not params.get('activity_upper_limit_scenarios')
        or scenario_name in params.get('activity_upper_limit_scenarios', [])
    ):
        chain_parts.append(params.get('activity_upper_limit_suffix', 'ActUpLim'))

    if not chain_parts:
        # No patcher in the chain produced a sibling .txt; nothing to sync.
        return original_folder

    base = f"{params['preprocess_data_name']}{scenario_name}_0"
    txt_name = f"{base}_{'_'.join(chain_parts)}.txt"
    txt_path = os.path.join(params['executables'], scenario_name + '_0', txt_name)
    csv_destination = os.path.join(patched_base_output_path, scenario_name)

    sync_params = params.get('sync_patched_csvs_params', [
        'ReserveMargin',
        'ReserveMarginTagTechnology',
        'TotalAnnualMaxCapacity',
        'TotalAnnualMaxCapacityInvestment',
        'TotalAnnualMinCapacity',
        'TotalAnnualMinCapacityInvestment',
    ])

    script_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'sync_patched_csvs_from_txt.py',
    )

    command = [
        sys.executable,
        script_path,
        '--txt', txt_path,
        '--source-csv-folder', original_folder,
        '--out-csv-folder', csv_destination,
        '--params', *list(sync_params),
    ]

    print(f"Syncing patched CSVs for '{scenario_name}_0' from {txt_name}:")
    print(' '.join(command))
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ERROR] sync_patched_csvs failed for '{scenario_name}':\n{result.stderr}")
        return original_folder
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    print('#------------------------------------------------------------------------------#')
    return csv_destination


def run_preprocessing_script(params, scenario_name):
    """
    Executes the preprocessing Python script specified in the YAML params file for a given scenario.

    Parameters:
        params (dict): Parameters loaded from the YAML file.
        scenario_name (str): The name of the scenario to preprocess.
    """
    # Step 1: Define paths
    script_path = os.path.join(params['Miscellaneous'], params['preprocess_data'])
    input_file = os.path.join(params['executables'], scenario_name + '_0', f"{scenario_name}_0.txt")
    output_file = os.path.join(params['executables'], scenario_name + '_0', f"{params['preprocess_data_name']}{scenario_name}_0.txt")

    # Step 2: Construct command
    command = [sys.executable, script_path, input_file, output_file]

    print(f"Running preprocessing script for scenario '{scenario_name}_0':")
    print(' '.join(command))

    # Step 3: Run the script
    result = subprocess.run(command, capture_output=True, text=True)

    # Step 4: Output result
    if result.returncode != 0:
        print(f"❌ Error during preprocessing of scenario '{scenario_name}':\n{result.stderr}")
        print('#------------------------------------------------------------------------------#')
    else:
        print(f"✅ Preprocessing completed for scenario '{scenario_name}':\n{result.stdout}")
        print('#------------------------------------------------------------------------------#')

def check_enviro_variables(solver_command):
    # Determine the command based on the operating system
    command = 'where' if platform.system() == 'Windows' else 'which'
    
    # Execute the appropriate command
    where_solver = subprocess.run([command, solver_command], capture_output=True, text=True)
    paths = where_solver.stdout.splitlines()
    
    if paths:  # Ensure that at least one path was found
        path_solver = paths[0]
        
        # Check if the path is already in the environment variable PATH
        if path_solver not in os.environ["PATH"]:
            # If not in PATH, add it
            os.environ["PATH"] += os.pathsep + path_solver
            print("Path added:", path_solver)
    else:
        print(f"No '{solver_command}' found on the system.")
    #

def get_config_main_path(here, base_folder):
    # Navigate to the repository root (parent of t1_confection)
    repo_root = Path(here).parent
    return str(repo_root / base_folder)

def main_executer(params, scenario_name, HERE):
    
    folder_scenario = os.path.join(HERE, params['executables'], scenario_name + '_0')                             
    
    # Constructing paths for the data file and the output file, adapting for file system differences
    data_file = os.path.join(folder_scenario, params['preprocess_data_name'] + scenario_name + '_0')
    output_file = os.path.join(folder_scenario, params['preprocess_data_name'] + scenario_name + '_0' + params['output_files'])
    this_case = scenario_name + '_0.txt'

    # storage_delay redirect: when active, point solver at the patched sibling file.
    # Produces e.g. Pre_processed_BAU_0_StorageDelayN5.txt
    if params.get('storage_delay_active', False):
        _sd_suffix = params.get('storage_delay_suffix', 'StorageDelayN5')
        _base = params['preprocess_data_name'] + scenario_name + '_0'
        data_file = os.path.join(folder_scenario, f"{_base}_{_sd_suffix}")
        output_file = os.path.join(folder_scenario, f"{_base}_{_sd_suffix}{params['output_files']}")
        print(f"[storage_delay] redirecting solver to: {data_file}.txt")

    # Strip-storage diagnostic redirect: when active, point solver at the patched sibling file.
    # Produces e.g. Pre_processed_BAU_0_NoStorage.txt and Pre_processed_BAU_0_NoStorage_output.{lp,sol,cplex.log}
    if params.get('strip_storage_active', False):
        _strip_suffix = params.get('strip_storage_suffix', 'NoStorage')
        _base = params['preprocess_data_name'] + scenario_name + '_0'
        data_file = os.path.join(folder_scenario, f"{_base}_{_strip_suffix}")
        output_file = os.path.join(folder_scenario, f"{_base}_{_strip_suffix}{params['output_files']}")
        print(f"[strip_storage] redirecting solver to: {data_file}.txt")

    # PWRBCK-cap-opening diagnostic redirect: chains OpenBCK suffix on top of
    # any active storage_delay/strip suffix.
    if params.get('open_pwrbck_active', False):
        _bck_suffix = params.get('open_pwrbck_suffix', 'OpenBCK')
        _base = params['preprocess_data_name'] + scenario_name + '_0'
        _chain_parts = []
        if params.get('storage_delay_active', False):
            _chain_parts.append(params.get('storage_delay_suffix', 'StorageDelayN5'))
        if params.get('strip_storage_active', False):
            _chain_parts.append(params.get('strip_storage_suffix', 'NoStorage'))
        _chain_parts.append(_bck_suffix)
        _chain = '_'.join(_chain_parts)
        data_file = os.path.join(folder_scenario, f"{_base}_{_chain}")
        output_file = os.path.join(folder_scenario, f"{_base}_{_chain}{params['output_files']}")
        print(f"[open_pwrbck] redirecting solver to: {data_file}.txt")

    # Reserve-margin repair redirect: chains after storage_delay/strip/open-BCK when active.
    if params.get('reserve_margin_repair_active', False):
        _rm_suffix = params.get('reserve_margin_repair_suffix', 'RMRepair')
        _base = params['preprocess_data_name'] + scenario_name + '_0'
        _chain_parts = []
        if params.get('storage_delay_active', False):
            _chain_parts.append(params.get('storage_delay_suffix', 'StorageDelayN5'))
        if params.get('strip_storage_active', False):
            _chain_parts.append(params.get('strip_storage_suffix', 'NoStorage'))
        if params.get('open_pwrbck_active', False):
            _chain_parts.append(params.get('open_pwrbck_suffix', 'OpenBCK'))
        _chain_parts.append(_rm_suffix)
        _chain = '_'.join(_chain_parts)
        data_file = os.path.join(folder_scenario, f"{_base}_{_chain}")
        output_file = os.path.join(folder_scenario, f"{_base}_{_chain}{params['output_files']}")
        print(f"[reserve_margin_repair] redirecting solver to: {data_file}.txt")

    # Careful XLSX reserve-margin repair redirect.
    if params.get('reserve_margin_xlsx_active', False):
        _xlsx_suffix = params.get('reserve_margin_xlsx_suffix', 'RMCarefulXLSX')
        _base = params['preprocess_data_name'] + scenario_name + '_0'
        _chain_parts = []
        if params.get('storage_delay_active', False):
            _chain_parts.append(params.get('storage_delay_suffix', 'StorageDelayN5'))
        if params.get('strip_storage_active', False):
            _chain_parts.append(params.get('strip_storage_suffix', 'NoStorage'))
        if params.get('open_pwrbck_active', False):
            _chain_parts.append(params.get('open_pwrbck_suffix', 'OpenBCK'))
        if params.get('reserve_margin_repair_active', False):
            _chain_parts.append(params.get('reserve_margin_repair_suffix', 'RMRepair'))
        _chain_parts.append(_xlsx_suffix)
        _chain = '_'.join(_chain_parts)
        data_file = os.path.join(folder_scenario, f"{_base}_{_chain}")
        output_file = os.path.join(folder_scenario, f"{_base}_{_chain}{params['output_files']}")
        print(f"[reserve_margin_xlsx] redirecting solver to: {data_file}.txt")

    # Determining the solver based on parameters
    solver = params['solver']
    commands = []

    if solver == 'glpk':
        if params['execute_model']:
            # Using newer GLPK options
                                       
            check_enviro_variables('glpsol')
            
            # Composing the command to solve the model with new options
            str_solve = f'glpsol -m {params["osemosys_model"]} -d {data_file}.txt --wglp {output_file}.glp --write {output_file}.sol'
            commands.append(str_solve)
        
    else:
        if params['create_matrix']:
            # For LP models
            str_solve = f'glpsol -m {params["osemosys_model"]} -d {data_file}.txt --wlp {output_file}.lp --check'
            commands.append(str_solve)
        
        if solver == 'cbc':
            # Using CBC solver
            if params['execute_model']:
                if os.path.exists(output_file + '.sol'):
                    os.remove(output_file + '.sol')

                check_enviro_variables('cbc')

                # Get random seed for reproducibility
                cbc_random_seed = params.get('cbc_random_seed', 12345)

                # Composing the command for CBC solver with random seeds for deterministic behavior
                str_solve = f'cbc {output_file}.lp randomSeed {cbc_random_seed} randomCbcSeed {cbc_random_seed} -seconds {params["iteration_time"]} solve -solu {output_file}.sol'
                commands.append(str_solve)
            
        elif solver == 'cplex':
            # Using CPLEX solver
            if params['execute_model']:
                if os.path.exists(output_file + '.sol'):
                    os.remove(output_file + '.sol')

                # Number of threads cplex use
                cplex_threads = params['cplex_threads']

                # Get random seed for reproducibility
                cplex_random_seed = params.get('cplex_random_seed', 12345)

                check_enviro_variables('cplex')

                # Composing the command for CPLEX solver with random seed for deterministic behavior
                str_solve = f'cplex -c "read {output_file}.lp" "set threads {cplex_threads}" "set randomseed {cplex_random_seed}" "set parallel 1" "optimize" "write {output_file}.sol"'
                commands.append(str_solve)

        elif solver == 'gurobi':
            # Using Gurobi solver
            if params['execute_model']:
                if os.path.exists(output_file + '.sol'):
                    os.remove(output_file + '.sol')

                # Number of threads gurobi use
                gurobi_threads = params['gurobi_threads']

                # Get random seed for reproducibility
                gurobi_seed = params.get('gurobi_seed', 12345)

                check_enviro_variables('gurobi_cl')

                # Composing the command for Gurobi solver with seed for deterministic behavior
                str_solve = f'gurobi_cl Threads={gurobi_threads} Seed={gurobi_seed} ResultFile={output_file}.sol {output_file}.lp'
                commands.append(str_solve)

    if params['execute_model'] or params['create_matrix']:
        for cmd in commands:
            subprocess.run(cmd, shell=True, check=True)
        
    print(f'✅ Scenario {scenario_name}_0 solve successfully.')
    print('\n#------------------------------------------------------------------------------#')

    # Paths for converting outputs
    file_path_conv_format = os.path.join(HERE, params['Miscellaneous'], params['conv_format'])
    # file_path_template = os.path.join(params['Miscellaneous'], params['templates'])
    file_path_template = os.path.join(HERE, params['A2_output_otoole'], scenario_name)
    file_path_outputs = os.path.join(folder_scenario, params['outputs'])

    # Converting outputs from .sol to csv format
    if solver == 'glpk' and params['glpk_option'] == 'new':
        str_outputs = f'otoole results {solver} csv {output_file}.sol {file_path_outputs} datafile {data_file}.txt {file_path_conv_format} --glpk_model {output_file}.glp'
        if params['execute_model']:
            subprocess.run(str_outputs, shell=True, check=True)

    elif solver in ['cbc', 'cplex', 'gurobi']:

        str_outputs = f'otoole results {solver} csv {output_file}.sol {file_path_outputs} csv {file_path_template} {file_path_conv_format} 2> {output_file}.log'
        if params['execute_model']:
            subprocess.run(str_outputs, shell=True, check=True)

    # Module to concatenate csvs otoole outputs
    if solver in ['glpk', 'cbc', 'cplex', 'gurobi']:
        file_conca_csvs = get_config_main_path(HERE, params['concatenate_folder'])
        script_concate_csv = os.path.join(file_conca_csvs, params['concat_csvs'])
        str_otoole_concate_csv = f'python -u {script_concate_csv} {file_path_outputs} {output_file}'  # last int is the ID tier
        if params['concat_otoole_csv']:
            subprocess.run(str_otoole_concate_csv, shell=True, check=True)
        print(f'✅ Concatenated outputs to {scenario_name}_0_Output.csv successfully.')
        print('\n#------------------------------------------------------------------------------#')

def delete_files(file, data_file, solver):
    # Delete files
    if file:
        shutil.os.remove(file)
        shutil.os.remove(data_file)
    
    # Check if the .sol file exists and is empty
    log_file = file.replace('.sol', '.log')
    if os.path.exists(log_file) and os.path.getsize(log_file) == 0:
        if os.path.exists(log_file):
            os.remove(log_file)
    
    if solver == 'glpk':
        shutil.os.remove(file.replace('sol', 'glp'))        
    else:
        shutil.os.remove(file.replace('sol', 'lp'))
    
    # Delete log files when solver is 'cplex' and del_files is True
    if solver == 'cplex':
        for filename in ['cplex.log', 'clone1.log', 'clone2.log']:
            if os.path.exists(filename):
                os.remove(filename)

    # Delete log files when solver is 'gurobi' and del_files is True
    if solver == 'gurobi':
        if os.path.exists('gurobi.log'):
            os.remove('gurobi.log')

def read_csv_files(input_dir):
    """Reads all CSV files in the given directory and returns a dictionary of DataFrames."""
    data_dict = {}
    for filename in sorted(os.listdir(input_dir)):
        if filename.endswith(".csv"):
            file_path = os.path.join(input_dir, filename)
            df = pd.read_csv(file_path)
            key = os.path.splitext(filename)[0]
            data_dict[key] = df
    return data_dict

def generate_combined_input_file(input_folder, output_folder, scenario_name):
    """
    Reads CSVs from input_folder, filters out metadata keys, renames VALUE columns by key,
    concatenates all non-empty DataFrames, orders columns, and saves the result to a CSV file.
    """
    keys_sets_delete = ['REGION', 'YEAR', 'TECHNOLOGY', 'FUEL', 'EMISSION', 'MODE_OF_OPERATION',
                        'TIMESLICE', 'STORAGE', 'SEASON', 'DAYTYPE', 'DAILYTIMEBRACKET']

    inputs_dataframes = []
    print(input_folder)
    print(sorted(os.listdir(input_folder)))
    for filename in sorted(os.listdir(input_folder)):
        if not filename.endswith(".csv"):
            continue
        key = filename.replace(".csv", "")
        if key in keys_sets_delete:
            continue
        path = os.path.join(input_folder, filename)
        df = pd.read_csv(path)
        if df.empty or 'VALUE' not in df.columns:
            continue
        df = df.rename(columns={'VALUE': key})
        inputs_dataframes.append(df)

    if not inputs_dataframes:
        print("[Warning] No valid dataframes found to concatenate.")
        return None, None

    # Concatenate all non-empty dataframes
    inputs_data = pd.concat(inputs_dataframes, ignore_index=True, sort=True)  # Sort for deterministic column order

    # Reorder columns
    present_keys = [col for col in keys_sets_delete if col in inputs_data.columns]
    other_columns = sorted([col for col in inputs_data.columns if col not in present_keys])
    inputs_data = inputs_data[present_keys + other_columns]

    # Save to CSV
    os.makedirs(output_folder, exist_ok=True)
    output_path = os.path.join(output_folder, f"{scenario_name}_Input.csv")
    inputs_data.to_csv(output_path, index=False)

    print(f'✅ Concatenated inputs to {scenario_name}_Input.csv successfully.')
    print('\n#------------------------------------------------------------------------------#')

    return output_path, inputs_data.head()


def export_root_datafile(here, params, scenario_name, export_name=None):
    """
    Copy the preprocessed main-scenario datafile to the repository root so the
    user has a single easy-to-find model datafile next to `t1_confection/`.

    When patchers (storage_delay, strip_storage, open_pwrbck, reserve_margin_*)
    are active, exports the final patched sibling — not the vanilla preprocessed
    file — so the root datafile matches what the solver actually consumed.
    """
    if export_name is None:
        if params.get('storage_delay_active', False):
            export_name = params.get('storage_delay_root_datafile', 'RELAC_TX_data_storage_delay.txt')
        else:
            export_name = 'RELAC_TX_data.txt'

    repo_root = Path(here).parent
    base = f"{params['preprocess_data_name']}{scenario_name}_0"
    chain_parts = []
    if params.get('storage_delay_active', False):
        chain_parts.append(params.get('storage_delay_suffix', 'StorageDelayN5'))
    if params.get('strip_storage_active', False):
        chain_parts.append(params.get('strip_storage_suffix', 'NoStorage'))
    if params.get('open_pwrbck_active', False):
        chain_parts.append(params.get('open_pwrbck_suffix', 'OpenBCK'))
    if params.get('reserve_margin_repair_active', False):
        chain_parts.append(params.get('reserve_margin_repair_suffix', 'RMRepair'))
    if params.get('reserve_margin_xlsx_active', False):
        chain_parts.append(params.get('reserve_margin_xlsx_suffix', 'RMCarefulXLSX'))

    source_name = f"{base}_{'_'.join(chain_parts)}.txt" if chain_parts else f"{base}.txt"
    source_path = (
        Path(here)
        / params['executables']
        / f"{scenario_name}_0"
        / source_name
    )
    target_path = repo_root / export_name

    if not source_path.exists():
        print(f"[WARN] Root datafile export skipped because source was not found: {source_path}")
        return None

    shutil.copy2(source_path, target_path)
    print(f"✅ Datafile exported to repository root: {target_path}")
    print('#------------------------------------------------------------------------------#')
    return target_path


def active_output_csv_candidates(params, scenario_future_name):
    """
    Return output CSV names in the same suffix order used by main_executer.

    The solver/otoole path can become, for example:
      Pre_processed_BAU_0_NoStorage_OpenBCK_RMCarefulXLSX_output.csv

    The final scenario concatenator used to look only for:
      Pre_processed_BAU_0_Output.csv

    Keep the active chained name first, with legacy fallbacks after it.
    """
    base = f"{params['preprocess_data_name']}{scenario_future_name}"
    chain_parts = []

    if params.get('storage_delay_active', False):
        chain_parts.append(params.get('storage_delay_suffix', 'StorageDelayN5'))
    if params.get('strip_storage_active', False):
        chain_parts.append(params.get('strip_storage_suffix', 'NoStorage'))
    if params.get('open_pwrbck_active', False):
        chain_parts.append(params.get('open_pwrbck_suffix', 'OpenBCK'))
    if params.get('reserve_margin_repair_active', False):
        chain_parts.append(params.get('reserve_margin_repair_suffix', 'RMRepair'))
    if params.get('reserve_margin_xlsx_active', False):
        chain_parts.append(params.get('reserve_margin_xlsx_suffix', 'RMCarefulXLSX'))

    candidates = []
    if chain_parts:
        candidates.append(f"{base}_{'_'.join(chain_parts)}{params['output_files']}.csv")

    candidates.extend([
        f"{base}{params['output_files']}.csv",
        f"{base}_Output.csv",
    ])

    return candidates


def concatenate_all_scenarios(HERE, params):
    """
    Iterates over all scenario folders in `base_input_path` (excluding 'Default'),
    reads *_Input.csv and *_Output.csv files, adds scenario metadata columns, concatenates
    them into single CSV files for inputs, outputs y combined, y devuelve sus rutas.

    Args:
        params (dict):
          - executables (str): Path to the base directory containing scenario folders.
          - prefix_final_files (str): Carpeta/ruta donde guardar los resultados.
          - inputs_file (str): Nombre base para el CSV de inputs.
          - outputs_file (str): Nombre base para el CSV de outputs.
          - combined_file (str, opcional): Nombre base para el CSV combinado inputs+outputs.
    Returns:
        tuple: (input_csv_path, output_csv_path, combined_csv_path)
    """
    # Columnas de metadatos que movemos al frente
    keys_sets_delete = [
        'REGION','YEAR','TECHNOLOGY','FUEL','EMISSION','MODE_OF_OPERATION',
        'TIMESLICE','STORAGE','SEASON','DAYTYPE','DAILYTIMEBRACKET'
    ]

    combined_inputs = []
    combined_outputs = []
    combined_inputs_outputs = []
    base_input_path = params['executables']

    for scenario_future_name in sorted(os.listdir(base_input_path)):
        if scenario_future_name.lower() in ['default', '__pycache__', 'local_dataset_creator_0.py']:
            continue

        scenario_path = os.path.join(HERE, base_input_path, scenario_future_name)
        parts = scenario_future_name.rsplit("_", 1)
        scenario = parts[0]
        future = parts[1]

        input_file = os.path.join(scenario_path, f"{scenario_future_name}_Input.csv")
        output_file = None
        for output_name in active_output_csv_candidates(params, scenario_future_name):
            candidate = os.path.join(scenario_path, output_name)
            if os.path.exists(candidate):
                output_file = candidate
                break

        if os.path.exists(input_file):
            df_in = pd.read_csv(input_file, low_memory=False)
            df_in.insert(0, "Future", future)
            df_in.insert(1, "Scenario", scenario)
            combined_inputs.append(df_in)
            combined_inputs_outputs.append(df_in)

        if output_file and os.path.exists(output_file):
            df_out = pd.read_csv(output_file, low_memory=False)
            df_out.insert(0, "Future", future)
            df_out.insert(1, "Scenario", scenario)
            combined_outputs.append(df_out)
            combined_inputs_outputs.append(df_out)

    # Concatenate inputs y outputs por separado
    df_inputs_all = pd.concat(combined_inputs, ignore_index=True) if combined_inputs else pd.DataFrame()
    df_outputs_all = pd.concat(combined_outputs, ignore_index=True) if combined_outputs else pd.DataFrame()
    # df_inputs_outputs_all = pd.concat(combined_inputs_outputs, ignore_index=True) if combined_inputs_outputs else pd.DataFrame()
    # df_list = []
    # df_list.append(combined_inputs)
    # df_list.append(combined_outputs)
    df_inputs_outputs_all = pd.concat([df_inputs_all,df_outputs_all], ignore_index=True, sort=True)  # Sort for deterministic column order
    

    # Function to reorder columns: metadata first, then alphabetical
    def reorder_columns(df):
        front = ['Future','Scenario'] + [c for c in keys_sets_delete if c in df.columns]
        rest = sorted([c for c in df.columns if c not in front])
        return df[front + rest]

    today = date.today().isoformat()  # 'YYYY-MM-DD'

    # 1) Save inputs
    if not df_inputs_all.empty:
        df_inputs_all = reorder_columns(df_inputs_all)
        # Sort rows for deterministic output
        sort_cols = [c for c in ['Future', 'Scenario', 'REGION', 'TECHNOLOGY', 'YEAR'] if c in df_inputs_all.columns]
        if sort_cols:
            df_inputs_all = df_inputs_all.sort_values(by=sort_cols).reset_index(drop=True)
        path_in = os.path.join(HERE,params['prefix_final_files'] + params['inputs_file'])
        df_inputs_all.to_csv(path_in, index=False)
        dated = path_in.replace('.csv', f'_{today}.csv')
        df_inputs_all.to_csv(dated, index=False)
    else:
        path_in = None

    # 2) Save outputs
    if not df_outputs_all.empty:
        df_outputs_all = reorder_columns(df_outputs_all)
        # Sort rows for deterministic output
        sort_cols = [c for c in ['Future', 'Scenario', 'REGION', 'TECHNOLOGY', 'YEAR'] if c in df_outputs_all.columns]
        if sort_cols:
            df_outputs_all = df_outputs_all.sort_values(by=sort_cols).reset_index(drop=True)
        path_out = os.path.join(HERE,params['prefix_final_files'] + params['outputs_file'])
        df_outputs_all.to_csv(path_out, index=False)
        dated = path_out.replace('.csv', f'_{today}.csv')
        df_outputs_all.to_csv(dated, index=False)
    else:
        path_out = None

    # 3) Nuevamente, combinar ambos DataFrames en uno solo y guardarlo
    combined_name = params.get('combined_file', 'Combined_Inputs_Outputs.csv')
    if not df_inputs_outputs_all.empty and not df_outputs_all.empty:
        # df_combined = pd.concat([df_inputs_all, df_outputs_all],
        #                         ignore_index=True, sort=False)
        df_combined = reorder_columns(df_inputs_outputs_all)
        # Sort rows for deterministic output
        sort_cols = [c for c in ['Future', 'Scenario', 'REGION', 'TECHNOLOGY', 'YEAR'] if c in df_combined.columns]
        if sort_cols:
            df_combined = df_combined.sort_values(by=sort_cols).reset_index(drop=True)
        
        
        #########################################################################################
        # Calculate AccumulatedTotalAnnualMinCapacityInvestment
        # Must group by (Future, Scenario, TECHNOLOGY) and accumulate within each group
        if "TotalAnnualMinCapacityInvestment" in df_combined.columns:
            df = df_combined.copy()

            # Initialize the accumulated column with NaN
            df['AccumulatedTotalAnnualMinCapacityInvestment'] = np.nan

            # Define grouping columns (exclude YEAR since we accumulate over years)
            group_cols = ['Future', 'Scenario', 'TECHNOLOGY']
            group_cols = [c for c in group_cols if c in df.columns]

            if group_cols:
                # Sort by group columns + YEAR to ensure correct order for cumsum
                sort_cols = group_cols + ['YEAR']
                df = df.sort_values(by=sort_cols).reset_index(drop=True)

                # Calculate cumulative sum within each group
                # Only for rows that have a value in TotalAnnualMinCapacityInvestment
                mask = df['TotalAnnualMinCapacityInvestment'].notna()
                df.loc[mask, 'AccumulatedTotalAnnualMinCapacityInvestment'] = (
                    df.loc[mask]
                    .groupby(group_cols, sort=False)['TotalAnnualMinCapacityInvestment']
                    .cumsum()
                )
            else:
                # Fallback: if no group columns, just do a simple cumsum
                mask = df['TotalAnnualMinCapacityInvestment'].notna()
                df.loc[mask, 'AccumulatedTotalAnnualMinCapacityInvestment'] = (
                    df.loc[mask, 'TotalAnnualMinCapacityInvestment'].cumsum()
                )

            df_combined = df
        #########################################################################################
        
        
        path_comb = os.path.join(HERE,params['prefix_final_files'] + combined_name)
        df_combined.to_csv(path_comb, index=False)
        # Note: dated copy with annualized data will be created after annualization (if enabled)
    else:
        path_comb = None

    return path_in, path_out, path_comb






def chunk_scenarios(
    scenarios: List[Any],
    max_x_per_iter: int,
) -> List[List[Any]]:
    """
    Split the input list ``scenarios`` into chunks of size ``max_x_per_iter``.

    Parameters
    ----------
    scenarios : List[Any]
        The list that holds all scenario values.
    max_x_per_iter : int
        Maximum number of elements allowed in each chunk.

    Returns
    -------
    List[List[Any]]
        A list where each element is a sub-list of ``scenarios`` with length
        up to ``max_x_per_iter``.
    """
    if max_x_per_iter <= 0:
        raise ValueError("max_x_per_iter must be a positive integer")

    # Build the chunks using slicing in a comprehension
    scenarios_list_max_per_iter: List[List[Any]] = [
        scenarios[i : i + max_x_per_iter]  # noqa: E203 (spacing around :)
        for i in range(0, len(scenarios), max_x_per_iter)
    ]
    return scenarios_list_max_per_iter

########################################################################################
if __name__ == "__main__":
    # Start timer
    start1 = time.time()
    
    # Folder where this script lives: .../OSTRAM/t1_confection
    global HERE
    def get_here() -> Path:
        # 1) Script normal
        if '__file__' in globals():
            return Path(__file__).resolve().parent
        # 2) Algunos IDEs exponen __main__.__file__
        main = sys.modules.get('__main__')
        if hasattr(main, '__file__'):
            return Path(main.__file__).resolve().parent
        # 3) Console/interactive execution: current working directory
        return Path.cwd().resolve()
    
    HERE = get_here()
    
    
    # (Optional) Change CWD to the script's folder
    if Path.cwd() != HERE:
        os.chdir(HERE)
        print(f"[INFO] Working dir -> {HERE}")
        
    # Load params from YAML
    with open('Config_MOMF_T1_AB.yaml', 'r') as f:
        params = yaml.safe_load(f)

    # storage_delay precedence: when this patcher is active it is mutually
    # exclusive with strip_storage, switches the solver to the patched model
    # written by patch_storage_delay.py, and uses its own prefix so the run's
    # combined inputs/outputs do not overwrite the baseline RELAC_TX_* artifacts.
    if params.get('storage_delay_active', False):
        if params.get('strip_storage_active', False):
            print("[storage_delay] strip_storage_active forced to False (mutually exclusive)")
            params['strip_storage_active'] = False
        params.setdefault('storage_delay_model_input', params['osemosys_model'])
        params.setdefault('storage_delay_model_output', 'osemosys_fast_preprocessed_storage_delay.txt')
        params['osemosys_model'] = params['storage_delay_model_output']
        if params.get('storage_delay_prefix_final_files'):
            params['prefix_final_files'] = params['storage_delay_prefix_final_files']
        print(f"[storage_delay] osemosys_model -> {params['osemosys_model']}")
        print(f"[storage_delay] prefix_final_files -> {params['prefix_final_files']}")

    # Load params from YAML
    with open('Config_MOMF_T1_A.yaml', 'r') as f:
        params_A2 = yaml.safe_load(f)

    # Define source and destination base paths
    base_input_path = os.path.join(HERE, params['A2_output'])
    template_path = os.path.join(HERE, params['Miscellaneous'], params['templates'])
    base_output_path = os.path.join(HERE, params['A2_output_otoole'])
    patched_base_output_path = os.path.join(
        HERE,
        params.get('sync_patched_csvs_folder', 'A2_Outputs_Params_otoole_patched'),
    )

    scenarios=sorted(os.listdir(base_input_path))
    try:
        scenarios.remove('Default')
    except ValueError:
        pass

    if params['only_main_scenario']:
        scenarios = []
        scenarios.append(params_A2['xtra_scen']['Main_Scenario'])

    main_scenario_name = params_A2['xtra_scen']['Main_Scenario']

    ###############################################################################################
    # Write txt model
    for scenario_name in scenarios:

        if params['A2_otoole_outputs']:
            process_scenario_folder(
                base_input_path=base_input_path,
                template_path=template_path,
                base_output_path=base_output_path,
                scenario_name=scenario_name
            )
        if params['write_txt_model']:
            conversion_ok = run_otoole_conversion(
                base_output_path=base_output_path,
                scenario_name=scenario_name,
                params=params
            )

            if conversion_ok:
                run_preprocessing_script(params, scenario_name)
                run_days_in_day_type_patcher(params, scenario_name)
                run_storage_delay_patcher(params, scenario_name)
                run_strip_storage_patcher(params, scenario_name)
                run_open_pwrbck_patcher(params, scenario_name)
                run_reserve_margin_repair_patcher(params, scenario_name)
                run_reserve_margin_xlsx_patcher(params, scenario_name)
                run_activity_upper_limit_patcher(params, scenario_name)
            else:
                print(f"❌ Skipping preprocessing for '{scenario_name}' because otoole conversion failed.")
                print('#------------------------------------------------------------------------------#')
                continue


        # When patchers + sync are active, redirect input_folder to the
        # `_patched` mirror so generate_combined_input_file reflects the
        # patched values the solver actually consumed.
        input_folder = run_sync_patched_csvs(
            params,
            scenario_name,
            base_output_path,
            patched_base_output_path,
        )
        output_folder = os.path.join(HERE, params['executables'], scenario_name + '_0')

        # List any available files for preview (just to verify setup)
        os.makedirs(input_folder, exist_ok=True)
        os.makedirs(output_folder, exist_ok=True)

        # Concatenate inputs
        generate_combined_input_file(input_folder, output_folder, scenario_name + '_0')

        #
    ###############################################################################################

    if params['write_txt_model'] and main_scenario_name in scenarios:
        export_root_datafile(HERE, params, main_scenario_name)
    ###############################################################################################
        
        
        
    ###############################################################################################
    # Execute txt model
    if params['execute_model'] or params['create_matrix']:
        if params['parallel']:
            print('Entered Parallelization of model execution')
            max_x_per_iter = params['max_x_per_iter'] # FLAG: This is an input
            scenarios_list_max_per_iter = chunk_scenarios(scenarios, max_x_per_iter)
            #
            for scens_list in scenarios_list_max_per_iter:
                processes = []
                for scenario_name in scens_list:
                    p = mp.Process(target=main_executer, args=(params, scenario_name, HERE) )
                    processes.append(p)
                    p.start()
                #
                for process in processes:
                    process.join()
            
        # This is for the linear version
        else:
            print('Started Linear Runs')
            for scenario_num in scenarios:
                main_executer(params, scenario_num, HERE)
    
    ###############################################################################################
    # Delete files
    for scenario_name in scenarios:        
        # Delete Outputs folder with otoole csvs files
        if params['del_files']:
            # Delete Outputs folder with otoole csvs files
            folder_scenario = os.path.join(HERE, params['executables'], scenario_name + '_0') 
            outputs_otoole_csvs = os.path.join(HERE, folder_scenario, params['outputs'])
            data_file = os.path.join(HERE, folder_scenario, scenario_name + '_0' + '.txt')
            sol_file = os.path.join(HERE, folder_scenario, params['preprocess_data_name'] + scenario_name + '_0' + params['output_files'] + '.sol')
            if os.path.exists(outputs_otoole_csvs):
                shutil.rmtree(outputs_otoole_csvs)
        
            # Delete glp, lp, txt and sol files
            if params['solver'] in ['glpk', 'cbc', 'cplex']:
                delete_files(sol_file, data_file, params['solver'])
            
            print(f'✅ Delete intermediate files to scenario {scenario_name}_0 successfully.')
            print('\n#------------------------------------------------------------------------------#')

    ###############################################################################################

    end_1 = time.time()   
    time_elapsed_1 = -start1 + end_1
    print( str( time_elapsed_1 ) + ' seconds /', str( time_elapsed_1/60 ) + ' minutes' )

    start2 = time.time()
    
    ###############################################################################################
    # Concatenate inputs and outputs
    if params['concat_scenarios_csv']:
        input_output_path, output_output_path, combined_output_path = concatenate_all_scenarios(HERE,params)
        print(f'✅ Concatenate inputs and outputs for all scenarios successfully.')
        print(f'The name files are: ({input_output_path}), ({output_output_path}) and ({combined_output_path})')
    ###############################################################################################

    ###############################################################################################
    # Annualize capital investment
    if params.get('annualize_capital', False):
        try:
            print('\n')
            print('#'*80)
            print('# CAPITAL INVESTMENT ANNUALIZATION')
            print('#'*80)

            # Import the annualization function
            from Z_AUX_capital_annualization_script import annualize_capital_investment

            # Define the path to the combined file
            combined_file_path = os.path.join(HERE, params['prefix_final_files'] + 'Combined_Inputs_Outputs.csv')

            # Check if file exists
            if os.path.exists(combined_file_path):
                print(f'Starting annualization for: {combined_file_path}')

                # Call the annualization function
                annualize_capital_investment(
                    input_file_path=combined_file_path,
                    verbose=True
                )

                print(f'✅ Capital investment annualization completed successfully.')

                # Create dated copy with annualized data
                today = date.today().isoformat()  # 'YYYY-MM-DD'
                dated_combined = combined_file_path.replace('.csv', f'_{today}.csv')
                shutil.copy2(combined_file_path, dated_combined)
                print(f'✅ Annualized file copied to: {dated_combined}')
                print('#'*80)
            else:
                print(f'⚠️  WARNING: Combined file not found at {combined_file_path}')
                print('Skipping capital investment annualization.')
                print('#'*80)

        except Exception as e:
            print(f'❌ ERROR during capital investment annualization: {e}')
            print('Continuing without annualization...')
            import traceback
            traceback.print_exc()
            print('#'*80)
    else:
        # If annualization is disabled, still create dated copy of combined file
        combined_file_path = os.path.join(HERE, params['prefix_final_files'] + 'Combined_Inputs_Outputs.csv')
        if os.path.exists(combined_file_path):
            today = date.today().isoformat()  # 'YYYY-MM-DD'
            dated_combined = combined_file_path.replace('.csv', f'_{today}.csv')
            shutil.copy2(combined_file_path, dated_combined)
            print(f'✅ Combined file copied to: {dated_combined}')
    ###############################################################################################




    # # 1. Carga los dataframes desde los CSV
    # df_inputs_all = pd.read_csv('REALC_TX_Inputs.csv', low_memory=False)
    # df_outputs_all = pd.read_csv('REALC_TX_Outputs.csv', low_memory=False)
    
    # # 2. Concatenate them vertically (one below the other)
    # df_combined = pd.concat([df_inputs_all, df_outputs_all], ignore_index=True, sort=False)
    
    # # 3. (Optional) Reorder columns if desired,
    # #    for example, putting 'Scenario' and 'Future' at the front
    # cols_front = ['Scenario', 'Future']
    # other_cols = [c for c in df_combined.columns if c not in cols_front]
    # df_combined = df_combined[cols_front + other_cols]
    
    # # 4. Guarda el CSV combinado
    # today = date.today().isoformat()  # e.g. '2025-07-14'
    # combined_filename = f"{params['prefix_final_files']}Combined_Inputs_Outputs_{today}.csv"
    # df_combined.to_csv(combined_filename, index=False)
    
    # print(f"Combined file saved to: {combined_filename}")
    ###############################################################################################
    
    
    end_2 = time.time()   
    time_elapsed_2 = -start2 + end_2
    print( str( time_elapsed_2 ) + ' seconds /', str( time_elapsed_2/60 ) + ' minutes' )
    print('\n#------------------------------------------------------------------------------#')
    
    time_elapsed_3 = -start1 + end_2
    print( str( time_elapsed_3 ) + ' seconds /', str( time_elapsed_3/60 ) + ' minutes' )
    print('*: For all effects, we have finished the work of this script.')

            

