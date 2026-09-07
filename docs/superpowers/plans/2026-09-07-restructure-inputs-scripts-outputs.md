# Reestructuración `inputs/` · `scripts/` · `outputs/` — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mover todo el repositorio a tres carpetas raíz (`inputs/`, `scripts/`, `outputs/`) cambiando únicamente rutas, y demostrar byte a byte que B1 y la cadena pre-solver de B2 producen exactamente los mismos archivos.

**Architecture:** Un módulo central `scripts/common/relac_paths.py` es el único lugar que conoce el layout; cada script lo importa con un bootstrap de dos líneas y sustituye sus `HERE / "X"` por constantes. B1 y B2 conservan sus claves YAML de directorios, pero todas pasan a ser relativas a la raíz del repo. El movimiento de archivos se hace en un único commit de `git mv` puro, separado de las ediciones, para preservar historia y detección de renombres.

**Tech Stack:** Python 3 (conda env `OG-MOMF-env`), pandas/openpyxl/pyyaml, DVC, otoole, GLPK/CPLEX (no se ejecuta el solver en este plan), Git Bash en Windows.

**Spec:** `docs/superpowers/specs/2026-09-07-restructure-inputs-scripts-outputs-design.md` (leer entero antes de empezar; el plan argumenta desde él).

## Global Constraints

- **No cambia ninguna lógica**: solo rutas, imports y `cwd`. Si una edición necesita algo más, parar y consultar.
- **Nada se renombra ni se borra**: ni scripts, ni datos, ni carpetas con espacios/acentos (`NO BORRAR A1_Outputs - Escenario Base`, `Matriz Balance energético`).
- **Lo versionado sigue versionado; lo ignorado sigue ignorado.** Movimientos versionados con `git mv`; no versionados con `mv` (Task 3).
- **Rutas en YAML relativas a la raíz del repo** (`inputs/...`, `outputs/...`, `scripts/...`).
- **Bootstrap estándar** en cada script (k = 1 en `scripts/<carpeta>/`, 2 en `scripts/experimental/<sub>/`, 3 en `scripts/pipeline/A3_process/rules_scripts/`):
  ```python
  import sys
  from pathlib import Path
  sys.path.insert(0, str(Path(__file__).resolve().parents[K]))  # -> scripts/
  from common import relac_paths as P
  ```
- **Ninguna corrida de B1, B2, A0–A2 ni de herramientas que escriben datos se lanza sin OK explícito del usuario.** Los pasos marcados `⚠️ REQUIERE OK` se detienen y preguntan.
- **Commits sin línea de coautoría** (preferencia del usuario). No hacer `push`.
- Shell de referencia: **Git Bash** desde la raíz del repo `C:/Users/ClimateLeadGroup/Desktop/CLG_repositories/relac_tx`. Python del pipeline: `conda run -n OG-MOMF-env --no-capture-output python`.
- Rama de trabajo: `restructure/inputs-scripts-outputs` (ya existe, HEAD `b4cb625`).

---

## Mapa de archivos del plan

| Archivo | Responsabilidad | Task |
|---------|-----------------|------|
| `scripts/common/__init__.py` | hace de `common` un paquete | 4 |
| `scripts/common/relac_paths.py` | layout del repo: `REPO_ROOT`, `INPUTS`, `OUTPUTS`, `SCRIPTS` y constantes con nombre | 4 |
| `scripts/tests/test_relac_paths.py` | verifica que cada constante apunta a algo que existe tras el movimiento | 4 |
| `scripts/tools/migrate_layout_untracked.py` | mueve artefactos no versionados de rutas viejas a nuevas (idempotente) | 3 |
| `<scratch>/compare_manifests.py` | manifiesto md5 antes/después y diff | 1, 18 |
| `<scratch>/verify_config.sh` | aplica la config de verificación a `Config_MOMF_T1_AB.yaml` de un worktree | 1, 18 |

`<scratch>` = `C:/Users/CLIMAT~1/AppData/Local/Temp/claude/c--Users-ClimateLeadGroup-Desktop-CLG-repositories-relac-tx/4b916f8e-7f5d-481c-8101-f485a8d29c7a/scratchpad`. Nada de ahí se commitea.

---

### Task 1: Baseline — worktree del layout viejo, herramientas de comparación y corrida de referencia

**Files:**
- Create: `<scratch>/compare_manifests.py`
- Create: `<scratch>/verify_config.sh`
- Worktree: `../relac_tx_baseline` (rama `clean-sirelac`, HEAD `c8f0efc`)

**Interfaces:**
- Produces: `<scratch>/manifest_baseline.json` con `{clave_canonica: md5}`; `compare_manifests.py manifest <root> <layout> <out.json>` y `compare_manifests.py diff <a.json> <b.json>`.

- [ ] **Step 1: Crear el worktree baseline**

```bash
cd "C:/Users/ClimateLeadGroup/Desktop/CLG_repositories/relac_tx"
git worktree add ../relac_tx_baseline clean-sirelac
ls ../relac_tx_baseline/t1_confection | head -5
```
Esperado: carpeta creada; `git -C ../relac_tx_baseline log --oneline -1` muestra `c8f0efc`.

- [ ] **Step 2: Escribir `compare_manifests.py`**

Claves canónicas independientes del layout: `A2_Output_Params/...`, `A2_Structure_Lists.xlsx`, `A2_Outputs_Params_otoole/...`, `Executables/...`, `model/osemosys_fast_preprocessed_storage_delay.txt`, `RELAC_TX_data_storage_delay.txt`, `fix_dispatch/upstream_floor_rows.csv`.

```python
#!/usr/bin/env python
"""compare_manifests.py manifest <repo_root> <old|new> <out.json>
   compare_manifests.py diff <a.json> <b.json>"""
import hashlib, json, sys
from pathlib import Path

# (carpeta relativa a la raíz, prefijo canónico)
LAYOUT = {
    "old": [
        ("t1_confection/A2_Output_Params", "A2_Output_Params"),
        ("t1_confection/A2_Outputs_Params_otoole", "A2_Outputs_Params_otoole"),
        ("t1_confection/Executables", "Executables"),
        ("t1_confection/osemosys_fast_preprocessed_storage_delay.txt", "model/osemosys_fast_preprocessed_storage_delay.txt"),
        ("RELAC_TX_data_storage_delay.txt", "RELAC_TX_data_storage_delay.txt"),
        ("fix_dispatch/upstream_floor_rows.csv", "fix_dispatch/upstream_floor_rows.csv"),
    ],
    "new": [
        ("outputs/A2_Output_Params", "A2_Output_Params"),
        ("outputs/A2_Outputs_Params_otoole", "A2_Outputs_Params_otoole"),
        ("outputs/Executables", "Executables"),
        ("outputs/model/osemosys_fast_preprocessed_storage_delay.txt", "model/osemosys_fast_preprocessed_storage_delay.txt"),
        ("outputs/RELAC_TX_data_storage_delay.txt", "RELAC_TX_data_storage_delay.txt"),
        ("outputs/fix_dispatch/upstream_floor_rows.csv", "fix_dispatch/upstream_floor_rows.csv"),
    ],
}
SKIP_SUFFIXES = (".pyc", ".png", ".lp", ".sol", ".glp")
SKIP_PARTS = ("__pycache__", "Outputs")   # Outputs/ = resultados de solver previos, no se comparan

def md5(p: Path) -> str:
    h = hashlib.md5()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def manifest(root: Path, layout: str) -> dict:
    out = {}
    for rel, key in LAYOUT[layout]:
        p = root / rel
        if p.is_file():
            out[key] = md5(p)
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if not f.is_file() or f.suffix in SKIP_SUFFIXES:
                    continue
                if any(part in SKIP_PARTS for part in f.relative_to(p).parts):
                    continue
                out[f"{key}/{f.relative_to(p).as_posix()}"] = md5(f)
        else:
            print(f"[warn] no existe: {p}")
    return out

def diff(a: dict, b: dict) -> int:
    only_a = sorted(set(a) - set(b)); only_b = sorted(set(b) - set(a))
    changed = sorted(k for k in set(a) & set(b) if a[k] != b[k])
    for title, items in (("SOLO EN BASELINE", only_a), ("SOLO EN NUEVO", only_b), ("DISTINTOS", changed)):
        print(f"== {title}: {len(items)}")
        for k in items[:200]:
            print("   ", k)
    print(f"\nTotal comparados: {len(set(a) & set(b))}  iguales: {len(set(a) & set(b)) - len(changed)}")
    return 0 if not (only_a or only_b or changed) else 1

if __name__ == "__main__":
    if sys.argv[1] == "manifest":
        m = manifest(Path(sys.argv[2]).resolve(), sys.argv[3])
        Path(sys.argv[4]).write_text(json.dumps(m, indent=1, sort_keys=True))
        print(f"{len(m)} archivos -> {sys.argv[4]}")
    elif sys.argv[1] == "diff":
        sys.exit(diff(json.loads(Path(sys.argv[2]).read_text()), json.loads(Path(sys.argv[3]).read_text())))
```

- [ ] **Step 3: Escribir `verify_config.sh`** (aplica la config de verificación del spec §9.1 al YAML de un worktree; se pasa la ruta del YAML)

```bash
#!/usr/bin/env bash
# uso: verify_config.sh <ruta/Config_MOMF_T1_AB.yaml>
set -euo pipefail
Y="$1"
sed -i -E 's/^execute_model: .*/execute_model: False/' "$Y"
sed -i -E 's/^create_matrix: .*/create_matrix: False/' "$Y"
sed -i -E 's/^concat_scenarios_csv: .*/concat_scenarios_csv: False/' "$Y"
sed -i -E 's/^annualize_capital: .*/annualize_capital: False/' "$Y"
sed -i -E 's/^del_files: .*/del_files: False/' "$Y"
grep -nE "^(execute_model|create_matrix|concat_scenarios_csv|annualize_capital|del_files):" "$Y"
```
Esperado al ejecutarlo: las cinco líneas impresas con `False`.

- [ ] **Step 4: Aplicar la config de verificación en el baseline**

```bash
bash "<scratch>/verify_config.sh" ../relac_tx_baseline/t1_confection/Config_MOMF_T1_AB.yaml
```

- [ ] **Step 5: ⚠️ REQUIERE OK — Correr B1 en el baseline** (~10–20 min)

```bash
cd ../relac_tx_baseline
PYTHONHASHSEED=0 conda run -n OG-MOMF-env --no-capture-output python -u t1_confection/B1_Run_Compiler.py 2>&1 | tee "<scratch>/baseline_B1.log"
```
Esperado: `[INFO] All done.`; existe `t1_confection/A2_Output_Params/{BAU,INV,OPT,VGB}/`. Si B1b pregunta algo, anotar la respuesta dada (habrá que repetirla igual en Task 18).

- [ ] **Step 6: ⚠️ REQUIERE OK — Correr B2 en el baseline sin solver** (~15–25 min)

```bash
cd ../relac_tx_baseline
PYTHONHASHSEED=0 conda run -n OG-MOMF-env --no-capture-output python -u t1_confection/B2_Executing_OG_Model.py 2>&1 | tee "<scratch>/baseline_B2.log"
ls t1_confection/Executables            # 13 carpetas *_0
ls t1_confection/Executables/VSRWF_0    # ..._FLOORED_VEGCON.txt presente
```
Esperado: 13 carpetas (`BAU BAC BSR INV INVWF ISR ISRWF OPC OPT VGB VGBWF VSR VSRWF`), `veg_tx PASS`, sin traceback. Con `execute_model: False` el bloque de solver se omite.

- [ ] **Step 7: Generar el manifiesto baseline**

```bash
cd "C:/Users/ClimateLeadGroup/Desktop/CLG_repositories/relac_tx"
python "<scratch>/compare_manifests.py" manifest ../relac_tx_baseline old "<scratch>/manifest_baseline.json"
```
Esperado: varios miles de archivos; guardar también `baseline_B1.log`/`baseline_B2.log` (se citan en Task 18).

No hay commit en esta task (todo es scratch/worktree).

---

### Task 2: Movimiento puro con `git mv` (un solo commit, sin cambios de contenido)

**Files:**
- Mueve todo lo versionado según spec §4. No edita ningún archivo.

**Interfaces:**
- Produces: el layout de spec §3 para los archivos versionados. Las Tasks 4–16 asumen estas rutas.

- [ ] **Step 1: Confirmar árbol limpio y rama correcta**

```bash
cd "C:/Users/ClimateLeadGroup/Desktop/CLG_repositories/relac_tx"
git branch --show-current          # restructure/inputs-scripts-outputs
git status --short | grep -v '^??' # vacío
```

- [ ] **Step 2: Ejecutar el script de movimientos** (copiar entero a `<scratch>/mv_all.sh` y ejecutar con `bash`)

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "C:/Users/ClimateLeadGroup/Desktop/CLG_repositories/relac_tx"
T1=t1_confection

mkdir -p inputs/config/A3_process inputs/model inputs/data inputs/reference \
         inputs/tx_chain/fix_dispatch inputs/tx_chain/outputs_BSR \
         scripts/common scripts/pipeline/A3_process/rules_scripts scripts/fix_dispatch \
         scripts/tx_chain scripts/dashboard scripts/tools scripts/tests \
         scripts/experimental/matriz_balance scripts/experimental/veg_tx_abs_test \
         outputs/model outputs/legacy outputs/fix_dispatch outputs/tx_chain \
         outputs/experimental/veg_tx_abs_test docs/fix_dispatch docs/experimental
# OJO: NO pre-crear destinos que reciben un directorio entero con git mv (inputs/OG_csvs_inputs,
# inputs/A1_Outputs, inputs/A2_Extra_Inputs, inputs/Miscellaneous, outputs/A2_Output_Params,
# outputs/A2_Outputs_Params_otoole, outputs/Figures, inputs/reference/<carpetas>): si el destino
# existe, git mv anida la carpeta dentro (Figures/Figures).

# ---------- raíz ----------
git mv RELAC_TX_data.txt outputs/RELAC_TX_data.txt
git mv RELAC_TX_data_storage_delay.txt outputs/RELAC_TX_data_storage_delay.txt
git mv concatenate_files/concatenate_relac.py scripts/tools/concatenate_relac.py

# ---------- t1_confection -> inputs ----------
for f in Config_MOMF_T1_A.yaml Config_MOMF_T1_AB.yaml Config_country_codes.yaml \
         Config_region_consolidation.yaml Config_tech_equivalences.yaml; do
  git mv "$T1/$f" inputs/config/; done
