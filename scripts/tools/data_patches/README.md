# data_patches — parches de datos aplicados a `inputs/` (historia versionada)

Scripts que modificaron los xlsx de `inputs/` (antes `t1_confection/`) entre el 2026-07-23 y el
2026-09-01 y que NO estaban en el repo. Se versionan aquí como **historia reproducible**, no para
volver a correrlos: **todos sus cambios YA están aplicados en `inputs/`** (restaurados desde
`stash@{0}` el 2026-09-08, ver `docs/superpowers/plans/2026-09-08-diagnostico-estado-C-solves.md`).
Si se corren en modo aplicación sobre `inputs/` actual, los que tienen precondición fallan
("ya aplicado") y los idempotentes reescriben lo mismo; aun así, **no correrlos con `--apply` /
`DRY_RUN=False` sin necesidad real** (p. ej. tras un A3 que regenere los A-O).

Rutas: todos resuelven `inputs/` vía `scripts/common/relac_paths.py`
(`sys.path.insert(0, parents[2])` + `from common import relac_paths as P`). La lógica es la
original; solo cambiaron las constantes de ruta y las líneas de "Uso".

## Scripts

| Script | Qué hace | Archivos que toca | Aplicado | Modo seguro |
|---|---|---|---|---|
| `add_bds_storage.py` | Clona la familia SDS→BDS (`PWRSDS{C}XX`→`PWRBDS{C}XX`, `SDS{C}XX01`→`BDS{C}XX01`) sobre el nodo no renovable `ELC{C}XX02`. Purge-and-reinsert idempotente según `COUNTRIES`. También inserta `BDS{C}XX01` en `xtra_scen.Storage` de `Config_MOMF_T1_A.yaml` y `BDS`/`PWRBDS` en `Config_MOMF_T1_AB.yaml`. | `A-O_AR_Model_Base_Year.xlsx` (Secondary), `A-O_AR_Projections.xlsx` (Secondary), `A-O_Parametrization.xlsx` (Fixed Horizon Parameters, Secondary Techs, VariableCost) de los 4 escenarios; `A2_Extra_Inputs/A-Xtra_Storage.xlsx` (3 hojas); los 2 YAML de `inputs/config/` | 2026-09-04 con `COUNTRIES = ["CHL", "PER"]` (16 filas en Xtra: 4+4+8; por escenario 4/4/4/22/2 filas) | `DRY_RUN` es una **constante del módulo** (`False` por defecto). Solo: `python -c "import add_bds_storage as b; b.run(countries=['CHL','PER'], dry_run=True, backup=False)"` desde esta carpeta |
| `validate_bds_structure.py` | Auditor post-aplicación (V1–V10 sobre xlsx y YAML; V11 opcional sobre un `Pre_processed_*.txt`). Solo lectura. | lee los mismos archivos | — | `python -c "import validate_bds_structure as v; v.audit(countries=['CHL','PER'])"` (con la lista por defecto de 19 países V1 falla, porque solo se clonaron CHL y PER) |
| `test_add_bds_storage.py` | Test del clonador en un sandbox temporal (copia de `inputs/`); no toca archivos reales. | copia a `%TEMP%/bds_sandbox_*` | — | `python scripts/tools/data_patches/test_add_bds_storage.py` |
| `patch_nueva_capacidad_2040_tx_advance.py` | (1) Pisos `TotalAnnualMinCapacityInvestment` 2040-2050 para 24 techs, **solo OPT**, leídos de `Nueva_Capacidad_2040+_LAC - copia.xlsx` (dataset externo en `Downloads/_Dataset_Transmission/`, ruta `--xlsx`); fija `Projection.Mode='User defined'`. (2) Adelanto de interconexiones en los 4 escenarios: `TRNCOLXXPANXX` RC 0.4 y UpperLimit 12.614 desde 2029; `TRNBOLXXBRAXX` RC 0.42 y UpperLimit 13.245 desde 2032. | `A-O_Parametrization.xlsx` / Secondary Techs (4 escenarios) | 2026-08-13 14:02 — log `nueva_capacidad_tx_changes_20260813_140245.json` (396 celdas: 200 pisos OPT + 8 RC y 41 UL por escenario) | `--dry-run` (requiere el xlsx externo; con `--only-tx` no lo necesita) |
| `patch_open_maxcaps_pisos_OPT.py` | En OPT, donde el piso nuevo supera el tope `TotalAnnualMaxCapacityInvestment`, abre el tope a `piso × 1.01` (precedente VGB). Celdas/filas `EMPTY` = sin tope, no se tocan. | `A1_Outputs_OPT/A-O_Parametrization.xlsx` / Secondary Techs | 2026-08-13 14:25 — log `open_maxcaps_pisos_OPT_20260813_142555.json` (82 celdas) | `--dry-run` (hoy reporta 0 conflictos) |
| `patch_rpo_operationallife.py` | `OperationalLife` 20 → 50 en todas las filas cuyo Tech contiene `RPO` (`RNWRPO*`, `TRNRPO*`: 38 techs). Precondición: todas en 20; si no, no toca el escenario. | `A-O_Parametrization.xlsx` / Fixed Horizon Parameters, col. H (4 escenarios) | 2026-09-01 (backups `.bak_20260901_*` en el stash) | dry-run por defecto; `--apply` escribe. Hoy reporta "NO SE SUSTITUYE: Value = 50" (ya aplicado) |
| `patch_rnwtrnbraxx_residualcapacity.py` | `ResidualCapacity` de `RNWTRNBRAXX` 52.990319556 → 85.40 en I..AJ (2023-2050). Precondición: las 28 celdas en 52.99. | `A-O_Parametrization.xlsx` / Demand Techs, fila 676 (4 escenarios) | 2026-09-02 | dry-run por defecto; `--apply` escribe. Hoy reporta "NO SE SUSTITUYE: = 85.4" (ya aplicado) |
| `add_fuentes_sheet.py` | Agrega/reemplaza la hoja documental **`Fuentes`** (fuente, archivo/hoja de origen y transformación por bloque de datos) al final de cada libro, leyendo la tabla maestra `inputs/config/data_sources.csv` (columna `Archivo` admite `A|B`). Idempotente. Sin columnas de años → `sync_historical_from_bau.py` la salta; `B1_Compiler.py` la excluye igual que `growth_formula`. | `A-O_Parametrization.xlsx` y `A-O_Demand.xlsx` de los 4 escenarios; `A2_Extra_Inputs/A-Xtra_Storage.xlsx`; plantillas `inputs/Miscellaneous/{A-O_Parametrization,A-O_Demand,A-Xtra_Storage}.xlsx` | 2026-09-14 (78 / 23 / 5 filas por tipo de libro) | dry-run por defecto; `--apply` escribe; `--no-templates` omite `Miscellaneous/`. Test: `python scripts/tools/data_patches/test_add_fuentes_sheet.py` |

