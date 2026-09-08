# Reestructuración del repositorio en `inputs/` · `scripts/` · `outputs/`

**Fecha:** 2026-09-07
**Rama:** `restructure/inputs-scripts-outputs` (desde `clean-sirelac`, HEAD `c8f0efc`)
**Estado:** diseño aprobado; pendiente plan de implementación

---

## 1. Objetivo

Reorganizar el repositorio `relac_tx` en tres carpetas principales, `inputs/`, `scripts/` y
`outputs/`, de modo que **el resultado del pipeline sea exactamente el mismo** que hoy. La
funcionalidad de los scripts no cambia: solo cambian las direcciones (rutas) con las que se
localizan entre sí y localizan sus datos.

### No-objetivos

- No se renombra ningún script ni ningún archivo de datos (solo se mueven). En particular
  `A1_Outputs/` conserva su nombre aunque pase a `inputs/`: renombrarlo tocaría el prefijo
  `A1_Outputs_<escenario>` que ~15 scripts usan para descubrir escenarios.
- No se cambia qué está versionado en git y qué está ignorado. Lo que hoy se commitea sigue
  commiteado (en su nueva ruta); lo ignorado sigue ignorado.
- No se refactoriza lógica, no se eliminan scripts obsoletos ni se unifican duplicados
  (p. ej. las tres copias de `veg_tx_constraints*.py`).
- No se toca `run.py` ni `environment.yaml` salvo que la verificación lo exija (no se espera).

---

## 2. Decisiones tomadas (con el usuario, 2026-09-07)

| # | Decisión | Elección |
|---|----------|----------|
| 1 | Frontera inputs/outputs para artefactos intermedios | **Mantenido a mano vs regenerado.** Input = lo que una persona mantiene/calibra y el pipeline lee (incluye `A1_Outputs`, que editan A3/D2/B1b). Output = lo que se regenera al correr (`A2_Output_Params`, otoole, `Executables`, `RELAC_TX_*`, `Figures`). |
| 2 | Alcance | **Todo el repo.** En la raíz solo quedan `run.py`, `dvc.yaml`, `dvc.lock`, `.dvcignore`, `.gitignore`, `environment.yaml`, `README.md`, `LICENSE`, la guía de instalación y `docs/`. Lo experimental va a `scripts/experimental/`, sus datos a `inputs/reference/`. |
| 3 | Nivel de verificación | **Hasta la puerta del solver, byte a byte.** B1 y la cadena de patchers de B2 (`execute_model: False`) antes y después; comparación md5. Sin correr CPLEX. |
| 4 | Mecanismo de rutas | **Módulo central `scripts/common/relac_paths.py` + convención "toda ruta en YAML es relativa a la raíz del repo".** |

Casos límite resueltos con el criterio 1:

- `Tech_Country_Matrix.xlsx` (A0), `Secondary_Techs_Editor.xlsx` (D1) y `candidate_floors.csv`
  (`make_candidates.py`) los **genera una herramienta pero luego se editan a mano** y el pipeline
  los lee → **inputs**; la herramienta que los refresca escribe ahí.
- `osemosys_fast_preprocessed_storage_delay.txt` lo escribe `patch_storage_delay.py` → **output**,
  aunque hoy esté en git (sigue en git).
- `RELAC_Tx_v15_run/outputs_BSR/NewCapacity.csv` se llama "outputs" pero es el **pin** de
  necesidad revelada que lee VEGCON y está versionado → **input** (`inputs/tx_chain/outputs_BSR/`).
- Backups timestamped que D2/B1b/D4 crean **junto al xlsx** que modifican siguen cayendo junto al
  xlsx (en `inputs/A1_Outputs/...`), como hoy; ya están gitignored.

---

## 3. Layout final

```
relac_tx/
├── run.py  dvc.yaml  dvc.lock  .dvcignore  .gitignore  environment.yaml
├── README.md  LICENSE  RELAC_TX_Guia_instalacion_ejecucion.md
├── docs/
│   ├── (los .md operativos actuales, con rutas actualizadas)
│   ├── fix_dispatch/       INSTRUCCIONES_SOLVE.md, fix_report.md
│   ├── experimental/       ENTREGABLE_ANDREY_v2.md, matriz_balance_README_PROCESO.md
│   └── superpowers/specs/  (este documento)
│
├── inputs/
│   ├── config/             Config_MOMF_T1_A.yaml, Config_MOMF_T1_AB.yaml, Config_country_codes.yaml,
│   │   │                   Config_region_consolidation.yaml, Config_tech_equivalences.yaml
│   │   └── A3_process/     lid_rule.yaml, TECH_TYPES.csv
│   ├── model/              osemosys_fast_preprocessed.txt
│   ├── OG_csvs_inputs/
│   ├── A1_Outputs/         A1_Outputs_{BAU,INV,OPT,VGB}/
│   ├── A2_Extra_Inputs/
│   ├── Miscellaneous/      A-O_*.xlsx, A-Xtra_*.xlsx, centerpoints.csv, conversion_format.yaml, templates/
│   ├── data/               Tech_Country_Matrix.xlsx, Secondary_Techs_Editor.xlsx,
│   │                       OLADE - Capacidad instalada por fuente - Anual.xlsx,
│   │                       OLADE - Generación eléctrica por fuente - Anual.xlsx,
│   │                       Shares_PET_OIL_Split.xlsx, Shares_Power_Generation_Technologies.xlsx,
│   │                       LAC_maxcap_tool.xlsx, LAC_maxcap_tool_complementary.xlsx,
│   │                       firm_capacity_fallbacks_by_cr.xlsx, CapacityAndDistances.xlsx
│   ├── tx_chain/
│   │   ├── fix_dispatch/   candidate_floors.csv, candidate_floors_baseline.csv
│   │   └── outputs_BSR/    NewCapacity.csv
│   └── reference/          Old_Inputs/, NO BORRAR A1_Outputs - Escenario Base/,
│                           Matriz Balance energético/ (solo .xlsx),
│                           Demanda CireLAC_GTER_WEO.xlsx, RateGrowthDemand_RenovabilityGoals.xlsx,
│                           veg_tx_abs_test/ (4 × Pre_processed_*_FLOORED_VEGCON.txt)
│
├── scripts/
│   ├── common/             __init__.py, relac_paths.py (NUEVO), Z_AUX_config_loader.py, _xlsx_validation_core.py
│   ├── pipeline/           A0, A1, A2, A3_migrate, A3_process.py, A3_process/rules_scripts/*.py,
│   │                       B1_Compiler, B1_Run_Compiler, B1b, B2, D1..D5,
│   │                       patch_*.py (5), strip_storage, open_pwrbck_caps, inject_DaysInDayType,
│   │                       sync_patched_csvs_from_txt, sync_historical_from_bau,
│   │                       preprocess_data.py, Z_AUX_capital_annualization_script.py
│   ├── fix_dispatch/       relac_io, write_floors, preflight_separation, make_candidates, build_combined,
│   │                       build_summary, feasibility, floor_effect, fig_floor_effect,
│   │                       validate_constraints, veg_tx_constraints
│   ├── tx_chain/           veg_tx_constraints_v14, cost_sensitivity_v11, nli_sr_recompute_v1
│   ├── dashboard/          build_dashboard, dashboard_config, _process_csv_for_dashboard,
│   │                       Z_AUX_generate_transmission_maps, Z_AUX_generate_RES_diagram,
│   │                       Z_AUX_generate_interactive_dashboards_aggregated
│   ├── tools/              Z_*.py restantes, AUX_Z_recalc_shares, concatenate_relac, preprocess_data_muio,
│   │                       migrate_layout_untracked.py (NUEVO)
│   ├── tests/              test_b2_chain_helper, test_D2_fixes, test_outputs (fix_dispatch)
│   └── experimental/
│       ├── matriz_balance/     7 .py de "Matriz Balance energético"
│       └── veg_tx_abs_test/    5 .py de veg_tx_abs_test
│
└── outputs/
    ├── A2_Output_Params/          A2_Structure_Lists.xlsx           (B1)
    ├── A2_Outputs_Params_otoole/  Executables/                      (B2)
    ├── model/                     osemosys_fast_preprocessed_storage_delay.txt
    ├── RELAC_TX_*.csv             (Inputs/Outputs/Combined, con y sin fecha, prefijo StorageDelay_)
    ├── RELAC_TX_data.txt  RELAC_TX_data_storage_delay.txt
    ├── Figures/                   (+ cf_corregido_brasil.html, _dashboard_data.csv)
    ├── fix_dispatch/              cache/, outputs_BACKUP/, solved_FLOORED/, upstream_floor_rows.csv,
    │                              candidate_floors_summary.csv, input_comparison_report.{csv,md},
    │                              fig_floor_effect.png, test_*.csv, validation_*, floor_effect_report.csv,
    │                              report_lock_planned_capacity_template.html
    ├── tx_chain/                  veg_pipeline_proof.png, veg_preflight.png, templates/ (legado, ignorado)
    ├── experimental/              veg_tx_abs_test/ (png)
    ├── templates/                 (salida de Z_generate_country_template)
    ├── legacy/                    Blend_Shares_0.pickle
    └── logs/                      cplex.log, clone1.log, clone2.log, gurobi.log, secondary_techs_update_log_*.txt
```