git mv "$T1/A3_process/rules_scripts/lid_rule.yaml" inputs/config/A3_process/lid_rule.yaml
git mv "$T1/A3_process/TECH_TYPES.csv"               inputs/config/A3_process/TECH_TYPES.csv
git mv "$T1/osemosys_fast_preprocessed.txt" inputs/model/osemosys_fast_preprocessed.txt
git mv "$T1/OG_csvs_inputs"   inputs/OG_csvs_inputs
git mv "$T1/A1_Outputs"       inputs/A1_Outputs
git mv "$T1/A2_Extra_Inputs"  inputs/A2_Extra_Inputs
git mv "$T1/Miscellaneous"    inputs/Miscellaneous
for f in Tech_Country_Matrix.xlsx Secondary_Techs_Editor.xlsx \
         "OLADE - Capacidad instalada por fuente - Anual.xlsx" \
         "OLADE - Generación eléctrica por fuente - Anual.xlsx" \
         Shares_PET_OIL_Split.xlsx Shares_Power_Generation_Technologies.xlsx \
         LAC_maxcap_tool.xlsx LAC_maxcap_tool_complementary.xlsx \
         firm_capacity_fallbacks_by_cr.xlsx CapacityAndDistances.xlsx; do
  git mv "$T1/$f" inputs/data/; done
git mv "$T1/Old_Inputs" inputs/reference/Old_Inputs
git mv "$T1/NO BORRAR A1_Outputs - Escenario Base" "inputs/reference/NO BORRAR A1_Outputs - Escenario Base"
git mv "$T1/Matriz Balance energético" "inputs/reference/Matriz Balance energético"
git mv "$T1/Demanda CireLAC_GTER_WEO.xlsx" inputs/reference/
git mv "$T1/RateGrowthDemand_RenovabilityGoals.xlsx" inputs/reference/

# ---------- t1_confection -> scripts ----------
git mv "$T1/Z_AUX_config_loader.py"   scripts/common/
git mv "$T1/_xlsx_validation_core.py" scripts/common/
for f in A0_generate_tech_country_matrix.py A1_Pre_processing_OG_csvs.py A2_AddTx.py \
         A3_migrate_old_inputs_CLG.py A3_process.py B1_Compiler.py B1_Run_Compiler.py \
         B1b_Pre_solver_validation.py B2_Executing_OG_Model.py \
         D1_generate_editor_template.py D2_update_secondary_techs.py D3_load_lac_max_capacity_caps.py \
         D4_load_dsptrn_max_cap_inv.py D5_load_fuel_var_costs.py inject_DaysInDayType.py \
         open_pwrbck_caps.py patch_activity_upper_limit.py patch_reserve_margin_repair_careful.py \
         patch_reserve_margin_repair_careful_xlsx.py patch_storage_delay.py strip_storage.py \
         sync_historical_from_bau.py sync_patched_csvs_from_txt.py Z_AUX_capital_annualization_script.py; do
  git mv "$T1/$f" scripts/pipeline/; done
git mv inputs/Miscellaneous/preprocess_data.py      scripts/pipeline/preprocess_data.py
git mv inputs/Miscellaneous/preprocess_data_muio.py scripts/tools/preprocess_data_muio.py
for f in add_max_cap_investment_lid_rule.py extend_lowerlimits_pwr.py reset_lowerlimits_from_base.py; do
  git mv "$T1/A3_process/rules_scripts/$f" scripts/pipeline/A3_process/rules_scripts/; done
for f in build_dashboard.py dashboard_config.py _process_csv_for_dashboard.py \
         Z_AUX_generate_transmission_maps.py Z_AUX_generate_RES_diagram.py \
         Z_AUX_generate_interactive_dashboards_aggregated.py; do
  git mv "$T1/$f" scripts/dashboard/; done
for f in AUX_Z_recalc_shares.py Z_AUX_apply_parametrization_review.py Z_AUX_D1b_set_trn_limits_from_flows.py \
         Z_AUX_fix_excel_profiles.py Z_AUX_sort_csv.py Z_AUX_united_regions.py \
         Z_AUX_update_maxcap_inv_from_tool.py Z_AUX_update_transmission_iar.py \
         Z_generate_country_template.py Z_TEMP_add_pwrbck_to_scenarios.py Z_validate_country_data.py; do
  git mv "$T1/$f" scripts/tools/; done
git mv "$T1/test_b2_chain_helper.py" scripts/tests/
git mv "$T1/test_D2_fixes.py"        scripts/tests/
for f in datos_flujos_internet.py estimar_flujos_desde_olade.py estimar_flujos_optimizacion.py \
         estimar_flujos_promedio.py estimar_flujos_ras.py generar_matriz_electricidad.py \
         generar_tabla_flujos_energia.py; do
  git mv "inputs/reference/Matriz Balance energético/$f" scripts/experimental/matriz_balance/; done
git mv "inputs/reference/Matriz Balance energético/README_PROCESO.md" docs/experimental/matriz_balance_README_PROCESO.md

# ---------- t1_confection -> outputs ----------
git mv "$T1/A2_Output_Params"          outputs/A2_Output_Params
git mv "$T1/A2_Outputs_Params_otoole"  outputs/A2_Outputs_Params_otoole
git mv "$T1/Figures"                   outputs/Figures
git mv "$T1/osemosys_fast_preprocessed_storage_delay.txt" outputs/model/
git mv "$T1/cf_corregido_brasil.html"  outputs/Figures/
git mv "$T1/_dashboard_data.csv"       outputs/Figures/
git mv "$T1/Blend_Shares_0.pickle"     outputs/legacy/

# ---------- fix_dispatch ----------
for f in relac_io.py write_floors.py preflight_separation.py make_candidates.py build_combined.py \
         build_summary.py feasibility.py floor_effect.py fig_floor_effect.py validate_constraints.py \
         veg_tx_constraints.py; do
  git mv "fix_dispatch/$f" scripts/fix_dispatch/; done
git mv fix_dispatch/test_outputs.py scripts/tests/
git mv fix_dispatch/candidate_floors.csv          inputs/tx_chain/fix_dispatch/
git mv fix_dispatch/candidate_floors_baseline.csv inputs/tx_chain/fix_dispatch/
for f in candidate_floors_summary.csv upstream_floor_rows.csv input_comparison_report.csv \
         input_comparison_report.md fig_floor_effect.png test_cf_targets.csv test_floor_compliance.csv \
         test_idle_capacity.csv test_scenario_separation.csv; do
  git mv "fix_dispatch/$f" outputs/fix_dispatch/; done
git mv fix_dispatch/INSTRUCCIONES_SOLVE.md docs/fix_dispatch/
git mv fix_dispatch/fix_report.md          docs/fix_dispatch/

# ---------- RELAC_Tx_v15_run ----------
for f in veg_tx_constraints_v14.py cost_sensitivity_v11.py nli_sr_recompute_v1.py; do
  git mv "RELAC_Tx_v15_run/$f" scripts/tx_chain/; done
git mv RELAC_Tx_v15_run/outputs_BSR/NewCapacity.csv inputs/tx_chain/outputs_BSR/NewCapacity.csv

# ---------- veg_tx_abs_test ----------
for f in veg_tx_constraints.py explain_shared_ceiling.py plot_floors_ceilings.py \
         verify_no_infeasibility.py why_ceiling_gt_floor.py; do
  git mv "veg_tx_abs_test/$f" scripts/experimental/veg_tx_abs_test/; done
mkdir -p inputs/reference/veg_tx_abs_test
git mv veg_tx_abs_test/Pre_processed_*_FLOORED_VEGCON.txt inputs/reference/veg_tx_abs_test/
git mv veg_tx_abs_test/veg_pipeline_proof.png outputs/experimental/veg_tx_abs_test/
git mv veg_tx_abs_test/veg_preflight.png      outputs/experimental/veg_tx_abs_test/
git mv veg_tx_abs_test/ENTREGABLE_ANDREY_v2.md docs/experimental/

echo "=== archivos versionados que siguen en carpetas viejas (debe ser 0) ==="
git ls-files t1_confection fix_dispatch RELAC_Tx_v15_run veg_tx_abs_test concatenate_files | wc -l
```

- [ ] **Step 3: Verificar que solo hay renombres**

```bash
git status --short | grep -vE '^(R |\?\?)' | head     # vacío: solo R (rename) y ?? (untracked)
git diff --cached --stat -M100% | tail -1              # N files changed, 0 insertions(+), 0 deletions(-)
git ls-files t1_confection fix_dispatch RELAC_Tx_v15_run veg_tx_abs_test concatenate_files | wc -l  # 0
```

- [ ] **Step 4: Commit**

```bash
git commit -q -m "refactor(layout): mover archivos a inputs/ scripts/ outputs/ (solo git mv, sin cambios de contenido)

Ver docs/superpowers/specs/2026-09-07-restructure-inputs-scripts-outputs-design.md §4."
git log --oneline -1
git log --follow --oneline -- scripts/pipeline/B2_Executing_OG_Model.py | wc -l   # > 1: historia preservada
```

---

### Task 3: `migrate_layout_untracked.py` y movimiento de artefactos no versionados

**Files:**
- Create: `scripts/tools/migrate_layout_untracked.py`

**Interfaces:**
- Produces: CLI `python scripts/tools/migrate_layout_untracked.py [--apply]`; sin `--apply` es dry-run.

- [ ] **Step 1: Escribir el script**

```python
#!/usr/bin/env python
"""Mueve artefactos NO versionados del layout viejo (t1_confection/, fix_dispatch/, ...) al nuevo
(inputs/ scripts/ outputs/). Idempotente: si el origen no existe, lo omite; si el destino ya
existe y no está vacío, NO sobrescribe (informa). Dry-run por defecto; --apply mueve.

Uso:  python scripts/tools/migrate_layout_untracked.py           # dry-run
      python scripts/tools/migrate_layout_untracked.py --apply
"""
import argparse
import shutil
import sys
from pathlib import Path

ROOT = next(p for p in [Path(__file__).resolve(), *Path(__file__).resolve().parents] if (p / "dvc.yaml").is_file())

# (origen relativo a la raíz, destino relativo a la raíz). Carpetas o archivos; globs con '*'.
MOVES = [
    ("t1_confection/Executables",                       "outputs/Executables"),
    ("t1_confection/A2_Structure_Lists.xlsx",           "outputs/A2_Structure_Lists.xlsx"),
    ("t1_confection/RELAC_TX_*.csv",                    "outputs/"),
    ("t1_confection/cplex.log",                         "outputs/logs/cplex.log"),
    ("t1_confection/clone1.log",                        "outputs/logs/clone1.log"),
    ("t1_confection/clone2.log",                        "outputs/logs/clone2.log"),
    ("t1_confection/gurobi.log",                        "outputs/logs/gurobi.log"),
    ("t1_confection/templates",                         "outputs/templates"),
    ("t1_confection/A1_Outputs",                        "inputs/A1_Outputs"),          # restos (backups) si git mv no los llevó
    ("t1_confection/Figures",                           "outputs/Figures"),
    ("fix_dispatch/cache",                              "outputs/fix_dispatch/cache"),
    ("fix_dispatch/outputs_BACKUP",                     "outputs/fix_dispatch/outputs_BACKUP"),
    ("fix_dispatch/solved_FLOORED",                     "outputs/fix_dispatch/solved_FLOORED"),
    ("fix_dispatch/report_lock_planned_capacity_template.html", "outputs/fix_dispatch/report_lock_planned_capacity_template.html"),
    ("RELAC_Tx_v15_run/veg_pipeline_proof.png",         "outputs/tx_chain/veg_pipeline_proof.png"),
    ("RELAC_Tx_v15_run/veg_preflight.png",              "outputs/tx_chain/veg_preflight.png"),
    ("RELAC_Tx_v15_run/templates",                      "outputs/tx_chain/templates"),
]
OLD_DIRS = ["t1_confection", "fix_dispatch", "RELAC_Tx_v15_run", "veg_tx_abs_test", "concatenate_files"]