Los dos JSON son los logs `old → new` por celda que generaron los parches del 2026-08-13 al aplicarse
(originalmente en `A1_Outputs/`; se mueven aquí porque `A1_Outputs/` está en `inputs/` y `*log*` cae en
`.gitignore`).

El sexto cambio de datos del mismo lote — la **demanda OLADE** en `A-O_Demand.xlsx` (D2 con
`DemandFromOLADE=YES`, `TradeBalanceDemandAdjustment=NO`; p. ej. `ELCARGXX03` 2023 = 564.3) — no tiene
script aquí: lo produce `scripts/pipeline/D2_update_secondary_techs.py` desde `Secondary_Techs_Editor.xlsx`.

## Orden de la cadena (si hay que re-aplicar tras regenerar los A-O)

```
A3 (regenera A-O_* y BORRA BDS)
 -> add_bds_storage.py                       (COUNTRIES = ["CHL", "PER"])
 -> patch_nueva_capacidad_2040_tx_advance.py (pisos OPT 2040+ + TRN COL-PAN / BOL-BRA)
 -> patch_open_maxcaps_pisos_OPT.py          (Max = piso x 1.01 donde Min > Max)
 -> patch_rpo_operationallife.py --apply     (OL RPO 20 -> 50)
 -> patch_rnwtrnbraxx_residualcapacity.py --apply (RC 52.99 -> 85.4)
 -> add_fuentes_sheet.py --apply             (hoja documental Fuentes; A3 la borra al regenerar)
 -> B1 -> B2
```

`validate_bds_structure.py` después de `add_bds_storage.py`; `D2_update_secondary_techs` y B1b son
seguros en cualquier punto (editan por match de Tech).

## Advertencias

- La hoja `Fuentes` es solo documental. Para cambiar una fuente, editar `inputs/config/data_sources.csv` y
  volver a correr `add_fuentes_sheet.py --apply` (no editar la hoja a mano: se reescribe entera).

- **A3 regenera los A-O y borra BDS** (y pisa cualquier edición manual de Secondary Techs / Fixed Horizon
  Parameters). Después de A3 hay que re-correr la cadena completa antes de B1.
- `add_bds_storage.py` escribe 13 xlsx + 2 YAML de una vez; con `BACKUP=True` deja copias en
  `inputs/_bds_backups/<timestamp>/` (ignorado por git).
- Los parches de OL y RC exigen el valor "viejo" exacto: sobre `inputs/` actual no hacen nada (correcto).
- Estado al 2026-09-08: los xlsx tienen los 6 cambios y los YAML de `inputs/config/` tienen `BDSCHLXX01`/
  `BDSPERXX01` en `xtra_scen.Storage` (Config A) y `PWRBDS` en `activity_upper_limit_exclude_prefixes`
  (Config AB). B1 arma el set STORAGE desde ese YAML: si un A3 o una edición lo pierde, `STORAGE.csv` de
  `outputs/A2_Output_Params/` deja de reproducir el versionado. El auditor (V7/V9) lo detecta.
