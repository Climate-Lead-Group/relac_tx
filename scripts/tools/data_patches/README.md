# scripts/tools/data_patches — data patches already applied to inputs/ (versioned history)

Scripts that modified the xlsx files in `inputs/` (formerly `t1_confection/`) between 2026-07-23 and
2026-09-01 and that were not yet in the repo. They are versioned here as **reproducible history**,
not to be run again: **all of their changes are ALREADY applied in `inputs/`** (restored from
`stash@{0}` on 2026-09-08, see `docs/superpowers/plans/2026-09-08-diagnostico-estado-C-solves.md`, spec kept on the author's disk only; not in git).
If run in apply mode against the current `inputs/`, the ones with a precondition fail ("already
applied") and the idempotent ones rewrite the same values; even so, **do not run them with
`--apply` / `DRY_RUN=False` without a real need** (e.g. after an A3 run that regenerates the A-O
workbooks).

Paths: all of them resolve `inputs/` via `scripts/common/relac_paths.py`
(`sys.path.insert(0, parents[2])` + `from common import relac_paths as P`). The logic is the
original; only the path constants and the "Usage" lines changed.

## Scripts

| Script | What it does | Reads / writes | Applied | Safe mode / Run |
|---|---|---|---|---|
| `add_bds_storage.py` | Clones the SDS→BDS family (`PWRSDS{C}XX`→`PWRBDS{C}XX`, `SDS{C}XX01`→`BDS{C}XX01`) onto the non-renewable node `ELC{C}XX02`. Idempotent purge-and-reinsert keyed on `COUNTRIES`. Also inserts `BDS{C}XX01` into `xtra_scen.Storage` in `Config_MOMF_T1_A.yaml` and `BDS`/`PWRBDS` into `Config_MOMF_T1_AB.yaml`. | `A-O_AR_Model_Base_Year.xlsx` (Secondary), `A-O_AR_Projections.xlsx` (Secondary), `A-O_Parametrization.xlsx` (Fixed Horizon Parameters, Secondary Techs, VariableCost) for the 4 scenarios; `A2_Extra_Inputs/A-Xtra_Storage.xlsx` (3 sheets); the 2 YAML files in `inputs/config/` | 2026-09-04 with `COUNTRIES = ["CHL", "PER"]` (16 rows in Xtra: 4+4+8; per scenario 4/4/4/22/2 rows) | `DRY_RUN` is a **module-level constant** (`False` by default). Safe only via: `python -c "import add_bds_storage as b; b.run(countries=['CHL','PER'], dry_run=True, backup=False)"` from this folder |
| `validate_bds_structure.py` | Post-application auditor (V1-V10 on xlsx and YAML; optional V11 on a `Pre_processed_*.txt`). Read-only. | reads the same files | — | `python -c "import validate_bds_structure as v; v.audit(countries=['CHL','PER'])"` (with the default 19-country list, V1 fails, because only CHL and PER were cloned) |
| `test_add_bds_storage.py` | Test of the cloner in a temporary sandbox (a copy of `inputs/`); does not touch real files. | copy under `%TEMP%/bds_sandbox_*` | — | `python scripts/tools/data_patches/test_add_bds_storage.py` |
| `patch_nueva_capacidad_2040_tx_advance.py` | (1) `TotalAnnualMinCapacityInvestment` floors for 2040-2050 for 24 techs, **OPT only**, read from `Nueva_Capacidad_2040+_LAC - copia.xlsx` (external dataset in `Downloads/_Dataset_Transmission/`, `--xlsx` path); sets `Projection.Mode='User defined'`. (2) Interconnection advance in the 4 scenarios: `TRNCOLXXPANXX` RC 0.4 and UpperLimit 12.614 from 2029; `TRNBOLXXBRAXX` RC 0.42 and UpperLimit 13.245 from 2032. | `A-O_Parametrization.xlsx` / Secondary Techs (4 scenarios) | 2026-08-13 14:02 — log `nueva_capacidad_tx_changes_20260813_140245.json` (396 cells: 200 OPT floors + 8 RC and 41 UL per scenario) | `--dry-run` (requires the external xlsx; not needed with `--only-tx`) |
| `patch_open_maxcaps_pisos_OPT.py` | In OPT, where the new floor exceeds the `TotalAnnualMaxCapacityInvestment` cap, opens the cap to `floor × 1.01` (VGB precedent). `EMPTY` cells/rows = no cap, left untouched. | `A1_Outputs_OPT/A-O_Parametrization.xlsx` / Secondary Techs | 2026-08-13 14:25 — log `open_maxcaps_pisos_OPT_20260813_142555.json` (82 cells) | `--dry-run` (today reports 0 conflicts) |
| `patch_rpo_operationallife.py` | `OperationalLife` 20 → 50 in every row whose Tech contains `RPO` (`RNWRPO*`, `TRNRPO*`: 38 techs). Precondition: all at 20; otherwise the scenario is left untouched. | `A-O_Parametrization.xlsx` / Fixed Horizon Parameters, col. H (4 scenarios) | 2026-09-01 (backups `.bak_20260901_*` in the stash) | dry-run by default; `--apply` writes. Currently reports `NO SE SUSTITUYE: Value = 50` (already applied) |
| `patch_rnwtrnbraxx_residualcapacity.py` | `ResidualCapacity` of `RNWTRNBRAXX` 52.990319556 → 85.40 in I..AJ (2023-2050). Precondition: all 28 cells at 52.99. | `A-O_Parametrization.xlsx` / Demand Techs, row 676 (4 scenarios) | 2026-09-02 | dry-run by default; `--apply` writes. Currently reports `NO SE SUSTITUYE: = 85.4` (already applied) |
| `add_fuentes_sheet.py` | Adds/replaces the documentation sheet **`Fuentes`** (source, origin file/sheet and transformation per data block) at the end of each workbook, reading the master table `inputs/config/data_sources.csv` (`Archivo` column accepts `A|B`). Idempotent. No year columns → `sync_historical_from_bau.py` skips it; `B1_Compiler.py` excludes it the same way as `growth_formula`. | `A-O_Parametrization.xlsx` and `A-O_Demand.xlsx` for the 4 scenarios; `A2_Extra_Inputs/A-Xtra_Storage.xlsx`; templates `inputs/Miscellaneous/{A-O_Parametrization,A-O_Demand,A-Xtra_Storage}.xlsx` (title + header only, no rows: the templates have no data) | 2026-09-14 (78 / 23 / 5 rows per workbook type) | dry-run by default; `--apply` writes; `--no-templates` skips `Miscellaneous/`. Test: `python scripts/tools/data_patches/test_add_fuentes_sheet.py` |
| `test_add_fuentes_sheet.py` | Test suite for `add_fuentes_sheet.py`, run against temporary copies; never touches `inputs/` (sheet content, idempotency, `Archivo` filter, B1-style reads, template header-only rows). | same files as `add_fuentes_sheet.py` (copied to a temp dir) | none in the real tree; temp copies only | `python scripts/tools/data_patches/test_add_fuentes_sheet.py` |

## How to run

Safe (non-writing) invocations, from the repo root unless noted otherwise:

- `python -c "import add_bds_storage as b; b.run(countries=['CHL','PER'], dry_run=True, backup=False)"` (from `scripts/tools/data_patches`)
- `python -c "import validate_bds_structure as v; v.audit(countries=['CHL','PER'])"` (from `scripts/tools/data_patches`)
- `python scripts/tools/data_patches/patch_nueva_capacidad_2040_tx_advance.py --dry-run`
- `python scripts/tools/data_patches/patch_open_maxcaps_pisos_OPT.py --dry-run`
- `python scripts/tools/data_patches/patch_rpo_operationallife.py` (dry-run by default)
- `python scripts/tools/data_patches/patch_rnwtrnbraxx_residualcapacity.py` (dry-run by default)
- `python scripts/tools/data_patches/add_fuentes_sheet.py` (dry-run by default)

Tests:

- `python scripts/tools/data_patches/test_add_bds_storage.py`
- `python scripts/tools/data_patches/test_add_fuentes_sheet.py`

## Order / dependencies

If re-applying after regenerating the A-O workbooks:

```
A3 (regenerates A-O_* and DELETES BDS)
 -> add_bds_storage.py                       (COUNTRIES = ["CHL", "PER"])
 -> patch_nueva_capacidad_2040_tx_advance.py (OPT floors 2040+ + TRN COL-PAN / BOL-BRA)
 -> patch_open_maxcaps_pisos_OPT.py          (Max = floor x 1.01 where Min > Max)
 -> patch_rpo_operationallife.py --apply     (OL RPO 20 -> 50)
 -> patch_rnwtrnbraxx_residualcapacity.py --apply (RC 52.99 -> 85.4)
 -> add_fuentes_sheet.py --apply             (Fuentes documentation sheet; A3 deletes it on regen)
 -> B1 -> B2
```

`validate_bds_structure.py` after `add_bds_storage.py`; `D2_update_secondary_techs` and B1b are safe
at any point (they edit by Tech match).

## Gotchas

- The two JSON files are the per-cell `old → new` logs that the 2026-08-13 patches generated when
  applied (originally under `A1_Outputs/`; moved here because `A1_Outputs/` is inside `inputs/` and
  `*log*` is caught by `.gitignore`).
- The sixth data change of the same batch — the **OLADE demand** in `A-O_Demand.xlsx` (D2 with
  `DemandFromOLADE=YES`, `TradeBalanceDemandAdjustment=NO`; e.g. `ELCARGXX03` 2023 = 564.3) — has no
  script here: it is produced by `scripts/pipeline/D2_update_secondary_techs.py` from
  `Secondary_Techs_Editor.xlsx`.
- The `Fuentes` sheet is documentation only. To change a source, edit
  `inputs/config/data_sources.csv` and re-run `add_fuentes_sheet.py --apply` (do not edit the sheet
  by hand: it gets rewritten wholesale).
- **A3 regenerates the A-O workbooks and deletes BDS** (and overwrites any manual edit to Secondary
  Techs / Fixed Horizon Parameters). After A3, the full chain above must be re-run before B1.
- `add_bds_storage.py` writes 13 xlsx + 2 YAML in one go; with `BACKUP=True` it leaves copies under
  `inputs/_bds_backups/<timestamp>/` (git-ignored).
- The OL and RC patches require the exact "old" value: against the current `inputs/` they do nothing
  (correct).
- Status as of 2026-09-08: the xlsx files have all 6 changes and the YAML files under
  `inputs/config/` have `BDSCHLXX01`/`BDSPERXX01` in `xtra_scen.Storage` (Config A) and `PWRBDS` in
  `activity_upper_limit_exclude_prefixes` (Config AB). B1 builds the STORAGE set from that YAML: if
  an A3 run or an edit loses it, `STORAGE.csv` under `outputs/A2_Output_Params/` stops reproducing
  the versioned state. The auditor (V7/V9) detects this.