def _merge_dir(src: Path, dst: Path, apply: bool) -> None:
    """Mueve el contenido de src dentro de dst (dst puede existir por el git mv previo)."""
    for item in sorted(src.iterdir()):
        target = dst / item.name
        if target.exists():
            if item.is_dir() and target.is_dir():
                _merge_dir(item, target, apply)
                continue
            print(f"  [skip] ya existe: {target}")
            continue
        print(f"  {item}  ->  {target}")
        if apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(item), str(target))
    if apply and not any(src.iterdir()):
        src.rmdir()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="mover de verdad (por defecto solo muestra)")
    args = ap.parse_args()
    print(f"Raíz: {ROOT}   modo: {'APPLY' if args.apply else 'DRY-RUN'}\n")
    for src_rel, dst_rel in MOVES:
        srcs = sorted(ROOT.glob(src_rel)) if "*" in src_rel else [ROOT / src_rel]
        for src in srcs:
            if not src.exists():
                continue
            dst = ROOT / dst_rel
            if dst_rel.endswith("/"):
                dst = dst / src.name
            if src.is_dir() and dst.exists():
                print(f"[merge] {src} -> {dst}")
                _merge_dir(src, dst, args.apply)
            elif dst.exists():
                print(f"[skip] ya existe: {dst}")
            else:
                print(f"[move] {src} -> {dst}")
                if args.apply:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(dst))
    print("\n=== Restos en carpetas viejas (revisar y borrar a mano si procede) ===")
    for d in OLD_DIRS:
        p = ROOT / d
        if p.exists():
            rest = [x for x in p.rglob("*") if x.is_file() and "__pycache__" not in x.parts]
            print(f"{d}/: {len(rest)} archivo(s)")
            for x in rest[:20]:
                print("   ", x.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Dry-run y revisar la lista**

```bash
python scripts/tools/migrate_layout_untracked.py
```
Esperado: lista `[move]`/`[merge]` con `Executables` (10 carpetas), los 7 `RELAC_TX_StorageDelay_*.csv`, `A2_Structure_Lists.xlsx`, 3 logs, `fix_dispatch/cache`, `outputs_BACKUP`, `report_lock...html`, 2 png, `RELAC_Tx_v15_run/templates`. Sin `[skip]` inesperados.

- [ ] **Step 3: Aplicar**

```bash
python scripts/tools/migrate_layout_untracked.py --apply
python scripts/tools/migrate_layout_untracked.py          # segunda pasada: no debe quedar nada que mover
ls outputs/Executables | wc -l                             # 10
```
Esperado: restos en carpetas viejas = solo `__pycache__` (borrar: `rm -rf t1_confection/__pycache__ fix_dispatch/__pycache__`) y luego `rmdir` de las carpetas vacías `t1_confection fix_dispatch RELAC_Tx_v15_run veg_tx_abs_test concatenate_files` (`find . -maxdepth 1 -type d -empty`).

- [ ] **Step 4: Commit**

```bash
git add scripts/tools/migrate_layout_untracked.py
git commit -q -m "tools: migrate_layout_untracked.py (mueve artefactos no versionados al layout nuevo)"
```

---

### Task 4: Paquete `scripts/common` con `relac_paths.py` y su test

**Files:**
- Create: `scripts/common/__init__.py` (vacío)
- Create: `scripts/common/relac_paths.py`
- Create: `scripts/tests/test_relac_paths.py`
- Modify: `scripts/common/Z_AUX_config_loader.py:12-13`

**Interfaces:**
- Produces (usadas por todas las tasks siguientes): `P.REPO_ROOT, P.INPUTS, P.SCRIPTS, P.OUTPUTS, P.CONFIG, P.CONFIG_A, P.CONFIG_AB, P.CONFIG_COUNTRY_CODES, P.CONFIG_REGION_CONSOLIDATION, P.CONFIG_TECH_EQUIVALENCES, P.A3_CONFIG, P.MODEL, P.OSEMOSYS_MODEL, P.OG_CSVS_INPUTS, P.A1_OUTPUTS, P.A2_EXTRA_INPUTS, P.MISCELLANEOUS, P.DATA, P.REFERENCE, P.OLD_INPUTS, P.BASE_SCENARIO_REF, P.MATRIZ_BALANCE, P.TX_CHAIN_IN, P.CANDIDATE_FLOORS, P.VEG_TX_NEEDS_CSV, P.A2_OUTPUT_PARAMS, P.A2_STRUCTURE_LISTS, P.A2_OTOOLE, P.EXECUTABLES, P.OUTPUT_MODEL, P.FIGURES, P.LOGS, P.FIX_DISPATCH_OUT, P.TX_CHAIN_OUT, P.EXPERIMENTAL_OUT, P.TEMPLATES_OUT, P.PIPELINE, P.FIX_DISPATCH, P.TX_CHAIN, P.TOOLS` (todas `pathlib.Path`), `P.scenario_dir(str) -> Path`, `P.executables_dir(str) -> Path`, `P.ensure_output_dirs() -> None`.

- [ ] **Step 1: Escribir el test (falla porque el módulo no existe)**

```python
# scripts/tests/test_relac_paths.py
"""Cada constante de relac_paths apunta a algo que existe en el repo (tras el git mv)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> scripts/
from common import relac_paths as P

MUST_EXIST = [
    P.REPO_ROOT / "dvc.yaml", P.INPUTS, P.SCRIPTS, P.OUTPUTS,
    P.CONFIG_A, P.CONFIG_AB, P.CONFIG_COUNTRY_CODES, P.CONFIG_REGION_CONSOLIDATION,
    P.CONFIG_TECH_EQUIVALENCES, P.A3_CONFIG / "lid_rule.yaml", P.A3_CONFIG / "TECH_TYPES.csv",
    P.OSEMOSYS_MODEL, P.OG_CSVS_INPUTS / "EMISSION.csv", P.scenario_dir("BAU") / "A-O_Parametrization.xlsx",
    P.A2_EXTRA_INPUTS / "A-Xtra_Storage.xlsx", P.MISCELLANEOUS / "conversion_format.yaml",
    P.MISCELLANEOUS / "templates", P.DATA / "firm_capacity_fallbacks_by_cr.xlsx",
    P.DATA / "Tech_Country_Matrix.xlsx", P.OLD_INPUTS, P.BASE_SCENARIO_REF / "Base", P.MATRIZ_BALANCE,
    P.CANDIDATE_FLOORS, P.VEG_TX_NEEDS_CSV, P.A2_OUTPUT_PARAMS / "BAU", P.A2_OTOOLE,
    P.OUTPUT_MODEL / "osemosys_fast_preprocessed_storage_delay.txt",
    P.PIPELINE / "B2_Executing_OG_Model.py", P.FIX_DISPATCH / "write_floors.py",
    P.TX_CHAIN / "veg_tx_constraints_v14.py", P.TOOLS / "concatenate_relac.py",
]

def main() -> int:
    missing = [p for p in MUST_EXIST if not p.exists()]
    for p in missing:
        print("FALTA:", p)
    assert P.executables_dir("BAU") == P.OUTPUTS / "Executables" / "BAU_0"
    assert P.REPO_ROOT.name == "relac_tx" or (P.REPO_ROOT / "dvc.yaml").is_file()
    print("OK relac_paths" if not missing else f"{len(missing)} rutas faltan")
    return 1 if missing else 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Ejecutar y ver que falla**

```bash
python scripts/tests/test_relac_paths.py
```
Esperado: `ModuleNotFoundError: No module named 'common'`.

- [ ] **Step 3: Crear el paquete y `relac_paths.py`** (contenido exacto del spec §5.1)

```bash
: > scripts/common/__init__.py
```

```python
# scripts/common/relac_paths.py
"""Layout del repositorio relac_tx. TODO script obtiene sus rutas de aquí.

Convención: inputs/ = mantenido a mano (el pipeline lo lee); outputs/ = regenerado al correr;
scripts/ = código. Ver docs/superpowers/specs/2026-09-07-restructure-inputs-scripts-outputs-design.md
"""
from pathlib import Path


def _find_repo_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / "dvc.yaml").is_file():
            return p
    raise RuntimeError(f"No se encontró dvc.yaml subiendo desde {start}")


REPO_ROOT = _find_repo_root(Path(__file__).resolve().parent)
INPUTS = REPO_ROOT / "inputs"
SCRIPTS = REPO_ROOT / "scripts"
OUTPUTS = REPO_ROOT / "outputs"

# ---- inputs ----
CONFIG = INPUTS / "config"
CONFIG_A = CONFIG / "Config_MOMF_T1_A.yaml"
CONFIG_AB = CONFIG / "Config_MOMF_T1_AB.yaml"
CONFIG_COUNTRY_CODES = CONFIG / "Config_country_codes.yaml"
CONFIG_REGION_CONSOLIDATION = CONFIG / "Config_region_consolidation.yaml"
CONFIG_TECH_EQUIVALENCES = CONFIG / "Config_tech_equivalences.yaml"
A3_CONFIG = CONFIG / "A3_process"                    # lid_rule.yaml, TECH_TYPES.csv
MODEL = INPUTS / "model"
OSEMOSYS_MODEL = MODEL / "osemosys_fast_preprocessed.txt"
OG_CSVS_INPUTS = INPUTS / "OG_csvs_inputs"
A1_OUTPUTS = INPUTS / "A1_Outputs"
A2_EXTRA_INPUTS = INPUTS / "A2_Extra_Inputs"
MISCELLANEOUS = INPUTS / "Miscellaneous"
DATA = INPUTS / "data"
REFERENCE = INPUTS / "reference"
OLD_INPUTS = REFERENCE / "Old_Inputs"
BASE_SCENARIO_REF = REFERENCE / "NO BORRAR A1_Outputs - Escenario Base"
MATRIZ_BALANCE = REFERENCE / "Matriz Balance energético"
TX_CHAIN_IN = INPUTS / "tx_chain"
CANDIDATE_FLOORS = TX_CHAIN_IN / "fix_dispatch" / "candidate_floors.csv"
VEG_TX_NEEDS_CSV = TX_CHAIN_IN / "outputs_BSR" / "NewCapacity.csv"

# ---- outputs ----
A2_OUTPUT_PARAMS = OUTPUTS / "A2_Output_Params"
A2_STRUCTURE_LISTS = OUTPUTS / "A2_Structure_Lists.xlsx"
A2_OTOOLE = OUTPUTS / "A2_Outputs_Params_otoole"
EXECUTABLES = OUTPUTS / "Executables"
OUTPUT_MODEL = OUTPUTS / "model"
FIGURES = OUTPUTS / "Figures"
LOGS = OUTPUTS / "logs"
FIX_DISPATCH_OUT = OUTPUTS / "fix_dispatch"
TX_CHAIN_OUT = OUTPUTS / "tx_chain"
EXPERIMENTAL_OUT = OUTPUTS / "experimental"
TEMPLATES_OUT = OUTPUTS / "templates"

# ---- scripts ----
PIPELINE = SCRIPTS / "pipeline"
FIX_DISPATCH = SCRIPTS / "fix_dispatch"
TX_CHAIN = SCRIPTS / "tx_chain"
TOOLS = SCRIPTS / "tools"


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

- [ ] **Step 4: Adaptar `Z_AUX_config_loader.py`** (líneas 12-13)

Antes:
```python
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "Config_country_codes.yaml"
```
Después:
```python
from . import relac_paths as P
CONFIG_PATH = P.CONFIG_COUNTRY_CODES
```
(`_xlsx_validation_core.py` no tiene rutas: sin cambios.)

- [ ] **Step 5: Ejecutar el test**

```bash
python scripts/tests/test_relac_paths.py
python -c "import sys; sys.path.insert(0,'scripts'); from common.Z_AUX_config_loader import get_countries; print(len(get_countries()))"
```
Esperado: `OK relac_paths`; el segundo imprime el número de países (19).

- [ ] **Step 6: Commit**

```bash
git add scripts/common scripts/tests/test_relac_paths.py
git commit -q -m "feat(common): relac_paths.py (layout central) + paquete common"
```

---

### Task 5: B1 (`B1_Run_Compiler.py`, `B1_Compiler.py`)

**Files:**
- Modify: `scripts/pipeline/B1_Run_Compiler.py:20-26` (imports), `:157-164` (`run_compiler`), `:167-175` (`main` rutas)
- Modify: `scripts/pipeline/B1_Compiler.py:23`, `:34`, `:72-73`, `:350`, `:542-544`, `:552`, `:1200`, `:1591-1616`

- [ ] **Step 1: `B1_Run_Compiler.py` — bootstrap y rutas**

Tras `from typing import List, Optional` añadir:
```python
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> scripts/
from common import relac_paths as P
```
En `run_compiler`, cambiar `result = subprocess.run([sys.executable, str(compiler)], cwd=str(script_dir))` por:
```python
    result = subprocess.run([sys.executable, str(compiler)], cwd=str(P.REPO_ROOT))
```
En `main`, sustituir:
```python
    yaml_file = script_dir / "Config_MOMF_T1_A.yaml"
    compiler_script = script_dir / "B1_Compiler.py"
    A1_Outputs_script = script_dir / "A1_Outputs"
```
por:
```python
    P.ensure_output_dirs()
    yaml_file = P.CONFIG_A
    compiler_script = script_dir / "B1_Compiler.py"
    A1_Outputs_script = P.A1_OUTPUTS
```

- [ ] **Step 2: `B1_Compiler.py` — bootstrap, YAML, prefijo A1**

Tras `import os` (línea 18) añadir:
```python
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> scripts/
from common import relac_paths as P
```
(`sys` ya está importado más arriba; comprobar con `grep -n "^import sys" scripts/pipeline/B1_Compiler.py`, si no, añadirlo.)

Línea 23: `with open('Config_MOMF_T1_A.yaml', 'r') as file:` → `with open(P.CONFIG_A, 'r') as file:`

Justo después de `params = yaml.safe_load(file)` añadir:
```python
# Prefijo de carpeta de escenario ("A1_Outputs"), independiente del directorio configurado.
A1_PREFIX = os.path.basename(params['A1_outputs'].rstrip('/\\'))
```

En las 11 líneas 34, 72, 73, 350, 542, 544, 552, 1591, 1598, 1607, 1616 sustituir el **segundo** uso `params['A1_outputs'] + '_' +` por `A1_PREFIX + '_' +`. Ejemplo, línea 72:

Antes:
```python
AR_Model_Base_Year = pd.ExcelFile(os.path.join(params['A1_outputs'], params['A1_outputs'] + '_' + params['xtra_scen']['Main_Scenario'] + params['Print_Base_Year']))
```
Después:
```python
AR_Model_Base_Year = pd.ExcelFile(os.path.join(params['A1_outputs'], A1_PREFIX + '_' + params['xtra_scen']['Main_Scenario'] + params['Print_Base_Year']))
```
Hacerlo con sed y verificar:
```bash
sed -i "s/params\['A1_outputs'\] + '_' +/A1_PREFIX + '_' +/g" scripts/pipeline/B1_Compiler.py
grep -c "A1_PREFIX + '_'" scripts/pipeline/B1_Compiler.py     # 14 (11 activas + 3 comentadas)
grep -n "params\['A1_outputs'\] + '_'" scripts/pipeline/B1_Compiler.py   # vacío
```

Línea 1200: `Emissions_OG = pd.read_csv(os.path.join('OG_csvs_inputs', 'EMISSION.csv'))` → `Emissions_OG = pd.read_csv(P.OG_CSVS_INPUTS / 'EMISSION.csv')`

- [ ] **Step 3: Actualizar temporalmente las claves YAML de B1** (Task 14 lo hace definitivo; aquí para poder probar)

En `inputs/config/Config_MOMF_T1_A.yaml` líneas 1-6 y 79:
```yaml
A1_inputs: inputs/A1_Inputs
A1_outputs: inputs/A1_Outputs
A2_extra_inputs: inputs/A2_Extra_Inputs
A2_output: outputs/A2_Output_Params/
A2_output_main_scen: outputs/A2_Output_Params/
A2_output_NDP: outputs/A2_Output_Params/NDC/
```
```yaml
Print_A2_Struct_List: outputs/A2_Structure_Lists.xlsx
```
Ojo: `B1_Compiler` concatena `params['A2_extra_inputs'] + params['Xtra_Proj']` y `Xtra_*` empiezan por `/`, así que `inputs/A2_Extra_Inputs` + `/A-Xtra_Projections.xlsx` funciona igual que hoy.

- [ ] **Step 4: Verificar sin correr B1**

