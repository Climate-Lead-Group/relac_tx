# Diagnóstico: por qué el estado C (B1+B2 en layout nuevo, kt0031) no reproduce A=B

**Fecha:** 2026-09-08 · **Rama:** `restructure/inputs-scripts-outputs` · **Para ejecutar en otra sesión / otra máquina**

## 1. Síntoma

Solves de los seis escenarios (BAC, ISR, ISRWF, OPC, VSR, VSRWF): A y B coinciden entre sí; C no.

| | A=B | C | Δ (C − A) |
|---|---|---|---|
| Restricciones (BAC) | 843 332 | 832 280 | **−11 052** |
| Variables (todos) | 608 272 | 603 904 | **−4 368** |
| Objetivo BAC | 1 152 123 | 6 731 569 | ×5.8 |
| Objetivo ISR / VSR | 41.6 M / 42.2 M | 54.6 M / 54.6 M | +30 % |
| Objetivo ISRWF / VSRWF | 29.8 M / 30.7 M | 59.3 M / 60.2 M | ×2 |

Lectura inmediata: **el LP que entra al solver es distinto** (menos filas y menos columnas en los seis
escenarios, siempre la misma cantidad de variables de menos). No es semilla, hilos, versión de CPLEX ni
"optimal w/ unscaled infeasibilities": es el datafile. Menos variables = menos tecnologías/almacenamientos
en los sets; el salto del objetivo con backstop disparado (PWRBCK) es el síntoma típico de perder capacidad
residual o almacenamiento.

## 2. Hipótesis principal — confirmada en el repo (2026-09-08) y corregida en `inputs/` el mismo día

Los **seis cambios de datos** (cuatro del 2026-09-04 más la apertura de topes OPT y la demanda OLADE) viven en los
CSV de `outputs/A2_Output_Params/` (salida de B1, commiteada en `93adb77`/`62937e0`) pero **no vivían en los xlsx de
`inputs/` que B1 lee**. Cualquier re-ejecución de
B1, en cualquier layout y cualquier máquina, regenera `A2_Output_Params` desde los xlsx y los pierde. El
estado C corrió B1; A y B usaron el `A2_Output_Params` ya parcheado (o un `Executables/` previo).

Evidencia tomada en este clon (`git show`, openpyxl, sin ejecutar el pipeline):

| Cambio del 04-09 | En `inputs/` (xlsx que lee B1) | En `outputs/A2_Output_Params/BAU` (B1 output versionado) |
|---|---|---|
| Clon BDS (`BDS{C}XX01`, `PWRBDS{C}XX`) | `A-Xtra_Storage.xlsx`: **0** filas BDS | `STORAGE.csv`/`TECHNOLOGY.csv`: 2 filas BDS |
| `RNWTRNBRAXX` ResidualCapacity | `A-O_Parametrization.xlsx` Demand Techs: **52.990319556** | `ResidualCapacity.csv`: **85.4** |
| `RNWRPO*XX` OperationalLife | `A-O_Parametrization.xlsx` Fixed Horizon: **20** | `OperationalLife.csv`: **50.0** |
| Pisos MinCapInv 2040+ (solo OPT) + adelanto TRNCOLXXPANXX (2029) / TRNBOLXXBRAXX (2032) | `A-O_Parametrization.xlsx` Secondary Techs: **1** celda 2040+ en OPT, TRN entran 2033/2036 | `OPT/TotalAnnualMinCapacityInvestment.csv`: 201 celdas; TRN 2029/2032 |
| Topes OPT abiertos (`TotalAnnualMaxCapacityInvestment` = piso×1.01, 82 celdas) | `A1_Outputs_OPT/A-O_Parametrization.xlsx`: topes viejos (< piso) | `OPT/TotalAnnualMaxCapacityInvestment.csv`: piso×1.01 |
| Demanda OLADE (D2 con `DemandFromOLADE=YES`, `TradeBalanceDemandAdjustment=NO`) | `A-O_Demand.xlsx` ELCARGXX03 2023 = **558.83** | `SpecifiedAnnualDemand.csv` ELCARGXX03 2023 = **564.3** |

Los xlsx de `inputs/` no cambiaban de contenido desde antes del 04-09 (último commit que los tocó = el
`git mv` puro `6731992`). Los scripts que aplicaron esos cambios **no estaban en el repo ni en su historia**
(`add_bds_storage.py`, `validate_bds_structure.py`, `patch_rnwtrnbraxx_residualcapacity.py`,
`patch_nueva_capacidad_2040_tx_advance.py`, `patch_open_maxcaps_pisos_OPT.py`, `patch_rpo_operationallife.py`):
se aplicaron localmente sobre el clon viejo (layout `t1_confection/`) sin volver a commitear la fuente de verdad (xlsx).

