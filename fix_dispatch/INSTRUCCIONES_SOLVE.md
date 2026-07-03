# Instrucciones para re-correr BAU y OPT con pisos de despacho (provisional)

Para: Andrey. Autocontenido -- no requiere haber estado en las sesiones de debugging previas.

## 1. Que cambio

Varias centrales termicas (gas/oil/petroleo) tienen `MinCapacityInvestment > 0`
despues de 2026: el modelo esta OBLIGADO a construirlas. Pero no tienen
`TotalTechnologyAnnualActivityLowerLimit` (piso de despacho) para esos mismos
anos: el modelo es LIBRE de no despacharlas nunca. Resultado confirmado en los
outputs: ~10 GW de capacidad forzada con factor de planta (CF) < 5% despues de
2026 ("construyo la planta pero no la uso").

La correccion: anadir un piso de actividad (`TotalTechnologyAnnualActivityLowerLimit`)
para esas centrales, desde su ano de entrada en servicio hasta 2050, calculado
como `capacidad_forzada_GW x 31.536 x CF_contratado`. Los valores de CF_contratado
son PROVISIONALES: NGS = 0.40, OIL/PET = 0.10 (ver seccion 7).

El piso solo se AUMENTA nunca se reduce: si ya existia un piso legitimo (p.ej.
el piso 2023-2026 de la flota historica de MEX, ~830 PJ), ese piso se preserva
tal cual. Cada piso nuevo o aumentado pasa por una prueba de factibilidad
(`fix_dispatch/feasibility.py`) antes de escribirse: ningun piso puede exceder
la capacidad maxima, la disponibilidad, o el `TotalTechnologyAnnualActivityUpperLimit`
de la planta. Ningun piso infactible se escribe.

## 2. Archivos modificados

**Ningun archivo original se edita.** El script `fix_dispatch/write_floors.py`
produce COPIAS junto a los originales:

| Escenario | Original (sin tocar) | Copia con piso |
|---|---|---|
| BAU | `t1_confection/Executables/BAU_0/Pre_processed_BAU_0_StorageDelayN5_OpenBCK_RMCarefulXLSX.txt` | `t1_confection/Executables/BAU_0/Pre_processed_BAU_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt` |
| OPT | `t1_confection/Executables/OPT_0/Pre_processed_OPT_0_StorageDelayN5_OpenBCK_RMCarefulXLSX.txt` | `t1_confection/Executables/OPT_0/Pre_processed_OPT_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt` |

La copia es byte-identica al original EXCEPTO dentro del bloque
`TotalTechnologyAnnualActivityLowerLimit`, donde se agregan/aumentan filas
puntuales. Ningun otro bloque del archivo cambia.

**Detalle exacto de que filas cambiaron:** ver
[`input_comparison_report.md`](input_comparison_report.md) (y su version
`.csv` para analisis). Resumen: BAU recibe piso en 2 plantas (MEX gas, ECU
petroleo -- las unicas ya forzadas en BAU); OPT recibe piso en las 11 plantas
del "working set". Esta diferencia de alcance es intencional: es justo lo que
se quiere observar entre escenarios.

**IMPORTANTE -- estado actual: `Pre_processed_<ESC>_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt` TODAVIA NO
EXISTE.** En la sesion de preparacion de este pipeline solo se corrio
`write_floors.py` en modo `--dry-run` (valida pero no escribe nada) para
confirmar que los 271 pisos nuevos/aumentados pasan la prueba de factibilidad
(0 rechazados). El Paso 0 de la seccion 3 es tu primera ejecucion REAL del
script -- no basta con haber visto el resultado del dry-run, hay que correr
el comando sin `--dry-run` para que las copias se escriban de verdad. Si al
llegar a este punto ya corriste el Paso 0 y las copias existen, puedes saltar
directo al Paso 1 ("resolver").

## 3. Que hacer

Ejecutar todo desde la raiz del repo salvo donde se indique lo contrario.
Requiere el mismo entorno que usas para correr `B2_Executing_OG_Model.py`
normalmente (GLPK/`glpsol` y `cplex` en el PATH).

### Paso 0 -- generar las copias FLOORED.txt (si no existen aun)

```
python fix_dispatch/write_floors.py --scenarios BAU OPT
```

