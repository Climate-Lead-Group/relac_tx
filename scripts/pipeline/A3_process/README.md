# scripts/pipeline/A3_process — rule scripts applied by A3

Library/CLI modules called by `scripts/pipeline/A3_process.py` per scenario, configured by
`inputs/config/A3_process/lid_rule.yaml`. They rewrite cells of `A-O_Parametrization.xlsx` (sheet
"Secondary Techs") for the scenarios listed in the YAML. This README also covers the
`rules_scripts/` sub-folder.

## Scripts

| Script | What it does | Reads | Writes | Run |
|---|---|---|---|---|
| `rules_scripts/add_max_cap_investment_lid_rule.py` | Fills `TotalAnnualMaxCapacityInvestment` for generation techs with `ResidualCapacity > 0` or `TotalAnnualMinCapacityInvestment > 0` with a calibrated per-year "lid" (`uniform` or `proportional` mode, scaled by demand growth); idempotent, recognizes prior 9999 placeholders | `A-O_Parametrization.xlsx` (Secondary Techs) | same workbook, in place, plus a `lid_rule_changes_<ts>.json` audit log | called by `A3_process.py` (step 1) for every scenario; standalone: `python add_max_cap_investment_lid_rule.py --input-dir <scenario_dir> [--modify-from-year Y] [--force-overwrite]` |
| `rules_scripts/extend_lowerlimits_pwr.py` | Extends the 2024 value of `TotalTechnologyAnnualActivityLowerLimit` for PWR techs flat through 2050 in "Secondary Techs", so the calibration floor does not expire; `--include-types` restricts it to a subset of PWR type codes | `A-O_Parametrization.xlsx` (Secondary Techs) | same workbook, in place, plus an `extend_lowerlimits_pwr_changes_<ts>.json` audit log | called by `A3_process.py` (step 2) only for scenarios listed in `lowerlimit_scenarios`; standalone: `python extend_lowerlimits_pwr.py --input-dir <scenario_dir> [--include-types HYD,GEO,...] [--force-overwrite]` |
| `rules_scripts/reset_lowerlimits_from_base.py` | Resets `TotalTechnologyAnnualActivityLowerLimit` for PWR techs in a scenario back to the Base scenario's values (2023–2050), undoing any prior `extend_lowerlimits_pwr.py`/B1b-V3 extension | target scenario's and Base's `A-O_Parametrization.xlsx` (Secondary Techs) | target workbook, in place (timestamped backup first), plus a `reset_lowerlimits_from_base_changes_<ts>.json` audit log | **not invoked by `A3_process.py`** — manual, standalone tool run before re-running A3: `python reset_lowerlimits_from_base.py --input-dir <scenario_dir> [--base-dir <base_scenario_dir>]` |

## How to run

`python scripts/pipeline/A3_process.py --scenario BAU` (runs the rules for that scenario).

## Order / dependencies

For each scenario, `A3_process.py` invokes, in order:

1. `rules_scripts/add_max_cap_investment_lid_rule.py --input-dir <scenario_dir> --modify-from-year 2026 [--force-overwrite]`
2. `rules_scripts/extend_lowerlimits_pwr.py --input-dir <scenario_dir> --modify-from-year 2026 [--include-types ...] [--force-overwrite]`
   — only if the scenario has an entry in `lowerlimit_scenarios`; otherwise skipped
3. `B1b_Pre_solver_validation.py --auto-fix-all --modify-from-year 2026` (not in this folder; lives
   in `scripts/pipeline/`) — always runs, regardless of the `lowerlimit_scenarios` allowlist

Then, once for all scenarios (not per scenario): `sync_historical_from_bau.py --apply` for every
scenario listed under `historical_sync_through` in `lid_rule.yaml`.

`reset_lowerlimits_from_base.py` is outside this chain: it is a manual reset run by hand before
re-running the A3 workflow, not something `A3_process.py` calls.

## Gotchas

- `lowerlimit_scenarios` in `lid_rule.yaml` is a map: BAU/INV = all 18 PWR types, OPT = renewable
  only (`--include-types`).
- B1b V3 always runs after these rules; reports on disk may be older than the code.