```bash
python -m py_compile scripts/pipeline/B1_Run_Compiler.py scripts/pipeline/B1_Compiler.py && echo OK
python - <<'EOF'
import sys, os, yaml; sys.path.insert(0,'scripts')
from common import relac_paths as P
params = yaml.safe_load(open(P.CONFIG_A))
A1_PREFIX = os.path.basename(params['A1_outputs'].rstrip('/\\'))
p = os.path.join(params['A1_outputs'], A1_PREFIX + '_BAU' + params['Print_Paramet'])
print(p, os.path.exists(os.path.join(P.REPO_ROOT, p)))
print(os.path.exists(os.path.join(P.REPO_ROOT, params['A2_extra_inputs'] + params['Xtra_Storage'])))
EOF
```
Esperado: `inputs/A1_Outputs/A1_Outputs_BAU/A-O_Parametrization.xlsx True` y `True`.

- [ ] **Step 5: Commit**

```bash
git add scripts/pipeline/B1_Run_Compiler.py scripts/pipeline/B1_Compiler.py inputs/config/Config_MOMF_T1_A.yaml
git commit -q -m "refactor(B1): rutas via relac_paths; cwd=raiz del repo; prefijo A1 desacoplado del directorio"
```

---

### Task 6: B2 (`B2_Executing_OG_Model.py`)

**Files:**
- Modify: `scripts/pipeline/B2_Executing_OG_Model.py` (cabecera; funciones `solve_universe`, `run_otoole_conversion`, patchers 275-536, `run_activity_upper_limit_patcher` 613-637, `run_preflight_separation_gate`/`run_dispatch_floors_patcher`/`run_veg_tx_stage`/`run_scenario_transforms` 677-745, 787, 839-858, 871-873, `get_config_main_path` 913-915, `main_executer` 919-1030, `export_root_datafile` 1123-1145, `generate_combined_*` 1207-1335, `__main__` 1383-1440, salidas finales 1496-1628)
- Modify: `inputs/config/Config_MOMF_T1_AB.yaml` (claves de rutas; definitivo en Task 14, aquí lo necesario para probar)

**Interfaces:**
- Consumes: `P.*` de Task 4.
- Produces: variables de módulo `SCRIPT_DIR` (Path, carpeta de B2) y `ROOT` (str, raíz del repo).

- [ ] **Step 1: Cabecera — bootstrap y `SCRIPT_DIR`/`ROOT`**

Tras `import numpy as np` (línea 21):
```python
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> scripts/
from common import relac_paths as P
SCRIPT_DIR = Path(__file__).resolve().parent   # scripts/pipeline (patchers hermanos)
ROOT = str(P.REPO_ROOT)                        # ancla de TODAS las rutas del YAML
```

- [ ] **Step 2: Sustituir el ancla `HERE`/`here` de rutas de datos por `ROOT`**

Todas las apariciones de `os.path.join(HERE, params[` y `os.path.join(here, params` pasan a `os.path.join(ROOT, params[`. Y las que usan `params['executables']` a pelo se anclan también:

```bash
F=scripts/pipeline/B2_Executing_OG_Model.py
sed -i "s/os\.path\.join(HERE, params\[/os.path.join(ROOT, params[/g; s/os\.path\.join(here, params\[/os.path.join(ROOT, params[/g" $F
sed -i "s/os\.path\.join(params\['executables'\]/os.path.join(ROOT, params['executables']/g" $F
sed -i "s/os\.path\.join(HERE, base_input_path/os.path.join(ROOT, base_input_path/g; s/os\.path\.join(HERE, base_output_path/os.path.join(ROOT, base_output_path/g; s/os\.path\.join(HERE, folder_scenario/os.path.join(ROOT, folder_scenario/g; s/os\.path\.join(HERE,params/os.path.join(ROOT,params/g" $F
grep -nE "join\((HERE|here)\b" $F     # revisar lo que quede a mano (ver Step 3)
```

- [ ] **Step 3: Casos puntuales (a mano)**

1. `run_otoole_conversion` (l.186-188): ya cubiertos por el sed (`ROOT`).
2. `run_storage_delay_patcher` (l.324, 332): `script_path = os.path.join(here, 'patch_storage_delay.py')` → `os.path.join(SCRIPT_DIR, 'patch_storage_delay.py')`; en el helper `return str(path if path.is_absolute() else Path(here) / path)` → `Path(ROOT) / path`.
3. `run_reserve_margin_xlsx_patcher` (l.522, 529): `script_path = os.path.join(here, 'patch_reserve_margin_repair_careful_xlsx.py')` → `SCRIPT_DIR`; `workbook = os.path.join(here, workbook)` → `os.path.join(P.DATA, workbook)`.
4. `run_activity_upper_limit_patcher` (l.613-637): `here = os.path.dirname(...)` se conserva para `sys.path.insert(0, here)` (importa el patcher hermano). `xlsx_path = os.path.join(here, 'A1_Outputs', f'A1_Outputs_{scenario_name}', 'A-O_Parametrization.xlsx')` → `xlsx_path = str(P.scenario_dir(scenario_name) / 'A-O_Parametrization.xlsx')`; `a2_root = os.path.join(here, params.get('A2_output_otoole', ...), scenario_name)` → `os.path.join(ROOT, params.get('A2_output_otoole', 'outputs/A2_Outputs_Params_otoole'), scenario_name)`.
5. `run_preprocessing_script` (l.871): `script_path = os.path.join(params['Miscellaneous'], params['preprocess_data'])` → `script_path = os.path.join(SCRIPT_DIR, params['preprocess_data'])`.
6. `get_config_main_path` (l.913-915): cuerpo → `return os.path.join(ROOT, base_folder)`.
7. `main_executer` (l.938, 944 y equivalentes cbc/cplex/gurobi): `params["osemosys_model"]` dentro de los f-string de `glpsol -m ...` → `os.path.join(ROOT, params["osemosys_model"])`. Hacerlo definiendo al inicio de `main_executer`: `model_file = os.path.join(ROOT, params['osemosys_model'])` y usando `{model_file}` en los comandos (`grep -n 'osemosys_model' $F` para no dejar ninguno).
8. `export_root_datafile` (l.1135-1145): `repo_root = Path(here).parent` → eliminar; `source_path = Path(here) / params['executables'] / ...` → `Path(ROOT) / params['executables'] / ...`; `target_path = repo_root / export_name` → `target_path = P.OUTPUTS / export_name`.
9. Salidas finales (l.1265, 1279, 1335, 1595, 1628): `os.path.join(HERE, params['prefix_final_files'] + ...)` → `os.path.join(P.OUTPUTS, params['prefix_final_files'] + ...)` (el sed del Step 2 los habrá convertido a `ROOT`; cambiarlos a `P.OUTPUTS` para que caigan en `outputs/`).
10. `__main__` (l.1400-1405 y 1434): sustituir el bloque `if Path.cwd() != HERE: os.chdir(HERE)` por:
    ```python
    P.ensure_output_dirs()
    os.chdir(P.LOGS)          # cplex.log / clone*.log / gurobi.log caen en outputs/logs/
    print(f"[INFO] Working dir -> {P.LOGS}")
    ```
    `with open('Config_MOMF_T1_AB.yaml', 'r') as f:` → `with open(P.CONFIG_AB, 'r') as f:`; `with open('Config_MOMF_T1_A.yaml', 'r') as f:` → `with open(P.CONFIG_A, 'r') as f:`.
11. Los `HERE` que siguen pasándose como argumento (`solve_universe(params, HERE, ...)`, `run_dispatch_floors_patcher(params, s, HERE)`, `run_veg_tx_stage(params, HERE, ...)`, `run_scenario_transforms(params, HERE)`, `export_root_datafile(HERE, ...)`, `main_executer(params, s, HERE)`) siguen funcionando porque dentro se usa `os.path.join(ROOT, ...)` tras el sed; dejar `HERE` tal cual (es solo un parámetro ya no usado como ancla). Verificar con `grep -n "HERE" $F` que ningún uso restante construya una ruta de datos.

- [ ] **Step 4: Actualizar las claves YAML de B2 necesarias para probar** (definitivo en Task 14)

En `inputs/config/Config_MOMF_T1_AB.yaml`:
```yaml
A2_output: 'outputs/A2_Output_Params'
A2_output_otoole: 'outputs/A2_Outputs_Params_otoole'
Miscellaneous: 'inputs/Miscellaneous'
executables: 'outputs/Executables'
concatenate_folder: 'scripts/tools'
osemosys_model: 'inputs/model/osemosys_fast_preprocessed.txt'
storage_delay_model_output: "outputs/model/osemosys_fast_preprocessed_storage_delay.txt"
dispatch_floors_script: "scripts/fix_dispatch/write_floors.py"      # relativo a la raiz del repo
preflight_separation_script: "scripts/fix_dispatch/preflight_separation.py"
veg_tx_script: "scripts/tx_chain/veg_tx_constraints_v14.py"
veg_tx_needs_csv: "inputs/tx_chain/outputs_BSR/NewCapacity.csv"
```
y en `scenario_transforms`: `script: "scripts/tx_chain/cost_sensitivity_v11.py"`, `script: "scripts/tx_chain/nli_sr_recompute_v1.py"`.

- [ ] **Step 5: Verificar estáticamente**

```bash
F=scripts/pipeline/B2_Executing_OG_Model.py
python -m py_compile $F && echo OK
grep -nE "join\((HERE|here)\b|open\('Config|'A1_Outputs'|Path\(here\)|repo_root" $F   # vacío
python - <<'EOF'
import sys, os, yaml; sys.path.insert(0,'scripts'); sys.path.insert(0,'scripts/pipeline')
from common import relac_paths as P
p = yaml.safe_load(open(P.CONFIG_AB))
for k in ('dispatch_floors_script','preflight_separation_script','veg_tx_script','veg_tx_needs_csv','osemosys_model','Miscellaneous','A2_output','executables','concatenate_folder'):
    print(k, os.path.exists(os.path.join(P.REPO_ROOT, p[k])))
for t in p['scenario_transforms']: print(t['name'], os.path.exists(os.path.join(P.REPO_ROOT, t['script'])))
import B2_Executing_OG_Model as b2   # importa sin ejecutar main
print(b2.ROOT, b2.SCRIPT_DIR)
EOF
python scripts/tests/test_b2_chain_helper.py 2>/dev/null || (cd scripts/pipeline && python ../tests/test_b2_chain_helper.py)
```
Esperado: todos `True`; `ROOT` = raíz del repo; `OK: chain helper` (el test se arregla del todo en Task 13).

- [ ] **Step 6: Commit**

```bash
git add scripts/pipeline/B2_Executing_OG_Model.py inputs/config/Config_MOMF_T1_AB.yaml
git commit -q -m "refactor(B2): SCRIPT_DIR/ROOT separados, rutas YAML ancladas a la raiz, cwd=outputs/logs"
```

---

### Task 7: Scripts de pipeline A0/A1/A2/A3_migrate/D1–D5/B1b/sync_historical/patch_activity_upper_limit

**Files:**
- Modify: `scripts/pipeline/{A0_generate_tech_country_matrix, A1_Pre_processing_OG_csvs, A2_AddTx, A3_migrate_old_inputs_CLG, D1_generate_editor_template, D2_update_secondary_techs, D3_load_lac_max_capacity_caps, D4_load_dsptrn_max_cap_inv, D5_load_fuel_var_costs, B1b_Pre_solver_validation, sync_historical_from_bau, patch_activity_upper_limit}.py`

Para cada archivo: (a) bootstrap k=1 justo después de los imports estándar; (b) imports `from Z_AUX_config_loader import ...` → `from common.Z_AUX_config_loader import ...` y `from _xlsx_validation_core import` → `from common._xlsx_validation_core import`; (c) rutas según la tabla; (d) docstring `python t1_confection/X.py` → `python scripts/pipeline/X.py`.

- [ ] **Step 1: A0** — l.26 `SCRIPT_DIR = ...` conservar; l.89 `SCRIPT_DIR / "Config_country_codes.yaml"` → `P.CONFIG_COUNTRY_CODES`; l.145 `SCRIPT_DIR / "Tech_Country_Matrix.xlsx"` → `P.DATA / "Tech_Country_Matrix.xlsx"`.

- [ ] **Step 2: A1** — l.36-43:
```python
SCRIPT_DIR = Path(__file__).resolve().parent
INPUT_FOLDER = P.OG_CSVS_INPUTS
OUTPUT_FOLDER = P.A1_OUTPUTS
MISCELLANEOUS_FOLDER = P.MISCELLANEOUS
A2_EXTRA_INPUTS_FOLDER = P.A2_EXTRA_INPUTS
REGION_CONSOLIDATION_CONFIG = P.CONFIG_REGION_CONSOLIDATION
TECH_COUNTRY_MATRIX_FILE = P.DATA / "Tech_Country_Matrix.xlsx"
OLADE_GENERATION_FILE = P.DATA / "OLADE - Capacidad instalada por fuente - Anual.xlsx"
```
Luego `grep -n "SCRIPT_DIR /" scripts/pipeline/A1_Pre_processing_OG_csvs.py` y anclar cualquier otro uso a `P`.

- [ ] **Step 3: A2** — l.636 `OUTPUT_FOLDER = script_dir / "A1_Outputs"` → `P.A1_OUTPUTS`; l.642-646 defaults: `"yaml": str(P.CONFIG_COUNTRY_CODES)`, `"base": str(P.scenario_dir(scen) / "A-O_AR_Model_Base_Year.xlsx")`, ídem `proj/param/demand`.

- [ ] **Step 4: A3_migrate** — localizar dónde se fija `self.base_path` (`grep -n "base_path =" ...`) y sustituir por rutas explícitas: l.211 `self.old_inputs_path = P.OLD_INPUTS`; l.225 `TechCountryMatrix(P.DATA / "Tech_Country_Matrix.xlsx")`; l.226 `TechEquivalences(P.CONFIG_TECH_EQUIVALENCES)`; l.229 `yaml_path = P.CONFIG_COUNTRY_CODES`; l.965/1050/1113 `self.base_path / "A1_Outputs" / ...` → `P.A1_OUTPUTS / ...`; cualquier `self.base_path / "A2_Extra_Inputs"` → `P.A2_EXTRA_INPUTS`.

- [ ] **Step 5: D1** — l.31 `Path(__file__).parent / "Config_MOMF_T1_AB.yaml"` → `P.CONFIG_AB`; l.52 y 215 `Path(__file__).parent / "A1_Outputs"` → `P.A1_OUTPUTS`; `grep -nE "Path\(__file__\)\.parent / \"(Secondary_Techs_Editor|OLADE|Shares)" ` → `P.DATA / "..."`.