Esto lee `fix_dispatch/candidate_floors.csv`, corre la prueba de factibilidad,
y escribe las dos copias de la tabla anterior. Al final imprime un resumen
(filas nuevas / aumentadas / sin cambio / rechazadas por infactibles -- en la
corrida de validacion de esta sesion: 0 rechazadas). Si aparece algun
`SKIP-INFEASIBLE`, revisa `fix_dispatch/upstream_floor_rows.csv` y detente
(ver seccion 6).

### Paso 1 -- resolver cada escenario (BAU, luego OPT)

El pipeline (`t1_confection/B2_Executing_OG_Model.py`, config actual:
`solver: cplex`, `storage_delay_active/open_pwrbck_active/reserve_margin_xlsx_active: True`)
resuelve asi para el archivo original. Para el FLOORED.txt, corre el mismo
encadenamiento de comandos sustituyendo el archivo de datos, **desde el
directorio `t1_confection/`**:

Para `<ESC>` en `BAU`, `OPT` (uno a la vez):

```
cd t1_confection

REM 1) Generar la matriz LP a partir del datafile FLOORED
glpsol -m osemosys_fast_preprocessed_storage_delay.txt -d Executables\<ESC>_0\Pre_processed_<ESC>_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt --wlp Executables\<ESC>_0\Pre_processed_<ESC>_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_output.lp --check

REM 2) Resolver con CPLEX (mismos threads/seed que usa el pipeline: 12 / 12345)
cplex -c "read Executables\<ESC>_0\Pre_processed_<ESC>_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_output.lp" "set threads 12" "set randomseed 12345" "set parallel 1" "optimize" "write Executables\<ESC>_0\Pre_processed_<ESC>_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_output.sol"

REM 3) Convertir la solucion a CSVs otoole (crear la carpeta de salida primero)
mkdir ..\fix_dispatch\solved_FLOORED\<ESC>\Outputs
otoole results cplex csv Executables\<ESC>_0\Pre_processed_<ESC>_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_output.sol ..\fix_dispatch\solved_FLOORED\<ESC>\Outputs csv A2_Outputs_Params_otoole\<ESC> Miscellaneous\conversion_format.yaml 2> Executables\<ESC>_0\Pre_processed_<ESC>_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_output.log
```

Notas:
- Estos comandos son el mismo encadenamiento que usa `main_executer()` en
  `B2_Executing_OG_Model.py` (lineas ~890-970), solo que apuntando al datafile
  FLOORED en vez del original, y con un prefijo de salida `_FLOORED_output`
  para no pisar los resultados de la corrida original (que quedan intactos en
  el mismo folder).
- Revisa el `.log` si CPLEX termina con error o "infeasible" -- ver seccion 6.
- Tiempo de corrida: no esta documentado con precision en este repo. Es el
  mismo tamano de matriz que una corrida normal de un escenario (el piso anade
  restricciones puntuales, no cambia la escala del problema), asi que espera
  aproximadamente el mismo tiempo que una corrida normal de BAU u OPT.

### Paso 2 -- armar el CSV combinado (inputs+outputs) para BAU+OPT

El CSV final de 89 columnas (`Future,Scenario,REGION,YEAR,TECHNOLOGY,...`) lo
arma la funcion `concatenate_all_scenarios()` en `B2_Executing_OG_Model.py`
(lineas ~1153-1312): toma `<ESC>_Input.csv` y `<ESC>_Output.csv` por escenario
y les agrega las columnas `Future`/`Scenario`.

Usa tu flujo habitual de concatenacion apuntado a las salidas FLOORED de
`fix_dispatch/solved_FLOORED/<ESC>/Outputs` (que generaste en el Paso 1) para
producir un CSV combinado en el mismo formato que el CSV base. Guardalo como:

```
fix_dispatch/solved_FLOORED/RELAC_TX_FLOORED_Combined_Inputs_Outputs.csv
```

Si prefieres, corre `concatenate_files/concatenate_relac.py <outputs_folder> <output_file_prefix>`
por escenario primero (asi es como se genera cada `<ESC>_Output.csv` normalmente),
y luego el paso de union de escenarios que ya usas para el dashboard.

## 4. Como verificar

