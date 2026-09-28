# scripts/tx_chain — transmission constraints and scenario-transform stage of B2

Post-FLOORED stage of `B2_Executing_OG_Model.py`: `veg_tx_constraints.py` runs once, as a
cross-scenario barrier, over the `_FLOORED.txt` of every base scenario, then the
`scenario_transforms` list in `inputs/config/Config_MOMF_T1_AB.yaml` runs each
`cost_sensitivity_v_*`/`nli_sr_recompute.py` script in turn, each producing or modifying
scenario datafiles under `outputs/Executables/<SCEN>_0/`. All seven scripts here are currently
invoked by B2 (`veg_tx_active` and `scenario_transforms`, both active in `Config_MOMF_T1_AB.yaml`)
— none is a one-shot manual tool.

## Scripts

| Script | What it does | Reads | Writes | Run |
|---|---|---|---|---|
| `veg_tx_constraints.py` | Reference implementation of the RELAC transmission rules (FIG 3 workstream): (0) swaps the committed Tx floor so OPT >= REF/INV/VGB from 2027; (1) calibrates a real-cost scale factor so the REF committed investment averages the IEA anchor (`CALIB_ANCHOR_MUSD=3080.0`, `veg_tx_constraints.py:136`) over `CALIB_WINDOW=(2024, 2029)` (`veg_tx_constraints.py:143`); (2) caps non-planned lines (TRNNLI/RNWNLI) to the remainder of a regional envelope `I_region(year) = 3300 (2022 MUSD) * 1.01^(year-2022)` after planned+RPO investment (`ANCHOR_MUSD=3300`, `ENV_GROWTH=0.01`, `veg_tx_constraints.py:147,291,342`), years 2030+, vegetativos only; (3) caps repowering (TRNRPO/RNWRPO) to a flat 1%/year of existing stock from 2028 (`RPO_PCT_START=RPO_PCT_END=0.01`, `veg_tx_constraints.py:154-155`); (3b) caps planned lines (PWRTRN/RNWTRN) to the post-swap OPT floor in all 4 scenarios; (4) escalates the corrected CapitalCost of the 6 Tx families by `COST_ESC_RATE=0.003`/year from `COST_ESC_FROM=2025` (`veg_tx_constraints.py:160`). Writes over COPIES only, never the original | `outputs/Executables/<SCEN>_0/*_FLOORED.txt` (all base scenarios), `--needs-csv` (`inputs/tx_chain/outputs_BSR/NewCapacity.csv`) | `outputs/Executables/<SCEN>_0/*_VEGCON.txt` (or flat in `outputs/tx_chain/` in legacy mode) | `python scripts/tx_chain/veg_tx_constraints.py --base-dir <Executables> --needs-csv <NewCapacity.csv>`; called by B2 once, after the per-scenario loop, when `veg_tx_active` (`veg_tx_script`) |
| `cost_sensitivity_v_FA.py` | Cost-sensitivity transform: scales `VariableCost` of fossil `MIN*` supply techs (COA/GAS/OIL/PET/OTH/COG) by `FUEL_MULT=1.7` (EIA AEO2025 High Oil Price case); values only, structure/bounds untouched; restricted to `BAC`/`INV` | base `_VEGCON.txt` (`BAC`, `INV`) | new datafile (`BFA`, `IFA`) under `outputs/Executables/<NEW>_0/` (or flat in `outputs/tx_chain/`) | `python scripts/tx_chain/cost_sensitivity_v_FA.py --executables-dir <Executables>`; called by B2 as the `cost_sensitivity_FA` entry of `scenario_transforms` |
| `cost_sensitivity_v_FB.py` | Same mechanism as FA but `FUEL_MULT=0.52` (EIA AEO2025 Low Oil Price, Brent 47 vs 91 USD/b in 2050); consolidates former v7/v9; restricted to `BAC`/`INV` | base `_VEGCON.txt` (`BAC`, `INV`) | new datafile (`BFB`, `IFB`) | `python scripts/tx_chain/cost_sensitivity_v_FB.py --executables-dir <Executables>`; called by B2 as the `cost_sensitivity_FB` entry of `scenario_transforms` |
| `cost_sensitivity_v_RA.py` | Renewable-only cost-sensitivity: scales `CapitalCost` of solar/CSP x1.33, wind x1.17, battery storage (PWRSDS) x1.49; **multipliers are a placeholder copy of RB, not yet calibrated for "Renovables Altos"** (module docstring, 2026-09-16); `PWRLDS` excluded; restricted to `BAC`/`INV` | base `_VEGCON.txt` (`BAC`, `INV`) | new datafile (`BRA`, `IRA`) | `python scripts/tx_chain/cost_sensitivity_v_RA.py --executables-dir <Executables>`; called by B2 as the `cost_sensitivity_RA` entry of `scenario_transforms` |
| `cost_sensitivity_v_RB.py` | Same mechanism as RA with calibrated multipliers: solar/CSP x0.60, wind x0.75, battery storage x0.50 (NREL ATB 2024 Moderate case); restricted to `BAC`/`INV` | base `_VEGCON.txt` (`BAC`, `INV`) | new datafile (`BRB`, `IRB`) | `python scripts/tx_chain/cost_sensitivity_v_RB.py --executables-dir <Executables>`; called by B2 as the `cost_sensitivity_RB` entry of `scenario_transforms` |
| `cost_sensitivity_v_SR_WF.py` | "SOLO REPOTENCIACION PLANIFICADA": for every RPO tech (TRNRPO*/RNWRPO*, 19 countries), pins `TotalAnnualMaxCapacityInvestment = TotalAnnualMinCapacityInvestment` in every model year, so the model can build exactly the planned repowering and nothing else; `TotalAnnualMinCapacityInvestment` itself is untouched; covers the water-fill family (`ISRWF`/`VSRWF`) added in v11 | base `_VEGCON.txt` for `BAU`, `INV`, `VGB`, `INVWF`, `VGBWF` | new datafile (`BSR`, `ISR`, `VSR`, `ISRWF`, `VSRWF`) | `python scripts/tx_chain/cost_sensitivity_v_SR_WF.py --executables-dir <Executables>`; called by B2 as the `cost_sensitivity` entry of `scenario_transforms` (first in the list) |
| `nli_sr_recompute.py` | Runs after `cost_sensitivity_v_SR_WF.py`, only on `ISR`/`VSR`/`ISRWF`/`VSRWF`: recomputes the NLI (TRNNLI/RNWNLI) ceilings using the pinned RPO floor as the true RPO cost (instead of the inherited INV/VGB ceiling-RPO cost), returning the budget the RPO pin left unspent to NLI; touches only `MaxCapacityInvestment`/`TotalAnnualMaxCapacity` rows for TRNNLI/RNWNLI, years 2030+; idempotent | `_VEGCON.txt`-chain datafile of `ISR`/`VSR`/`ISRWF`/`VSRWF` (post `cost_sensitivity_v_SR_WF`) | same datafiles, in place | `python scripts/tx_chain/nli_sr_recompute.py --executables-dir <Executables>`; called by B2 as the `nli_sr_recompute` entry of `scenario_transforms` (right after `cost_sensitivity`) |