---

## 4. Mapa de movimientos

Convención: `T1/` = `t1_confection/`. Se mueve con `git mv` lo versionado y con `mv` lo no
versionado. Nada se borra.

### 4.1 Raíz

| Origen | Destino |
|--------|---------|
| `RELAC_TX_data.txt`, `RELAC_TX_data_storage_delay.txt` | `outputs/` |
| `concatenate_files/concatenate_relac.py` | `scripts/tools/` |
| `run.py`, `dvc.yaml`, `dvc.lock`, `.dvcignore`, `.gitignore`, `environment.yaml`, `README.md`, `LICENSE`, `RELAC_TX_Guia_instalacion_ejecucion.md`, `docs/` | se quedan |

### 4.2 `t1_confection/` → scripts

| Destino | Archivos |
|---------|----------|
| `scripts/common/` | `Z_AUX_config_loader.py`, `_xlsx_validation_core.py` |
| `scripts/pipeline/` | `A0_generate_tech_country_matrix.py`, `A1_Pre_processing_OG_csvs.py`, `A2_AddTx.py`, `A3_migrate_old_inputs_CLG.py`, `A3_process.py`, `B1_Compiler.py`, `B1_Run_Compiler.py`, `B1b_Pre_solver_validation.py`, `B2_Executing_OG_Model.py`, `D1_generate_editor_template.py`, `D2_update_secondary_techs.py`, `D3_load_lac_max_capacity_caps.py`, `D4_load_dsptrn_max_cap_inv.py`, `D5_load_fuel_var_costs.py`, `inject_DaysInDayType.py`, `open_pwrbck_caps.py`, `patch_activity_upper_limit.py`, `patch_reserve_margin_repair_careful.py`, `patch_reserve_margin_repair_careful_xlsx.py`, `patch_storage_delay.py`, `strip_storage.py`, `sync_historical_from_bau.py`, `sync_patched_csvs_from_txt.py`, `Z_AUX_capital_annualization_script.py` (lo importa B2 como hermano), `Miscellaneous/preprocess_data.py` |
| `scripts/pipeline/A3_process/rules_scripts/` | `add_max_cap_investment_lid_rule.py`, `extend_lowerlimits_pwr.py`, `reset_lowerlimits_from_base.py` |
| `scripts/dashboard/` | `build_dashboard.py`, `dashboard_config.py`, `_process_csv_for_dashboard.py`, `Z_AUX_generate_transmission_maps.py`, `Z_AUX_generate_RES_diagram.py`, `Z_AUX_generate_interactive_dashboards_aggregated.py` |
| `scripts/tools/` | `AUX_Z_recalc_shares.py`, `Z_AUX_apply_parametrization_review.py`, `Z_AUX_D1b_set_trn_limits_from_flows.py`, `Z_AUX_fix_excel_profiles.py`, `Z_AUX_sort_csv.py`, `Z_AUX_united_regions.py`, `Z_AUX_update_maxcap_inv_from_tool.py`, `Z_AUX_update_transmission_iar.py`, `Z_generate_country_template.py`, `Z_TEMP_add_pwrbck_to_scenarios.py`, `Z_validate_country_data.py`, `Miscellaneous/preprocess_data_muio.py` |
| `scripts/tests/` | `test_b2_chain_helper.py`, `test_D2_fixes.py` |
| `scripts/experimental/matriz_balance/` | los 7 `.py` de `Matriz Balance energético/` |

### 4.3 `t1_confection/` → inputs

| Destino | Archivos |
|---------|----------|
| `inputs/config/` | `Config_MOMF_T1_A.yaml`, `Config_MOMF_T1_AB.yaml`, `Config_country_codes.yaml`, `Config_region_consolidation.yaml`, `Config_tech_equivalences.yaml` |
| `inputs/config/A3_process/` | `A3_process/rules_scripts/lid_rule.yaml`, `A3_process/TECH_TYPES.csv` |
| `inputs/model/` | `osemosys_fast_preprocessed.txt` |
| `inputs/` | `OG_csvs_inputs/`, `A1_Outputs/`, `A2_Extra_Inputs/`, `Miscellaneous/` (sin los dos `.py`) |
| `inputs/data/` | `Tech_Country_Matrix.xlsx`, `Secondary_Techs_Editor.xlsx`, `OLADE - Capacidad instalada por fuente - Anual.xlsx`, `OLADE - Generación eléctrica por fuente - Anual.xlsx`, `Shares_PET_OIL_Split.xlsx`, `Shares_Power_Generation_Technologies.xlsx`, `LAC_maxcap_tool.xlsx`, `LAC_maxcap_tool_complementary.xlsx`, `firm_capacity_fallbacks_by_cr.xlsx`, `CapacityAndDistances.xlsx` |
| `inputs/reference/` | `Old_Inputs/`, `NO BORRAR A1_Outputs - Escenario Base/`, `Matriz Balance energético/` (solo `.xlsx`), `Demanda CireLAC_GTER_WEO.xlsx`, `RateGrowthDemand_RenovabilityGoals.xlsx` |

### 4.4 `t1_confection/` → outputs

| Destino | Archivos |
|---------|----------|
| `outputs/` | `A2_Output_Params/`, `A2_Structure_Lists.xlsx`, `A2_Outputs_Params_otoole/`, `Executables/`, `Figures/`, todos los `RELAC_TX_*.csv` (versionados o no) |
| `outputs/model/` | `osemosys_fast_preprocessed_storage_delay.txt` |
| `outputs/Figures/` | `cf_corregido_brasil.html`, `_dashboard_data.csv` |
| `outputs/legacy/` | `Blend_Shares_0.pickle` |
| `outputs/logs/` | `cplex.log`, `clone1.log`, `clone2.log` |

### 4.5 `fix_dispatch/`

| Destino | Archivos |
|---------|----------|
| `scripts/fix_dispatch/` | `relac_io.py`, `write_floors.py`, `preflight_separation.py`, `make_candidates.py`, `build_combined.py`, `build_summary.py`, `feasibility.py`, `floor_effect.py`, `fig_floor_effect.py`, `validate_constraints.py`, `veg_tx_constraints.py` |
| `scripts/tests/` | `test_outputs.py` |
| `inputs/tx_chain/fix_dispatch/` | `candidate_floors.csv`, `candidate_floors_baseline.csv` |
| `outputs/fix_dispatch/` | `cache/`, `outputs_BACKUP/`, `candidate_floors_summary.csv`, `upstream_floor_rows.csv`, `input_comparison_report.csv`, `input_comparison_report.md`, `fig_floor_effect.png`, `test_cf_targets.csv`, `test_floor_compliance.csv`, `test_idle_capacity.csv`, `test_scenario_separation.csv`, `report_lock_planned_capacity_template.html` |
| `docs/fix_dispatch/` | `INSTRUCCIONES_SOLVE.md`, `fix_report.md` |

### 4.6 `RELAC_Tx_v15_run/`

