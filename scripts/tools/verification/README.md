# Verificación byte a byte de la reestructuración `inputs/ scripts/ outputs/`

Procedimiento para demostrar que B1 y la cadena pre-solver de B2 producen exactamente los mismos
archivos en el layout nuevo (rama `restructure/inputs-scripts-outputs`) que en el viejo
(`clean-sirelac` @ `c8f0efc`). No se ejecuta el solver. Corresponde a las Tasks 1, 18 y 19 del plan
`docs/superpowers/plans/2026-09-07-restructure-inputs-scripts-outputs.md`; el criterio de aceptación
es **cero diferencias** (spec §9.2 y §12).

Requisitos en la máquina: clon del repo con ambas ramas, entorno conda `OG-MOMF-env` (lo crea
`run.py`), `otoole` y `glpsol` en el PATH (los usa B2 aunque no se resuelva el modelo). Tiempo
estimado por corrida: 30-45 min (B1 ~10-20, B2 sin solver ~15-25).

Herramientas (en esta carpeta):

- `verify_config.sh <Config_MOMF_T1_AB.yaml>` — pone `execute_model`, `create_matrix`,
  `concat_scenarios_csv`, `annualize_capital` y `del_files` en `False` (misma config en ambos lados).
- `compare_manifests.py manifest <raiz> <old|new> <out.json>` — md5 de todos los productos
  comparables (`A2_Output_Params`, `A2_Outputs_Params_otoole`, `Executables/**.txt`, modelo parcheado,
  datafile raíz, `upstream_floor_rows.csv`), con claves independientes del layout.
- `compare_manifests.py diff <a.json> <b.json>` — lista faltantes, sobrantes y distintos; exit 0 si
  todo es idéntico.

## Pasos

Desde la raíz del clon (rama `restructure/inputs-scripts-outputs`), con `V=../relac_tx_verif`
como carpeta local para manifiestos y logs (fuera del repo):

```bash
mkdir -p ../relac_tx_verif; V=../relac_tx_verif

# 1. Worktrees limpios: layout viejo y layout nuevo
git worktree add ../relac_tx_baseline clean-sirelac
git worktree add ../relac_tx_new      restructure/inputs-scripts-outputs
bash scripts/tools/verification/verify_config.sh ../relac_tx_baseline/t1_confection/Config_MOMF_T1_AB.yaml
bash scripts/tools/verification/verify_config.sh ../relac_tx_new/inputs/config/Config_MOMF_T1_AB.yaml

# 2. Baseline (layout viejo)
( cd ../relac_tx_baseline \
  && PYTHONHASHSEED=0 conda run -n OG-MOMF-env --no-capture-output python -u t1_confection/B1_Run_Compiler.py 2>&1 | tee $V/baseline_B1.log \
  && PYTHONHASHSEED=0 conda run -n OG-MOMF-env --no-capture-output python -u t1_confection/B2_Executing_OG_Model.py 2>&1 | tee $V/baseline_B2.log )
python scripts/tools/verification/compare_manifests.py manifest ../relac_tx_baseline old $V/manifest_baseline.json

# 3. Nuevo (layout inputs/ scripts/ outputs/)
( cd ../relac_tx_new \
  && PYTHONHASHSEED=0 conda run -n OG-MOMF-env --no-capture-output python -u scripts/pipeline/B1_Run_Compiler.py 2>&1 | tee $V/new_B1.log \
  && PYTHONHASHSEED=0 conda run -n OG-MOMF-env --no-capture-output python -u scripts/pipeline/B2_Executing_OG_Model.py 2>&1 | tee $V/new_B2.log )
python scripts/tools/verification/compare_manifests.py manifest ../relac_tx_new new $V/manifest_new.json

# 4. Comparación
python scripts/tools/verification/compare_manifests.py diff $V/manifest_baseline.json $V/manifest_new.json | tee $V/diff_result.txt
```

Comprobaciones esperadas: en ambos worktrees B2 crea 13 carpetas `Executables/<S>_0/` (BAU BAC BSR INV
INVWF ISR ISRWF OPC OPT VGB VGBWF VSR VSRWF) y termina con `veg_tx PASS`; el `diff` imprime
`SOLO EN BASELINE: 0`, `SOLO EN NUEVO: 0`, `DISTINTOS: 0`. Si B1b (validador pre-solver) pregunta algo
en el baseline, responder exactamente igual en el nuevo.

Complementos (plan Task 18, steps 5-7): comparar `A2_Structure_Lists.xlsx` por contenido con openpyxl
(el xlsx lleva timestamp, no vale md5) y los logs de la cadena (`grep -E "PASS|FAIL|veg_tx|\[chain\]"`
en ambos `*_B2.log`, normalizando `t1_confection/` y `outputs/`). Opcional (Task 19): correr
A0 → A1 → A2 en ambos worktrees y comparar `A1_Outputs/**/*.xlsx` hoja a hoja.

Si aparece alguna diferencia, las únicas clases aceptables son comentarios con rutas absolutas o
timestamps embebidos en un archivo generado; cualquier diferencia en valores es un bug de rutas
que hay que localizar en el script responsable. Registrar el resultado en la sección 13 del spec
(`docs/superpowers/specs/2026-09-07-restructure-inputs-scripts-outputs-design.md`) y eliminar los
worktrees (`git worktree remove --force ../relac_tx_baseline ../relac_tx_new; git worktree prune`).
