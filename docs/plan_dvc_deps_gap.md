# Contexto: dependencias no declaradas en `dvc.yaml` (brecha de `deps`)

Estado al 2026-09-10. Documento de contexto para planear la solución en otra sesión.
Nada de lo descrito aquí está roto hoy; es una brecha de **detección de cambios**, no de ejecución.

Revisado el 2026-09-10 (segunda pasada): inventario contrastado con imports reales, `dvc status` y
`dvc repro --dry`. Correcciones respecto al borrador inicial: `patch_reserve_margin_repair_careful.py`
sí corre (import), B2 lee `Config_MOMF_T1_A.yaml`, y los deps de carpeta bajo `scripts/` requieren
`.dvcignore` para `__pycache__`.

**Estado de aplicación (2026-09-10):** el §7 está aplicado en la rama `dvc/declare-deps` (`dvc.yaml` +
`.dvcignore`). Validación en seco OK: `dvc stage list`, `dvc dag`, `dvc status` (lista los 8 deps de
`preprocess` y 26 de `executing` sin error de ruta), `dvc repro --dry`, y `dvc check-ignore` confirma
que `scripts/**/__pycache__` queda excluido. Pendiente: una corrida real que actualice `dvc.lock`,
commitear ese lock en la rama y mergear a `main`.

**Hallazgo de la primera corrida real (kt0031, 2026-09-09):** B2 terminó bien (62 min) pero `dvc repro`
falló con `output 'outputs\RELAC_TX_Inputs.csv' does not exist`. Causa: con `storage_delay_active: True`
B2 escribe con prefijo `RELAC_TX_StorageDelay_` (`storage_delay_prefix_final_files`), y los `outs` de
`dvc.yaml` seguían con `RELAC_TX_`. Bug previo a esta rama: explica que `dvc.lock` de `executing` no se
actualizara desde 2026-02-10 y los seis `deleted` del §4.2. Corregido en la rama renombrando los seis
`outs`.

**Seguimiento (2026-09-11, rama `fix/dvc-outs-prefix-and-legacy-rm-patcher`):** (1) prefijo único
`RELAC_TX_` para los CSV finales (se eliminó `storage_delay_prefix_final_files`; los `outs` ya no
dependen de ningún flag) y B2 verifica al arrancar que los `outs` CSV de `dvc.yaml` coincidan con
`prefix_final_files` (`check_dvc_outs_prefix`, aborta antes del solve). (2) Eliminado el patcher
legacy `run_reserve_margin_repair_patcher` (B2:459 apuntaba a un script inexistente y su CLI era
incompatible con `_careful.py`), su entrada en `CHAIN_ORDER` y `reserve_margin_repair_active`.
Hallazgo adicional: kt0031 hace checkout con CRLF y esta máquina con LF; los md5 de `dvc.lock`
difieren por máquina para archivos de texto (verificado: relac_paths.py y osemosys txt). Sin
`.gitattributes` el lock de una máquina invalida ambos stages en la otra. Pendiente de decidir.

## 1. El problema en una frase

`dvc.yaml` declara como `deps` solo una fracción de los scripts y datos que cada stage realmente
ejecuta o lee. Si se edita algo no declarado y nada más, `dvc repro` (y por tanto `run.py`) considera
el stage al día y **no lo vuelve a correr**.

## 2. Cómo funciona hoy la cadena de ejecución

```
run.py
  └─ parchea 'fecha' -> YYYY-MM-DD en dvc.yaml (backup + restore al final)
  └─ conda run -n OG-MOMF-env dvc repro
       ├─ stage preprocess : python -u scripts/pipeline/B1_Run_Compiler.py
       │     └─ subprocess B1_Compiler.py (por escenario)
       │           └─ import B1b_Pre_solver_validation  (pre_solver_validation default True)
       └─ stage executing  : python -u scripts/pipeline/B2_Executing_OG_Model.py
             ├─ subprocess por escenario: preprocess_data, inject_DaysInDayType,
             │     patch_storage_delay, strip_storage, open_pwrbck_caps,
             │     patch_reserve_margin_repair_careful_xlsx, sync_patched_csvs_from_txt
             ├─ subprocess fix_dispatch: preflight_separation (gate), write_floors (por escenario)
             │     └─ ambos importan relac_io, feasibility; preflight importa floor_effect
             ├─ subprocess tx_chain: veg_tx_constraints (barrera), cost_sensitivity_v11,
             │     nli_sr_recompute (transforms)
             ├─ subprocess scripts/tools/concatenate_relac.py (post-solve)
             └─ import Z_AUX_capital_annualization_script (annualize_capital True)
```