- [ ] **Step 6: D2** — l.79 → `P.CONFIG_AB`; l.2697 `Path(__file__).parent / 'Miscellaneous' / 'conversion_format.yaml'` → `P.MISCELLANEOUS / 'conversion_format.yaml'`; l.4768 `log_path = self.base_path / f"secondary_techs_update_log_..."` → `log_path = P.LOGS / f"secondary_techs_update_log_..."` (añadir `P.LOGS.mkdir(parents=True, exist_ok=True)` antes); l.4789-4796:
```python
        editor_path = P.DATA / "Secondary_Techs_Editor.xlsx"
        base_path = P.A1_OUTPUTS
        olade_file_path = P.DATA / "OLADE - Capacidad instalada por fuente - Anual.xlsx"
        shares_file_path = P.DATA / "Shares_PET_OIL_Split.xlsx"
        generation_file_path = P.DATA / "OLADE - Generación eléctrica por fuente - Anual.xlsx"
        shares_total_file_path = P.DATA / "Shares_Power_Generation_Technologies.xlsx"
        trade_balance_file_path = P.MATRIZ_BALANCE / "flujos_energia_estimados_optimizacion.xlsx"
```

- [ ] **Step 7: D3, D4, D5, sync_historical** — D3 l.20 `PARAM_PATH = P.scenario_dir('BAU') / 'A-O_Parametrization.xlsx'`; D4 l.73-74 `COMBINED_CSV = P.OUTPUTS / 'RELAC_TX_Combined_Inputs_Outputs.csv'`, `A1_OUTPUTS = P.A1_OUTPUTS`; D5 l.359 `default_base = P.A1_OUTPUTS`; sync_historical l.72 `A1_OUTPUTS = P.A1_OUTPUTS`.

- [ ] **Step 8: B1b** — l.39 `sys.path.insert(0, str(Path(__file__).parent))` → bootstrap k=1; l.40 import → `from common._xlsx_validation_core import (`; l.80 → `return P.scenario_dir(scenario) / "A-O_Parametrization.xlsx"`; l.85 → `cfg = P.CONFIG_A`; l.99 → `cfg = P.CONFIG_AB`; l.237 → `out_dir = P.executables_dir(scenario)`; l.497 → `a2_root = P.A2_OTOOLE / scenario`. La línea 25 (`from B1b_Pre_solver_validation import run as pre_solver_validate`) está en el docstring: solo texto.

- [ ] **Step 9: patch_activity_upper_limit** — l.24 `sys.path.insert(0, str(Path(__file__).parent))` → bootstrap k=1; l.29 → `from common._xlsx_validation_core import (`.

- [ ] **Step 10: Verificar**

```bash
for f in scripts/pipeline/{A0_generate_tech_country_matrix,A1_Pre_processing_OG_csvs,A2_AddTx,A3_migrate_old_inputs_CLG,D1_generate_editor_template,D2_update_secondary_techs,D3_load_lac_max_capacity_caps,D4_load_dsptrn_max_cap_inv,D5_load_fuel_var_costs,B1b_Pre_solver_validation,sync_historical_from_bau,patch_activity_upper_limit}.py; do python -m py_compile "$f" || echo "FALLA $f"; done
grep -nE "(SCRIPT_DIR|script_dir|HERE|Path\(__file__\)\.parent|base_path) / ['\"](A1_Outputs|OG_csvs_inputs|Miscellaneous|A2_Extra_Inputs|Config_|Tech_Country|Secondary_Techs|OLADE|Shares_|Old_Inputs|Executables|A2_Outputs|RELAC_TX)" scripts/pipeline/*.py    # vacío
grep -nE "^from (Z_AUX_config_loader|_xlsx_validation_core)" scripts/pipeline/*.py   # vacío
python scripts/pipeline/D4_load_dsptrn_max_cap_inv.py --dry-run | tail -3
python scripts/pipeline/sync_historical_from_bau.py --dry-run | tail -3
python scripts/pipeline/B1b_Pre_solver_validation.py --scenario BAU --report-only | tail -3
python scripts/pipeline/A2_AddTx.py --help | head -3
```
Esperado: compila todo; greps vacíos; los dry-run terminan sin `FileNotFoundError` (D4 dirá que falta `RELAC_TX_Combined_Inputs_Outputs.csv` si no existe en `outputs/`: es el comportamiento actual, no un error de rutas).

- [ ] **Step 11: Commit**

```bash
git add scripts/pipeline
git commit -q -m "refactor(pipeline A/D/B1b): rutas via relac_paths e imports common.*"
```

---

### Task 8: `A3_process.py` y `rules_scripts/`

**Files:**
- Modify: `scripts/pipeline/A3_process.py:86-105`
- Modify: `scripts/pipeline/A3_process/rules_scripts/add_max_cap_investment_lid_rule.py:1307-1326, 1509-1540`
- Modify: `scripts/pipeline/A3_process/rules_scripts/extend_lowerlimits_pwr.py` (si carga `lid_rule.yaml` junto al script)
- Modify: `scripts/pipeline/A3_process/rules_scripts/reset_lowerlimits_from_base.py:67-68`

- [ ] **Step 1: `A3_process.py`** — bootstrap k=1 tras `from pathlib import Path`; l.91-105:
```python
T1_CONFECTION = Path(__file__).resolve().parent          # scripts/pipeline (solo para localizar scripts hermanos)
A3_PROCESS_DIR = T1_CONFECTION / "A3_process"
RULES_SCRIPTS_DIR = A3_PROCESS_DIR / "rules_scripts"
A1_OUTPUTS_DIR = P.A1_OUTPUTS
SCENARIO_PREFIX = "A1_Outputs_"
...
B1B_VALIDATOR = T1_CONFECTION / "B1b_Pre_solver_validation.py"
SYNC_HIST_SCRIPT = T1_CONFECTION / "sync_historical_from_bau.py"
LID_RULE_YAML = P.A3_CONFIG / "lid_rule.yaml"
```
Comprobar con `grep -n "yaml\|--yaml" scripts/pipeline/A3_process.py` si A3 pasa `--yaml` a los rules scripts; si no lo hace, añadir `"--yaml", LID_RULE_YAML` al `cmd` de la l.432 (y al `ext_cmd` de l.449 si `extend_lowerlimits_pwr.py` acepta `--yaml`), para que los rules scripts no dependan de su default.

- [ ] **Step 2: `add_max_cap_investment_lid_rule.py`** — bootstrap **k=3**; l.1307 `yaml_path = Path(__file__).resolve().parent / YAML_FILE_NAME` → `yaml_path = P.A3_CONFIG / YAML_FILE_NAME`; l.1325-1326 `tech_types_path = script_dir.parent / TECH_TYPES_FILE` → `tech_types_path = P.A3_CONFIG / TECH_TYPES_FILE`; l.1511 `default=Path("A1_Outputs/A1_Outputs_BAU")` → `default=P.scenario_dir("BAU")`; l.1538 texto de ayuda `next to this script` → `in inputs/config/A3_process/`.

- [ ] **Step 3: `extend_lowerlimits_pwr.py`** — `grep -n "yaml\|Path(__file__)" scripts/pipeline/A3_process/rules_scripts/extend_lowerlimits_pwr.py`; si carga `lid_rule.yaml` relativo al script, bootstrap k=3 y `P.A3_CONFIG / "lid_rule.yaml"`; si solo recibe `--input-dir`, únicamente actualizar el docstring (`t1_confection/A1_Outputs/...` → `inputs/A1_Outputs/...`).

- [ ] **Step 4: `reset_lowerlimits_from_base.py`** — bootstrap k=3; l.67-68:
```python
DEFAULT_BASE_DIR = P.BASE_SCENARIO_REF / "Base"
```
(eliminar `T1_CONFECTION = Path(__file__).resolve().parents[2]`); docstring l.31 `<t1_confection>/NO BORRAR ...` → `inputs/reference/NO BORRAR ...`.

- [ ] **Step 5: Verificar**

```bash
python -m py_compile scripts/pipeline/A3_process.py scripts/pipeline/A3_process/rules_scripts/*.py && echo OK
python scripts/pipeline/A3_process.py --list
python scripts/pipeline/A3_process/rules_scripts/add_max_cap_investment_lid_rule.py --help | head -5
python scripts/pipeline/A3_process/rules_scripts/reset_lowerlimits_from_base.py --help | head -5
```
Esperado: `--list` muestra `BAU, INV, OPT, VGB`; los `--help` salen con 0.

- [ ] **Step 6: Commit**

```bash
git add scripts/pipeline/A3_process.py scripts/pipeline/A3_process
git commit -q -m "refactor(A3): rutas via relac_paths; lid_rule.yaml y TECH_TYPES.csv en inputs/config/A3_process"
```

---

### Task 9: `scripts/fix_dispatch/`

**Files:**
- Modify: `relac_io.py:30-35, 257-262`, `write_floors.py:42-47`, `preflight_separation.py:42-43`, `make_candidates.py:50-54`, `build_combined.py:50-62, 92, 206`, `floor_effect.py:41-42`, `fig_floor_effect.py:34-42`, `validate_constraints.py:35-37`, `veg_tx_constraints.py:52-63`, `feasibility.py`, `build_summary.py`

- [ ] **Step 1: `relac_io.py`** — bootstrap k=1 antes de los imports de terceros; l.30-35:
```python
EXECUTABLES = P.EXECUTABLES
OTOOLE = P.A2_OTOOLE
CACHE = P.FIX_DISPATCH_OUT / "cache"
CACHE.mkdir(parents=True, exist_ok=True)
```
l.258 `cands = sorted(REPO.glob("RELAC_TX*Combined_Inputs_Outputs*.csv"))` → `sorted(P.OUTPUTS.glob(...))`; l.260 mensaje `in repo root` → `in outputs/`. Actualizar el docstring de cabecera (`t1_confection/Executables/...` → `outputs/Executables/...`, `fix_dispatch/cache/` → `outputs/fix_dispatch/cache/`).

- [ ] **Step 2: `write_floors.py`, `preflight_separation.py`, `make_candidates.py`** — bootstrap k=1 (antes de `import relac_io as io`, que sigue funcionando por ser hermano);
  - write_floors l.46-47: `CANDIDATES_CSV = P.CANDIDATE_FLOORS`, `UPSTREAM_OUT = P.FIX_DISPATCH_OUT / "upstream_floor_rows.csv"`; añadir `UPSTREAM_OUT.parent.mkdir(parents=True, exist_ok=True)` antes de escribir (buscar `UPSTREAM_OUT.open\|open(UPSTREAM_OUT`); l.235 `relative_to(io.REPO)` → `relative_to(P.REPO_ROOT)`.
  - preflight l.43: `DEFAULT_CANDIDATES = P.CANDIDATE_FLOORS`.
  - make_candidates l.54: `OUT = P.CANDIDATE_FLOORS` (refresca el input, como hoy).

- [ ] **Step 3: `build_combined.py`** — l.50-62:
```python
HERE = Path(__file__).resolve().parent           # scripts/fix_dispatch
sys.path.insert(0, str(HERE.parents[0]))         # -> scripts/
from common import relac_paths as P
SOLVED = P.FIX_DISPATCH_OUT / "solved_FLOORED"
CONCAT_SCRIPT = P.TOOLS / "concatenate_relac.py"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(P.PIPELINE))
import relac_io as io                            # noqa: E402
import B2_Executing_OG_Model as b2               # noqa: E402
```
l.92 `T1 / "Miscellaneous" / "conversion_format.yaml"` → `P.MISCELLANEOUS / "conversion_format.yaml"`; l.206 `T1 / "Config_MOMF_T1_AB.yaml"` → `P.CONFIG_AB`. `grep -n "T1\b\|REPO\b" scripts/fix_dispatch/build_combined.py` → vacío.

- [ ] **Step 4: `fig_floor_effect.py`, `floor_effect.py`, `validate_constraints.py`, `veg_tx_constraints.py`, `feasibility.py`, `build_summary.py`** — bootstrap k=1;
  - fig_floor_effect l.37-42: `BASELINE_COMBINED = P.OUTPUTS / "RELAC_TX_StorageDelay_Combined_Inputs_Outputs_2026-06-19.csv"`, `FLOORED_COMBINED = P.FIX_DISPATCH_OUT / "solved_FLOORED" / "RELAC_TX_FLOORED_Combined_Inputs_Outputs.csv"`, `FLOORED_INPUTS = P.FIX_DISPATCH_OUT / "solved_FLOORED" / "RELAC_TX_FLOORED_Inputs.csv"`, `CANDIDATES_CSV = P.CANDIDATE_FLOORS`, `OUT_PNG = P.FIX_DISPATCH_OUT / "fig_floor_effect.png"`; eliminar `REPO = HERE.parent`.
  - floor_effect l.42: `DEFAULT_OUT = P.FIX_DISPATCH_OUT / "floor_effect_report.csv"`.
  - validate_constraints l.36-37: `REPORT_TXT = P.FIX_DISPATCH_OUT / "validation_report.txt"`, `FLAGS_CSV = P.FIX_DISPATCH_OUT / "validation_flags.csv"`.
  - veg_tx_constraints l.53 `EXE = P.EXECUTABLES`; l.63 `OUT_DIR = P.FIX_DISPATCH_OUT`.
  - feasibility, build_summary: `grep -nE "HERE /|REPO|T1" ` y anclar salidas a `P.FIX_DISPATCH_OUT`; si no tienen rutas, solo bootstrap si importan algo de `P` (si no, no tocar).

- [ ] **Step 5: Verificar**

```bash
for f in scripts/fix_dispatch/*.py; do python -m py_compile "$f" || echo "FALLA $f"; done
grep -nE "t1_confection|HERE\.parent|REPO\b|\bT1\b" scripts/fix_dispatch/*.py | grep -vE "^\S+:[0-9]+:\s*#|\"\"\"" # vacío (docstrings aparte)
python scripts/fix_dispatch/write_floors.py --dry-run --scenarios BAU | tail -5
python scripts/fix_dispatch/preflight_separation.py --help | head -3
python -c "import sys; sys.path.insert(0,'scripts/fix_dispatch'); import relac_io as io; print(io.EXECUTABLES, io.executable_txt('BAU').exists())"
```
Esperado: compila; `write_floors --dry-run` lee `candidate_floors.csv` y el `.txt` de `outputs/Executables/BAU_0/` (True en la última línea).

- [ ] **Step 6: Commit**

