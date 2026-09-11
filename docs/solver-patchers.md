# Solver Patcher Chain (Stage B2)

After the OSeMOSYS preprocessor produces the GMPL datafile (`.txt`) but **before** the solver runs, Stage B2 applies an ordered chain of *patchers* that rewrite parameter blocks directly in the `.txt`. These patchers implement the **reserve-margin and storage** modeling features and several feasibility safeguards.

This page documents the chain, what each patcher does, and the configuration that controls it. All patcher settings live in [`Config_MOMF_T1_AB.yaml`](configuration.md#config_momf_t1_abyaml).

:::{important}
Every patcher is gated by an `*_active` master switch. When a switch is `False` (or absent), that patcher is a **no-op** and the pipeline behaves as if it were not there. Some switches ship **enabled** in the current `Config_MOMF_T1_AB.yaml` — see the "Shipped default" column in each section.
:::

---

## Why patch the `.txt` instead of the CSVs?

Some adjustments are easier or only possible on the fully-assembled GMPL model:

- `DaysInDayType` is never emitted by the `B1 → otoole → preprocess` path, so it must be injected post-preprocess.
- Reserve-margin tags, firm-capacity caps, and storage-build timing are global, cross-scenario rules best applied as a final reconciliation step.
- The patched values are then **synced back** into the otoole CSVs (see [Sync patched CSVs](#sync-patched-csvs-back-to-the-otoole-folder)) so the combined input/output files reflect what the solver actually consumed.

---

## Execution order

For each scenario, B2 runs (in [`B2_Executing_OG_Model.py`](../scripts/pipeline/B2_Executing_OG_Model.py)):

```
otoole conversion → OSeMOSYS preprocessing
   ↓
1. DaysInDayType injector        (always)
2. Storage-delay patcher          (storage_delay_active)
3. Storage-strip patcher          (strip_storage_active)
4. PWRBCK cap-opening patcher     (open_pwrbck_active)
5. Reserve-margin repair (blunt)  (reserve_margin_repair_active)
6. Reserve-margin repair (XLSX)   (reserve_margin_xlsx_active)
7. Activity-upper-limit patcher   (activity_upper_limit_active)
   ↓
Sync patched CSVs → solver → results
```

Each active patcher appends a suffix to the datafile name (e.g. `Pre_processed_BAU_0_NoStorage_OpenBCK_RMCarefulXLSX.txt`) and feeds its output to the next patcher in the chain.

---

## Storage-delay mode and the dual output pipeline

The storage-delay patcher is special: when `storage_delay_active: True`, B2 redirects the solver model file and the root datafile.

| Aspect | Baseline run | Storage-delay run |
|--------|--------------|-------------------|
| Solver model file | `osemosys_fast_preprocessed.txt` | `osemosys_fast_preprocessed_storage_delay.txt` (`storage_delay_model_output`) |
| Root datafile | `RELAC_TX_data.txt` | `RELAC_TX_data_storage_delay.txt` (`storage_delay_root_datafile`) |
| Final CSV prefix | `RELAC_TX_` | `RELAC_TX_` (unchanged) |

The final CSVs (`RELAC_TX_Inputs.csv`, `RELAC_TX_Outputs.csv`, `RELAC_TX_Combined_Inputs_Outputs.csv`) always use `prefix_final_files`. Until 2026-09-11 storage-delay runs used a separate `RELAC_TX_StorageDelay_` prefix; that desynced the `outs` in `dvc.yaml` (so `dvc repro` failed after the solve) and the consumers that read the un-prefixed name (dashboard, D4). B2 now checks at startup that the `dvc.yaml` outs carry `prefix_final_files` and aborts otherwise.

:::{note}
`storage_delay_active` is **mutually exclusive** with `strip_storage_active`. When storage-delay is on, B2 silently forces `strip_storage_active = False`.
:::

[`patch_storage_delay.py`](../scripts/pipeline/patch_storage_delay.py) keeps storage in the model but **blocks storage builds for the first N years** (`storage_delay_first_n_years`), then reopens the linked PWR storage technologies so the optimizer can add storage afterward.

---

## The patchers

### 1. DaysInDayType injector

**Script:** [`inject_DaysInDayType.py`](../scripts/pipeline/inject_DaysInDayType.py) — runs unconditionally.

The `B1 → otoole → preprocess` chain never generates the `DaysInDayType` block, so the `.txt` ships with an empty block and OSeMOSYS falls back to `default = 7`. With 4 seasons × 1 daytype that makes storage equations treat the year as 4 × 7 = 28 days while the energy balance uses the real year length — a mismatch. This patcher writes the correct `DaysInDayType` values in place.

### 2. Storage-delay patcher

**Script:** [`patch_storage_delay.py`](../scripts/pipeline/patch_storage_delay.py) · **Switch:** `storage_delay_active` · **Shipped default: True**

| Param | Default | Description |
|-------|---------|-------------|
| `storage_delay_first_n_years` | `5` | Number of initial model years where storage builds are blocked |
| `storage_delay_storage_prefixes` | `[SDS, LDS]` | Storage classes to delay |
| `storage_delay_storages` | *(unset)* | Exact storage names; overrides prefixes if set |
| `storage_delay_allowed_value` | `"-1"` | PWR cap value applied in the open years (`-1` = unconstrained) |
| `storage_delay_suffix` | `"StorageDelayN5"` | Filename suffix for the chained `.txt` |
| `storage_delay_model_output` | `osemosys_fast_preprocessed_storage_delay.txt` | Patched model file the solver is redirected to |
| `storage_delay_root_datafile` | `RELAC_TX_data_storage_delay.txt` | Root datafile name |

### 3. Storage-strip patcher (diagnostic)

**Script:** [`strip_storage.py`](../scripts/pipeline/strip_storage.py) · **Switch:** `strip_storage_active` · **Shipped default: True** (forced off when storage-delay is on)

Produces a new `.txt` with selected storage facilities **and their feeding PWR technologies disabled** — used to diagnose whether storage is the source of an infeasibility.

| Param | Default | Description |
|-------|---------|-------------|
| `strip_storage_mode` | `"all"` | `"tech"` (exact names), `"class"` (by prefix), or `"all"` |
| `strip_storage_targets` | `[]` | Facility names (`tech` mode) or prefixes (`class` mode) |
| `strip_storage_suffix` | `"NoStorage"` | Filename suffix |

### 4. PWRBCK cap-opening patcher (diagnostic)

**Script:** [`open_pwrbck_caps.py`](../scripts/pipeline/open_pwrbck_caps.py) · **Switch:** `open_pwrbck_active` · **Shipped default: True**

`PWRBCK*` are high-cost backstop generators that absorb feasibility edge cases. If their `TotalAnnualMaxCapacity` / `TotalAnnualMaxCapacityInvestment` are hardcapped at 0, the safety net is removed and the LP can become infeasible. This patcher reopens those caps.

| Param | Default | Description |
|-------|---------|-------------|
| `open_pwrbck_value` | `9999` | Cap value applied to PWRBCK* techs |
| `open_pwrbck_pattern` | `"PWRBCK"` | Technology-name prefix to match |
| `open_pwrbck_suffix` | `"OpenBCK"` | Filename suffix |

### 5. Reserve-margin repair — blunt (legacy)

**Switch:** `reserve_margin_repair_active` · **Shipped default: False**

The original, blunter reserve-margin repair (`patch_reserve_margin_repair.py`). The switch is preserved in B2 for compatibility, but the script is **not shipped in this repository** — only the careful variants below are. Leave this disabled and use the XLSX path (step 6).

### 6. Reserve-margin repair — careful XLSX

**Script:** [`patch_reserve_margin_repair_careful_xlsx.py`](../scripts/pipeline/patch_reserve_margin_repair_careful_xlsx.py) · **Switch:** `reserve_margin_xlsx_active` · **Shipped default: True**

Adds reserve-margin tags and repairs firm fossil capacity caps using per-country-region fallback values from an XLSX workbook. It keeps **stock** (`TotalAnnualMaxCapacity`) and **flow** (`TotalAnnualMaxCapacityInvestment`) limits separate and only replaces sentinel values.

| Param | Default | Description |
|-------|---------|-------------|
| `reserve_margin_xlsx_workbook` | `firm_capacity_fallbacks_by_cr.xlsx` | Workbook of per-country-region firm-capacity fallbacks |
| `reserve_margin_xlsx_sheet` | `"fallbacks"` | Worksheet name |
| `reserve_margin_xlsx_backstop_credit` | `1.0` | Reserve credit for PWRBCK capacity (1.0 = full) |
| `reserve_margin_xlsx_ccs_credit` | `0.9` | Reserve credit for PWRCCS capacity |
| `reserve_margin_xlsx_target_prefixes` | `[PWRPET, PWROIL, PWRNGS]` | Firm fossil techs whose sentinel caps may be replaced |
| `reserve_margin_xlsx_sentinel_values` | `[0, 9999]` | Only these existing cap values are replaced |
| `reserve_margin_xlsx_global_value` | `0.15` | Global `ReserveMargin` written for every (REGION, YEAR); unset = leave block untouched |
| `reserve_margin_xlsx_suffix` | `"RMCarefulXLSX"` | Filename suffix |

### 7. Activity-upper-limit patcher

**Script:** [`patch_activity_upper_limit.py`](../scripts/pipeline/patch_activity_upper_limit.py) · **Switch:** `activity_upper_limit_active` · **Shipped default: False**

Reads rows from the **Secondary Techs** sheet of `A-O_Parametrization.xlsx` whose `Parameter` equals `activity_upper_limit_parameter_label`. Each year cell holds a **fraction** in `[0, 1]` of that country's electricity demand. The patcher maps each tech to its demand fuel via `OutputActivityRatio`, converts `fraction × demand / OAR` into an absolute cap, and rewrites the `TotalTechnologyAnnualActivityUpperLimit` block.

| Param | Default | Description |
|-------|---------|-------------|
| `activity_upper_limit_scenarios` | `["BAU"]` | Scenarios where the patch applies (data lives in each scenario's own xlsx) |
| `activity_upper_limit_parameter_label` | `TotalTechnologyAnnualActivityUpperLimit_fraction` | Row label that holds the fractions |
| `activity_upper_limit_demand_fuel_prefixes` | `["ELC"]` | Demand fuel prefixes |
| `activity_upper_limit_tech_prefixes` | `["PWR"]` | Technology prefixes the cap applies to |
| `activity_upper_limit_exclude_prefixes` | `[PWRSDS, PWRLDS, PWRBCK, PWRTRN]` | Technology prefixes excluded |
| `activity_upper_limit_coverage_tolerance` | `0.15` | If summed fractions per region/fuel/year fall below `1 − tolerance`, B1b raises a **V4** warning |
| `activity_upper_limit_suffix` | `"ActUpLim"` | Filename suffix |

---

## Sync patched CSVs back to the otoole folder

**Script:** [`sync_patched_csvs_from_txt.py`](../scripts/pipeline/sync_patched_csvs_from_txt.py) · **Switch:** `sync_patched_csvs_active` · **Shipped default: True**

After the chain runs, this step extracts the listed parameter blocks from the **final** patched `.txt` and overwrites the matching CSVs in `A2_Outputs_Params_otoole/<scenario>/` **in place**. `generate_combined_input_file()` then reads those CSVs, so the patched values appear in `RELAC_TX_Combined_Inputs_Outputs.csv`.

`sync_patched_csvs_params` lists which parameters are synced (default):

```yaml
sync_patched_csvs_params:
  - ReserveMargin
  - ReserveMarginTagTechnology
  - TotalAnnualMaxCapacity
  - TotalAnnualMaxCapacityInvestment
  - TotalAnnualMinCapacity
  - TotalAnnualMinCapacityInvestment
  - TotalTechnologyAnnualActivityUpperLimit
```

:::{note}
The sync writes into the original A2 folder in place. Re-running the pipeline regenerates those CSVs from A1 before the patcher chain re-applies, so the operation is repeatable.
:::

---

## Turning the chain off

To run the plain baseline pipeline (no patchers, single `RELAC_TX_*` output set), set every master switch to `False` in `Config_MOMF_T1_AB.yaml`:

```yaml
storage_delay_active: False
strip_storage_active: False
open_pwrbck_active: False
reserve_margin_repair_active: False
reserve_margin_xlsx_active: False
activity_upper_limit_active: False
sync_patched_csvs_active: False
```

The `DaysInDayType` injector still runs (it only fixes a missing block and does not change modeling assumptions).