```
python fix_dispatch/test_outputs.py --csv fix_dispatch/solved_FLOORED/RELAC_TX_FLOORED_Combined_Inputs_Outputs.csv
```

El script corre 4 chequeos de solo lectura (no modifica nada):

1. **Cumplimiento de piso**: para cada fila de `candidate_floors.csv`,
   verifica `TotalTechnologyAnnualActivity >= floor_PJ`.
2. **CF objetivo**: para cada planta del working set, compara el CF real
   (`actividad / (capacidad x 31.536)`) contra el CF contratado, con 10% de
   tolerancia.
3. **Separacion de escenarios**: generacion fosil total, participacion
   renovable, costo total del sistema, emisiones CO2, y numero de tecnologias
   despachables activas (CF > 5%) -- BAU vs OPT lado a lado.
4. **Capacidad ociosa**: repite el diagnostico de CF < 5% despues de 2026
   sobre las plantas del working set -- ya no deberian aparecer ociosas.

Corrido contra el CSV base (sin piso) en esta sesion, el chequeo 1 falla en
540 de 562 filas (el bug confirmado); el chequeo 4 muestra las 11 plantas
ociosas. Eso es lo esperado del CSV base. Con tu corrida FLOORED, ambos deben
pasar (ver criterios de exito).

## 5. Criterios de exito

- [ ] El modelo resuelve sin errores de infactibilidad (BAU y OPT).
- [ ] Todas las restricciones de piso se respetan: `TotalTechnologyAnnualActivity >= floor_PJ`
      para cada (escenario, tecnologia, ano) en `candidate_floors.csv` (chequeo 1 = 0 FAIL).
- [ ] Las plantas del working set operan a CF >= 90% del CF contratado
      (0.40 para NGS, 0.10 para OIL/PET) despues de 2026 (chequeo 2 = 0 BELOW_TARGET).
- [ ] Ningun despacho de backstop (si el backstop aparece generando, los
      pisos son demasiado agresivos -- revisar antes de reportar exito).
- [ ] BAU y OPT muestran diferencias materiales en: generacion fosil total
      (PJ/ano), participacion renovable (%), y costo total del sistema
      (chequeo 3).
- [ ] Las plantas forzadas del working set YA NO aparecen como inactivas
      (CF < 5%) en el diagnostico de capacidad ociosa (chequeo 4 = 0 filas).

## 6. Que hacer si falla

- **Infactible al resolver (CPLEX/GLPK reporta infeasible):** revisa cual
  piso esta atado. `write_floors.py` ya filtro los pisos que el chequeo de
  factibilidad (`feasibility.py`) marca como imposibles ANTES de escribirlos
  (en la validacion de esta sesion: 0 rechazados de 271), asi que una
  infactibilidad real en el solver indica una interaccion no capturada por
  ese chequeo (p.ej. margen de reserva, restriccion de transmision). No
  intentes depurarlo tu mismo: reporta con el mensaje de infactibilidad del
  solver y el `.log` correspondiente.
- **El backstop despacha:** los pisos son demasiado agresivos para la
  capacidad/demanda disponible ese ano. Reporta con la salida de
  `test_outputs.py` (chequeo 3, revisa si `PWRBCK*` aparece con actividad > 0).
- **Cualquier otro fallo en los criterios de exito:** no depures, reporta con
  la salida completa de `test_outputs.py` (los 4 CSVs que produce:
  `test_floor_compliance.csv`, `test_cf_targets.csv`,
  `test_scenario_separation.csv`, `test_idle_capacity.csv`) y el `.log` del
  solver.

## 7. Nota

Estos valores de CF (NGS 0.40, OIL/PET 0.10) son **PROVISIONALES**, pendientes
de revision con los planes nacionales de cada pais. Esta corrida es para
validar el MECANISMO y la DIRECCION del efecto (que las plantas forzadas
efectivamente despachen, y que BAU/OPT se separen), no las magnitudes finales.

Cuando lleguen los valores calibrados: se edita `fix_dispatch/candidate_floors.csv`
(o `CF_BY_FUEL` en `fix_dispatch/make_candidates.py` y se re-corre ese script),
se vuelve a correr `write_floors.py`, y se repite este mismo procedimiento.
Nada mas del pipeline cambia.
