# scripts/tools — country templates, live pipeline helpers, and one-shot maintenance scripts

Mixed folder: a few scripts are **live** (imported or subprocess-called by the `scripts/pipeline`
chain — `concatenate_relac.py` by B2, `Z_AUX_D1b_set_trn_limits_from_flows.py` by D2,
`Z_AUX_fix_excel_profiles.py` by `A3_migrate_old_inputs_CLG.py`), two are the **country-management**
tools documented in `docs/country-management.md` (`Z_generate_country_template.py`,
`Z_validate_country_data.py`), and the rest are `Z_AUX_*`/`Z_TEMP_*` maintenance or one-shot data
tools, each described from its own module docstring below. Two sub-folders have their own READMEs:
`data_patches/` (data patches already applied to `inputs/`, versioned as reproducible history — see
`scripts/tools/data_patches/README.md`) and `verification/` (byte-for-byte verification procedure for
the `inputs/scripts/outputs` restructure — see `scripts/tools/verification/README.md`).

## Scripts

| Script | What it does | Reads | Writes | Run |
|---|---|---|---|---|
| `AUX_Z_recalc_shares.py` | Back-calculates Diesel / Fuel oil / Bunker shares in `Shares_PET_OIL_Split.xlsx` so `D2_update_secondary_techs.py` reproduces the `ResidualCapacity` values from `Old_Inputs` parametrization files; legacy scenario scope (`BAU`, `NDC`) hardcoded in `SCENARIO_CONFIG`, no CLI flags | `inputs/data/Shares_PET_OIL_Split.xlsx`, `inputs/data/OLADE - Capacidad instalada por fuente - Anual.xlsx`, `A-O_Parametrization.xlsx` under `Old_Inputs` (BAU/NDC) | `Shares_PET_OIL_Split.xlsx`, in place (`.xlsx.bak` backup first) | `python scripts/tools/AUX_Z_recalc_shares.py` |
| `concatenate_relac.py` | Concatenates one scenario's otoole result CSVs into a single combined CSV (one row per dimension combination, one column per parameter). **Live**: called by B2 as a subprocess right after the solve (`scripts/pipeline/B2_Executing_OG_Model.py`, `concat_csvs` config key) | positional `<outputs_folder>` (otoole per-parameter CSVs) | `<output_file>.csv` | `python scripts/tools/concatenate_relac.py <outputs_folder> <output_file>`; normally invoked by B2, not run standalone |
| `Z_AUX_apply_parametrization_review.py` | Applies `Conservar_con_ajuste`/`Quitar` actions from audit review workbooks (`A-O_Parametrization_Review_PWR.xlsx` → "Secondary Techs", `A-O_Parametrization_Review_Tx.xlsx` → "Demand Techs") onto `TotalAnnualMinCapacityInvestment` for BAU and INV, then sweeps every row so `TotalAnnualMaxCapacityInvestment`/`TotalAnnualMaxCapacity` stay consistent with the new floors; sets `Projection.Mode = 'User defined'` on touched rows | `A-O_Parametrization_Review_{PWR,Tx}.xlsx` per scenario, `A-O_Parametrization.xlsx` (Fixed Horizon Parameters, for `OperationalLife`) | `A-O_Parametrization.xlsx`, in place — only with `--apply` (timestamped backup) | `python scripts/tools/Z_AUX_apply_parametrization_review.py [--dry-run\|--apply] [--scenario BAU\|INV\|ALL]` |
| `Z_AUX_D1b_set_trn_limits_from_flows.py` | Pre-populates TRN interconnection Lower/Upper activity limits in `Secondary_Techs_Editor.xlsx` from bilateral flow data (±5% of `flujos_energia_estimados_optimizacion.xlsx`; flat projection from the 2025 value for 2026-2050). **Live**: imported by `D2_update_secondary_techs.py` (`read_flow_data`, `fill_trn_sheet`), part of the D-tools chain | `flujos_energia_estimados_optimizacion.xlsx` (matriz-de-balance folder) | `inputs/data/Secondary_Techs_Editor.xlsx`, in place | `python scripts/tools/Z_AUX_D1b_set_trn_limits_from_flows.py [--scenarios BAU,NDC]`; also imported by `D2_update_secondary_techs.py` |
| `Z_AUX_fix_excel_profiles.py` | Normalizes `SpecifiedDemandProfile` sums in the "Profiles" sheet of `A-O_Demand.xlsx` to exactly 1.0 per country/year (fixes 0.99/1.01 rounding that breaks OSeMOSYS). **Live**: imported by `A3_migrate_old_inputs_CLG.py` (`normalize_excel_profiles`), its legacy migration path — see `scripts/pipeline/README.md` for that script's historical-one-shot status | `A-O_Demand.xlsx` of each scenario | same file, in place (timestamped backup first) | `python scripts/tools/Z_AUX_fix_excel_profiles.py`; also imported by `A3_migrate_old_inputs_CLG.py` |
| `Z_AUX_united_regions.py` | One-shot Brazil region-consolidation tool: with `parametrization=True` unifies `BRACN`→`BRAXX`, drops the other BRA regional splits and merges BRA↔country TRN interconnections in "Fixed Horizon Parameters"; with `demand=True`/`storage=True` does the equivalent consolidation for `A-O_Demand.xlsx` / `A2_Extra_Inputs/A-Xtra_Storage.xlsx`. Scenario and which branch runs are hardcoded at the top of the file (`folder = 'BAU'`, boolean flags) — edit before running, no CLI | `A-O_Parametrization.xlsx` / `A-O_Demand.xlsx` / `A-Xtra_Storage.xlsx`, per the active flag (scenario = `folder`) | `A-O_Parametrization_cleaned.xlsx` (new file, parametrization branch); `A-O_Demand.xlsx` and `A-Xtra_Storage.xlsx` in place (demand/storage branches) | `python scripts/tools/Z_AUX_united_regions.py` (after editing the flags/`folder` at the top) |
| `Z_AUX_update_maxcap_inv_from_tool.py` | Merges `TotalAnnualMaxCapacityInvestment` into the "Secondary Techs" sheet from two sources: `LAC_maxcap_tool.xlsx` (Export sheet, LOGISTIC×HEADROOM saturating-cap table, 12 PWRSPV*/PWRWON* techs) takes precedence over `LAC_maxcap_tool_complementary.xlsx` (Updated sheet, all PWR* techs); copies `Projection.Mode` only on rows that received a value; docstring notes only BAU is populated today even though `SCENARIOS` lists BAU/INV/OPT/VGB | `inputs/data/LAC_maxcap_tool.xlsx`, `inputs/data/LAC_maxcap_tool_complementary.xlsx` | `A-O_Parametrization.xlsx` / Secondary Techs, in place — only with `--apply` (backup unless `--no-backup`) | `python scripts/tools/Z_AUX_update_maxcap_inv_from_tool.py [--dry-run\|--apply] [--no-backup] [--scenario BAU] [--tool PATH] [--complementary PATH]` |
| `Z_AUX_update_transmission_iar.py` | Updates the Input Activity Ratio (IAR) of transmission technologies per country (6 prefixes × 19 countries) in the "Demand Techs" sheet of `A-O_AR_Model_Base_Year.xlsx` (column D, mode 1) and `A-O_AR_Projections.xlsx` (year columns, "Input" rows only), from a hardcoded per-country IAR table (η = 1 − α·d) | `A-O_AR_Model_Base_Year.xlsx`, `A-O_AR_Projections.xlsx` per scenario | same files, in place (writes by default; `.bak` backup unless `--no-backup`) | `python scripts/tools/Z_AUX_update_transmission_iar.py [--scenario S ...] [--dry-run] [--no-backup]` |
| `Z_generate_country_template.py` | Country-management tool: generates the minimum CSV set for a new country in `OG_csvs_inputs`, copied from a reference country; does not modify the original input files. See `docs/country-management.md` | `inputs/OG_csvs_inputs/*.csv`, `inputs/config/Config_country_codes.yaml` (`template_generation` section) | new CSVs under an output directory (default `templates/<new_code>`), for manual review before merging | `python scripts/tools/Z_generate_country_template.py` (reads YAML) or `--new NCC --ref ARG -i BOL PRY [--output DIR] [--region R] [--lat LAT] [--lon LON]` |
| `Z_TEMP_add_pwrbck_to_scenarios.py` | Upserts `PWRBCK*` rows into the BAU/INV/OPT Excel workbooks from `OG_csvs_inputs`, leaving non-`PWRBCK` rows untouched (existing PWRBCK rows are overwritten, new ones appended); sets `Projection.Mode = 'User defined'` on every sheet that has that column. Imports `assign_tech_type`/`parse_fuel_name`/`parse_tech_name`/`remap_pwrbck_output_fuel` from `scripts/pipeline/A1_Pre_processing_OG_csvs.py` to stay consistent with the A1 tech/fuel parsing | `inputs/OG_csvs_inputs/` (CapitalCost, FixedCost, VariableCost, CapacityToActivityUnit, OutputActivityRatio) | `A-O_Parametrization.xlsx` (Secondary Techs, VariableCost, Fixed Horizon Parameters), `A-O_AR_Model_Base_Year.xlsx` / `A-O_AR_Projections.xlsx` (Secondary), in place — only with `--apply` | `python scripts/tools/Z_TEMP_add_pwrbck_to_scenarios.py [--dry-run\|--apply] [--scenarios BAU INV OPT] [--scen-paths ...] [--pwrbck-varcost VALUE]` |
| `Z_validate_country_data.py` | Country-management tool: validates that a country has all required sets (TECHNOLOGY/FUEL/EMISSION/STORAGE) and parameters in `OG_csvs_inputs`; read-only, prints a summary or detailed report. See `docs/country-management.md` | `inputs/OG_csvs_inputs/*.csv`, `inputs/config/Config_country_codes.yaml` | — (stdout only) | `python scripts/tools/Z_validate_country_data.py [--country ARG] [--report] [--quiet]` |
| `test_inputs.py` | not tracked (gitignored) | — | — | — |

