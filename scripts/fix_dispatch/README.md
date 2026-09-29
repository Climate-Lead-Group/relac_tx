# scripts/fix_dispatch — fossil dispatch-floor fix (candidates, feasibility, writer, QA)

Fixes a gap in the pre-2026 activity floors: `TotalTechnologyAnnualActivityLowerLimit` stops at
2026 for most fossil fleets, so large fleets with a forced build (e.g. BRA/MEX/ARG gas) go
completely unfloored from 2027 on. `make_candidates.py` computes 2027-2050 floors per
(scenario, tech, year) into the versioned `inputs/tx_chain/fix_dispatch/candidate_floors.csv`;
`write_floors.py` is the only script B2 calls, reading that CSV and writing floored copies of the
preprocessed `.txt`. The rest are read-only QA/analysis tools around that CSV. `relac_io.py` is
the shared IO library (never writes a live input).

## Scripts

| Script | What it does | Reads | Writes | Run |
|---|---|---|---|---|
| `relac_io.py` | Shared read-only IO/parsing library: loads activity limits and forced builds from the preprocessed GLPK/MathProg `.txt`, other parameters from the A2 otoole CSVs, model outputs from the combined CSV; defines `SCENARIOS`, fuel-code classification (`FOSSIL_CODES`, `RENEWABLE_CODES`, …) and `C2A_DEFAULT` | `outputs/Executables/<SCEN>_0/*.txt`, `outputs/A2_Outputs_Params_otoole/<SCEN>/*.csv`, combined outputs CSV | `outputs/fix_dispatch/cache/*.parquet` (cache only) | library only (imported by every other script here) |
| `feasibility.py` | Shared feasibility model: `feasible_floor(tech, year, floor_PJ)` checks a candidate floor against the binding capacity ceiling (`TotalAnnualMaxCapacity`, or `ResidualCapacity` + cumulative `TotalAnnualMaxCapacityInvestment`) and `TotalTechnologyAnnualActivityUpperLimit`; a NECESSARY-condition (generous upper bound), not a dispatch prediction | preprocessed `.txt`, A2 otoole CSVs (via `relac_io`) | — | library only (imported by `write_floors.py`, `floor_effect.py`, `preflight_separation.py`, `validate_constraints.py`) |
| `make_candidates.py` | Generates 2027-2050 candidate floors for the full fossil fleet (`relac_io.nonren_floor_techs`, not the older 11-tech WORKING_SET); two scenario profiles per PI decision 2026-07-03 (COMMITTED = OPT/VGB held flat at the plan-grounded CF; PERMISSIVE = BAU/INV anchored to the same CF then declining); 2023-2026 is left untouched | preprocessed `.txt`, A2 otoole CSVs (via `feasibility.Feasibility`) | `inputs/tx_chain/fix_dispatch/candidate_floors.csv` | `python scripts/fix_dispatch/make_candidates.py`; **not called by B2** — manual step, re-run only to change a CF (see Gotchas) |
| `preflight_separation.py` | Read-only gate, input-side only: checks `candidate_floors.csv` as a share of `SpecifiedAnnualDemand` (identical across scenarios) so BAU never floors more fossil than OPT (and INV vs VGB), plus a non-crossing check from 2035 on; exits 1 on failure | `inputs/tx_chain/fix_dispatch/candidate_floors.csv` (or `--candidates`), A2 otoole CSVs | — | `python scripts/fix_dispatch/preflight_separation.py [--candidates FILE]`; called by B2 once, before the per-scenario loop, when `dispatch_floors_active` (`preflight_separation_active`) |
| `write_floors.py` | Writer: for each (scenario, tech, year) candidate row, `final_floor = max(existing_floor, candidate_floor_PJ)` — can only raise a floor, gated by `feasible_floor()`; writes a floored COPY of the preprocessed `.txt` next to the original, never edits it in place | `inputs/tx_chain/fix_dispatch/candidate_floors.csv`, target preprocessed `.txt` | `outputs/Executables/<SCEN>_0/Pre_processed_<SCEN>_0_..._FLOORED.txt`, `outputs/fix_dispatch/upstream_floor_rows.csv` | `python scripts/fix_dispatch/write_floors.py [--scenarios BAU OPT] [--dry-run]`; called by B2 per scenario when `dispatch_floors_active` (`dispatch_floors_script`) |
| `validate_constraints.py` | Read-only STEP 1 input validator: flags `FORCED_NO_FLOOR`, `FLOOR_ENDS_BEFORE_LIFE`, `FLOOR_CF_IMPLAUSIBLE`, `FLOOR_INFEASIBLE`, `FLOOR_NEAR_CAP`, `ORPHAN_FLOOR`, `SCENARIO_ASYMMETRY`, `PIPELINE_MISMATCH` per scenario | preprocessed `.txt`, A2 otoole CSVs, combined outputs CSV (via `relac_io`/`feasibility`) | `outputs/fix_dispatch/validation_report.txt`, `outputs/fix_dispatch/validation_flags.csv` | `python scripts/fix_dispatch/validate_constraints.py`; standalone QA, not called by B2 |
| `floor_effect.py` | Read-only STEP 2 calculator: for each candidate floor, computes only what the floor mathematically guarantees (forced generation, implied capacity factor, feasibility, implied fuel input/CO2, demand share) — a partial energy balance, not a dispatch prediction | `--candidates` CSV (default: working-set demo), A2 otoole CSVs | `outputs/fix_dispatch/floor_effect_report.csv` (or `--out`) | `python scripts/fix_dispatch/floor_effect.py [--candidates FILE] [--out FILE]`; standalone QA, not called by B2 |
| `fig_floor_effect.py` | Read-only: renders a 3-panel before/after figure of the floor fix, comparing the pre-floor baseline combined CSV against a manually-solved floored run (`solved_FLOORED/`, BAU+OPT only) | baseline and `solved_FLOORED` combined CSVs, `candidate_floors.csv`, preprocessed `.txt` | `outputs/fix_dispatch/fig_floor_effect.png` | `python scripts/fix_dispatch/fig_floor_effect.py`; standalone analysis, not called by B2 |

