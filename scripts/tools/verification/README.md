# scripts/tools/verification — byte-for-byte verification of the inputs/scripts/outputs restructure

Procedure to demonstrate that B1 and the B2 pre-solver chain produce exactly the same files in the
new layout (branch `restructure/inputs-scripts-outputs`) as in the old one (`clean-sirelac` @
`c8f0efc`). The solver is not run. Corresponds to Tasks 1, 18 and 19 of the plan
`docs/superpowers/plans/2026-09-07-restructure-inputs-scripts-outputs.md`; the acceptance criterion
is **zero differences** (spec §9.2 and §12).

Machine requirements: a clone of the repo with both branches, the `OG-MOMF-env` conda environment
(created by `run.py`), `otoole` and `glpsol` on the PATH (B2 uses them even without solving the
model). Estimated time per run: 30-45 min (B1 ~10-20, B2 without solver ~15-25).

## Scripts

| Script | What it does | Run |
|---|---|---|
| `compare_manifests.py` | Two subcommands. `manifest <root> <old\|new> <out.json>` computes md5 of every comparable product (`A2_Output_Params`, `A2_Outputs_Params_otoole`, `Executables/**.txt`, the patched model, the root datafile, `upstream_floor_rows.csv`), with layout-independent keys. `diff <a.json> <b.json>` lists missing, extra and differing entries; exits 0 when everything matches. | `python scripts/tools/verification/compare_manifests.py manifest <root> <old\|new> <out.json>`; `python scripts/tools/verification/compare_manifests.py diff <a.json> <b.json>` |
| `verify_config.sh <Config_MOMF_T1_AB.yaml>` (not Python) | Sets `execute_model`, `create_matrix`, `concat_scenarios_csv`, `annualize_capital` and `del_files` to `False` (same config on both sides). | `bash scripts/tools/verification/verify_config.sh <path/to/Config_MOMF_T1_AB.yaml>` |

## How to run

From the root of the clone (branch `restructure/inputs-scripts-outputs`), with `V=../relac_tx_verif`
as the local folder for manifests and logs (outside the repo):

```bash
mkdir -p ../relac_tx_verif; V=../relac_tx_verif

# 1. Clean worktrees: old layout and new layout
git worktree add ../relac_tx_baseline clean-sirelac
git worktree add ../relac_tx_new      restructure/inputs-scripts-outputs
bash scripts/tools/verification/verify_config.sh ../relac_tx_baseline/t1_confection/Config_MOMF_T1_AB.yaml
bash scripts/tools/verification/verify_config.sh ../relac_tx_new/inputs/config/Config_MOMF_T1_AB.yaml

# 2. Baseline (old layout)
( cd ../relac_tx_baseline \
  && PYTHONHASHSEED=0 conda run -n OG-MOMF-env --no-capture-output python -u t1_confection/B1_Run_Compiler.py 2>&1 | tee $V/baseline_B1.log \
  && PYTHONHASHSEED=0 conda run -n OG-MOMF-env --no-capture-output python -u t1_confection/B2_Executing_OG_Model.py 2>&1 | tee $V/baseline_B2.log )
python scripts/tools/verification/compare_manifests.py manifest ../relac_tx_baseline old $V/manifest_baseline.json

# 3. New (inputs/ scripts/ outputs/ layout)
( cd ../relac_tx_new \
  && PYTHONHASHSEED=0 conda run -n OG-MOMF-env --no-capture-output python -u scripts/pipeline/B1_Run_Compiler.py 2>&1 | tee $V/new_B1.log \
  && PYTHONHASHSEED=0 conda run -n OG-MOMF-env --no-capture-output python -u scripts/pipeline/B2_Executing_OG_Model.py 2>&1 | tee $V/new_B2.log )
python scripts/tools/verification/compare_manifests.py manifest ../relac_tx_new new $V/manifest_new.json

# 4. Comparison
python scripts/tools/verification/compare_manifests.py diff $V/manifest_baseline.json $V/manifest_new.json | tee $V/diff_result.txt
```

Expected checks: in both worktrees B2 creates 13 `Executables/<S>_0/` folders (BAU BAC BSR INV INVWF
ISR ISRWF OPC OPT VGB VGBWF VSR VSRWF) and finishes with `veg_tx PASS`; the `diff` prints
`SOLO EN BASELINE: 0`, `SOLO EN NUEVO: 0`, `DISTINTOS: 0`. If B1b (the pre-solver validator) prompts
for anything in the baseline, answer exactly the same way in the new run.

Extras (plan Task 18, steps 5-7): compare `A2_Structure_Lists.xlsx` by content with openpyxl (the
xlsx carries a timestamp, so md5 does not work) and the chain logs (`grep -E "PASS|FAIL|veg_tx|\[chain\]"`
on both `*_B2.log` files, normalizing `t1_confection/` and `outputs/`). Optional (Task 19): run
A0 → A1 → A2 in both worktrees and compare `A1_Outputs/**/*.xlsx` sheet by sheet.

## Gotchas

- Requirements: the conda env `OG-MOMF-env` (created by `run.py`), `otoole` and `glpsol` on the
  PATH, and 30-45 minutes per run (B1 ~10-20 min, B2 without solver ~15-25 min).
- The acceptance criterion is **zero differences**: `SOLO EN BASELINE: 0`, `SOLO EN NUEVO: 0`,
  `DISTINTOS: 0` from `compare_manifests.py diff`.
- If any difference appears, the only acceptable classes are comments with absolute paths or
  timestamps embedded in a generated file; any difference in values is a path bug that must be
  traced to the responsible script. Record the result in section 13 of the spec
  (`docs/superpowers/specs/2026-09-07-restructure-inputs-scripts-outputs-design.md`) and remove the
  worktrees (`git worktree remove --force ../relac_tx_baseline ../relac_tx_new; git worktree prune`).
