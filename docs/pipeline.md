# Pipeline Workflow

RELAC TX processes energy system data through a multi-stage pipeline. This page documents each stage in detail, including its inputs, outputs, and configuration.

## Pipeline Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                        DATA PREPARATION                             │
│                                                                      │
│  A0: Generate Tech-Country Matrix                                    │
│   ↓                                                                  │
│  A1: Preprocess Raw CSVs → Excel Model Files                        │
│   ↓                                                                  │
│  A2: Add Transmission Technologies                                   │
│   ↓                                                                  │
│  (Optional) A3: Migrate Old Inputs                                   │
│   ↓                                                                  │
│  (Optional) A3_process: LID rule → extend lowerlimits → B1b         │
│   ↓                                                                  │
│  (Optional) D1 → Manual Editing → D2: Secondary Techs Editing       │
│   ↓                                                                  │
│  (Optional) B1b: Pre-solver validation (auto-fix)                   │
├──────────────────────────────────────────────────────────────────────┤
│                        MODEL EXECUTION                               │
│                                                                      │
│  B1: Compile Excel → OSeMOSYS CSVs                                  │
│   ↓                                                                  │
│  B2: Patcher chain → Execute Solver → Results                        │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Stage A0: Generate Technology-Country Matrix

**Script:** `scripts/pipeline/A0_generate_tech_country_matrix.py`

Generates `Tech_Country_Matrix.xlsx`, which controls which technology-country combinations are included in the model.

### Usage

```bash
python scripts/pipeline/A0_generate_tech_country_matrix.py
```

### What It Does

1. Reads the country list from `Config_country_codes.yaml`.
2. Creates a matrix of 21 technology codes against all countries.
3. Marks implausible combinations (from `implausible_combinations` in the YAML) as **NO** with red highlighting.
4. All other combinations default to **YES**.
5. Writes the matrix to `Tech_Country_Matrix.xlsx` with 5 sheets.

### Technology Codes

| Code | Description |
|------|-------------|
| BCK | Backstop |
| BIO | Biomass |
| CCS | Carbon Capture & Storage (Coal) |
| COA | Coal |
| COG | Cogeneration |
| CSP | Concentrated Solar Power |
| GAS | Natural Gas |
| GEO | Geothermal |
| HYD | Hydroelectric |
| LDS | Long Duration Storage |
| NGS | Natural Gas (CCG + OCG unified) |
| OIL | Oil |
| OTH | Other |
| PET | Petroleum |
| SDS | Short Duration Storage |
| SPV | Solar Photovoltaic |
| URN | Nuclear |
| WAS | Waste |
| WAV | Wave |
| WOF | Offshore Wind |
| WON | Onshore Wind |

:::{note}
Structural prefixes (`ELC`, `MIN`, `PWR`, `RNW`, `TRN`) are **not** included in the matrix. They combine with the codes above to form full technology names (e.g., `PWRBIOARGXX`, `MINCOAARG`).
:::

### After Generation

Edit `Tech_Country_Matrix.xlsx` to customize:
- In the **Matrix** sheet: change YES/NO for any technology-country pair.
- In the **NGS_Unification** sheet: toggle YES/NO to enable CCG+OCG merging into NGS.

---

## Stage A1: Preprocess Raw CSVs

**Script:** `scripts/pipeline/A1_Pre_processing_OG_csvs.py`

The largest processing step. Reads raw OSeMOSYS CSV files and produces structured Excel model files for each scenario.

### Usage

```bash
python scripts/pipeline/A1_Pre_processing_OG_csvs.py
```

### Input Files

- `OG_csvs_inputs/*.csv` -- All standard OSeMOSYS parameter and set CSV files.
- `Tech_Country_Matrix.xlsx` -- Technology filtering configuration.
- `Config_country_codes.yaml` -- Country definitions and settings.
- `Config_region_consolidation.yaml` -- Region consolidation rules.

### Output Files (per scenario)

Written to `A1_Outputs/A1_Outputs_{scenario}/`:

| File | Content |
|------|---------|
| `A-O_Parametrization.xlsx` | All technology parameters (costs, capacities, limits, etc.) |
| `A-O_Demand.xlsx` | Demand data, profiles, and projections |
| `A-O_AR_Model_Base_Year.xlsx` | Base year activity ratios (InputActivityRatio, OutputActivityRatio) |
| `A-O_AR_Projections.xlsx` | Projection activity ratios |

