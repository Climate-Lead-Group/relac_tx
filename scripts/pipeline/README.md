# scripts/pipeline — A3 → B1 → B2 model pipeline and editor tools

Stages: **A** prepares the per-scenario A-O workbooks in `inputs/A1_Outputs/`; **B1** compiles
them to parameter CSVs in `outputs/A2_Output_Params/`; **B2** builds the OSeMOSYS datafile per
scenario, applies the patch chain, runs the solver and concatenates results into
`outputs/RELAC_TX_*.csv`. **D1–D5** are editor tools that write into the A-O workbooks. DVC stages
`preprocess` (B1) and `executing` (B2) are in `dvc.yaml`; `run.py` drives them. User docs:
`docs/pipeline.md`, `docs/solver-patchers.md`, `docs/secondary-techs-editor.md`.

## Scripts

| Script | What it does | Reads | Writes | Run |
|---|---|---|---|---|
| `A0_generate_tech_country_matrix.py` | Builds `Tech_Country_Matrix.xlsx` (which tech-country combos A1 includes, NGS unification, aggregation rules) from the country list and `implausible_combinations` | `inputs/config/Config_country_codes.yaml` | `inputs/data/Tech_Country_Matrix.xlsx` | `python scripts/pipeline/A0_generate_tech_country_matrix.py` |
| `A1_Pre_processing_OG_csvs.py` | Largest A-stage script: reads raw OSeMOSYS CSVs, applies the tech-country matrix, region consolidation and NGS unification, and rebuilds the four `A-O_*.xlsx` workbooks per scenario from the templates (overwrites them) | `inputs/OG_csvs_inputs/*.csv`, `inputs/data/Tech_Country_Matrix.xlsx`, `inputs/config/*.yaml`, `inputs/Miscellaneous/` templates | `inputs/A1_Outputs/A1_Outputs_<scenario>/A-O_*.xlsx` | `python scripts/pipeline/A1_Pre_processing_OG_csvs.py` |
| `A2_AddTx.py` | Adds transmission/dispatch (RNWTRN/PWRTRN/TRNRPO/TRNNLI/DSPTRN) technology entries and remaps `ELC*` fuel codes in the "Secondary"/"Demand Techs" sheets of every scenario | `inputs/A1_Outputs/A1_Outputs_<scenario>/A-O_*.xlsx` | same files, in place | `python scripts/pipeline/A2_AddTx.py [--yaml --base --proj --param --demand]` |
| `A3_migrate_old_inputs_CLG.py` | Historical one-shot migrator from `inputs/reference/Old_Inputs/` to the current model structure (tech renames via `Config_tech_equivalences.yaml`); not part of the normal chain, kept for legacy transitions | `inputs/reference/Old_Inputs/**`, `inputs/data/Tech_Country_Matrix.xlsx`, `inputs/config/Config_tech_equivalences.yaml` | `inputs/A1_Outputs/A1_Outputs_<scenario>/A-O_*.xlsx`, `inputs/A2_Extra_Inputs/A-Xtra_Storage.xlsx` | `python scripts/pipeline/A3_migrate_old_inputs_CLG.py [--dry-run]` |
| `A3_process.py` | Orchestrator: per scenario runs `rules_scripts/add_max_cap_investment_lid_rule.py` then `rules_scripts/extend_lowerlimits_pwr.py` (if listed in `lowerlimit_scenarios`) then `B1b_Pre_solver_validation.py --auto-fix-all`; then, once for all scenarios, `sync_historical_from_bau.py` per `historical_sync_through` | `inputs/config/A3_process/lid_rule.yaml` | `inputs/A1_Outputs/A1_Outputs_<scenario>/A-O_Parametrization.xlsx`, in place | `python scripts/pipeline/A3_process.py [--scenario BAU] [--list] [--skip-validation] [--skip-historical-sync] [--force-overwrite]` |
| `B1_Compiler.py` | Compiles the A-O workbooks + `A2_Extra_Inputs` into OSeMOSYS parameter CSVs for the scenario named in `Config_MOMF_T1_A.yaml`; runs `B1b_Pre_solver_validation` on that workbook first | `inputs/A1_Outputs/**`, `inputs/A2_Extra_Inputs/**`, `inputs/OG_csvs_inputs/EMISSION.csv`, `inputs/config/Config_MOMF_T1_A.yaml` | `outputs/A2_Output_Params/<scenario>/*.csv`, `outputs/A2_Structure_Lists.xlsx` | called by `B1_Run_Compiler.py`, not run directly |
| `B1_Run_Compiler.py` | Discovers `A1_Outputs_*` scenario folders, sets `xtra_scen.Main_Scenario` in `Config_MOMF_T1_A.yaml` for each in turn and runs `B1_Compiler.py`; restores the YAML afterward | `inputs/A1_Outputs/A1_Outputs_*/` (folder names), `inputs/config/Config_MOMF_T1_A.yaml` | (via `B1_Compiler.py`) `outputs/A2_Output_Params/` | `python -u scripts/pipeline/B1_Run_Compiler.py` — DVC stage `preprocess` |
| `B1b_Pre_solver_validation.py` | Detects and optionally auto-fixes infeasibility-prone data: V1 (min≥max investment per year), V2 (cumulative max vs residual+min), V3 (activity lower limit above max activity); V4 is a coverage warning only | `A-O_Parametrization.xlsx` of the target scenario | same workbook, in place (timestamped backup first) | `python scripts/pipeline/B1b_Pre_solver_validation.py --scenario BAU [--auto-fix-all\|--report-only\|--non-interactive] [--skip-v3] [--modify-from-year Y]`; also imported by `B1_Compiler.py` and called by `A3_process.py` |
| `B2_Executing_OG_Model.py` | Converts each scenario's A2 CSVs to an OSeMOSYS `.txt` via otoole, runs the patch chain and Tx chain, solves with the configured solver, converts results back to CSV and concatenates all scenarios | `outputs/A2_Output_Params/`, `inputs/model/osemosys_fast_preprocessed.txt`, `inputs/config/Config_MOMF_T1_AB.yaml` (+ `_A.yaml`) | `outputs/Executables/<scenario>_0/*`, `outputs/RELAC_TX_*.csv`, `outputs/logs/` | `python -u scripts/pipeline/B2_Executing_OG_Model.py` — DVC stage `executing`; **solver step, requires approval** |
| `D1_generate_editor_template.py` | Reads every scenario's "Secondary Techs" sheet plus OLADE mappings and builds one `Secondary_Techs_Editor.xlsx` for manual review | `inputs/A1_Outputs/A1_Outputs_*/A-O_Parametrization.xlsx`, `inputs/data/OLADE*.xlsx`, `inputs/config/Config_MOMF_T1_AB.yaml` | `inputs/data/Secondary_Techs_Editor.xlsx` | `python scripts/pipeline/D1_generate_editor_template.py` |
| `D2_update_secondary_techs.py` | Reads the edited `Secondary_Techs_Editor.xlsx` back and applies the changes to each scenario's `A-O_Parametrization.xlsx` (also fills TRN limits from flow data) | `inputs/data/Secondary_Techs_Editor.xlsx`, `inputs/data/OLADE*.xlsx`, `inputs/data/Shares_PET_OIL_Split.xlsx` | `inputs/A1_Outputs/A1_Outputs_<scenario>/A-O_Parametrization.xlsx`, in place | `python scripts/pipeline/D2_update_secondary_techs.py` |
| `D3_load_lac_max_capacity_caps.py` | Historical one-shot loader: writes LAC market-realistic `TotalAnnualMaxCapacityInvestment` ceilings for `PWRSPV`/`PWRWON` (19 countries) into BAU, keeping `Max >= Min * 1.01` | caps hardcoded in-script (documented against `LAC_Capacity_Ceilings_Consolidated.md`) | `inputs/A1_Outputs/A1_Outputs_BAU/A-O_Parametrization.xlsx`, in place (backup first) | `python scripts/pipeline/D3_load_lac_max_capacity_caps.py` |
| `D4_load_dsptrn_max_cap_inv.py` | Caps `TotalAnnualMaxCapacityInvestment` for the TRN techs feeding node 02 in "Demand Techs", scaling BAU's built `NewCapacity` by a per-scenario/year factor with per-country exemptions (default target: INV; OPT intentionally excluded) | BAU `NewCapacity` results, `inputs/A1_Outputs/A1_Outputs_<scenario>/A-O_Parametrization.xlsx` | same workbook, "Demand Techs" sheet, in place | `python scripts/pipeline/D4_load_dsptrn_max_cap_inv.py [--apply\|--dry-run] [--scenario INV]` |
| `D5_load_fuel_var_costs.py` | Loads fuel `VariableCost` values (USD/L → M$/PJ) from `LAC_Fuel_Price_Projections_2026_v2_audit.xlsx` into the "VariableCost" sheet of every scenario; idempotent per price scenario | `inputs/A1_Outputs/<scenario>/LAC_Fuel_Price_Projections_2026_v2_audit.xlsx` | `inputs/A1_Outputs/<scenario>/A-O_Parametrization.xlsx`, sheet `VariableCost` (backup unless `--no-backup`) | `python scripts/pipeline/D5_load_fuel_var_costs.py [--price-scenario HIGH\|LOW\|REF] [--base inputs/A1_Outputs] [--no-backup]` |
| `inject_DaysInDayType.py` | Patches the empty `DaysInDayType` block of a preprocessed `.txt` in place, computed from `YearSplit`, so storage-cycling and energy-balance equations agree on days/year | target `.txt` | same `.txt`, in place | called by B2, always (after `preprocess_data`); standalone: `python scripts/pipeline/inject_DaysInDayType.py <path/to/Pre_processed_X_0.txt>` |
| `open_pwrbck_caps.py` | Diagnostic patcher: opens `TotalAnnualMaxCapacity`/`TotalAnnualMaxCapacityInvestment` caps for `PWRBCK*` (backstop) techs that are hardcapped at 0, writing a sibling `.txt` | input `.txt` | sibling output `.txt` (source untouched) | `python scripts/pipeline/open_pwrbck_caps.py <input_file> -o <output_file> [--pattern --value --blocks]`; called by B2 when `open_pwrbck_active` |
| `patch_activity_upper_limit.py` | Library, no CLI: caps `TotalTechnologyAnnualActivityUpperLimit` from user-entered fractions in the "Secondary Techs" sheet, mapping each tech to its country demand fuel via `OutputActivityRatio` | `A-O_Parametrization.xlsx`, input `.txt` | sibling output `.txt` | imported and called (`apply(...)`) by `B2_Executing_OG_Model.py` when `activity_upper_limit_active`; no standalone CLI |
| `patch_reserve_margin_repair_careful.py` | Library behind `patch_reserve_margin_repair_careful_xlsx.py`: reserve-margin repair with per-country-region firm-capacity fallbacks; patches stock (`TotalAnnualMaxCapacity`) and flow (`TotalAnnualMaxCapacityInvestment`) caps independently, replacing only sentinel values (0, 9999) | — | — | library only (imported by `patch_reserve_margin_repair_careful_xlsx.py` and `patch_activity_upper_limit.py`) |
| `patch_reserve_margin_repair_careful_xlsx.py` | XLSX-driven sibling of the above: reads per-country-region firm-capacity fallbacks from an xlsx workbook and patches the reserve-margin/capacity blocks of a `.txt` datafile, writing a sibling output | input `.txt`, `--fallback-xlsx` workbook | sibling output `.txt` | `python scripts/pipeline/patch_reserve_margin_repair_careful_xlsx.py <input> -o <output> --fallback-xlsx <path> [flags]`; called by B2 when `reserve_margin_xlsx_active` |
| `patch_storage_delay.py` | Non-destructive patcher: blocks storage builds for the first N model years then reopens `PWRLDS*`/`PWRSDS*` caps in later years, writing a sibling datafile plus a sibling OSeMOSYS model file with the new constraint | input `.txt`, `--model-input` | sibling output `.txt`, sibling model `.txt` | `python scripts/pipeline/patch_storage_delay.py <input> -o <output> --model-input <path> --model-output <path> [flags]`; called by B2 when `storage_delay_active` |
| `preprocess_data.py` | OSeMOSYS preprocessor: derives `MODEperTECHNOLOGY` / `MODExTECHNOLOGYperFUEL{in,out}` / `MODExTECHNOLOGYperSTORAGE{to,from}` sets from the activity-ratio and storage-link blocks, to cut matrix-generation time | input `.txt` | output `.txt` | `python scripts/pipeline/preprocess_data.py <data_infile> <data_outfile>` (positional args, no flags); called by B2 as the first patcher-chain step |
| `strip_storage.py` | Diagnostic patcher: removes selected storage facilities (and their feeding PWR techs) from a preprocessed `.txt`, writing a sibling output; source untouched | input `.txt` | sibling output `.txt` | `python scripts/pipeline/strip_storage.py <input> -o <output> --mode tech\|class\|all [--targets ...]`; called by B2 when `strip_storage_active` |
| `sync_historical_from_bau.py` | Copies BAU's cell values for a given year window into other scenarios' `A-O_Parametrization.xlsx` sheets, so historical/near-term years match across scenarios; supports `--protect-params` and a TX-specific protection toggle | `A-O_Parametrization.xlsx` of BAU and of the target scenario(s) | target scenario's `A-O_Parametrization.xlsx`, in place | `python scripts/pipeline/sync_historical_from_bau.py --apply --scenarios <S> --years 2023,2024,2025 [--protect-params ...] [--no-protect-tx]`; called by `A3_process.py`'s final harmonization step |
| `sync_patched_csvs_from_txt.py` | Extracts parameter blocks from the final patched `.txt` datafile and overwrites the matching otoole CSVs in the original A2 folder in place, so the combined input/output CSVs reflect what the solver actually consumed | patched `.txt` (`--txt`) | `outputs/A2_Outputs_Params_otoole/<scenario>/*.csv`, in place | called by B2 between the patcher chain and `generate_combined_input_file()`; standalone: `python scripts/pipeline/sync_patched_csvs_from_txt.py --txt <path> --csv-folder <dir> --params <names>` |
| `Z_AUX_capital_annualization_script.py` | Reads the combined outputs CSV and computes annualized capital investment per technology via the Capital Recovery Factor with temporal accumulation, adding an accumulated column | `outputs/RELAC_TX_Combined_Inputs_Outputs.csv` | same CSV, in place (adds column) | called by B2 when `annualize_capital: true` (imports `annualize_capital_investment`) |
| `setup_utils.py` | not tracked (gitignored legacy) | — | — | — |
| `maxcapacity.py` | not tracked (gitignored legacy) | — | — | — |