```bash
git add scripts/fix_dispatch
git commit -q -m "refactor(fix_dispatch): rutas via relac_paths; candidate_floors en inputs/tx_chain, cache/salidas en outputs/fix_dispatch"
```

---

### Task 10: `scripts/tx_chain/`

**Files:**
- Modify: `veg_tx_constraints_v14.py:66-100, 298`, `cost_sensitivity_v11.py:23-37`, `nli_sr_recompute_v1.py:29-38`

- [ ] **Step 1: `veg_tx_constraints_v14.py`** — tras `HERE = ...` (l.66) añadir bootstrap k=1; l.79-80:
```python
BASE_DIR_OVERRIDE = Path(_args.base_dir) if _args.base_dir else P.EXECUTABLES
```
l.100 `OUT_DIR = HERE` → `OUT_DIR = P.TX_CHAIN_OUT` y `OUT_DIR.mkdir(parents=True, exist_ok=True)`; l.298 `HERE / "outputs_BSR" / "NewCapacity.csv"` → `P.VEG_TX_NEEDS_CSV`. Revisar el comentario de l.67-70 (quitar la mención a `BASE_DIR_OVERRIDE` con ruta de otra máquina).

- [ ] **Step 2: `cost_sensitivity_v11.py`** — bootstrap k=1 tras l.23; l.37 `return HERE / FN(s)` → `return P.TX_CHAIN_OUT / FN(s)` (modo legado).

- [ ] **Step 3: `nli_sr_recompute_v1.py`** — bootstrap k=1 tras l.29; l.38 `(HERE / _NAME(s))` → `(P.TX_CHAIN_OUT / _NAME(s))`.

- [ ] **Step 4: Verificar**

```bash
for f in scripts/tx_chain/*.py; do python -m py_compile "$f" || echo "FALLA $f"; done
grep -n "kt0031\|t1_confection\|outputs_BSR" scripts/tx_chain/*.py | grep -v "^\S*:[0-9]*:\s*#"   # solo la constante P.VEG_TX_NEEDS_CSV, sin literales
python scripts/tx_chain/cost_sensitivity_v11.py --help | head -3
```

- [ ] **Step 5: Commit**

```bash
git add scripts/tx_chain
git commit -q -m "refactor(tx_chain): defaults via relac_paths (Executables, pin NewCapacity, salidas en outputs/tx_chain)"
```

---

### Task 11: `scripts/dashboard/`

**Files:**
- Modify: `dashboard_config.py:14-20`, `build_dashboard.py:30, 1586-1587, 1616, 3133-3134`, `_process_csv_for_dashboard.py:13-18`, `Z_AUX_generate_transmission_maps.py:60, 1232-1240`, `Z_AUX_generate_RES_diagram.py:34-36, 864-865`, `Z_AUX_generate_interactive_dashboards_aggregated.py:189, 1403`

- [ ] **Step 1: `dashboard_config.py`** — bootstrap k=1; l.14-20:
```python
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = str(P.OUTPUTS / "RELAC_TX_Combined_Inputs_Outputs.csv")
FIGURES_DIR = str(P.FIGURES)
OLADE_BALANCE_PATH = str(P.MATRIZ_BALANCE / "OLADE - Matriz de balance energético - Anual.xlsx")
```

- [ ] **Step 2: `build_dashboard.py`** — l.30 conservar (`sys.path` al propio dir para `dashboard_config`) y añadir el bootstrap; l.1587 `centerpoints_path = os.path.join(script_dir, "Miscellaneous", "centerpoints.csv")` → `str(P.MISCELLANEOUS / "centerpoints.csv")`; l.1616 `res.SCRIPT_DIR / "A1_Outputs" / "A1_Outputs_BAU" / ...` → `P.scenario_dir("BAU") / "A-O_AR_Model_Base_Year.xlsx"`; l.3133-3134 → `path = str(P.MISCELLANEOUS / "centerpoints.csv")`; `grep -n "CapacityAndDistances" ` → `str(P.DATA / "CapacityAndDistances.xlsx")`. Los módulos `tx`/`res` que importa (`Z_AUX_generate_transmission_maps`, `Z_AUX_generate_RES_diagram`) ahora son hermanos en `scripts/dashboard/`: comprobar con `grep -n "^import Z_AUX\|^from Z_AUX\|import_module" scripts/dashboard/build_dashboard.py` que se importan por nombre (sys.path del propio dir ya está).

- [ ] **Step 3: `_process_csv_for_dashboard.py`** — bootstrap k=1; l.16-18 `os.path.join(SCRIPT_DIR, 'RELAC_TX_Combined_Inputs_Outputs_ReLAC.csv')` etc. → `str(P.OUTPUTS / '...')`; `DASHBOARD_HTML` → `str(P.FIGURES / 'dashboard_capacity_cost.html')`.

- [ ] **Step 4: `Z_AUX_generate_transmission_maps.py`** — bootstrap k=1; l.1234 `csv_path = find_combined_csv(script_dir)` → `find_combined_csv(P.OUTPUTS)`; l.1239 `centerpoints_path = P.MISCELLANEOUS / 'centerpoints.csv'`; l.1240 `output_dir = P.FIGURES`.

- [ ] **Step 5: `Z_AUX_generate_RES_diagram.py`** — bootstrap k=1 antes de l.36; l.36 `open(P.CONFIG_COUNTRY_CODES, ...)`; l.864 `xlsx_path = P.scenario_dir('BAU') / 'A-O_AR_Model_Base_Year.xlsx'`; l.865 `output_path = P.FIGURES / 'RES_Diagram.html'`.

- [ ] **Step 6: `Z_AUX_generate_interactive_dashboards_aggregated.py`** — bootstrap k=1; l.1403 `glob.glob("*.csv")` → `glob.glob(str(P.OUTPUTS / "*.csv"))`; l.189 `output_file = f"Dashboard_..."` → `output_file = str(P.FIGURES / f"Dashboard_Interactive_Aggregated_{base_name}_{timestamp}.html")`.

- [ ] **Step 7: Verificar**

```bash
for f in scripts/dashboard/*.py; do python -m py_compile "$f" || echo "FALLA $f"; done
python -c "import sys; sys.path.insert(0,'scripts/dashboard'); import dashboard_config as c; print(c.CSV_PATH, c.FIGURES_DIR, c.OLADE_BALANCE_PATH); import os; print(os.path.exists(c.OLADE_BALANCE_PATH))"
grep -nE "(script_dir|SCRIPT_DIR|BASE_DIR)[ ,/)].*(Miscellaneous|A1_Outputs|Figures|RELAC_TX|Config_|Matriz)" scripts/dashboard/*.py   # vacío
```

- [ ] **Step 8: Commit**

```bash
git add scripts/dashboard
git commit -q -m "refactor(dashboard): rutas via relac_paths (CSV y Figures en outputs/, datos en inputs/)"
```

---

### Task 12: `scripts/tools/`

**Files:**
- Modify: `Z_validate_country_data.py:17, 22`, `Z_generate_country_template.py:32-34, 460-481, 573`, `Z_AUX_update_maxcap_inv_from_tool.py:51-54`, `Z_AUX_update_transmission_iar.py:77-78`, `Z_AUX_D1b_set_trn_limits_from_flows.py:482-485`, `Z_AUX_fix_excel_profiles.py:142-150`, `Z_AUX_united_regions.py:534-848`, `Z_AUX_apply_parametrization_review.py:58-69`, `AUX_Z_recalc_shares.py:18-30`, `Z_TEMP_add_pwrbck_to_scenarios.py:38-48`

- [ ] **Step 1: Edición por archivo** (bootstrap k=1 en todos salvo los tres sin rutas)
  - `Z_validate_country_data.py`: l.17 `from common.Z_AUX_config_loader import get_countries`; l.22 `INPUT_DIR = str(P.OG_CSVS_INPUTS)`.
  - `Z_generate_country_template.py`: l.33 `INPUT_DIR = str(P.OG_CSVS_INPUTS)`; l.34 `CONFIG_PATH = str(P.CONFIG_COUNTRY_CODES)`; `os.path.join(SCRIPT_DIR, "Miscellaneous", "centerpoints.csv")` → `str(P.MISCELLANEOUS / "centerpoints.csv")`; `os.path.join(SCRIPT_DIR, "templates", ...)` → `os.path.join(P.TEMPLATES_OUT, ...)`; l.471 texto de ayuda `cd t1_confection` → `cd inputs/OG_csvs_inputs` (revisar el contexto del `merge_into_inputs.py` generado, l.455-490: `INPUT_DIR` que escribe debe ser `P.OG_CSVS_INPUTS`).
  - `Z_AUX_update_maxcap_inv_from_tool.py`: l.52-54 `TOOL_XLSX = P.DATA / 'LAC_maxcap_tool.xlsx'`, `TOOL_COMPLEMENTARY_XLSX = P.DATA / 'LAC_maxcap_tool_complementary.xlsx'`, `A1_OUTPUTS = P.A1_OUTPUTS`.
  - `Z_AUX_update_transmission_iar.py`: l.78 `A1_BASE = P.A1_OUTPUTS`.
  - `Z_AUX_D1b_set_trn_limits_from_flows.py`: l.484 `flow_file = P.MATRIZ_BALANCE / "flujos_energia_estimados_optimizacion.xlsx"`; l.485 `editor_file = P.DATA / "Secondary_Techs_Editor.xlsx"`.
  - `Z_AUX_fix_excel_profiles.py`: l.150 `scenario_dir = base_dir / "A1_Outputs" / f"A1_Outputs_{scenario}"` → `P.scenario_dir(scenario)`.
  - `Z_AUX_united_regions.py`: usa rutas relativas al cwd (`A1_Outputs_{folder}`, `A2_Extra_Inputs/...`). Anclar: `os.path.join(P.A1_OUTPUTS, f"A1_Outputs_{folder}", ...)` y `P.A2_EXTRA_INPUTS / "A-Xtra_Storage.xlsx"` en l.534, 666, 683, 848 (y cualquier otro `os.path.join(f"A1_Outputs_` que muestre `grep -n "A1_Outputs_\|A2_Extra" `).
  - `Z_AUX_apply_parametrization_review.py`: l.58 → bootstrap; l.59 `from common._xlsx_validation_core import (`; l.69 `OUTPUTS_DIR = P.A1_OUTPUTS`; localizar dónde se abren `A-O_Parametrization_Review_PWR.xlsx`/`_Tx.xlsx` (`grep -n "Review_PWR\|Review_Tx" ` líneas 79-88): si se resuelven relativos a `Path(__file__).parent`, pasar a `P.DATA / nombre`.
  - `AUX_Z_recalc_shares.py`: l.22-23 `SHARES_FILE = P.DATA / "Shares_PET_OIL_Split.xlsx"`, `OLADE_FILE = P.DATA / "OLADE - Capacidad instalada por fuente - Anual.xlsx"`; l.27, 30 `SCRIPT_DIR / "Old_Inputs" / ...` → `P.OLD_INPUTS / ...`.
  - `Z_TEMP_add_pwrbck_to_scenarios.py`: l.39 `sys.path.insert(0, str(HERE))` → bootstrap; l.47-48 `CSV_DIR = P.OG_CSVS_INPUTS`, `OUT_DIR = P.A1_OUTPUTS`; `grep -n "Config_region_consolidation" ` → `P.CONFIG_REGION_CONSOLIDATION`.
  - `Z_AUX_sort_csv.py`, `concatenate_relac.py`, `preprocess_data_muio.py`: sin cambios.
  - Docstrings `python t1_confection/X.py` → `python scripts/tools/X.py` en todos.

- [ ] **Step 2: Verificar**

```bash
for f in scripts/tools/*.py; do python -m py_compile "$f" || echo "FALLA $f"; done
grep -nE "(SCRIPT_DIR|HERE|script_dir|base_dir)[ /,)].*(A1_Outputs|OG_csvs|Config_|Miscellaneous|LAC_maxcap|Shares_|OLADE|Old_Inputs|Secondary_Techs|Matriz)" scripts/tools/*.py | grep -vE "^\S+:[0-9]+:\s*#"   # vacío
python scripts/tools/Z_validate_country_data.py | tail -3
python scripts/tools/Z_AUX_update_maxcap_inv_from_tool.py | tail -3          # dry-run por defecto
python scripts/tools/Z_AUX_apply_parametrization_review.py | tail -3         # dry-run por defecto
python scripts/tools/Z_generate_country_template.py --help | head -3
```

- [ ] **Step 3: Commit**

```bash
git add scripts/tools
git commit -q -m "refactor(tools): rutas via relac_paths"
```

---

### Task 13: `scripts/tests/`

**Files:**
- Modify: `test_b2_chain_helper.py:3`, `test_D2_fixes.py:250-252`, `test_outputs.py:55-60`

- [ ] **Step 1: Editar**
  - `test_b2_chain_helper.py`: antes de `import B2_Executing_OG_Model as b2`:
    ```python
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
    ```
    y docstring l.1 `# scripts/tests/test_b2_chain_helper.py`.
  - `test_D2_fixes.py`: bootstrap k=1; l.251 `base_path = P.A1_OUTPUTS`; l.253 `find_scenarios(script_dir)` → `find_scenarios(P.A1_OUTPUTS)` (revisar la firma de `find_scenarios`: si recibe el dir padre de `A1_Outputs`, pasar `P.INPUTS`).
  - `test_outputs.py`: bootstrap k=1 y `sys.path.insert(0, str(P.FIX_DISPATCH))` antes de `import relac_io as io`; l.60 `CANDIDATES_CSV = P.CANDIDATE_FLOORS`; l.369-424 `HERE / "test_*.csv"` → `P.FIX_DISPATCH_OUT / "test_*.csv"`.

- [ ] **Step 2: Verificar**

```bash
python scripts/tests/test_b2_chain_helper.py     # OK: chain helper
python scripts/tests/test_relac_paths.py         # OK relac_paths
python -m py_compile scripts/tests/test_D2_fixes.py scripts/tests/test_outputs.py && echo OK
python scripts/tests/test_outputs.py --help | head -3
```

- [ ] **Step 3: Commit**

```bash
git add scripts/tests
git commit -q -m "refactor(tests): rutas e imports para el layout nuevo"
```

---

### Task 14: `scripts/experimental/`