DVC decide re-ejecutar un stage si cambia alguno de: `cmd`, md5 de cada `deps`, o la definición
de `outs`. Todo lo que no esté en `deps` es invisible para esa decisión.

## 3. Inventario verificado (2026-09-10)

### Stage `preprocess` — declarado hoy

- `scripts/pipeline/B1_Compiler.py`
- `inputs/config/Config_MOMF_T1_A.yaml`
- `inputs/A1_Outputs/`, `inputs/A2_Extra_Inputs/`

### Stage `preprocess` — se ejecuta y NO está declarado

- `scripts/pipeline/B1_Run_Compiler.py` (es el propio `cmd`)
- `scripts/pipeline/B1b_Pre_solver_validation.py` (importado en `B1_Compiler.py:36`)
- `scripts/common/relac_paths.py` (importado por todo; cambiarlo cambia rutas)
- `scripts/common/_xlsx_validation_core.py` (importado por B1b en `B1b_Pre_solver_validation.py:41`)

No corre en B1: `scripts/common/Z_AUX_config_loader.py` (lo usan A0-A3, D1, D2 y el inactivo
`patch_activity_upper_limit.py`; ninguno está en la ruta B1/B2).

### Stage `executing` — declarado hoy

- `inputs/config/Config_MOMF_T1_AB.yaml`
- `inputs/model/osemosys_fast_preprocessed.txt`
- `scripts/tools/concatenate_relac.py`
- `scripts/pipeline/Z_AUX_capital_annualization_script.py`
- `outputs/A2_Output_Params/`, `inputs/Miscellaneous/`

### Stage `executing` — se ejecuta y NO está declarado

Scripts (`scripts/pipeline/`):
- `B2_Executing_OG_Model.py` (es el propio `cmd`)
- `preprocess_data.py`, `inject_DaysInDayType.py`, `patch_storage_delay.py`, `strip_storage.py`,
  `open_pwrbck_caps.py`, `patch_reserve_margin_repair_careful_xlsx.py`, `sync_patched_csvs_from_txt.py`
- `patch_reserve_margin_repair_careful.py`: su flag propio está apagado
  (`reserve_margin_repair_active: False`; ojo, B2:459 busca `patch_reserve_margin_repair.py`, que no
  existe), pero **sí corre**: lo importa la variante activa en
  `patch_reserve_margin_repair_careful_xlsx.py:16`. Debe declararse.
- Inactivo por flag y sin otro consumidor en B2: `patch_activity_upper_limit.py`
  (`activity_upper_limit_active: False`)

Scripts (`scripts/fix_dispatch/`):
- `write_floors.py`, `preflight_separation.py` (ejecutados; rutas en yaml `dispatch_floors_script`,
  `preflight_separation_script`)
- `relac_io.py`, `feasibility.py`, `floor_effect.py` (importados por los dos anteriores)

Scripts (`scripts/tx_chain/`), los tres corren:
- `veg_tx_constraints.py` (yaml `veg_tx_script`)
- `cost_sensitivity_v11.py`, `nli_sr_recompute.py` (yaml `scenario_transforms[*].script`)

Scripts comunes:
- `scripts/common/relac_paths.py`

Config:
- `inputs/config/Config_MOMF_T1_A.yaml` (B2:1436 lo carga; `xtra_scen.Main_Scenario` decide la lista
  de escenarios en B2:1452-1454)

Datos:
- `inputs/tx_chain/fix_dispatch/candidate_floors.csv` (`relac_paths.CANDIDATE_FLOORS`, leído por write_floors/preflight)
- `inputs/tx_chain/outputs_BSR/NewCapacity.csv` (yaml `veg_tx_needs_csv`)
- `inputs/data/firm_capacity_fallbacks_by_cr.xlsx` (yaml `reserve_margin_xlsx_workbook`, resuelto contra `P.DATA` en B2:535)