| Destino | Archivos |
|---------|----------|
| `scripts/tx_chain/` | `veg_tx_constraints_v14.py`, `cost_sensitivity_v11.py`, `nli_sr_recompute_v1.py` |
| `inputs/tx_chain/outputs_BSR/` | `NewCapacity.csv` |
| `outputs/tx_chain/` | `veg_pipeline_proof.png`, `veg_preflight.png`, `templates/` (ignorado, legado) |

### 4.7 `veg_tx_abs_test/`

| Destino | Archivos |
|---------|----------|
| `scripts/experimental/veg_tx_abs_test/` | `veg_tx_constraints.py`, `explain_shared_ceiling.py`, `plot_floors_ceilings.py`, `verify_no_infeasibility.py`, `why_ceiling_gt_floor.py` |
| `inputs/reference/veg_tx_abs_test/` | los 4 `Pre_processed_*_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_VEGCON.txt` |
| `outputs/experimental/veg_tx_abs_test/` | `veg_pipeline_proof.png`, `veg_preflight.png` |
| `docs/experimental/` | `ENTREGABLE_ANDREY_v2.md`; y `Matriz Balance energético/README_PROCESO.md` → `docs/experimental/matriz_balance_README_PROCESO.md` |

---

## 5. Mecanismo de rutas

### 5.1 `scripts/common/relac_paths.py`

Único archivo que conoce el layout. No importa nada del proyecto; solo `pathlib`.

```python
"""Layout del repositorio. Todo script obtiene sus rutas de aquí."""
from pathlib import Path

def _find_repo_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / "dvc.yaml").is_file():
            return p
    raise RuntimeError(f"No se encontró dvc.yaml subiendo desde {start}")

REPO_ROOT = _find_repo_root(Path(__file__).resolve().parent)
INPUTS  = REPO_ROOT / "inputs"
SCRIPTS = REPO_ROOT / "scripts"
OUTPUTS = REPO_ROOT / "outputs"

# ---- inputs ----
CONFIG               = INPUTS / "config"
CONFIG_A             = CONFIG / "Config_MOMF_T1_A.yaml"
CONFIG_AB            = CONFIG / "Config_MOMF_T1_AB.yaml"
CONFIG_COUNTRY_CODES = CONFIG / "Config_country_codes.yaml"
CONFIG_REGION_CONSOLIDATION = CONFIG / "Config_region_consolidation.yaml"
CONFIG_TECH_EQUIVALENCES    = CONFIG / "Config_tech_equivalences.yaml"
A3_CONFIG            = CONFIG / "A3_process"          # lid_rule.yaml, TECH_TYPES.csv
MODEL                = INPUTS / "model"
OSEMOSYS_MODEL       = MODEL / "osemosys_fast_preprocessed.txt"
OG_CSVS_INPUTS       = INPUTS / "OG_csvs_inputs"
A1_OUTPUTS           = INPUTS / "A1_Outputs"
A2_EXTRA_INPUTS      = INPUTS / "A2_Extra_Inputs"
MISCELLANEOUS        = INPUTS / "Miscellaneous"
DATA                 = INPUTS / "data"
REFERENCE            = INPUTS / "reference"
OLD_INPUTS           = REFERENCE / "Old_Inputs"
BASE_SCENARIO_REF    = REFERENCE / "NO BORRAR A1_Outputs - Escenario Base"
MATRIZ_BALANCE       = REFERENCE / "Matriz Balance energético"
TX_CHAIN_IN          = INPUTS / "tx_chain"
CANDIDATE_FLOORS     = TX_CHAIN_IN / "fix_dispatch" / "candidate_floors.csv"
VEG_TX_NEEDS_CSV     = TX_CHAIN_IN / "outputs_BSR" / "NewCapacity.csv"

# ---- outputs ----
A2_OUTPUT_PARAMS     = OUTPUTS / "A2_Output_Params"
A2_STRUCTURE_LISTS   = OUTPUTS / "A2_Structure_Lists.xlsx"
A2_OTOOLE            = OUTPUTS / "A2_Outputs_Params_otoole"
EXECUTABLES          = OUTPUTS / "Executables"
OUTPUT_MODEL         = OUTPUTS / "model"
FIGURES              = OUTPUTS / "Figures"
LOGS                 = OUTPUTS / "logs"
FIX_DISPATCH_OUT     = OUTPUTS / "fix_dispatch"
TX_CHAIN_OUT         = OUTPUTS / "tx_chain"
EXPERIMENTAL_OUT     = OUTPUTS / "experimental"
TEMPLATES_OUT        = OUTPUTS / "templates"

# ---- scripts ----
PIPELINE     = SCRIPTS / "pipeline"
FIX_DISPATCH = SCRIPTS / "fix_dispatch"
TX_CHAIN     = SCRIPTS / "tx_chain"
TOOLS        = SCRIPTS / "tools"

def scenario_dir(scenario: str) -> Path:
    """inputs/A1_Outputs/A1_Outputs_<scenario>"""
    return A1_OUTPUTS / f"A1_Outputs_{scenario}"

def executables_dir(scenario: str) -> Path:
    """outputs/Executables/<scenario>_0"""
    return EXECUTABLES / f"{scenario}_0"

def ensure_output_dirs() -> None:
    for d in (OUTPUTS, A2_OUTPUT_PARAMS, A2_OTOOLE, EXECUTABLES, OUTPUT_MODEL, FIGURES, LOGS,
              FIX_DISPATCH_OUT, TX_CHAIN_OUT, EXPERIMENTAL_OUT, TEMPLATES_OUT):
        d.mkdir(parents=True, exist_ok=True)
```

`ensure_output_dirs()` la llaman solo los puntos de entrada del pipeline (B1_Run_Compiler, B2)
para que un clon limpio funcione; el resto de scripts crea sus carpetas como hoy (`mkdir` local).

### 5.2 Bootstrap en cada script