## How to run

Run from the repo root inside an Anaconda Prompt with the `OG-MOMF-env` environment
(`run.py` creates it):

```bash
python run.py                                          # whole DVC pipeline (B1 -> B2), creates the env
python scripts/pipeline/A3_process.py [--scenario BAU]  # regenerate A-O_* workbooks (~20 min)
python -u scripts/pipeline/B1_Run_Compiler.py           # B1 compiler + B1b validation (~10-20 min)
python -u scripts/pipeline/B2_Executing_OG_Model.py     # pre-solver chain + SOLVER (hours)  <- approval required
```

D-tools (manual editing helpers, run individually, no DVC stage):

```bash
python scripts/pipeline/D1_generate_editor_template.py   # build Secondary_Techs_Editor.xlsx
# ... edit inputs/data/Secondary_Techs_Editor.xlsx by hand ...
python scripts/pipeline/D2_update_secondary_techs.py      # write the edits back into A-O_*.xlsx
python scripts/pipeline/D3_load_lac_max_capacity_caps.py  # one-shot LAC SPV/WON ceilings (BAU)
python scripts/pipeline/D4_load_dsptrn_max_cap_inv.py --dry-run --scenario INV   # preview; add --apply to write
python scripts/pipeline/D5_load_fuel_var_costs.py --price-scenario REF          # fuel VariableCost load
```