**Files:**
- Modify: `matriz_balance/{estimar_flujos_desde_olade, estimar_flujos_optimizacion, estimar_flujos_promedio, estimar_flujos_ras, generar_tabla_flujos_energia}.py` (línea `base_path = Path(__file__).parent`), `matriz_balance/generar_matriz_electricidad.py:44, 207, 265`, `matriz_balance/datos_flujos_internet.py` (si escribe archivos)
- Modify: `veg_tx_abs_test/{veg_tx_constraints:64-75, plot_floors_ceilings:10-19,298, explain_shared_ceiling:7-8, verify_no_infeasibility:8-17, why_ceiling_gt_floor:6-7}.py`

- [ ] **Step 1: matriz_balance** — bootstrap **k=2** en los 5 con `base_path`; `base_path = Path(__file__).parent` → `base_path = P.MATRIZ_BALANCE`. En `generar_matriz_electricidad.py` los literales `'OLADE - Matriz de balance energético - Anual.xlsx'`, `'Matriz_Completa_Con_Produccion.xlsx'`, `'Matriz_ImportExport_PorPais.xlsx'` → `str(P.MATRIZ_BALANCE / '...')` (bootstrap k=2). `datos_flujos_internet.py`: `grep -n "to_excel\|to_csv\|open(" `; si escribe, anclar a `P.MATRIZ_BALANCE`.

- [ ] **Step 2: veg_tx_abs_test** — bootstrap k=2 en los 5;
  - `veg_tx_constraints.py` l.65 `EXE = P.EXECUTABLES`; l.75 `OUT_DIR = P.EXPERIMENTAL_OUT / "veg_tx_abs_test"` + `OUT_DIR.mkdir(parents=True, exist_ok=True)`.
  - `plot_floors_ceilings.py` l.11 `EXE = P.EXECUTABLES`; l.19 `HERE / f"Pre_processed_..."` → `P.REFERENCE / "veg_tx_abs_test" / f"Pre_processed_..."`; l.298 `png = P.EXPERIMENTAL_OUT / "veg_tx_abs_test" / "floors_ceilings_comparison.png"` (+ mkdir).
  - `explain_shared_ceiling.py` l.8, `verify_no_infeasibility.py` l.17, `why_ceiling_gt_floor.py` l.7: `HERE / "Pre_processed_..."` → `P.REFERENCE / "veg_tx_abs_test" / "Pre_processed_..."`. El `spec_from_file_location("vtc", HERE / "veg_tx_constraints.py")` no cambia (hermano).

- [ ] **Step 3: Verificar**

```bash
for f in scripts/experimental/*/*.py; do python -m py_compile "$f" || echo "FALLA $f"; done
grep -n "t1_confection\|HERE.parent" scripts/experimental/*/*.py | grep -v "^\S*:[0-9]*:\s*#"   # vacío
python -c "import sys; sys.path.insert(0,'scripts'); from common import relac_paths as P; import os; print(all((P.REFERENCE/'veg_tx_abs_test'/f'Pre_processed_{s}_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_VEGCON.txt').exists() for s in ['BAU','INV','OPT','VGB']))"
```

- [ ] **Step 4: Commit**

```bash
git add scripts/experimental
git commit -q -m "refactor(experimental): rutas via relac_paths (datos en inputs/reference, png en outputs/experimental)"
```

---

### Task 15: YAML definitivos, `dvc.yaml`, `dvc.lock`, `.gitignore`, `.dvcignore`

**Files:**
- Modify: `inputs/config/Config_MOMF_T1_A.yaml` (comentarios), `inputs/config/Config_MOMF_T1_AB.yaml` (comentarios "relativo a t1_confection"), `dvc.yaml`, `dvc.lock`, `.gitignore`, `.dvcignore`

- [ ] **Step 1: Revisar los dos YAML** — `grep -n "t1_confection\|relativo a" inputs/config/*.yaml`; cambiar los comentarios a "relativo a la raíz del repo". Verificar que todas las claves de la tabla del spec §5.3 tienen el valor nuevo.

- [ ] **Step 2: `dvc.yaml`** — reescribir con el contenido del spec §7.1 (conservar los bloques `cache: false` / `persist: true` de cada `out` de `executing`, exactamente como hoy).

- [ ] **Step 3: `dvc.lock`** — solo rutas:

```bash
sed -i -E 's#path: t1_confection/(B1_Compiler\.py|Z_AUX_capital_annualization_script\.py)#path: scripts/pipeline/\1#; s#path: t1_confection/Config_MOMF_T1_A(B?)\.yaml#path: inputs/config/Config_MOMF_T1_A\1.yaml#; s#path: t1_confection/osemosys_fast_preprocessed\.txt#path: inputs/model/osemosys_fast_preprocessed.txt#; s#path: concatenate_files/concatenate_relac\.py#path: scripts/tools/concatenate_relac.py#; s#path: t1_confection/(A1_Outputs|A2_Extra_Inputs|Miscellaneous)/#path: inputs/\1/#; s#path: t1_confection/(A2_Output_Params|A2_Outputs_Params_otoole|Executables)/#path: outputs/\1/#; s#path: t1_confection/(A2_Structure_Lists\.xlsx|RELAC_TX_[^ ]*)#path: outputs/\1#; s#cmd: python -u t1_confection/#cmd: python -u scripts/pipeline/#' dvc.lock
grep -n "t1_confection\|concatenate_files" dvc.lock dvc.yaml   # vacío
```

- [ ] **Step 4: `.dvcignore`**

```
# Ignorar __pycache__ y bytecode SOLO dentro de outputs/Executables
outputs/Executables/**/__pycache__/
outputs/Executables/**/*.py[cod]
```

- [ ] **Step 5: `.gitignore`** — reescribir el archivo completo con el mismo orden y comentarios, cambiando prefijos:

```gitignore
# Executables: ignore everything except the RMCarefulXLSX pre-processed file per scenario
outputs/Executables/**
!outputs/Executables/*/
!outputs/Executables/*/Pre_processed_*_StorageDelayN5_OpenBCK_RMCarefulXLSX.txt
!outputs/Executables/*/Pre_processed_*_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt

# Excel files
inputs/_GDP_Ref.xlsx
outputs/A2_Structure_Lists.xlsx
inputs/requirements
outputs/COSTS_ENERGY_BE_Anualized.csv
inputs/Discounted_Rate.xlsx
outputs/RELAC_TX_Combined_Inputs_Outputs.csv
outputs/RELAC_TX_Inputs.csv
outputs/RELAC_TX_Outputs.csv
outputs/RELAC_TX_Combined_Inputs_Outputs_*.csv
outputs/RELAC_TX_Inputs_*.csv
outputs/RELAC_TX_Outputs_*.csv
# StorageDelay combined I/O dumps (~390 MB c/u, generados; no versionar)
outputs/RELAC_TX_StorageDelay_*.csv

# Excel backups
inputs/A1_Outputs/**/*.xlsx.bak

# Python scripts
scripts/pipeline/setup_utils.py
scripts/pipeline/maxcapacity.py
scripts/tools/test_inputs.py

# Pickle files
outputs/legacy/Blend_Shares_0.pickle

# figs
RELAC_cambiarporfecha.twbx
workflow.pptx

# Tableau files
*.twbx

# logs
outputs/logs/
inputs/A1_Outputs/secondary_techs_update_log_*.txt

# All files containing "log", "debug", or "backup" in their name
*log*
*Log*
*LOG*
*debug*
*Debug*
*DEBUG*
*backup*
*Backup*
*BACKUP*
# Excepcion: A2_Output_Params se versiona completo (sus CSV "Technology*" caen en *log* por core.ignorecase)
!outputs/A2_Output_Params/**
!outputs/A2_Outputs_Params_otoole/**
# Excepcion: el codigo y la config nunca se ignoran por estos patrones
!scripts/**
!inputs/config/**

# All files containing "_audit" in their name
*_audit*
*_Audit*
*_AUDIT*

# PowerPoint files
*.pptx

# All files or folders containing "temp", "copia", or "copy" in their name
*temp*
*Temp*
*TEMP*
*copia*
*Copia*
*COPIA*
*copy*
*Copy*
*COPY*
# Excepcion: plantillas otoole versionadas
!inputs/Miscellaneous/templates/
!inputs/Miscellaneous/templates/**

# guides
RELAC_TX_Guia_instalacion_ejecucion.pdf

# Secondary Techs Editor - temporary files
inputs/data/~$Secondary_Techs_Editor.xlsx
inputs/A1_Outputs/*/A-O_Parametrization_backup_*.xlsx
inputs/A1_Outputs/*/A-O_Demand_backup_*.xlsx
inputs/A1_Outputs/*/A-O_AR_Model_Base_Year_backup_*.xlsx
inputs/A1_Outputs/*/A-O_AR_Projections_backup_*.xlsx
inputs/A1_Outputs/*/A-O_Parametrization.backup*.xlsx

# OG csvs inputs - backup files
inputs/OG_csvs_inputs/*backup*
# Dashboard chart PNG exports (regenerated by build_dashboard.py)
outputs/Figures/chart*.png

# Bytecode (al FINAL: debe ir despues de la excepcion !scripts/** para que gane)
__pycache__/
*.py[cod]
```

- [ ] **Step 6: Verificar que git ve exactamente lo mismo que antes**

```bash
git status --short | grep -v '^??' | head          # solo los archivos editados en esta task
git status --short --ignored | grep '^!!' | grep -E "^\!\! (scripts|inputs/config)/" # vacío: nada de código/config ignorado
git check-ignore -v outputs/Executables/BAU_0/BAU_0.txt                                # ignorado
git check-ignore -v outputs/Executables/BAU_0/Pre_processed_BAU_0_StorageDelayN5_OpenBCK_RMCarefulXLSX.txt || echo "NO ignorado (correcto)"
git check-ignore -v outputs/logs/cplex.log outputs/RELAC_TX_StorageDelay_Inputs.csv  # ignorados
git ls-files --others --exclude-standard | head -20   # untracked "nuevos": no debe aparecer nada de inputs/ ni scripts/ salvo lo esperado
conda run -n OG-MOMF-env dvc status                   # esperado: "Data and pipelines are up to date." (si no, ver spec §7.2 fallback)
```

- [ ] **Step 7: Commit**

```bash
git add inputs/config dvc.yaml dvc.lock .gitignore .dvcignore
git commit -q -m "chore: YAML relativos a la raiz, dvc.yaml/dvc.lock, .gitignore y .dvcignore para el layout nuevo"
```

---

### Task 16: Documentación

**Files:**
- Modify: `README.md`, `RELAC_TX_Guia_instalacion_ejecucion.md`, `docs/{auxiliary-tools, configuration, country-management, installation, pipeline, quickstart, secondary-techs-editor, solver-patchers}.md`
- Modify (solo cabecera): `docs/plan_port_reserve_margin_and_storage_from_OSTRAM.md`; `docs/plan_integracion_tx_chain_B2.md` está **sin versionar** (`??`): no tocarlo ni añadirlo.

- [ ] **Step 1: Reemplazo sistemático de rutas** (revisar cada hit; los nombres de script no cambian, solo su carpeta)

```bash
DOCS="README.md RELAC_TX_Guia_instalacion_ejecucion.md docs/auxiliary-tools.md docs/configuration.md docs/country-management.md docs/installation.md docs/pipeline.md docs/quickstart.md docs/secondary-techs-editor.md docs/solver-patchers.md"
# scripts de pipeline
sed -i -E 's#t1_confection/(A[0-3]_[A-Za-z_]+\.py|B1[b]?_[A-Za-z_]+\.py|B2_Executing_OG_Model\.py|D[1-5]_[A-Za-z_]+\.py|patch_[a-z_]+\.py|strip_storage\.py|open_pwrbck_caps\.py|inject_DaysInDayType\.py|sync_[a-z_]+\.py|A3_process/)#scripts/pipeline/\1#g' $DOCS
sed -i -E 's#t1_confection/(Z_validate_country_data|Z_generate_country_template|Z_AUX_(sort_csv|fix_excel_profiles|united_regions|config_loader|capital_annualization_script|apply_parametrization_review|update_[a-z_]+|D1b_[a-z_]+))\.py#scripts/tools/\1.py#g' $DOCS
sed -i -E 's#t1_confection/Z_AUX_generate_[a-z_]+\.py#scripts/dashboard/&#; s#scripts/dashboard/t1_confection/#scripts/dashboard/#g' $DOCS
sed -i -E 's#t1_confection/(build_dashboard|dashboard_config)\.py#scripts/dashboard/\1.py#g' $DOCS
sed -i -E 's#fix_dispatch/(write_floors|preflight_separation|relac_io|make_candidates|build_combined)\.py#scripts/fix_dispatch/\1.py#g; s#RELAC_Tx_v15_run/(veg_tx_constraints_v14|cost_sensitivity_v11|nli_sr_recompute_v1)\.py#scripts/tx_chain/\1.py#g; s#RELAC_Tx_v15_run/outputs_BSR/#inputs/tx_chain/outputs_BSR/#g; s#concatenate_files/#scripts/tools/#g' $DOCS
# datos y configs
sed -i -E 's#t1_confection/Config_[A-Za-z_0-9]+\.yaml#inputs/config/&#; s#inputs/config/t1_confection/#inputs/config/#g' $DOCS
sed -i -E 's#t1_confection/(A1_Outputs|A2_Extra_Inputs|OG_csvs_inputs|Miscellaneous)#inputs/\1#g; s#t1_confection/(A2_Output_Params|A2_Outputs_Params_otoole|Executables|Figures|RELAC_TX_)#outputs/\1#g' $DOCS
sed -i -E 's#t1_confection/A3_process/rules_scripts/lid_rule\.yaml#inputs/config/A3_process/lid_rule.yaml#g; s#t1_confection/test_b2_chain_helper\.py#scripts/tests/test_b2_chain_helper.py#g' $DOCS
grep -n "t1_confection\|fix_dispatch/\|RELAC_Tx_v15_run\|concatenate_files" $DOCS
```
Los hits que queden se editan a mano (frases como "Los resultados se generan en `t1_confection/`" → "`outputs/`"; "El folder `Old_Inputs/` debe crearse dentro de `t1_confection/`" → "dentro de `inputs/reference/`"; `relac_tx\t1_confection\Config_MOMF_T1_AB.yaml` en la guía → `relac_tx\inputs\config\Config_MOMF_T1_AB.yaml`).

- [ ] **Step 2: Añadir al README una sección "Estructura del repositorio"** con el árbol de tres carpetas (versión compacta del spec §3, 15-20 líneas) y la regla: inputs = mantenido a mano, outputs = regenerado, scripts = código; rutas YAML relativas a la raíz; `scripts/common/relac_paths.py` como única fuente del layout.