Ya cubierto por `inputs/Miscellaneous/` (declarado): `conversion_format.yaml` (otoole, B2:193 y 1009)
y las plantillas otoole (`params['templates']`). `candidate_floors_baseline.csv` no lo lee ningún script.

## 4. Por qué hoy casi nunca se nota

1. **Parche `fecha` de `run.py`.** Los `outs` `*_fecha.csv` se renombran con la fecha del día antes
   de `dvc repro`. `dvc.lock` registra los del último repro real (`*_2026-02-10.csv`). Cualquier día
   distinto cambia la definición del stage `executing` → DVC lo re-ejecuta aunque ninguna `dep` haya
   cambiado. En la práctica `executing` corre en cada `run.py` de un día nuevo.
2. **Deps ya desincronizadas.** `dvc status` al 2026-09-10:
   - `preprocess`: modificados `B1_Compiler.py`, `Config_MOMF_T1_A.yaml`, `inputs/A1_Outputs/`,
     `inputs/A2_Extra_Inputs/`; out `A2_Structure_Lists.xlsx` no está en caché.
   - `executing`: modificados `Config_MOMF_T1_AB.yaml` (renombrado tx_chain), `concatenate_relac.py`,
     `outputs/A2_Output_Params/`, `inputs/Miscellaneous/`; los seis outs `outputs/RELAC_TX_*.csv`
     figuran como `deleted`.

   `dvc repro --dry` confirma que la próxima corrida re-ejecuta ambos stages de todos modos.

## 5. Cuándo SÍ muerde

Correr `run.py` dos veces el **mismo día** y, entre ambas, editar **solo** un script no declarado
(p. ej. la lógica de `veg_tx_constraints.py`, `write_floors.py` o un patcher de `scripts/pipeline`).
La segunda corrida dice "todo al día" y no ejecuta nada. Escenario típico de una sesión de ajustes.

Efecto secundario relacionado: `dvc.lock` está versionado en git, así que un `git pull` que traiga
un lock ajeno también altera lo que DVC cree que está al día.

## 6. Opciones de solución

| Opción | Qué | Pros | Contras |
|---|---|---|---|
| A. Archivo por archivo | Listar cada script/dato del §3 en `deps` | Preciso: solo re-ejecuta por cambios que de verdad corren | Mantener la lista al añadir/quitar un patcher |
| B. Carpetas enteras | `scripts/pipeline/`, `scripts/fix_dispatch/`, `scripts/tx_chain/`, `scripts/common/` | Cero mantenimiento | Editar herramientas manuales (`make_candidates.py`, D1-D5, A3…) invalida el stage y fuerza un solve de horas sin motivo |
| C. Híbrida (recomendada) | Archivos explícitos en `pipeline/`, `fix_dispatch/` y `common/`; carpeta solo en `tx_chain/` (sus 3 scripts corren) | Precisión donde hay mezcla, simplicidad donde no | Lista mediana; exige `.dvcignore` para `tx_chain/__pycache__` |

`common/` pasa a archivos sueltos porque `Z_AUX_config_loader.py` solo lo usa la fase A (ver §3):
declarar la carpeta dispararía B1 por ediciones ajenas.

Descartado: `params:` de DVC solo vigila valores del yaml, no código.

Nota sobre carpetas y `__pycache__`: `.dvcignore` hoy solo ignora bytecode bajo `outputs/Executables/`.
`scripts/common/`, `scripts/tx_chain/` y `scripts/pipeline/` ya contienen `__pycache__/`. Los `.pyc` se
regeneran al cambiar el mtime de la fuente (checkout, pull) y difieren por versión de Python, así que
cualquier dep de carpeta bajo `scripts/` marcaría el stage como modificado sin cambios reales. Toda
opción con carpetas (B o C) exige añadir a `.dvcignore`:

```
scripts/**/__pycache__/
scripts/**/*.py[cod]
```

Con archivos sueltos (A) el problema no aparece.

Nota sobre `cmd`: DVC no hashea el script del `cmd` automáticamente; hay que declararlo en `deps`
(`B1_Run_Compiler.py`, `B2_Executing_OG_Model.py`).

## 7. Borrador opción C