### Processing Steps

The script performs these operations in order:

1. **Read all CSV files** into memory as DataFrames.
2. **Replace country codes** according to the configuration.
3. **Filter by first year** -- removes data before `first_year`.
4. **Normalize temporal profiles** -- ensures SpecifiedDemandProfile sums to 1.0 per fuel/tech/year.
5. **Consolidate regions** (if enabled) -- merges sub-regional data using avg/sum rules.
6. **Remove internal interconnections** after consolidation.
7. **Clean PWR technologies** -- handles PWR00/PWR01 duplicates based on `pwr_cleanup_mode`.
8. **Apply Tech-Country Matrix filtering** -- removes technology-country pairs marked NO.
9. **Unify NGS technologies** -- merges CCG+OCG into NGS where enabled.
10. **Write Excel output files** with formatted sheets and human-readable names.
11. **Update demand profiles and projections**.
12. **Update parametrization capacities and temporal splits**.

---

## Stage A2: Add Transmission Technologies

**Script:** `scripts/pipeline/A2_AddTx.py`

Adds transmission (TRN) and dispatch (DSPTRN) technology entries to the Excel model files. Creates 6 transmission types plus 1 dispatch type per country for renewable and non-renewable power routing, and updates interconnection fuel codes.

### Usage

```bash
python scripts/pipeline/A2_AddTx.py
```

### Transmission Technology Types

| Code | Description |
|------|-------------|
| `RNWTRN` | Renewable transmission (existing) |
| `RNWRPO` | Renewable transmission (repowered) |
| `RNWNLI` | Renewable transmission (new lines) |
| `PWRTRN` | Non-renewable transmission (existing) |
| `TRNRPO` | Non-renewable transmission (repowered) |
| `TRNNLI` | Non-renewable transmission (new lines) |
| `DSPTRN` | Dispatch (interconnection routing, 2 modes) |

### Fuel Routing

The script assigns fuel codes for the energy flow:

- `ELC*00` -- Renewable electricity
- `ELC*01` -- Non-renewable electricity
- `ELC*02` -- Transmission output / Demand
- `ELC*03` -- Dispatch-ready for interconnection

### What It Does

1. Reads the country list from `Config_country_codes.yaml`.
2. For each scenario's Excel files:
   - Classifies power plant output as renewable (`ELC*00`) or non-renewable (`ELC*01`) in **Secondary** sheets.
   - Updates TRN interconnection fuel codes from `ELC*02`/`ELC*01` to `ELC*03` in **Secondary** sheets.
   - Adds transmission technology entries (RNWTRN, PWRTRN, etc.) to **Demand Techs** sheets.
   - Adds DSPTRN dispatch technology (Mode 1: `ELC*02` → `ELC*03`, Mode 2: `ELC*03` → `ELC*01`) to **Demand Techs** sheets.
   - Adds parameter entries to `A-O_Parametrization.xlsx` (sheets: **Fixed Horizon Parameters**, **Demand Techs**).

### Command-Line Options

| Flag | Default | Description |
|------|---------|-------------|
| `--yaml` | Auto-detected | Path to YAML configuration |
| `--base` | `A-O_AR_Model_Base_Year.xlsx` | Base year filename |
| `--proj` | `A-O_AR_Projections.xlsx` | Projections filename |
| `--param` | `A-O_Parametrization.xlsx` | Parametrization filename |

---

## Stage A3: Migrate Old Inputs (Optional)

**Script:** `scripts/pipeline/A3_migrate_old_inputs_CLG.py`

Migrates data from an older input format (`Old_Inputs/` directory) into the current model structure. This is only needed when transitioning from a legacy data format.

### Usage

```bash
python scripts/pipeline/A3_migrate_old_inputs_CLG.py
python scripts/pipeline/A3_migrate_old_inputs_CLG.py --dry-run  # Preview without writing
```

### Required Setup

The `Old_Inputs/` folder **must be created manually** inside `inputs/reference/`. It is not generated by any script. The folder must contain the following files, which must have **the same format** as the current model files:

```
Old_Inputs/
├── A2_Extra_Inputs/
│   └── A-Xtra_Storage.xlsx
└── A1_Outputs/
    └── A1_Outputs_{scenario}/
        ├── A-O_Parametrization.xlsx
        ├── A-O_Demand.xlsx
        ├── A-O_AR_Projections.xlsx
        └── A-O_AR_Model_Base_Year.xlsx
```

If the `Old_Inputs/` folder does not exist, the script will exit with an error.

### What It Does

- Applies technology name transformations (CCG+OCG to NGS, suffix removal).
- Imports and normalizes profiles from old files.
- Reads equivalence rules from `Config_tech_equivalences.yaml`.

---

## Stage A3_process: Parametrization Modification Workflow (Optional)

**Script:** [`A3_process.py`](../scripts/pipeline/A3_process.py)

An orchestrator that applies a set of post-A1/A2 calibration rules to each scenario's `A-O_Parametrization.xlsx`. For every scenario folder under `A1_Outputs/A1_Outputs_<scenario>/` it runs three steps in order:

1. **LID rule** ([`A3_process/rules_scripts/add_max_cap_investment_lid_rule.py`](../scripts/pipeline/A3_process/rules_scripts/add_max_cap_investment_lid_rule.py)) — fills `TotalAnnualMaxCapacityInvestment` placeholders with calibrated "lid" values, configured in [`lid_rule.yaml`](../inputs/config/A3_process/lid_rule.yaml).
2. **Extend lower limits** ([`A3_process/rules_scripts/extend_lowerlimits_pwr.py`](../scripts/pipeline/A3_process/rules_scripts/extend_lowerlimits_pwr.py)) — extends the 2024 value of `TotalTechnologyAnnualActivityLowerLimit` for PWR techs flat through 2050 in the **Secondary Techs** sheet, so the calibration floor does not expire and the optimizer cannot dump thermal generation in 2025+.
3. **Pre-solver validation** — runs `B1b_Pre_solver_validation.py --auto-fix-all` to reconcile any residual inconsistencies (see below).

### Usage

```bash
python scripts/pipeline/A3_process.py                  # all discovered scenarios
python scripts/pipeline/A3_process.py --scenario BAU   # one scenario
python scripts/pipeline/A3_process.py --scenario BAU,INV
python scripts/pipeline/A3_process.py --list           # list discovered scenarios
python scripts/pipeline/A3_process.py --skip-validation # skip the B1b auto-fix step
```

### Command-Line Options

| Flag | Description |
|------|-------------|
| `--scenario` | Comma-separated scenario name(s); default = all discovered |
| `--rules-script` | Override the rules script path |
| `--list` | Show discovered scenarios and exit |
| `--skip-validation` | Skip the final B1b auto-fix step |

:::{note}
The LID script writes a JSON change log (`lid_rule_changes_<timestamp>.json`) inside each scenario directory but does **not** make a folder-level backup — recovery is via git. B1b makes its own timestamped backup of the xlsx before writing.
:::

---

## Pre-Solver Validation (B1b)

**Script:** [`B1b_Pre_solver_validation.py`](../scripts/pipeline/B1b_Pre_solver_validation.py)

Detects infeasibility-prone data in `A-O_Parametrization.xlsx` **before** `B1_Compiler` reads the workbook (and before B2 emits the `.txt` for the solver). For each issue it shows the auto-fix formula and, by default, asks before writing. It can run standalone or as the final step of `A3_process.py`.

### Validations

| ID | Check | Auto-fix |
|----|-------|----------|
| **V1** | Per-year: `TotalAnnualMinCapacityInvestment(y) >= TotalAnnualMaxCapacityInvestment(y)` | `Max_inv(y) = Min_inv(y) × 1.01` |
| **V2** | Cumulative: `TotalAnnualMaxCapacity(y) <= ResidualCapacity(y) + Σ Min_inv` over the operational-life window | `Max_tot(y) = (Residual + ΣMin) × 1.01` |
| **V3** | Activity: `TotalTechnologyAnnualActivityLowerLimit(y) > max_activity(y)` (where `max_activity = max_capacity × AvailabilityFactor × CapacityToActivityUnit × Σ(CF·YearSplit)`) | `ActivityLowerLimit(y) = max_activity(y) × 0.99` |
| **V4** | Coverage: summed activity-upper-limit fractions per region/fuel/year below `1 − activity_upper_limit_coverage_tolerance` | Warning only (no auto-fix) |