`data_patches/` and `verification/` are documented in their own READMEs (linked above).

## How to run

Most of these are single-file, standalone scripts run from the repo root with the `OG-MOMF-env`
conda environment active:

```bash
python scripts/tools/Z_validate_country_data.py --country ARG   # read-only check
python scripts/tools/Z_generate_country_template.py             # reads Config_country_codes.yaml
python scripts/tools/Z_AUX_apply_parametrization_review.py --dry-run   # preview, default
```

The **live** scripts (`concatenate_relac.py`, `Z_AUX_D1b_set_trn_limits_from_flows.py`,
`Z_AUX_fix_excel_profiles.py`) are normally invoked by the pipeline itself (B2, D2,
`A3_migrate_old_inputs_CLG.py` respectively); running them standalone is for debugging only.

## Gotchas

- `AUX_Z_recalc_shares.py`, `Z_AUX_apply_parametrization_review.py` and
  `Z_AUX_update_maxcap_inv_from_tool.py` read external reference workbooks
  (`Old_Inputs`, review files, `LAC_maxcap_tool*.xlsx`) that are not regenerated by the normal
  A3→B1→B2 chain; missing files fail loudly rather than silently.
- `Z_AUX_united_regions.py` has no CLI: the scenario (`folder`) and which branch runs
  (`parametrization`/`demand`/`storage`) are booleans/constants at the top of the file — read
  them before running, since only one branch is meant to run per invocation.
- `Z_TEMP_add_pwrbck_to_scenarios.py` imports from `scripts/pipeline/A1_Pre_processing_OG_csvs.py`
  to reuse its tech/fuel parsing; keep the two in sync if that parsing logic changes.
- Of the writers that touch "Secondary Techs" (the sheet with a `Projection.Mode` column),
  `Z_AUX_apply_parametrization_review.py`, `Z_AUX_united_regions.py`,
  `Z_AUX_update_maxcap_inv_from_tool.py` and `Z_TEMP_add_pwrbck_to_scenarios.py` set
  `Projection.Mode = 'User defined'` on the rows they touch, matching the "when writing: pin
  column G" rule used across the repo's Excel-writing tools. The other writers here
  (`AUX_Z_recalc_shares.py`, `Z_AUX_D1b_set_trn_limits_from_flows.py`,
  `Z_AUX_fix_excel_profiles.py`, `Z_AUX_update_transmission_iar.py`) touch sheets without that
  column ("Demand Techs", or a non-Parametrization workbook) and do not set it.
- `test_inputs.py` is listed in `.gitignore` and not present in this checkout.