**Fuente de verdad recuperada (2026-09-08):** `stash@{0}` de este repo ("wip: equalize-scenario-early-years-adjust-BAU-OPT
antes de clean-sirelac", 2026-09-03, sha `1d09222`) contiene los xlsx con los seis cambios ya aplicados. El stash tiene
un objeto corrupto (no xlsx), así que se extrajo archivo por archivo con `git show "stash@{0}:<ruta>"` (nunca `stash pop`):
44 xlsx (38 de `A1_Outputs/`, 4 de `A2_Extra_Inputs/`, `Secondary_Techs_Editor.xlsx`), md5 idéntico al blob del stash.
Los scripts de parche quedaron versionados en `scripts/tools/data_patches/` (con README y los JSON de aplicación).

Consecuencia secundaria ya visible: los `outputs/A2_Outputs_Params_otoole/{BAC,OPC}` versionados están
desfasados (sin BDS, 52.99, OL 20) frente a `BAU/OPT/INV/VGB/VSRWF`, que están al día. B2 los sobreescribe
con `copytree(base → derivado, dirs_exist_ok=True)` al resolver, así que no explican C, pero son un snapshot
inconsistente en git.

**Conclusión provisional:** la reestructuración no cambió el resultado; destapó que la fuente de verdad
(`inputs/`) está detrás de los artefactos derivados (`outputs/A2_Output_Params`). Queda confirmarlo con los
archivos de kt0031 (§3) y decidir cómo alinear (§4).

## 3. Plan de verificación (otra sesión)

Cada paso es barato y cierra o abre una rama del árbol. Orden recomendado.

### 3.1 Identidad de los tres estados (5 min)
Para A, B y C anotar: máquina, ruta del clon, `git rev-parse HEAD`, `git status --short` (¡xlsx modificados
sin commitear!), layout (viejo/nuevo), si se corrió B1 o solo B2, fecha, y los flags del YAML
(`solve_scenarios`, `parallel`, `cplex_threads`, `storage_delay_active`). Hipótesis: A y B **no** re-corrieron
B1 sobre los xlsx versionados; C sí.

### 3.2 Comparar el datafile del solver, no el .sol (10 min, decisivo)
Para BAC (el de mayor salto) y uno de sensibilidad (ISR):
```bash
# archivos: Executables/<S>_0/Pre_processed_<S>_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_VEGCON.txt
md5sum A/BAC.txt C/BAC.txt
diff <(grep -n "^set " A/BAC.txt) <(grep -n "^set " C/BAC.txt)          # ¿qué sets difieren?
diff <(sed -n '/^set STORAGE/,/;/p' A/BAC.txt) <(sed -n '/^set STORAGE/,/;/p' C/BAC.txt)
diff <(sed -n '/^set TECHNOLOGY/,/;/p' A/BAC.txt) <(sed -n '/^set TECHNOLOGY/,/;/p' C/BAC.txt) | grep -c "BDS"
grep -A3 "RNWTRNBRAXX" A/BAC.txt | grep -m1 -E "2023|85|52"; grep -A3 "RNWTRNBRAXX" C/BAC.txt | grep -m1 -E "2023|85|52"
```
Esperado si §2 es cierta: sets TECHNOLOGY/STORAGE de C sin `*BDS*`; `ResidualCapacity RNWTRNBRAXX` 85.4 en A vs
52.99 en C; `OperationalLife RNWRPO*`/`TRNRPO*` 50 vs 20; en OPC además faltan pisos 2040+ en
`TotalAnnualMinCapacityInvestment`. Si los datafiles son **idénticos** y aun así el .sol difiere, saltar a §3.5.

### 3.3 Subir aguas arriba hasta la primera divergencia (15 min)
Con `scripts/tools/verification/compare_manifests.py` (ya en el repo) sobre los dos árboles:
```bash
python scripts/tools/verification/compare_manifests.py manifest <arbol_A_o_B> old|new manA.json
python scripts/tools/verification/compare_manifests.py manifest <arbol_C> new manC.json
python scripts/tools/verification/compare_manifests.py diff manA.json manC.json
```
Ver en qué capa aparece la diferencia: `A2_Output_Params` (B1) → entonces la causa es xlsx vs CSV parcheados
(§2); `A2_Outputs_Params_otoole` pero no `A2_Output_Params` → problema en B2/templates; solo `Executables`
→ problema en la cadena de patchers/Tx chain. Comparar también `outputs/A2_Output_Params/BAU/*.csv` de C
contra los versionados en git (`git diff --no-index`): si C ≠ git, B1 regeneró y perdió los parches.

### 3.4 Confirmar la deriva xlsx ↔ CSV en kt0031 (5 min)
En el clon viejo de kt0031 (layout `t1_confection/`): `git status --short t1_confection/A1_Outputs
t1_confection/A2_Extra_Inputs` y buscar BDS / 85.4 / OL 50 en sus xlsx. Tres salidas posibles:
(a) xlsx locales modificados y con los cambios → los parches se aplicaron ahí y nunca se commitearon:
commitearlos resuelve todo; (b) xlsx sin cambios, CSV de A2 con cambios → los parches se aplicaron a los CSV
(o a un B1 output) y B1 nunca los tuvo: hay que reaplicarlos a los xlsx con los scripts originales;
(c) ninguno → los cambios llegaron por otra vía (revisar `Downloads`/`_bds_backups`/logs JSON de los parches).

### 3.5 Solo si los datafiles son idénticos: solver (10 min)
Comparar `cplex.log` de ambos lados: versión de CPLEX, `threads`, `randomseed`, tolerancias; el estado
"optimal w/ unscaled infeasibilities" aparece en ambos lados (OPC) así que no es la causa. Con LP idéntico y
misma versión/semilla, CPLEX es determinista; una diferencia aquí apuntaría a `parallel: True` compartiendo
`cplex.log`/`clone*.log` en `outputs/logs/` entre procesos (solo afecta al log, no al .sol).

### 3.6 Revisar los derivados versionados (5 min)
`outputs/A2_Outputs_Params_otoole/BAC` y `OPC` en git están desfasados. Decidir: re-commitear tras el próximo
B2 correcto, o dejar de versionar los otoole de derivados (B2 los regenera siempre desde la base).

## 4. Decisión y corrección (tras §3)

El estado correcto es **A=B con los seis cambios** (BDS, pisos OPT 2040+ y topes abiertos, TRN COL-PAN/BOL-BRA,
OL RPO 50, RC RNWTRNBRAXX 85.4, demanda OLADE). La demanda OLADE se adopta porque es la que usan el A2 versionado y los
solves de referencia. Para que cualquier máquina lo reproduzca desde `inputs/`:

1. ✅ **Hecho (2026-09-08).** Los seis scripts de parche (+ `test_add_bds_storage.py` y los 2 JSON de aplicación del
   2026-08-13) versionados en `scripts/tools/data_patches/` con rutas del layout nuevo (`relac_paths`) y README.
2. ✅ **Hecho (2026-09-08).** En vez de re-aplicar los parches, se restauraron los xlsx ya parcheados desde `stash@{0}`
   (ver §2). Verificado con openpyxl en los 4 escenarios: BDS 16 filas en Xtra (4/4/22 en
   Base_Year/Projections/Secondary Techs), RC RNWTRNBRAXX 85.4, OL RPO 50 (38 techs), TRN 2029/2032, pisos 2040+
   OPT=201 / BAU=1 / INV=1 / VGB=17, 0 conflictos Min>Max en OPT, demanda ARG 564.3 / BRA 2599.63.
   Orden documentado para BDS: tras A3 y antes de B1 (A3 regenera los A-O y borra BDS).
   También se agregaron a `inputs/config/Config_MOMF_T1_A.yaml` las entradas `BDSCHLXX01`/`BDSPERXX01` en
   `xtra_scen.Storage` y a `Config_MOMF_T1_AB.yaml` `PWRBDS` en `activity_upper_limit_exclude_prefixes` (B1 arma el set
   STORAGE desde ese YAML; el auditor `validate_bds_structure.py` pasa V1–V10 con CHL/PER).
   **Pendientes de decisión** (no se tocaron): (b) `OLADE_Config` del editor restaurado dice Residual/ActivityLower=YES, ActivityUpper=EXISTING_ONLY,
   TradeBalance=YES (el editor del clon de backup dice NO en los cuatro, coherente con la demanda generada);
   (c) el resto de xlsx del stash (`CapacityAndDistances`, `Demanda CireLAC_GTER_WEO`, `LAC_maxcap_tool*`, matrices
   OLADE, `Miscellaneous/`, `NO BORRAR…`, `Old_Inputs/`) no se restauró.
3. ✅ **Hecho (2026-09-08).** B1 corrido sobre `inputs/` restaurado (commits `fbfe827` + `b6a314f`): el resultado
   reproduce el estado A=B. `inputs/` volvió a ser la fuente de verdad.
4. ✅ **Hecho (2026-09-08).** B2 con el nuevo workflow reproduce los solves de referencia A=B: el estado C quedó cerrado.
5. ✅ **Hecho (2026-09-08).** Spec §13 y memorias actualizadas: la diferencia fue de datos, no de layout.

Atajo aceptable mientras tanto: correr **solo B2** (sin B1) sobre el `A2_Output_Params` versionado, que ya está
correcto. `run.py`/DVC volvería a lanzar B1: no usarlo hasta cerrar el punto 2.

## 5. Archivos a pasar a la sesión de análisis (histórico; ya no necesarios)

Prioridad 1 (bastan para cerrar §3.2 y §3.3; ~6 MB cada txt, comprimir):
- De **A o B** y de **C**, para BAC e ISR: `Executables/<S>_0/Pre_processed_<S>_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_VEGCON.txt`
  (es el datafile que recibe `glpsol -d`; el `.lp` no hace falta, pesa mucho más y se deriva de este).
- De ambos lados: `Executables/BAU_0/BAU_0.txt` (salida cruda de otoole, antes de la cadena) y
  `Pre_processed_BAU_0_StorageDelayN5_OpenBCK_RMCarefulXLSX.txt` — sitúan si la divergencia nace en A2/otoole
  o en los patchers. BAC deriva de BAU; para ISR pedir los de INV.
- De ambos lados: `outputs/model/osemosys_fast_preprocessed_storage_delay.txt` (o `t1_confection/…` en el viejo).
- Los `manifest_*.json` de `compare_manifests.py` de cada árbol (§3.3), o directamente `outputs/A2_Output_Params/BAU/`
  de C (47 MB en total; si pesa, solo `STORAGE.csv`, `TECHNOLOGY.csv`, `ResidualCapacity.csv`, `OperationalLife.csv`,
  `TotalAnnualMinCapacityInvestment.csv`).

Prioridad 2 (contexto):
- `B1.log` y `B2.log` de C; `cplex.log` de A/B y C (solo si §3.2 no muestra diferencias).
- Salida de `git rev-parse HEAD; git status --short` en los tres árboles y el `Config_MOMF_T1_AB.yaml` usado en C.
- Los `.sol` **no** son necesarios: la tabla del §1 ya prueba que el LP difiere; el .sol solo confirmaría el efecto.

Prioridad 3 (para la corrección del §4): los scripts `add_bds_storage.py`, `validate_bds_structure.py`,
`patch_rnwtrnbraxx_residualcapacity.py`, `patch_nueva_capacidad_2040_tx_advance.py`, `patch_open_maxcaps_pisos_OPT.py`
y el parche de OperationalLife RPO, tal como están en kt0031, para versionarlos.

## 6. Cierre (2026-09-08)

**Resultado replicable.** Con `inputs/` restaurado desde `stash@{0}` (commit `fbfe827`), los YAML de `inputs/config/` con
las entradas BDS y los scripts de parche versionados (`b6a314f`), el nuevo workflow `inputs/ → scripts/ → outputs/`
(B1 → B2 en el layout reestructurado) reproduce el resultado de referencia A=B: el estado C descrito en §1 ya no ocurre.
La reestructuración no cambió el resultado; la divergencia era de datos (xlsx detrás de los CSV derivados) y quedó
corregida en la fuente de verdad.

**Qué garantiza la replicabilidad a partir de aquí**

- Cualquier clon de la rama `restructure/inputs-scripts-outputs` desde `b6a314f` puede correr B1 → B2 desde `inputs/` y
  obtener el mismo LP y el mismo solve, sin parches locales ni artefactos externos.
- Los seis cambios de datos están en los xlsx versionados y su historia está en `scripts/tools/data_patches/README.md`.
- Si se vuelve a correr A3 (regenera los A-O y borra BDS), hay que re-aplicar la cadena documentada en ese README antes
  de B1; `validate_bds_structure.py` (V1–V10) detecta si falta algo, incluidos los YAML.
- Si se corre D2 con el `Secondary_Techs_Editor.xlsx` actual (OLADE_Config con `TradeBalanceDemandAdjustment=YES`),
  la demanda se regenera distinta a la versionada (ELCARGXX03 2023 pasaría de 564.3 a otro valor). Decisión del
  2026-09-08: se conserva el editor del stash tal cual; no correr D2 sin revisar esa configuración.

**Queda fuera** (decisiones abiertas, no bloquean): el resto de xlsx del stash listados en §4.2(c) y la limpieza de
`outputs/A2_Outputs_Params_otoole/{BAC,OPC}` versionados (§3.6).