```yaml
stages:
  preprocess:
    cmd: python -u scripts/pipeline/B1_Run_Compiler.py
    deps:
      - scripts/pipeline/B1_Run_Compiler.py
      - scripts/pipeline/B1_Compiler.py
      - scripts/pipeline/B1b_Pre_solver_validation.py
      - scripts/common/relac_paths.py
      - scripts/common/_xlsx_validation_core.py
      - inputs/config/Config_MOMF_T1_A.yaml
      - inputs/A1_Outputs/
      - inputs/A2_Extra_Inputs/
    outs: (sin cambios)

  executing:
    cmd: python -u scripts/pipeline/B2_Executing_OG_Model.py
    deps:
      # config y modelo
      - inputs/config/Config_MOMF_T1_AB.yaml
      - inputs/config/Config_MOMF_T1_A.yaml        # B2:1436, Main_Scenario
      - inputs/model/osemosys_fast_preprocessed.txt
      # orquestador y parches activos
      - scripts/pipeline/B2_Executing_OG_Model.py
      - scripts/pipeline/preprocess_data.py
      - scripts/pipeline/inject_DaysInDayType.py
      - scripts/pipeline/patch_storage_delay.py
      - scripts/pipeline/strip_storage.py
      - scripts/pipeline/open_pwrbck_caps.py
      - scripts/pipeline/patch_reserve_margin_repair_careful_xlsx.py
      - scripts/pipeline/patch_reserve_margin_repair_careful.py   # importado por el anterior
      - scripts/pipeline/sync_patched_csvs_from_txt.py
      - scripts/pipeline/Z_AUX_capital_annualization_script.py
      - scripts/tools/concatenate_relac.py
      - scripts/common/relac_paths.py
      # pisos de despacho
      - scripts/fix_dispatch/write_floors.py
      - scripts/fix_dispatch/preflight_separation.py
      - scripts/fix_dispatch/relac_io.py
      - scripts/fix_dispatch/feasibility.py
      - scripts/fix_dispatch/floor_effect.py
      - inputs/tx_chain/fix_dispatch/candidate_floors.csv
      # cadena Tx (los 3 corren)
      - scripts/tx_chain/
      - inputs/tx_chain/outputs_BSR/NewCapacity.csv
      # datos
      - inputs/data/firm_capacity_fallbacks_by_cr.xlsx
      - outputs/A2_Output_Params/
      - inputs/Miscellaneous/
    outs: (sin cambios)
```

Y en `.dvcignore` (junto a las reglas existentes de `outputs/Executables/`):

```
scripts/**/__pycache__/
scripts/**/*.py[cod]
```

Decisión pendiente: incluir o no `patch_activity_upper_limit.py` (inactivo, sin importadores en la
ruta B2). Activarlo en el yaml ya dispara re-ejecución por el yaml mismo; incluirlo solo añade
detección de cambios en su código mientras esté apagado. Recomendación: no incluirlo hasta que se
active. (`patch_reserve_margin_repair_careful.py` ya no entra en esta decisión: corre vía import.)

## 8. Efectos secundarios de aplicar el cambio

- Cambiar `deps` altera la firma de ambos stages en `dvc.lock`: el **siguiente `dvc repro`
  re-ejecuta todo** (B1 ~10-20 min; B2 con solver, horas). En general, aplicarlo justo antes de una
  corrida que igual se iba a lanzar, no cuando solo se quiera reproducir resultados existentes.
- **Hoy (2026-09-10) es un momento barato:** ambos stages ya están invalidados por deps y outs
  desincronizados (§4.2), así que añadir `deps` ahora no provoca ningún re-cómputo adicional.
- `dvc.lock` cambiará y hay que commitearlo junto con `dvc.yaml` y `.dvcignore`.
- `run.py` sigue parcheando `fecha`; no interfiere con `deps`.
- Regla de la casa: **no ejecutar B2 ni `run.py` sin aprobación explícita** (memoria
  `feedback_no_execute_pipeline_scripts`). La verificación debe ser en seco.

## 9. Verificación en seco (sin correr el pipeline)