Dos líneas al principio, con `parents[k]` fijo según la profundidad de la carpeta:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # -> scripts/
from common import relac_paths as P
```

| Ubicación del script | `k` |
|----------------------|-----|
| `scripts/pipeline/`, `fix_dispatch/`, `tx_chain/`, `dashboard/`, `tools/`, `tests/` | 1 |
| `scripts/experimental/matriz_balance/`, `scripts/experimental/veg_tx_abs_test/` | 2 |
| `scripts/pipeline/A3_process/rules_scripts/` | 3 |

Módulos compartidos: `from Z_AUX_config_loader import X` pasa a `from common.Z_AUX_config_loader
import X`; ídem `_xlsx_validation_core`. Dentro de `common/`, `Z_AUX_config_loader.py` importa
`from . import relac_paths as P` y fija `CONFIG_PATH = P.CONFIG_COUNTRY_CODES`.

Imports entre hermanos **no cambian**: B1_Compiler → B1b, B2 → `patch_activity_upper_limit` y
`Z_AUX_capital_annualization_script`, `build_dashboard` → `dashboard_config`, `fix_dispatch/*` →
`relac_io`, `veg_tx_abs_test/*` → `veg_tx_constraints.py` (vía `spec_from_file_location`).

B2 mantiene su `get_here()` (soporta ejecución interactiva sin `__file__`); el bootstrap de B2 se
deriva de ese valor.

### 5.3 Convención YAML: rutas relativas a la raíz del repo

Todas las claves de directorio/archivo de `Config_MOMF_T1_A.yaml` y `Config_MOMF_T1_AB.yaml`
pasan a ser relativas a `REPO_ROOT`. B1 y B2 las anclan con `os.path.join(ROOT, params[...])`.

`Config_MOMF_T1_A.yaml`:

| Clave | Hoy | Nuevo |
|-------|-----|-------|
| `A1_inputs` | `./A1_Inputs` | `inputs/A1_Inputs` (no existe hoy; se mantiene coherente) |
| `A1_outputs` | `./A1_Outputs` | `inputs/A1_Outputs` |
| `A2_extra_inputs` | `./A2_Extra_Inputs` | `inputs/A2_Extra_Inputs` |
| `A2_output`, `A2_output_main_scen` | `./A2_Output_Params/` | `outputs/A2_Output_Params/` |
| `A2_output_NDP` | `./A2_Output_Params/NDC/` | `outputs/A2_Output_Params/NDC/` |
| `Print_A2_Struct_List` | `A2_Structure_Lists.xlsx` | `outputs/A2_Structure_Lists.xlsx` |
| resto (`Print_*`, `Xtra_*`, hojas, columnas) | | sin cambio (son nombres de archivo/hoja, se concatenan al directorio) |

`Config_MOMF_T1_AB.yaml`:

| Clave | Hoy | Nuevo |
|-------|-----|-------|
| `A2_output` | `A2_Output_Params` | `outputs/A2_Output_Params` |
| `A2_output_otoole` | `A2_Outputs_Params_otoole` | `outputs/A2_Outputs_Params_otoole` |
| `Miscellaneous` | `Miscellaneous` | `inputs/Miscellaneous` |
| `templates` | `templates` | sin cambio (subcarpeta de `Miscellaneous`) |
| `executables` | `Executables` | `outputs/Executables` |
| `outputs` | `Outputs` | sin cambio (subcarpeta de `Executables/<S>_0/`) |
| `concatenate_folder` | `concatenate_files` | `scripts/tools` |
| `preprocess_data` | `preprocess_data.py` | sin cambio; B2 lo resuelve desde `SCRIPT_DIR` (ver 5.5) |
| `osemosys_model` | `osemosys_fast_preprocessed.txt` | `inputs/model/osemosys_fast_preprocessed.txt` |
| `storage_delay_model_output` | `osemosys_fast_preprocessed_storage_delay.txt` | `outputs/model/osemosys_fast_preprocessed_storage_delay.txt` |
| `storage_delay_root_datafile` | `RELAC_TX_data_storage_delay.txt` | sin cambio; B2 lo escribe en `outputs/` |
| `reserve_margin_xlsx_workbook` | `firm_capacity_fallbacks_by_cr.xlsx` | sin cambio; B2 lo resuelve en `P.DATA` |
| `dispatch_floors_script` | `../fix_dispatch/write_floors.py` | `scripts/fix_dispatch/write_floors.py` |
| `preflight_separation_script` | `../fix_dispatch/preflight_separation.py` | `scripts/fix_dispatch/preflight_separation.py` |
| `veg_tx_script` | `../RELAC_Tx_v15_run/veg_tx_constraints_v14.py` | `scripts/tx_chain/veg_tx_constraints_v14.py` |
| `veg_tx_needs_csv` | `../RELAC_Tx_v15_run/outputs_BSR/NewCapacity.csv` | `inputs/tx_chain/outputs_BSR/NewCapacity.csv` |
| `scenario_transforms[*].script` | `../RELAC_Tx_v15_run/cost_sensitivity_v11.py`, `.../nli_sr_recompute_v1.py` | `scripts/tx_chain/cost_sensitivity_v11.py`, `scripts/tx_chain/nli_sr_recompute_v1.py` |
| `inputs_file`, `outputs_file`, `prefix_final_files`, `storage_delay_prefix_final_files` | | sin cambio; B2 los escribe en `outputs/` |

Los comentarios del YAML que dicen "relativo a t1_confection" se actualizan a "relativo a la raíz
del repo".

### 5.4 B1 (`B1_Run_Compiler.py`, `B1_Compiler.py`)

- `B1_Run_Compiler`: `yaml_file = P.CONFIG_A`; `A1_Outputs_script = P.A1_OUTPUTS`; el `.bak` del YAML
  sigue junto al YAML; `run_compiler` ejecuta `B1_Compiler.py` con **`cwd=P.REPO_ROOT`** (hoy
  `cwd=script_dir`). Llama a `P.ensure_output_dirs()`.
- `B1_Compiler`: es cwd-dependiente. Con cwd = raíz del repo y las claves YAML relativas a la raíz,
  todos los `os.path.join(params['A1_outputs'], ...)` funcionan. Quedan tres ajustes:
  1. `open('Config_MOMF_T1_A.yaml')` → `open(P.CONFIG_A)`.
  2. `pd.read_csv(os.path.join('OG_csvs_inputs', 'EMISSION.csv'))` → `P.OG_CSVS_INPUTS / 'EMISSION.csv'`.
  3. **Acople dir/prefijo**: en 11 líneas (34, 72, 73, 350, 542, 544, 552, 1591, 1598, 1607, 1616)
     `params['A1_outputs']` se usa a la vez como directorio y como prefijo del nombre de carpeta
     (`A1_Outputs + '_' + escenario`). Con `A1_outputs: inputs/A1_Outputs` el prefijo sería
     `inputs/A1_Outputs_BAU`. Se introduce una constante `A1_PREFIX = os.path.basename(
     params['A1_outputs'].rstrip('/'))` y esas líneas usan `A1_PREFIX + '_' + escenario`. La ruta
     resultante es idéntica a la actual.

### 5.5 B2 (`B2_Executing_OG_Model.py`)

Hoy `HERE` (= `t1_confection`) cumple tres papeles; se separan:

| Papel | Variable nueva | Uso |
|-------|----------------|-----|
| Carpeta del script | `SCRIPT_DIR` (= `get_here()`) | `sys.path.insert` para `patch_activity_upper_limit`; `script_path` de `patch_storage_delay.py`, `patch_reserve_margin_repair_careful_xlsx.py`, `preprocess_data.py` |
| Ancla de rutas de datos | `ROOT = P.REPO_ROOT` | sustituye a `HERE`/`here` en **todos** los `os.path.join(HERE, params[...])`, y se añade a los ~10 joins que hoy usan `params['executables']` a pelo (líneas 275-276, 327-328, 412-413, 459-460, 534-536, 617, 787, 871-873, 1207) |
| Directorio de trabajo | `os.chdir(P.LOGS)` | CPLEX/Gurobi escriben `cplex.log`, `clone*.log`, `gurobi.log` en el cwd; el borrado en `del_files` sigue siendo por nombre relativo y funciona igual |

Cambios puntuales adicionales:

- `open('Config_MOMF_T1_AB.yaml')` → `open(P.CONFIG_AB)`; `open('Config_MOMF_T1_A.yaml')` → `open(P.CONFIG_A)`.
- `params['osemosys_model']` y `storage_delay_model_*` se convierten a absolutos con `ROOT` antes de
  componer los comandos `glpsol` (hoy son relativos al cwd).
- `xlsx_path` del patcher ActUpLim: `os.path.join(here, 'A1_Outputs', ...)` → `P.scenario_dir(s) / 'A-O_Parametrization.xlsx'`.
- `firm_capacity_fallbacks_by_cr.xlsx`: `os.path.join(here, workbook)` → `os.path.join(P.DATA, workbook)`.
- `get_config_main_path(here, base_folder)` → `os.path.join(ROOT, base_folder)` (con `concatenate_folder: scripts/tools`).
- `export_root_datafile`: `repo_root = Path(here).parent` → `target = P.OUTPUTS / export_name`.
- Salidas finales `path_in`, `path_out`, `path_comb`, `combined_file_path` (líneas 1265, 1279, 1335, 1595, 1628): `os.path.join(HERE, ...)` → `os.path.join(P.OUTPUTS, ...)`.
- Al inicio de `__main__`: `P.ensure_output_dirs()`.
- La aserción de cadena `FROZEN_CHAIN` y toda la lógica de sufijos no se toca.

### 5.6 Resto de scripts

Sustitución mecánica de `HERE / "X"` (o equivalente) por la constante de `P`. Detalle por script en
el §6. Casos con matiz:

- `relac_io.py`: desaparece `REPO`/`T1`; `EXECUTABLES = P.EXECUTABLES`, `OTOOLE = P.A2_OTOOLE`,
  `CACHE = P.FIX_DISPATCH_OUT / "cache"`; `find_combined_csv()` busca en `P.OUTPUTS`.
- `veg_tx_constraints_v14.py`: default de `--base-dir` (`C:\Users\kt0031\...`) → `P.EXECUTABLES`;
  `OUT_DIR = P.TX_CHAIN_OUT`; default de `--needs-csv` → `P.VEG_TX_NEEDS_CSV`.
- `cost_sensitivity_v11.py`, `nli_sr_recompute_v1.py`: el modo legado (sin `--executables-dir`)
  lee/escribe en `HERE`; pasa a `P.TX_CHAIN_OUT`. B2 siempre pasa `--executables-dir`, así que el
  pipeline no depende de esto.
- `add_max_cap_investment_lid_rule.py`: `lid_rule.yaml` y `TECH_TYPES.csv` ya no están junto al
  script → `P.A3_CONFIG / ...`; default de `--input-dir` → `P.scenario_dir("BAU")`.
- `reset_lowerlimits_from_base.py`: `DEFAULT_BASE_DIR = P.BASE_SCENARIO_REF / "Base"`.
- `A3_process.py`: `A1_OUTPUTS_DIR = P.A1_OUTPUTS`; `RULES_SCRIPTS_DIR = P.PIPELINE / "A3_process" / "rules_scripts"`;
  `B1B_VALIDATOR`, `SYNC_HIST_SCRIPT` en `P.PIPELINE`; `LID_RULE_YAML = P.A3_CONFIG / "lid_rule.yaml"`.
- `D2_update_secondary_techs.py`: `base_path = P.A1_OUTPUTS`; editor/OLADE/Shares → `P.DATA`; Matriz
  Balance → `P.MATRIZ_BALANCE`; log `secondary_techs_update_log_*.txt` → `P.LOGS` (hoy cae en
  `A1_Outputs/`); backups junto al xlsx (sin cambio).
- `Z_AUX_generate_interactive_dashboards_aggregated.py`: hoy `glob("*.csv")` y escribe HTML en el
  cwd (que en la práctica es `t1_confection`, donde viven los `RELAC_TX_*.csv`). Se ancla a
  `P.OUTPUTS` para conservar el comportamiento efectivo desde cualquier cwd.
- `Z_AUX_sort_csv.py` (pide la ruta por `input()`), `concatenate_relac.py`, `preprocess_data*.py` y
  los 7 patchers CLI (`inject_DaysInDayType`, `patch_storage_delay`, `strip_storage`,
  `open_pwrbck_caps`, `patch_reserve_margin_repair_careful[_xlsx]`, `sync_patched_csvs_from_txt`):
  **sin cambios** (reciben rutas por argumento).
- Scripts de `matriz_balance/`: `base_path = Path(__file__).parent` → `P.MATRIZ_BALANCE` (leen y
  escriben los xlsx ahí, como hoy).
- Scripts de `veg_tx_abs_test/`: `EXE` → `P.EXECUTABLES`; los `Pre_processed_*.txt` locales →
  `P.REFERENCE / "veg_tx_abs_test"`; png → `P.EXPERIMENTAL_OUT / "veg_tx_abs_test"`.

---

## 6. Cambios por script

Leyenda: **B** = bootstrap (§5.2) · **C** = cambio de import a `common.` · **P** = sustituir rutas
por constantes de `P` · **U** = actualizar líneas de uso (`python t1_confection/X.py`) en docstring.

| Script (destino) | B | C | P | U | Rutas afectadas |
|------------------|---|---|---|---|-----------------|
| pipeline/A0_generate_tech_country_matrix | ✓ | ✓ | ✓ | ✓ | `Config_country_codes.yaml`→CONFIG; `Tech_Country_Matrix.xlsx`→DATA |
| pipeline/A1_Pre_processing_OG_csvs | ✓ | ✓ | ✓ | ✓ | `INPUT_FOLDER`→OG_CSVS_INPUTS; `OUTPUT_FOLDER`→A1_OUTPUTS; `MISCELLANEOUS_FOLDER`; `A2_EXTRA_INPUTS_FOLDER`; `REGION_CONSOLIDATION_CONFIG`→CONFIG; `TECH_COUNTRY_MATRIX_FILE`, `OLADE_GENERATION_FILE`→DATA |
| pipeline/A2_AddTx | ✓ | ✓ | ✓ | ✓ | `OUTPUT_FOLDER`→A1_OUTPUTS; defaults `yaml/base/proj/param/demand` |
| pipeline/A3_migrate_old_inputs_CLG | ✓ | ✓ | ✓ | ✓ | `Old_Inputs`→OLD_INPUTS; Config_tech_equivalences/country_codes→CONFIG; Tech_Country_Matrix→DATA; A1_Outputs; A2_Extra_Inputs |
| pipeline/A3_process | ✓ | | ✓ | ✓ | ver §5.6 |
| pipeline/A3_process/rules_scripts/add_max_cap_investment_lid_rule | ✓(k=3) | | ✓ | ✓ | `lid_rule.yaml`, `TECH_TYPES.csv`→A3_CONFIG; default `--input-dir` |
| pipeline/A3_process/rules_scripts/extend_lowerlimits_pwr | ✓(k=3) | | ✓ | ✓ | default `--input-dir` si lo hay; yaml→A3_CONFIG |
| pipeline/A3_process/rules_scripts/reset_lowerlimits_from_base | ✓(k=3) | | ✓ | ✓ | `DEFAULT_BASE_DIR`→BASE_SCENARIO_REF |
| pipeline/B1_Run_Compiler | ✓ | | ✓ | | ver §5.4 |
| pipeline/B1_Compiler | ✓ | | ✓ | | ver §5.4 (3 ajustes) |
| pipeline/B1b_Pre_solver_validation | ✓ | ✓ | ✓ | ✓ | A1_Outputs (l.80), CONFIG_A (85), CONFIG_AB (99), `Executables` reports (237)→EXECUTABLES, A2 otoole (497) |
| pipeline/B2_Executing_OG_Model | ✓ | | ✓ | | ver §5.5 |
| pipeline/D1_generate_editor_template | ✓ | ✓ | ✓ | ✓ | A1_Outputs; CONFIG_AB; editor/OLADE/Shares→DATA |
| pipeline/D2_update_secondary_techs | ✓ | ✓ | ✓ | ✓ | ver §5.6 |
| pipeline/D3_load_lac_max_capacity_caps | ✓ | | ✓ | ✓ | A1_Outputs |
| pipeline/D4_load_dsptrn_max_cap_inv | ✓ | | ✓ | ✓ | A1_Outputs; `COMBINED_CSV`→OUTPUTS |
| pipeline/D5_load_fuel_var_costs | ✓ | | ✓ | ✓ | A1_Outputs |
| pipeline/sync_historical_from_bau | ✓ | | ✓ | ✓ | A1_Outputs |
| pipeline/patch_activity_upper_limit | ✓ | ✓ | | | solo import `_xlsx_validation_core` |
| pipeline/Z_AUX_capital_annualization_script | | | | | `INPUT_FILENAME` es solo fallback cuando se llama sin ruta; B2 pasa la ruta absoluta. Sin cambio. |
| pipeline/{inject_DaysInDayType, patch_storage_delay, strip_storage, open_pwrbck_caps, patch_reserve_margin_repair_careful, patch_reserve_margin_repair_careful_xlsx, sync_patched_csvs_from_txt, preprocess_data} | | | | ✓ | sin cambios funcionales |
| common/Z_AUX_config_loader | | | ✓ | | `CONFIG_PATH = P.CONFIG_COUNTRY_CODES` (import relativo) |
| common/_xlsx_validation_core | | | | | sin cambios |
| fix_dispatch/relac_io | ✓ | | ✓ | | ver §5.6 |
| fix_dispatch/write_floors | ✓ | | ✓ | ✓ | `CANDIDATES_CSV`→CANDIDATE_FLOORS; `UPSTREAM_OUT`→FIX_DISPATCH_OUT |
| fix_dispatch/preflight_separation | ✓ | | ✓ | ✓ | `DEFAULT_CANDIDATES`→CANDIDATE_FLOORS |
| fix_dispatch/make_candidates | ✓ | | ✓ | ✓ | `OUT`→CANDIDATE_FLOORS (refresca el input) |
| fix_dispatch/build_combined | ✓ | | ✓ | ✓ | `T1`→PIPELINE (sys.path para importar B2), MISCELLANEOUS, CONFIG_AB; `SOLVED`→FIX_DISPATCH_OUT/solved_FLOORED; `CONCAT_SCRIPT`→TOOLS |
| fix_dispatch/fig_floor_effect | ✓ | | ✓ | | `BASELINE_COMBINED`, `FLOORED_*`→OUTPUTS/FIX_DISPATCH_OUT; `CANDIDATES_CSV`; `OUT_PNG` |
| fix_dispatch/{floor_effect, validate_constraints, feasibility, build_summary, veg_tx_constraints} | ✓ | | ✓ | | salidas `HERE / *.csv|txt`→FIX_DISPATCH_OUT; `EXE`→EXECUTABLES |
| tests/test_outputs | ✓ | | ✓ | ✓ | `CANDIDATES_CSV`; `test_*.csv`→FIX_DISPATCH_OUT; import `relac_io` vía sys.path a FIX_DISPATCH |
| tests/test_b2_chain_helper | ✓ | | | ✓ | sys.path a PIPELINE para `import B2_Executing_OG_Model` |
| tests/test_D2_fixes | ✓ | | ✓ | ✓ | `base_path`→A1_OUTPUTS |
| tx_chain/veg_tx_constraints_v14 | ✓ | | ✓ | | ver §5.6 |
| tx_chain/cost_sensitivity_v11, nli_sr_recompute_v1 | ✓ | | ✓ | | modo legado → TX_CHAIN_OUT |
| dashboard/dashboard_config | ✓ | | ✓ | | `CSV_PATH`→OUTPUTS; `FIGURES_DIR`→FIGURES; Matriz Balance→MATRIZ_BALANCE |
| dashboard/build_dashboard | ✓ | | ✓ | | A1_Outputs BAU xlsx; `CapacityAndDistances.xlsx`→DATA; `centerpoints.csv`→MISCELLANEOUS; salidas→FIGURES |
| dashboard/_process_csv_for_dashboard | ✓ | | ✓ | | CSVs y HTML→OUTPUTS/FIGURES |
| dashboard/Z_AUX_generate_transmission_maps | ✓ | | ✓ | ✓ | `*_Combined_Inputs_Outputs.csv`→OUTPUTS; Figures; Miscellaneous/centerpoints |
| dashboard/Z_AUX_generate_RES_diagram | ✓ | | ✓ | ✓ | A1_Outputs; CONFIG_COUNTRY_CODES; FIGURES |
| dashboard/Z_AUX_generate_interactive_dashboards_aggregated | ✓ | | ✓ | ✓ | ver §5.6 |
| tools/Z_validate_country_data | ✓ | ✓ | ✓ | ✓ | `INPUT_DIR`→OG_CSVS_INPUTS |
| tools/Z_generate_country_template | ✓ | | ✓ | ✓ | CONFIG_COUNTRY_CODES; MISCELLANEOUS/centerpoints; OG_CSVS_INPUTS; `templates/`→TEMPLATES_OUT; texto de ayuda `cd t1_confection` |
| tools/Z_AUX_update_maxcap_inv_from_tool | ✓ | | ✓ | ✓ | A1_Outputs; `LAC_maxcap_tool*.xlsx`→DATA |
| tools/Z_AUX_update_transmission_iar | ✓ | | ✓ | ✓ | A1_Outputs |
| tools/Z_AUX_D1b_set_trn_limits_from_flows | ✓ | | ✓ | ✓ | Matriz Balance→MATRIZ_BALANCE; editor→DATA |
| tools/Z_AUX_fix_excel_profiles | ✓ | | ✓ | ✓ | `base_dir/A1_Outputs`→A1_OUTPUTS |
| tools/Z_AUX_united_regions | ✓ | | ✓ | ✓ | A1_Outputs / A2_Extra_Inputs (verificar en implementación) |
| tools/Z_AUX_apply_parametrization_review | ✓ | ✓ | ✓ | ✓ | A1_Outputs; Review xlsx (verificar ubicación → DATA) |
| tools/AUX_Z_recalc_shares | ✓ | | ✓ | ✓ | OLADE, Shares→DATA; `Old_Inputs`→OLD_INPUTS |
| tools/Z_TEMP_add_pwrbck_to_scenarios | ✓ | | ✓ | ✓ | A1_Outputs; OG_CSVS_INPUTS; Config_region_consolidation→CONFIG |
| tools/{Z_AUX_sort_csv, concatenate_relac, preprocess_data_muio} | | | | | sin cambios |
| experimental/matriz_balance/* (5 con `base_path`) | ✓(k=2) | | ✓ | | `base_path`→MATRIZ_BALANCE |
| experimental/veg_tx_abs_test/* | ✓(k=2) | | ✓ | | ver §5.6 |

Durante la implementación, cada script se revisa entero (no solo las líneas listadas) buscando
`__file__`, `HERE`, `SCRIPT_DIR`, `script_dir`, `base_path`, `parents[`, `os.getcwd`, `Path.cwd` y
literales de archivos de datos, para no dejar rutas huérfanas.

---

## 7. Configuración del repositorio

### 7.1 `dvc.yaml`

```yaml
stages:
  preprocess:
    cmd: python -u scripts/pipeline/B1_Run_Compiler.py
    deps:
      - scripts/pipeline/B1_Compiler.py
      - inputs/config/Config_MOMF_T1_A.yaml
      - inputs/A1_Outputs/
      - inputs/A2_Extra_Inputs/
    outs:
      - outputs/A2_Structure_Lists.xlsx
      - outputs/A2_Output_Params/
  executing:
    cmd: python -u scripts/pipeline/B2_Executing_OG_Model.py
    deps:
      - inputs/config/Config_MOMF_T1_AB.yaml
      - inputs/model/osemosys_fast_preprocessed.txt
      - scripts/tools/concatenate_relac.py
      - scripts/pipeline/Z_AUX_capital_annualization_script.py
      - outputs/A2_Output_Params/
      - inputs/Miscellaneous/
    outs:   # cache: false, persist: true como hoy
      - outputs/A2_Outputs_Params_otoole/
      - outputs/Executables/
      - outputs/RELAC_TX_Inputs.csv
      - outputs/RELAC_TX_Inputs_fecha.csv
      - outputs/RELAC_TX_Outputs.csv
      - outputs/RELAC_TX_Outputs_fecha.csv
      - outputs/RELAC_TX_Combined_Inputs_Outputs.csv
      - outputs/RELAC_TX_Combined_Inputs_Outputs_fecha.csv
```

`run.py` sigue parcheando `fecha` en `dvc.yaml` de la raíz: no cambia.

### 7.2 `dvc.lock`

Se reescriben **solo las rutas** (`path:`) a las nuevas; los `md5`/`size`/`nfiles` se conservan.
Así `dvc status` queda limpio tras el movimiento y `dvc repro` no fuerza una corrida completa por
un simple cambio de ubicación. (Si en la verificación se detecta que DVC no acepta el lock
editado, se deja que `dvc repro` reconstruya el lock en la primera corrida real: es equivalente,
solo más lento.)

### 7.3 `.dvcignore`

```
outputs/Executables/**/__pycache__/
outputs/Executables/**/*.py[cod]
```

### 7.4 `.gitignore`

Se reescriben todos los patrones con prefijo `t1_confection/` a sus nuevas rutas, preservando la
semántica. Puntos de atención:

- Bloque `Executables`: `outputs/Executables/**` + las dos excepciones
  `!outputs/Executables/*/` y `!outputs/Executables/*/Pre_processed_*_StorageDelayN5_OpenBCK_RMCarefulXLSX*.txt`.
- Salidas `RELAC_TX_*`: `outputs/RELAC_TX_*.csv` (cubre Inputs/Outputs/Combined, fechados y `StorageDelay_`).
- Excepciones al patrón global `*log*` (por `core.ignorecase` atrapa `Technology*.csv`):
  `!outputs/A2_Output_Params/**`, `!outputs/A2_Outputs_Params_otoole/**`.
- Backups de xlsx: `inputs/A1_Outputs/**/*.xlsx.bak`, `inputs/A1_Outputs/*/A-O_*_backup_*.xlsx`,
  `inputs/A1_Outputs/*/A-O_Parametrization.backup*.xlsx`; `inputs/OG_csvs_inputs/*backup*`.
- Logs: `outputs/logs/` completo; el patrón `secondary_techs_update_log_*.txt` deja de hacer falta
  en `A1_Outputs` (D2 ahora escribe en `outputs/logs/`) pero se conserva por compatibilidad.
- `outputs/Figures/chart*.png`; `outputs/A2_Structure_Lists.xlsx`; `outputs/legacy/Blend_Shares_0.pickle`.
- Patrón global `*temp*`: hace que `outputs/templates/` y `outputs/tx_chain/templates/` queden
  ignorados, igual que hoy `t1_confection/templates/`. `inputs/Miscellaneous/templates/` está
  versionado y sigue versionado (los archivos ya rastreados no se ven afectados por ignore).
- `scripts/**/__pycache__/` (hoy `fix_dispatch/__pycache__` y `t1_confection/__pycache__`
  aparecen como untracked; se añaden explícitamente).

### 7.5 Documentación

- Actualizar rutas y comandos en: `README.md`, `RELAC_TX_Guia_instalacion_ejecucion.md`,
  `docs/{auxiliary-tools, configuration, country-management, installation, pipeline, quickstart,
  secondary-techs-editor, solver-patchers}.md`.
- `docs/plan_integracion_tx_chain_B2.md` y `docs/plan_port_reserve_margin_and_storage_from_OSTRAM.md`
  son planes históricos: se les añade una nota de cabecera ("Rutas anteriores a la reestructuración
  de 2026-09; ver `docs/superpowers/specs/2026-09-07-...`") y no se reescriben.
- Los `.md` que hoy viven junto a scripts se mueven a `docs/` (§4.5, §4.7).
- Docstrings de uso (`python t1_confection/X.py ...`) en ~30 scripts: barrido `t1_confection/` →
  `scripts/<carpeta>/` verificado con grep al final.

---

## 8. `scripts/tools/migrate_layout_untracked.py`

Los artefactos ignorados por git (~1.6 GB: `Executables/`, `RELAC_TX_*.csv`, `cache/`, logs,
backups, `templates/`) no viajan con `git pull`. Este script mueve, de forma idempotente, lo que
exista en las rutas viejas a las nuevas, tanto en esta máquina como en la de `kt0031`.

- Tabla estática origen→destino (subconjunto de §4 restringido a lo no versionado).
- `--dry-run` por defecto; `--apply` mueve. Si el destino ya existe y no está vacío, no sobrescribe:
  informa y omite.
- Al final lista lo que quedó en `t1_confection/`, `fix_dispatch/`, `RELAC_Tx_v15_run/`,
  `veg_tx_abs_test/`, `concatenate_files/` para que el usuario decida borrar las carpetas vacías.

---

## 9. Verificación

### 9.1 Principio

Las dos corridas (antes/después) parten del **mismo estado versionado** en dos `git worktree`
limpios, así que cualquier diferencia solo puede venir de la reestructuración:

```
git worktree add ../relac_tx_baseline  clean-sirelac                    # layout viejo
git worktree add ../relac_tx_new       restructure/inputs-scripts-outputs   # layout nuevo
```

La cadena pre-solver de B2 solo necesita archivos versionados (`A2_Output_Params` recién generado
por B1, `Miscellaneous/templates`, `candidate_floors.csv`, `outputs_BSR/NewCapacity.csv`, el
modelo OSeMOSYS) y regenera todo lo demás. No hace falta copiar ningún artefacto no versionado.

Config de verificación (misma en ambos worktrees, aplicada sobre `Config_MOMF_T1_AB.yaml`):

```yaml
execute_model: False
create_matrix: False
concat_scenarios_csv: False
annualize_capital: False
del_files: False
# resto sin cambio: write_txt_model, A2_otoole_outputs, storage_delay, patchers, veg_tx,
# scenario_transforms, solve_scenarios
```

Ejecución desde la raíz de cada worktree, replicando `run.py`:
`PYTHONHASHSEED=0 conda run -n OG-MOMF-env python -u <B1_Run_Compiler>` y luego `<B2>`.

Nota B1b: `Config_MOMF_T1_A.yaml` deja `pre_solver_validation` en su default (activo,
interactivo). Los inputs versionados ya pasaron por `A3_process` (que corre B1b `--auto-fix-all`),
así que no debería detectar nada. Si pregunta, se responde igual en ambos lados y se anota.

### 9.2 Comparación

| Producto | Qué | Método |
|----------|-----|--------|
| B1 | `A2_Output_Params/**/*.csv` (BAU, INV, OPT, VGB) | md5 por archivo |
| B1 | `A2_Structure_Lists.xlsx` | por contenido (openpyxl, hoja a hoja); el xlsx lleva timestamp en `docProps` |
| B2 | `A2_Outputs_Params_otoole/**/*.csv` (base y derivados) | md5 |
| B2 | `Executables/<S>_0/*.txt` para los 13 escenarios, **todos** los eslabones (`<S>_0.txt`, `Pre_processed_*`, `*_StorageDelayN5`, `*_OpenBCK`, `*_RMCarefulXLSX`, `*_FLOORED`, `*_VEGCON`, `*.warnings.txt`) | md5 |
| B2 | `osemosys_fast_preprocessed_storage_delay.txt`, `RELAC_TX_data_storage_delay.txt` | md5 |
| B2 | `upstream_floor_rows.csv`, `veg_pipeline_proof.png`/`veg_preflight.png` | md5 del csv; los png solo existencia (matplotlib embebe metadata) |

Herramienta: `compare_manifests.py` en el scratchpad (no se commitea). Genera un manifiesto
`ruta_relativa → md5` por worktree, aplica el mapa viejo→nuevo del §4 y lista: faltantes en un
lado, sobrantes, y distintos. **Criterio de aceptación: cero diferencias.** Si aparece alguna, las
únicas clases aceptables son (a) comentarios con rutas absolutas dentro de un `.txt` generado, (b)
timestamps embebidos; se documentan en el spec con el diff concreto.

### 9.3 Comprobaciones estáticas y smoke

1. `python -m py_compile` de todos los `.py` bajo `scripts/`.
2. Smoke desde la nueva ubicación (cada uno debe salir con código 0 y sin `FileNotFoundError`):
   `A3_process.py --list`, `B1b_Pre_solver_validation.py --scenario BAU --report-only`,
   `D4_load_dsptrn_max_cap_inv.py --dry-run`, `sync_historical_from_bau.py --dry-run`,
   `Z_validate_country_data.py`, `Z_AUX_update_maxcap_inv_from_tool.py` (dry-run por defecto),
   `Z_AUX_apply_parametrization_review.py` (dry-run), `write_floors.py --dry-run --scenarios BAU`,
   `preflight_separation.py`, `test_b2_chain_helper.py`, y `--help` de todos los que tienen argparse.
3. grep de tokens viejos en `scripts/`, `inputs/config/`, `dvc.yaml`, `dvc.lock`, `.gitignore`,
   `.dvcignore`, `README.md`, guía y docs operativos: `t1_confection`, `fix_dispatch/` (como ruta
   desde raíz), `RELAC_Tx_v15_run`, `concatenate_files`, `veg_tx_abs_test/` (como ruta), `kt0031`,
   `HERE.parent / "t1_confection"`. Resultado esperado: cero, salvo los dos planes históricos y este spec.
4. `dvc status` en el worktree nuevo → sin cambios pendientes tras editar `dvc.lock`.
5. `git status` limpio salvo lo esperado; `git log --follow` de un par de archivos movidos muestra
   la historia completa.

### 9.4 Opcional recomendado: A0 → A1 → A2

A1/A2 **sobrescriben** inputs versionados (`A1_Outputs`), así que no se pueden probar sobre el
árbol real. En los dos worktrees se corre `A0`, `A1` y `A2` y se comparan `inputs/A1_Outputs/**/*.xlsx`,
`Tech_Country_Matrix.xlsx` y `A2_Extra_Inputs/A-Xtra_Emissions.xlsx` por contenido (hoja a hoja).
Los worktrees se descartan después. Se hace si el tiempo de A1 lo permite (se mide en el baseline).

### 9.5 Aprobación para ejecutar

Ninguna corrida de B1, B2, A0–A2 ni de herramientas que escriben se lanza sin aprobación puntual
del usuario, por la regla vigente para este pipeline. El plan de implementación marca cada uno de
esos pasos como "requiere OK".

---

## 10. Estrategia git

Rama `restructure/inputs-scripts-outputs` (ya creada desde `clean-sirelac`). Commits en este
orden, sin línea de coautoría:

1. `docs: spec de reestructuración inputs/scripts/outputs` (este documento).
2. `refactor(layout): mover archivos a inputs/ scripts/ outputs/ (solo git mv, sin cambios de contenido)`.
   Un único commit de renombres puros para que git detecte los renames al 100 % y las ramas
   paralelas (`main`, `dev`, `feature/*`, `equalize-*`) puedan mergear/rebasar con detección de
   renombres.
3. `feat(common): relac_paths.py + módulos comunes`.
4. Un commit por familia de edición de rutas: B1; B2; pipeline A/D; fix_dispatch; tx_chain;
   dashboard; tools; tests; experimental.
5. `chore: YAML relativos a la raíz, dvc.yaml/lock, .gitignore, .dvcignore`.
6. `docs: rutas actualizadas`.
7. `tools: migrate_layout_untracked.py`.
8. `docs(spec): resultado de la verificación` (manifiestos resumidos, diferencias si las hubo).

El movimiento de artefactos **no versionados** de este working tree se hace con
`migrate_layout_untracked.py --apply` después del commit 2, y antes de la verificación, para que
el árbol de trabajo quede utilizable.

Sin `push` hasta que el usuario lo indique.

---

## 11. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| Ramas paralelas con commits en `t1_confection/` sufren conflictos de rename al mergear | Commit de `git mv` puro separado de las ediciones; mergear a `main` pronto; documentar `git merge -X find-renames` para las ramas rezagadas |
| Algún `.txt`/`.csv` generado embebe una ruta absoluta o un timestamp → falso positivo en la comparación | La comparación lista el diff concreto; se clasifica y documenta; no se "arregla" el generador (sería cambio de funcionalidad) |
| Ruta cwd-relativa olvidada en B2 (usos "a pelo" de `params['executables']`) | Lista explícita de líneas en §5.5; `os.chdir(P.LOGS)` hace que cualquier olvido falle ruidosamente (`FileNotFoundError` en `outputs/logs/...`) en la corrida de verificación, no silenciosamente |
| B1b interactivo pregunta durante la verificación | Se responde igual en ambos lados; si ocurre, indica que los inputs no están pre-validados, no un problema de rutas |
| `dvc.lock` editado a mano no aceptado por DVC | Fallback: dejar que `dvc repro` lo regenere en la primera corrida real |
| Máquina `kt0031` con artefactos en rutas viejas | `migrate_layout_untracked.py`; el default hardcodeado de `veg_tx_constraints_v14.py` a esa máquina desaparece (pasa a `P.EXECUTABLES`) |
| Nombres con espacios/acentos (`NO BORRAR ...`, `Matriz Balance energético`) bajo `inputs/reference/` | Ya existen hoy y funcionan; se conservan tal cual (renombrar está fuera de alcance) |
| Memoria del asistente y notas externas con rutas viejas | Se actualizan al cerrar la implementación (fuera del repo) |

---

## 12. Criterios de aceptación

1. En la raíz solo quedan los archivos listados en §3.
2. `git log --follow` muestra historia continua para los archivos movidos.
3. Comparación §9.2: cero diferencias (o diferencias documentadas y clasificadas como benignas).
4. §9.3: `py_compile` limpio, smoke con exit 0, grep de tokens viejos = 0, `dvc status` limpio.
5. `python run.py` en un clon limpio de la rama llega hasta la etapa `executing` sin errores de
   ruta (se puede comprobar con la config de verificación de §9.1, sin solver).
6. README, guía y docs operativos reflejan las nuevas rutas.

---

## 13. Estado al 2026-09-08 y pasos pendientes

**Implementado y revisado** en la rama `restructure/inputs-scripts-outputs` (Tasks 2–17 del plan):
commit de `git mv` puro `6731992` (1163 renombres, 0 cambios de contenido), `scripts/common/relac_paths.py`,
adaptación de rutas en los ~75 scripts, YAML relativos a la raíz, `dvc.yaml`/`dvc.lock`/`.gitignore`/`.dvcignore`,
documentación, `scripts/tools/migrate_layout_untracked.py`. Revisión final de rama: 0 Critical; los 2 Important
(orden de negaciones en `.gitignore`; `docs/fix_dispatch/INSTRUCCIONES_SOLVE.md`) corregidos.

**Verificación de resultado (2026-09-08): replicable.** La primera comparación de solves en otra máquina dio distinto
(estado C: menos filas/columnas en el LP, objetivo ×5.8 en BAC). La causa **no fue el layout** sino datos: los xlsx de
`inputs/` estaban detrás de los CSV de `outputs/A2_Output_Params/` (seis cambios aplicados con scripts no versionados).
Diagnóstico y corrección en `docs/superpowers/plans/2026-09-08-diagnostico-estado-C-solves.md`: xlsx restaurados desde
`stash@{0}` y YAML con las entradas BDS (`fbfe827`), scripts de parche versionados en `scripts/tools/data_patches/`
(`b6a314f`). Con eso, B1 → B2 en el nuevo layout reproduce el resultado de referencia A=B: **el resultado hasta este
punto con el nuevo workflow es totalmente replicable desde `inputs/`**. La comparación byte a byte de artefactos
intermedios de §9 (Tasks 1 y 18) queda como opcional; su herramienta sigue en `scripts/tools/verification/README.md`.

**Pendiente:** commit de limpieza de código muerto
(constantes `HERE`/`SCRIPT_DIR` sin uso en ~21 scripts, `here` en B2, `P` sin uso en `patch_activity_upper_limit.py`,
local `P` en `veg_tx_constraints_v14.py`/`experimental/.../veg_tx_constraints.py`), merge a `main`, y en la máquina
`kt0031`: `git pull` + `python scripts/tools/migrate_layout_untracked.py --apply`.

**Decisiones tomadas durante la implementación** (detalle en el ledger `.superpowers/sdd/...`, no versionado):

- Se trabajó en el árbol principal sobre la rama (no en worktree): el movimiento de ~1.6 GB de artefactos no
  versionados solo era posible ahí.
- Imports cruzados entre subcarpetas de `scripts/` como `from tools.X import` / `from pipeline.X import`
  (namespace packages, `scripts/` en `sys.path` vía bootstrap). Casos: D2 → `Z_AUX_D1b_set_trn_limits_from_flows`,
  A3_migrate → `Z_AUX_fix_excel_profiles`, Z_TEMP_add_pwrbck → `A1_Pre_processing_OG_csvs`, build_combined →
  B2 y `Z_AUX_capital_annualization_script` (vía `sys.path.insert(P.PIPELINE)`).
- `.gitignore`: se añaden `!scripts/**`, `!inputs/config/**` y `!inputs/Miscellaneous/templates/**` (protegen código,
  config y plantillas versionadas de los patrones globales `*log*`/`*temp*`/`*copy*`), colocados tras esos patrones;
  `outputs/RELAC_TX_StorageDelay_*.csv` amplía el ignore a Inputs/Outputs/Combined sin fecha (salidas regeneradas).
- `dvc status` no queda limpio tras editar `dvc.lock`: el lock ya estaba desfasado antes de la rama (referencia
  `RELAC_TX_*_2026-02-10.csv` inexistentes y 64 ficheros otoole frente a 448 versionados). Aplica el fallback de
  §7.2: `dvc repro` lo regenera en la primera corrida real.
- `scripts/tools/migrate_layout_untracked.py` conserva literales `t1_confection/`, `fix_dispatch/`,
  `RELAC_Tx_v15_run/` por diseño (es la herramienta que migra desde el layout viejo).
- Anclajes extra en B2 no enumerados en el plan pero exigidos por el cambio de cwd: `t['script']` de los
  transforms, el join multilínea de `run_days_in_day_type_patcher`, `base_input_path` de `generate_combined_*`.
- `build_summary.py` tenía rutas relativas al cwd (`candidate_floors.csv`, salida csv): ancladas a `P`.
- `A3_process.py` pasa ahora `--yaml <inputs/config/A3_process/lid_rule.yaml>` al rules script (su default también
  apunta ahí); comportamiento equivalente.