- [ ] **Step 3: Nota de cabecera en el plan histórico versionado**

Al inicio de `docs/plan_port_reserve_margin_and_storage_from_OSTRAM.md`:
```markdown
> **Nota (2026-09):** las rutas de este documento son anteriores a la reestructuración del repo en
> `inputs/ scripts/ outputs/`. Ver `docs/superpowers/specs/2026-09-07-restructure-inputs-scripts-outputs-design.md`.
```

- [ ] **Step 4: Barrido de docstrings en scripts** (líneas de uso que Tasks 7–14 no hayan cubierto)

```bash
grep -rn "t1_confection/" scripts/ --include=*.py | grep -v "^\S*:[0-9]*:\s*#.*historic"
```
Cada hit: `python t1_confection/X.py` → `python scripts/<carpeta real de X>/X.py`; menciones a datos → ruta nueva. Objetivo: `grep -rn "t1_confection" scripts/ | wc -l` = 0.

- [ ] **Step 5: Verificar y commit**

```bash
grep -rn "t1_confection\|RELAC_Tx_v15_run\|concatenate_files" README.md RELAC_TX_Guia_instalacion_ejecucion.md docs/*.md scripts/ inputs/config/ dvc.yaml .gitignore | grep -v "docs/plan_\|docs/superpowers/" # vacío
git add README.md RELAC_TX_Guia_instalacion_ejecucion.md docs/*.md scripts
git commit -q -m "docs: rutas actualizadas al layout inputs/ scripts/ outputs/"
```

---

### Task 17: Comprobaciones estáticas y smoke global

**Files:** ninguno nuevo (solo verificación; corregir lo que falle en el script correspondiente y commitear como `fix(layout): ...`).

- [ ] **Step 1: Compilación de todo**

```bash
python -m compileall -q scripts && echo "compileall OK"
```

- [ ] **Step 2: Grep de tokens viejos en todo lo operativo**

```bash
grep -rnE "t1_confection|RELAC_Tx_v15_run|concatenate_files|kt0031|HERE\.parent / \"t1|parents\[1\] / \"t1" scripts inputs/config dvc.yaml dvc.lock .gitignore .dvcignore README.md RELAC_TX_Guia_instalacion_ejecucion.md docs/*.md | grep -v "docs/plan_" 
```
Esperado: vacío.

- [ ] **Step 3: Smoke de CLIs desde la raíz** (todos con exit 0)

```bash
set -e
python scripts/tests/test_relac_paths.py
python scripts/tests/test_b2_chain_helper.py
python scripts/pipeline/A3_process.py --list
python scripts/pipeline/B1b_Pre_solver_validation.py --scenario BAU --report-only | tail -2
python scripts/pipeline/D4_load_dsptrn_max_cap_inv.py --dry-run | tail -2
python scripts/pipeline/sync_historical_from_bau.py --dry-run | tail -2
python scripts/pipeline/D5_load_fuel_var_costs.py --help >/dev/null
python scripts/pipeline/A2_AddTx.py --help >/dev/null
python scripts/pipeline/A3_migrate_old_inputs_CLG.py --help >/dev/null
python scripts/fix_dispatch/write_floors.py --dry-run --scenarios BAU | tail -2
python scripts/fix_dispatch/preflight_separation.py --help >/dev/null
python scripts/tx_chain/cost_sensitivity_v11.py --help >/dev/null
python scripts/tools/Z_validate_country_data.py | tail -1
python scripts/tools/Z_AUX_update_maxcap_inv_from_tool.py | tail -1
python scripts/tools/Z_AUX_apply_parametrization_review.py | tail -1
python scripts/tools/Z_generate_country_template.py --help >/dev/null
python scripts/tools/migrate_layout_untracked.py | tail -3
for f in scripts/pipeline/patch_storage_delay.py scripts/pipeline/strip_storage.py scripts/pipeline/open_pwrbck_caps.py scripts/pipeline/patch_reserve_margin_repair_careful_xlsx.py scripts/pipeline/sync_patched_csvs_from_txt.py; do python $f --help >/dev/null; done
echo "SMOKE OK"
```

- [ ] **Step 4: Smoke de import de los módulos que otros importan**

```bash
python -c "import sys; sys.path[0:0]=['scripts','scripts/pipeline','scripts/fix_dispatch','scripts/dashboard']; import common.relac_paths, common.Z_AUX_config_loader, common._xlsx_validation_core, relac_io, dashboard_config, B2_Executing_OG_Model, patch_activity_upper_limit, Z_AUX_capital_annualization_script; print('imports OK')"
```

- [ ] **Step 5: `run.py` no necesita cambios** — comprobar que sigue apuntando a `dvc.yaml` y `environment.yaml` en la raíz: `grep -n "DVC_FILE_DEFAULT\|ENV_FILE_DEFAULT" run.py`. Sin edición.

- [ ] **Step 6: Commit de correcciones (si las hubo)**

```bash
git status --short | grep -v '^??'
git commit -qam "fix(layout): correcciones de rutas detectadas en smoke" || echo "nada que commitear"
```

---

### Task 18: Verificación byte a byte en worktree nuevo

**Files:**
- Worktree: `../relac_tx_new` (rama `restructure/inputs-scripts-outputs`)
- Modify: `docs/superpowers/specs/2026-09-07-restructure-inputs-scripts-outputs-design.md` (sección "Resultado de la verificación")

- [ ] **Step 1: Crear el worktree nuevo y aplicar la config de verificación**

```bash
cd "C:/Users/ClimateLeadGroup/Desktop/CLG_repositories/relac_tx"
git worktree add ../relac_tx_new restructure/inputs-scripts-outputs
bash "<scratch>/verify_config.sh" ../relac_tx_new/inputs/config/Config_MOMF_T1_AB.yaml
```

- [ ] **Step 2: ⚠️ REQUIERE OK — B1 en el worktree nuevo**

```bash
cd ../relac_tx_new
PYTHONHASHSEED=0 conda run -n OG-MOMF-env --no-capture-output python -u scripts/pipeline/B1_Run_Compiler.py 2>&1 | tee "<scratch>/new_B1.log"
ls outputs/A2_Output_Params            # BAU INV OPT VGB
```
Si B1b preguntó algo en Task 1, responder exactamente igual.

- [ ] **Step 3: ⚠️ REQUIERE OK — B2 sin solver en el worktree nuevo**

```bash
cd ../relac_tx_new
PYTHONHASHSEED=0 conda run -n OG-MOMF-env --no-capture-output python -u scripts/pipeline/B2_Executing_OG_Model.py 2>&1 | tee "<scratch>/new_B2.log"
ls outputs/Executables | wc -l         # 13
ls outputs/logs                        # (vacío o logs de glpsol; sin cplex por execute_model False)
ls outputs/RELAC_TX_data_storage_delay.txt outputs/model/osemosys_fast_preprocessed_storage_delay.txt
```

- [ ] **Step 4: Manifiesto y diff**

```bash
cd "C:/Users/ClimateLeadGroup/Desktop/CLG_repositories/relac_tx"
python "<scratch>/compare_manifests.py" manifest ../relac_tx_new new "<scratch>/manifest_new.json"
python "<scratch>/compare_manifests.py" diff "<scratch>/manifest_baseline.json" "<scratch>/manifest_new.json" | tee "<scratch>/diff_result.txt"
```
Esperado: `SOLO EN BASELINE: 0`, `SOLO EN NUEVO: 0`, `DISTINTOS: 0`, exit 0.

Si hay `DISTINTOS`, para cada uno: `diff <(sed 's/\r$//' ../relac_tx_baseline/<viejo>) <(sed 's/\r$//' ../relac_tx_new/<nuevo>) | head -20`. Solo son aceptables comentarios con rutas absolutas o timestamps. Cualquier diferencia en valores numéricos o en filas es un **bug de rutas** (p. ej. un script leyó un archivo de otro escenario o un input distinto): localizar el script, corregir, commitear `fix(layout): ...`, y repetir desde el Step 2 (borrar antes `outputs/A2_Output_Params outputs/A2_Outputs_Params_otoole outputs/Executables` del worktree nuevo).

- [ ] **Step 5: Comparar `A2_Structure_Lists.xlsx` por contenido**

```bash
python - <<'EOF'
import openpyxl
a = openpyxl.load_workbook("../relac_tx_baseline/t1_confection/A2_Structure_Lists.xlsx", read_only=True, data_only=True)
b = openpyxl.load_workbook("../relac_tx_new/outputs/A2_Structure_Lists.xlsx", read_only=True, data_only=True)
assert a.sheetnames == b.sheetnames, (a.sheetnames, b.sheetnames)
for s in a.sheetnames:
    ra = [tuple(r) for r in a[s].iter_rows(values_only=True)]
    rb = [tuple(r) for r in b[s].iter_rows(values_only=True)]
    assert ra == rb, f"hoja {s} difiere"
print("A2_Structure_Lists.xlsx: contenido idéntico")
EOF
```

- [ ] **Step 6: Comprobar que los logs de la cadena coinciden en lo esencial**

```bash
grep -E "PASS|FAIL|veg_tx|\[chain\]" "<scratch>/baseline_B2.log" | sed 's#t1_confection/##; s#outputs/##' | sort > "<scratch>/b.txt"
grep -E "PASS|FAIL|veg_tx|\[chain\]" "<scratch>/new_B2.log"      | sed 's#t1_confection/##; s#outputs/##' | sort > "<scratch>/n.txt"
diff "<scratch>/b.txt" "<scratch>/n.txt" && echo "logs equivalentes"
```

- [ ] **Step 7: Documentar el resultado en el spec**

Añadir al final del spec una sección:
```markdown
## 13. Resultado de la verificación (YYYY-MM-DD)

- Baseline: worktree `clean-sirelac` @ c8f0efc; nuevo: `restructure/inputs-scripts-outputs` @ <sha>.
- Config: execute_model/create_matrix/concat_scenarios_csv/annualize_capital/del_files = False.
- Archivos comparados: N. Iguales: N. Distintos: 0. Solo en un lado: 0.
- A2_Structure_Lists.xlsx: idéntico por contenido.
- Diferencias benignas documentadas: (ninguna | lista con diff).
- Tiempos: B1 baseline X min / nuevo Y min; B2 (sin solver) X / Y.
```

- [ ] **Step 8: Commit y limpieza de worktrees**

```bash
git add docs/superpowers/specs/2026-09-07-restructure-inputs-scripts-outputs-design.md
git commit -q -m "docs(spec): resultado de la verificacion byte a byte del layout nuevo"
git worktree remove ../relac_tx_new --force
# el baseline se conserva hasta terminar la Task 19 (opcional); luego: git worktree remove ../relac_tx_baseline --force
```

---

### Task 19 (opcional, recomendada): Verificación de A0 → A1 → A2 por contenido

**Files:** ninguno en el repo; usa los dos worktrees.

- [ ] **Step 1: ⚠️ REQUIERE OK — Correr A0, A1, A2 en ambos worktrees** (A1/A2 sobrescriben `A1_Outputs` y `Tech_Country_Matrix.xlsx` **del worktree**, no del repo principal)

```bash
for W in ../relac_tx_baseline ../relac_tx_new; do (cd $W && git status --short | grep -v '^??' | head -1); done   # limpios salvo YAML de verificación
cd ../relac_tx_baseline && for s in A0_generate_tech_country_matrix A1_Pre_processing_OG_csvs A2_AddTx; do PYTHONHASHSEED=0 conda run -n OG-MOMF-env --no-capture-output python -u t1_confection/$s.py 2>&1 | tail -3; done
cd ../relac_tx_new      && for s in A0_generate_tech_country_matrix A1_Pre_processing_OG_csvs A2_AddTx; do PYTHONHASHSEED=0 conda run -n OG-MOMF-env --no-capture-output python -u scripts/pipeline/$s.py 2>&1 | tail -3; done
```
(Si Task 18 ya eliminó `../relac_tx_new`, recrearlo con `git worktree add`.)

- [ ] **Step 2: Comparar xlsx por contenido**

```bash
cd "C:/Users/ClimateLeadGroup/Desktop/CLG_repositories/relac_tx"
python - <<'EOF'
import openpyxl
from pathlib import Path
B = Path("../relac_tx_baseline/t1_confection"); N = Path("../relac_tx_new/inputs")
pairs = [(B/"Tech_Country_Matrix.xlsx", N/"data/Tech_Country_Matrix.xlsx"),
         (B/"A2_Extra_Inputs/A-Xtra_Emissions.xlsx", N/"A2_Extra_Inputs/A-Xtra_Emissions.xlsx")]
for s in ["BAU","INV","OPT","VGB"]:
    for f in ["A-O_Parametrization.xlsx","A-O_Demand.xlsx","A-O_AR_Model_Base_Year.xlsx","A-O_AR_Projections.xlsx"]:
        pairs.append((B/"A1_Outputs"/f"A1_Outputs_{s}"/f, N/"A1_Outputs"/f"A1_Outputs_{s}"/f))
bad = 0
for a, b in pairs:
    wa = openpyxl.load_workbook(a, read_only=True, data_only=True); wb = openpyxl.load_workbook(b, read_only=True, data_only=True)
    ok = wa.sheetnames == wb.sheetnames and all(
        [tuple(r) for r in wa[s].iter_rows(values_only=True)] == [tuple(r) for r in wb[s].iter_rows(values_only=True)] for s in wa.sheetnames)
    print("OK " if ok else "DIF", a.name, "" if ok else f"({a} vs {b})"); bad += (not ok)
print("TOTAL DIF:", bad)
EOF
```
Esperado: `TOTAL DIF: 0`. Registrar el resultado en la sección 13 del spec (commit `docs(spec): verificacion A0-A2 por contenido`) y eliminar ambos worktrees:
```bash
git worktree remove ../relac_tx_baseline --force; git worktree remove ../relac_tx_new --force; git worktree prune
```

---

## Cierre

Al terminar Task 18 (y 19 si se hace): `git log --oneline clean-sirelac..HEAD` debe mostrar los commits en el orden del spec §10; la raíz del repo solo contiene lo listado en spec §3; `dvc status` limpio. El `push` y el merge a `main` se hacen solo cuando el usuario lo indique (spec §10 y §11: mergear pronto para minimizar conflictos de rename en ramas paralelas).