## How to run

`veg_tx_constraints.py` and the `scenario_transforms` scripts are designed to run inside the B2
chain (`--base-dir`/`--executables-dir` pointing at `outputs/Executables`); running them standalone
without that flag falls back to a flat legacy layout in `outputs/tx_chain/`:

```bash
python scripts/tx_chain/veg_tx_constraints.py --base-dir outputs/Executables --needs-csv inputs/tx_chain/outputs_BSR/NewCapacity.csv
python scripts/tx_chain/cost_sensitivity_v_SR_WF.py --executables-dir outputs/Executables
python scripts/tx_chain/nli_sr_recompute.py --executables-dir outputs/Executables
python scripts/tx_chain/cost_sensitivity_v_FA.py --executables-dir outputs/Executables
python scripts/tx_chain/cost_sensitivity_v_FB.py --executables-dir outputs/Executables
python scripts/tx_chain/cost_sensitivity_v_RB.py --executables-dir outputs/Executables
python scripts/tx_chain/cost_sensitivity_v_RA.py --executables-dir outputs/Executables
```

In normal use these all run automatically as part of
`python -u scripts/pipeline/B2_Executing_OG_Model.py` (approval required — solver step).

## Order / dependencies

Per `Config_MOMF_T1_AB.yaml` (`veg_tx_script`, then `scenario_transforms` in list order) and
`scripts/pipeline/B2_Executing_OG_Model.py` (`run_veg_tx_stage`, `run_scenario_transforms`), both
called once after the per-scenario `_FLOORED.txt` loop, before `export_root_datafile`/solve (see
`scripts/pipeline/README.md` "Order / dependencies", steps 11-12):

1. `veg_tx_constraints.py` — barrier: requires every base scenario's `_FLOORED.txt` to exist first;
   produces `*_VEGCON.txt` for all base + derived scenarios.
2. `cost_sensitivity_v_SR_WF.py` (`scenario_transforms` entry `cost_sensitivity`) — produces
   `BSR`/`ISR`/`VSR`/`ISRWF`/`VSRWF` from the VEGCON datafiles.
3. `nli_sr_recompute.py` (`scenario_transforms` entry `nli_sr_recompute`) — in place on
   `ISR`/`VSR`/`ISRWF`/`VSRWF`, must run after step 2.
4. `cost_sensitivity_v_FA.py`, `cost_sensitivity_v_FB.py`, `cost_sensitivity_v_RB.py`,
   `cost_sensitivity_v_RA.py` — each independent of the others and of steps 2-3, producing
   `B*`/`I*` scenarios from `BAC`/`INV` VEGCON datafiles.

## Gotchas

- All seven scripts are wired into B2 today (`veg_tx_active: True`, all six `scenario_transforms`
  entries present in `Config_MOMF_T1_AB.yaml`); none is a "historical, do not re-run" one-shot.
- `cost_sensitivity_v_RA.py`'s multipliers are an explicit placeholder (identical to RB) pending
  calibration — its own docstring says so; do not read RA results as a real "Renovables Altos"
  scenario yet.
- Every `cost_sensitivity_v_*`/`nli_sr_recompute.py` script parses `--executables-dir` with
  `parse_known_args()` at import time (before `if __name__ == "__main__"`), so importing the
  module also parses `sys.argv`.
- `veg_tx_constraints.py` is the single largest file in the repo's `scripts/tx_chain` (~1400
  lines); the numeric derivations (IEA/SEGIB anchor, repowering rate, cost escalation) are
  documented at length in its module docstring — read that before changing a constant.