### Usage

```bash
python scripts/pipeline/B1b_Pre_solver_validation.py --scenario BAU                 # interactive
python scripts/pipeline/B1b_Pre_solver_validation.py --scenario BAU --auto-fix-all  # apply all fixes
python scripts/pipeline/B1b_Pre_solver_validation.py --scenario BAU --report-only   # report, no changes
```

### Command-Line Options

| Flag | Description |
|------|-------------|
| `--scenario` | Scenario name (e.g. `BAU`); used to derive the default xlsx path |
| `--xlsx` | Override the xlsx path directly |
| `--non-interactive` | Do not prompt; fail on issues |
| `--auto-fix-all` | Apply every fix without prompting |
| `--report-only` | Write the report only; do not modify the xlsx |

:::{note}
`--non-interactive`, `--auto-fix-all`, and `--report-only` are mutually exclusive. B1b creates a timestamped backup of the workbook before applying any fix.
:::

---

## Stage B1: Compile to OSeMOSYS Format

**Script:** `scripts/pipeline/B1_Compiler.py` (invoked via `B1_Run_Compiler.py`)

Reads the Excel model files and compiles them into OSeMOSYS-format CSV parameter files.

### Usage

This stage runs automatically via the DVC pipeline:

```bash
python -u scripts/pipeline/B1_Run_Compiler.py
```

### Input Files

- `A1_Outputs/A1_Outputs_{scenario}/A-O_*.xlsx` -- All Excel model files.
- `A2_Extra_Inputs/A-Xtra_*.xlsx` -- Extra inputs (storage, emissions, projections).
- `Config_MOMF_T1_A.yaml` -- Compiler configuration.

### Output Files

- `A2_Output_Params/{scenario}/*.csv` -- One CSV per OSeMOSYS parameter.
- `A2_Structure_Lists.xlsx` -- Generated structure/set listings.

### Compilation Logic

The compiler handles:

- **Projection modes**: Flat, yearly percentage change, user-defined, interpolation to stated value, zero.
- **Activity ratios**: InputActivityRatio and OutputActivityRatio from base year and projection sheets.
- **Parametrization**: All technology parameters (costs, capacities, operational life, etc.).
- **Transport** (when enabled): Fleet calculations, distance handling, occupancy rates.
- **Capacity limits**: Hard limits, lower limits, continuous residual capacity.

---

## Stage B2: Execute the Model

**Script:** `scripts/pipeline/B2_Executing_OG_Model.py`

Runs the OSeMOSYS optimization model using the configured solver.

### Usage

This stage runs automatically via the DVC pipeline:

```bash
python -u scripts/pipeline/B2_Executing_OG_Model.py
```

### Execution Steps

1. **CSV to datafile conversion** via otoole (per base scenario: BAU, OPT, INV, VGB).
2. **Preprocessing** -- runs the OSeMOSYS preprocessor.
3. **Patcher chain** -- rewrites parameter blocks directly in the GMPL `.txt` to apply the reserve-margin and storage features plus feasibility safeguards (DaysInDayType, storage-delay, PWRBCK caps, reserve margin, activity upper limits, dispatch floors). See {doc}`solver-patchers` for the full chain.
4. **Sync patched CSVs** -- overwrites the affected otoole CSVs in place so the combined input/output files reflect the patched values the solver consumed.
5. **Tx chain (FLOORED → VEGCON → scenario transforms)** -- see subsection below; produces the derived scenarios (BAC, OPC, BSR, ISR, VSR, ISRWF, VSRWF, plus INVWF/VGBWF) that the rest of the pipeline treats like any other scenario.
6. **Solver execution** -- runs the selected solver (GLPK/CBC/CPLEX/Gurobi) over the configured `solve_scenarios` universe (base + derived).
7. **Result extraction** -- converts solver output back to CSV, using each derived scenario's base A2 as the otoole-results reference (derived scenarios share sets with their base; only values differ).
8. **Post-processing** -- input re-sync from the final `.txt` (fixes stale-input bug for derived scenarios), capital annualization, scenario concatenation.

:::{note}
The final CSVs always use `prefix_final_files` (`RELAC_TX_`), regardless of which patchers are active; `dvc.yaml` declares them as `outs` under that name and B2 aborts at startup if they disagree. When `storage_delay_active: True` (the shipped default) only the solver model file and the root datafile are redirected. See {doc}`solver-patchers` for details.
:::