## Order / dependencies

A0 → A1 → A2 → A3_process (`add_max_cap_investment_lid_rule` → `extend_lowerlimits_pwr` →
`B1b_Pre_solver_validation --auto-fix-all` per scenario, then `sync_historical_from_bau` once)
→ B1 (`B1_Run_Compiler.py` → `B1_Compiler.py` → `B1b_Pre_solver_validation.py`)
→ B2, whose `__main__` runs, per scenario, in this order (confirmed against
`B2_Executing_OG_Model.py`'s `CHAIN_ORDER` list and the call sequence at the bottom of the file):

1. otoole CSV → `.txt` conversion (`process_scenario_folder`, `run_otoole_conversion`)
2. `preprocess_data.py` (always)
3. `inject_DaysInDayType.py` (always)
4. `patch_storage_delay.py` — if `storage_delay_active`
5. `strip_storage.py` — if `strip_storage_active` (mutually exclusive with step 4 in practice)
6. `open_pwrbck_caps.py` — if `open_pwrbck_active`
7. `patch_reserve_margin_repair_careful_xlsx.py` — if `reserve_margin_xlsx_active`
8. `patch_activity_upper_limit.py` (imported, not a subprocess) — if `activity_upper_limit_active`
9. dispatch floors, `scripts/fix_dispatch/write_floors.py` (outside this folder) — if `dispatch_floors_active`
10. `sync_patched_csvs_from_txt.py` — if `sync_patched_csvs_active` (default False; True in
    `Config_MOMF_T1_AB.yaml`); overwrites the A2 otoole CSVs from the final patched `.txt`
    (runs BEFORE the solve, between the patcher chain and `generate_combined_input_file`)
11. Tx chain: `scripts/tx_chain/veg_tx_constraints.py` (barrier, produces FLOORED_VEGCON files) then
    the `scenario_transforms` list (cost-sensitivity scripts under `scripts/tx_chain/`) — if
    `veg_tx_active` / `scenario_transforms` is configured
12. solve (`main_executer`: solver run, otoole results, per-scenario `scripts/tools/concatenate_relac.py`)
13. `concatenate_all_scenarios` — combines all scenarios into `outputs/RELAC_TX_*.csv`
14. `Z_AUX_capital_annualization_script.py` — if `annualize_capital: true`

## Gotchas

- B2 is the solver step: hours per run, overwrites `outputs/`; requires explicit approval.
- B2/otoole (not B1) writes the `.txt` datafiles in `outputs/Executables/`.
- `sync_patched_csvs_from_txt.py` runs BEFORE the solve (right after the patcher chain), not after
  it — it exists so `generate_combined_input_file`/`concatenate_all_scenarios` reflect the patched
  inputs the solver actually consumed.
- `sync_historical_from_bau.py` does not copy `Projection.Mode`.
- INV/OPT/VGB equal BAU through 2026; divergence starts 2027.
- `patch_activity_upper_limit.py` is imported directly by B2 (no subprocess, no CLI) and is not
  currently listed among the `dvc.yaml` `executing` stage deps, unlike the other chain scripts.
- `setup_utils.py` and `maxcapacity.py` are gitignored legacy modules; do not depend on them.