```bash
# 1) que dvc parsea el yaml y ve las deps nuevas
conda run -n OG-MOMF-env dvc stage list
conda run -n OG-MOMF-env dvc dag

# 2) qué considera desactualizado y por qué (no ejecuta nada)
conda run -n OG-MOMF-env dvc status

# 3) simulacro de repro
conda run -n OG-MOMF-env dvc repro --dry

# 4) tras la próxima corrida real: confirmar que dvc.lock lista cada dep nueva con su md5
grep -nE "^\s*- path:" dvc.lock
```

Nota operativa: en esta máquina `conda` no está en el PATH de PowerShell. El entorno vive en
`C:\Users\ClimateLeadGroup\anaconda3\envs\OG-MOMF-env`; usar la ruta completa
`C:\Users\ClimateLeadGroup\anaconda3\Scripts\conda run -n OG-MOMF-env dvc ...` (verificado con
DVC 3.62.0, 2026-09-10).

Prueba de la brecha cerrada (solo tras una corrida real que actualice `dvc.lock`): tocar un
comentario en `scripts/tx_chain/veg_tx_constraints.py`, `dvc status` debe marcar `executing` como
cambiado. Hoy no se puede probar en seco: `dvc status` ya marca ambos stages por otras causas
(§4.2), y un `dvc commit` forzado registraría hashes de deps que no produjeron los outs actuales.

## 10. Preguntas abiertas para la sesión de planificación

1. ¿Mantener el parche `fecha` de `run.py`? Hoy fuerza re-ejecución diaria de `executing` y duplica
   cada CSV de salida con y sin fecha. Alternativas: `outs` sin fecha y copia fechada fuera de DVC,
   o dejar como está y aceptar que `executing` casi siempre corre.
2. `scripts/common/`: resuelto a favor de archivos sueltos. B1 necesita `relac_paths.py` y
   `_xlsx_validation_core.py` (import en B1b:41); B2 solo `relac_paths.py`. `Z_AUX_config_loader.py`
   es de la fase A y no debe invalidar B1/B2. Además evita el problema de `__pycache__` (§6).
3. ¿Añadir `outputs/Executables/` también como `dep` implícita de algo? No: es `out` del stage.
4. Arreglar de paso `B2_Executing_OG_Model.py:459` (nombre `patch_reserve_margin_repair.py`
   inexistente) aunque el flag esté apagado.
5. `B1_Run_Compiler.py` reescribe `Config_MOMF_T1_A.yaml` (dep declarado) por cada escenario
   (`update_main_scenario`) y lo restaura desde `.bak` en un `finally` (líneas 190-215). Con un
   kill duro a mitad de corrida el yaml queda con otro `Main_Scenario` y el `.bak` en disco; el dep
   aparecerá modificado hasta restaurarlo a mano. Documentar el síntoma o mover el escenario a
   una variable de entorno/argumento en vez de editar el yaml.

## 11. Referencias

- `dvc.yaml`, `dvc.lock` (raíz)
- `run.py:237-246` (parche `fecha`), `run.py:305-309` (repro)
- `.dvcignore` (raíz; hoy solo cubre `outputs/Executables/`)
- `scripts/pipeline/B2_Executing_OG_Model.py`: 681 (preflight), 697 (write_floors), 724 (veg_tx),
  745 (transforms), 535 (workbook RM), 1029-1030 (concatenate), 1594 (annualize), 1478-1486 (orden),
  1436 y 1452-1454 (lee `Config_MOMF_T1_A.yaml` / `Main_Scenario`), 193 y 1009 (`conversion_format.yaml`)
- `scripts/pipeline/patch_reserve_margin_repair_careful_xlsx.py:16` (import de `_careful.py`)
- `scripts/pipeline/B1_Compiler.py:36` (import B1b)
- `scripts/pipeline/B1b_Pre_solver_validation.py:41` (import `_xlsx_validation_core`)
- `scripts/pipeline/B1_Run_Compiler.py:190-215` (edita y restaura `Config_MOMF_T1_A.yaml`)
- `inputs/config/Config_MOMF_T1_AB.yaml`: 232-238 (fix_dispatch), 246-249 (veg_tx), 260-266 (transforms)
- `scripts/tests/test_relac_paths.py` (smoke de rutas; correrlo tras cualquier cambio de layout)
- Análisis previo de uso de scripts por carpeta: sesión 2026-09-10 (limpieza de `experimental/`,
  `fix_dispatch/`, `tools/`, renombrado `tx_chain/`).