## How to run

From the repo root, in the `OG-MOMF-env` environment:

```bash
python scripts/fix_dispatch/make_candidates.py         # regenerate candidate_floors.csv (manual)
python scripts/fix_dispatch/preflight_separation.py    # gate: BAU/OPT and INV/VGB separation
python scripts/fix_dispatch/write_floors.py --scenarios BAU OPT   # write floored .txt copies
python scripts/fix_dispatch/validate_constraints.py    # STEP 1 input validation report
python scripts/fix_dispatch/floor_effect.py            # STEP 2 read-only floor-effect report
python scripts/fix_dispatch/fig_floor_effect.py        # before/after figure
```

`write_floors.py` and `preflight_separation.py` are also invoked automatically by
`scripts/pipeline/B2_Executing_OG_Model.py` (see Order / dependencies).

## Order / dependencies

1. `make_candidates.py` (manual, outside B2) reads the preprocessed `.txt` + A2 otoole CSVs and
   writes `inputs/tx_chain/fix_dispatch/candidate_floors.csv` — the single swappable input every
   downstream script reads.
2. `preflight_separation.py` — B2 runs this once, before the per-scenario loop, when
   `dispatch_floors_active` is set; a non-zero exit aborts B2 before any floor is written.
3. `write_floors.py` — B2 runs this per scenario (`--scenarios <name>`) right after
   `patch_activity_upper_limit`, producing the `_FLOORED.txt` that later chain steps
   (`sync_patched_csvs_from_txt.py`, the `tx_chain` stage) consume. See
   `scripts/pipeline/README.md` "Order / dependencies" for where this sits in the full B2 chain.
4. `validate_constraints.py`, `floor_effect.py` and `fig_floor_effect.py` are
   post-hoc, read-only analysis over `candidate_floors.csv` and/or solved outputs; none of them
   are called by B2.

## Gotchas

- `inputs/tx_chain/fix_dispatch/candidate_floors.csv` is the versioned input B2 actually reads
  (via `write_floors.py`); regenerating it with `make_candidates.py` changes what every future
  solve floors — an approval-required action, not a routine QA step.
- A candidate can only RAISE an existing floor (`write_floors.py`), never lower one; an infeasible
  raise is skipped and logged, never written.
- `fig_floor_effect.py` reads a manually-solved `outputs/fix_dispatch/solved_FLOORED/` run that is
  not reproducible by re-running B2 alone (BAU+OPT only, produced from a floored otoole CSV, not a
  floored `.txt`).
- None of these scripts write to a live `A-O_*.xlsx` or A2 otoole input; the only writes into
  `outputs/Executables/` are from `write_floors.py`: the `_FLOORED.txt` siblings plus a one-time
  `.bak` backup of the original preprocessed `.txt` (skipped on `--dry-run`, and only written once
  per file).
- `build_summary.py` (per-country/tier summary) was removed on 2026-09-29: it grouped by the
  `"tier"` column that `make_candidates.py` v3 replaced with `"profile"`, so it could no longer
  run; `outputs/fix_dispatch/candidate_floors_summary.csv` went with it.