### Tx Chain Integration (FLOORED → VEGCON → scenario transforms)

B2 orchestrates four previously-manual scripts as subprocesses, with their internal logic untouched (only CLI path arguments were added). The canonical suffix chain is `StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_VEGCON`; B2 asserts this at startup and aborts with a clear message if the YAML's active flags would produce a different chain (the four scripts below have it hardcoded in their file-matching logic).

| Etapa | What runs | Script (unmodified logic) | Output |
|---|---|---|---|
| B (per-scenario) | `preflight_separation` gate once, then `write_floors.py --scenarios <S>` per base scenario | `scripts/fix_dispatch/write_floors.py` | `Executables/<S>_0/..._FLOORED.txt` |
| C (barrier, 1 call) | `veg_tx_constraints.py --base-dir Executables --needs-csv <pin>` | `scripts/tx_chain/veg_tx_constraints.py` | `..._FLOORED_VEGCON.txt` for BAU, OPT, INV, VGB, BAC, OPC, INVWF, VGBWF (creates the derived scenarios' `<S>_0/` folders) |
| D (barrier, registry) | `cost_sensitivity_v_SR_WF.py` then `nli_sr_recompute.py`, both `--executables-dir Executables` | `scripts/tx_chain/cost_sensitivity_v_SR_WF.py`, `nli_sr_recompute.py` | BSR, ISR, VSR, ISRWF, VSRWF (new scenarios); ISR/VSR/ISRWF/VSRWF edited in place |

Extensibility: a new constraint script or derived scenario is added entirely in `Config_MOMF_T1_AB.yaml` -- a `scenario_transforms` entry (script + `produces`/`in_place`) plus a `derived_scenarios` mapping and, if it should be solved, an entry in `solve_scenarios`. No B2 code change is needed.

Solve universe: `solve_universe()` resolves `solve_scenarios` from the YAML (defaulting to the base scenarios) and validates each has its final datafile before the solver stage runs; `scenario_base()` maps a derived scenario back to the base whose A2/sets it reuses for otoole results.

:::{note}
Validated end-to-end (golden run, 2026-09-03): all 13 scenarios (11 in `solve_scenarios` + INVWF/VGBWF) reach VEGCON with `preflight_separation` PASS and `veg_tx` PASS=35/FAIL=0; a 2-scenario solver smoke test (BAC, ISR, parallel) both reached CPLEX optimal. See the plan's own validation log for the two issues this surfaced and fixed: a chain-suffix `upto=` omission in `run_dispatch_floors_patcher`, and the `outputs_BSR/NewCapacity.csv` revealed-need pin (documented as Risk R3) needing to exist before the VEGCON barrier can process the derived scenarios.
:::

### Solver Configuration

Configure in `Config_MOMF_T1_AB.yaml`:

```yaml
solver: 'cplex'        # glpk | cbc | cplex | gurobi
cplex_threads: 4
cplex_random_seed: 12345
```

### Parallel Execution

When `parallel: True` and `only_main_scenario: False`, multiple scenarios are solved simultaneously:

```yaml
parallel: True
max_x_per_iter: 4  # Max scenarios per batch
```

### Output Files

| Directory/File | Content |
|----------------|---------|
| `A2_Outputs_Params_otoole/{scenario}/` | otoole-format CSVs (one per parameter); for derived scenarios (BAC, OPC, BSR, ISR, VSR, ISRWF, VSRWF) this is a copy of the base scenario's folder, re-synced from that derived scenario's own final `.txt` |
| `Executables/{scenario}_0/` | Compiled solver data files -- one folder per scenario, base or derived; derived scenarios' folders are created by the Tx chain (etapas C/D), not by A1/A2 |
| `RELAC_TX_Inputs.csv` | Combined inputs (all scenarios) |
| `RELAC_TX_Outputs.csv` | Combined outputs (all scenarios) |
| `RELAC_TX_Combined_Inputs_Outputs.csv` | Merged inputs and outputs |

### Reproducibility

Deterministic results are ensured through:

- `PYTHONHASHSEED=0` (set by `run.py`).
- Configurable random seeds per solver.
- Sorted CSV files for consistent ordering.
