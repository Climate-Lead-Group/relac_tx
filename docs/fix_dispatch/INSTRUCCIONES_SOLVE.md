# Instrucciones para re-correr BAU, INV, OPT y VGB con pisos de despacho

Para: Andrey. Autocontenido, no requiere haber estado en las sesiones de debugging previas.

## 1. Que cambio

Varias centrales termicas (carbon/gas/petroleo/diesel) tienen
`MinCapacityInvestment > 0` despues de 2026: el modelo esta OBLIGADO a
construirlas. Pero no todas tienen `TotalTechnologyAnnualActivityLowerLimit`
(piso de despacho) para esos mismos anos: el modelo es LIBRE de no
despacharlas nunca. Resultado confirmado en los outputs: ~10 GW de capacidad
forzada con factor de planta (CF) menor a 5% despues de 2026 ("construyo la
planta pero no la uso").

La correccion actual (rediseno completo, ya no el parche de 11 plantas de la
version anterior de este documento) anade un piso de actividad a TODA la
flota fosil residual + forzada del modelo (carbon, gas, petroleo, diesel;
nuclear queda excluido a proposito), no solo a las plantas sin piso previo.
El motivo: las plantas que YA tenian un piso 2023-2026 (MEX, BRA, ARG, etc.)
tenian ese piso limitado a 2026; de 2027 en adelante esas flotas grandes
quedaban sin ningun piso y el optimizador las apagaba. Ahora se cubre
`relac_io.nonren_floor_techs(escenario)`: ~51 tecnologias en total repartidas
entre los 4 escenarios, anos 2027-2050 (2023-2026 se mantiene congelado, sin
ningun cambio).

El piso se calcula como:

```
capacidad_GW(tech, ano) = ResidualCapacity(tech, ano) + capacidad_forzada_acumulada(tech, ano)
piso_PJ = capacidad_GW x 31.536 x CF_contratado(escenario, tech, ano)
```

Hay dos perfiles de escenario (decision del PI, 2026-07-03):

- **COMMITTED = OPT, VGB** ("usa lo que construyes"): CF plano 2027-2050,
  igual al "CF comprometido" del tech (ver abajo). Estos dos escenarios
  tambien fuerzan aproximadamente 3 veces mas capacidad fosil que BAU/INV.
- **PERMISSIVE = BAU, INV** ("deja que la flota se apague gradualmente"): CF
  anclado al MISMO "CF comprometido" que usa COMMITTED, plano hasta 2030, y
  despues declina linealmente hasta `min(CF_comprometido, 0.05)` en 2050.

El "CF comprometido" de cada tecnologia sale de una jerarquia de fuentes, en
este orden: `plan_grounded` (numero calculado a partir de los planes
nacionales de expansion, ver `cf_table_full.py` en la carpeta de trabajo
`_Dataset_Power`, 37 tecnologias) -> `historical_implied` (el CF que ya
implica el piso 2023-2026 existente de esa misma tecnologia) -> un
`fuel_fallback` regional por tipo de combustible si no hay ninguna de las dos
anteriores. Como PERMISSIVE nunca supera a su propio ancla, BAU/INV nunca
puede superar a OPT/VGB en ningun ano ni tecnologia: esto se verifica con
`fix_dispatch/preflight_separation.py` antes de resolver (ver seccion 4).

Los valores de CF ya NO son provisionales genericos por combustible (la
version anterior de este documento usaba NGS = 0.40, OIL/PET = 0.10 para
todo el "working set" de 11 plantas). Ahora cada tecnologia tiene, cuando el
material lo permite, un CF propio calculado del plan nacional correspondiente
(ver seccion 7 sobre que tan solido es cada numero).

El piso solo se AUMENTA, nunca se reduce: si ya existia un piso legitimo
(p.ej. el piso 2023-2026 de la flota historica de MEX, ~830 PJ), ese piso se
preserva tal cual. Cada piso nuevo o aumentado pasa por una prueba de
factibilidad (`fix_dispatch/feasibility.py`) antes de escribirse: ningun piso
puede exceder la capacidad maxima, la disponibilidad, o el
`TotalTechnologyAnnualActivityUpperLimit` de la planta. Ningun piso
infactible se escribe.

## 2. Archivos modificados

**Ningun archivo original se edita.** El script `fix_dispatch/write_floors.py`
produce COPIAS junto a los originales, una por cada uno de los 4 escenarios:

| Escenario | Original (sin tocar) | Copia con piso |
|---|---|---|
| BAU | `t1_confection/Executables/BAU_0/Pre_processed_BAU_0_StorageDelayN5_OpenBCK_RMCarefulXLSX.txt` | `t1_confection/Executables/BAU_0/Pre_processed_BAU_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt` |
| INV | `t1_confection/Executables/INV_0/Pre_processed_INV_0_StorageDelayN5_OpenBCK_RMCarefulXLSX.txt` | `t1_confection/Executables/INV_0/Pre_processed_INV_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt` |
| OPT | `t1_confection/Executables/OPT_0/Pre_processed_OPT_0_StorageDelayN5_OpenBCK_RMCarefulXLSX.txt` | `t1_confection/Executables/OPT_0/Pre_processed_OPT_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt` |
| VGB | `t1_confection/Executables/VGB_0/Pre_processed_VGB_0_StorageDelayN5_OpenBCK_RMCarefulXLSX.txt` | `t1_confection/Executables/VGB_0/Pre_processed_VGB_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt` |

La copia es byte-identica al original EXCEPTO dentro del bloque
`TotalTechnologyAnnualActivityLowerLimit`, donde se agregan/aumentan filas
puntuales. Ningun otro bloque del archivo cambia, y el bloque 2023-2026 de
ese mismo parametro tampoco cambia (congelado por diseno).

**Detalle exacto de que filas cambiaron:** ver
[`input_comparison_report.md`](input_comparison_report.md) (y su version
`.csv` para analisis). Alcance actual: ~51 tecnologias, 3956 filas de piso
candidato entre los 4 escenarios (BAU=INV=961 filas cada uno, OPT=VGB=1017
filas cada uno). Esta diferencia de alcance y magnitud entre COMMITTED y
PERMISSIVE es intencional: es justo lo que se quiere observar entre
escenarios.

**Estado actual:** las cuatro copias
`Pre_processed_<ESC>_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt` YA
EXISTEN (se generaron al cerrar el rediseno completo). Si vuelves a correr
`fix_dispatch/make_candidates.py` (por ejemplo porque cambio un CF), debes
volver a correr `write_floors.py` sin `--dry-run` para que las copias
reflejen el nuevo `candidate_floors.csv` antes de resolver.

## 3. Que hacer

Ejecutar todo desde la raiz del repo salvo donde se indique lo contrario.
Requiere el mismo entorno que usas para correr `B2_Executing_OG_Model.py`
normalmente (GLPK/`glpsol` y `cplex` en el PATH).

### Paso 0 -- generar (o regenerar) las copias FLOORED.txt

```
python fix_dispatch/write_floors.py
```

(o `python fix_dispatch/write_floors.py --scenarios BAU OPT` para un
subconjunto). Esto lee `fix_dispatch/candidate_floors.csv`, corre la prueba
de factibilidad, y escribe las copias de la tabla anterior. Al final imprime
un resumen (filas nuevas / aumentadas / sin cambio / rechazadas por
infactibles). Corre primero con `--dry-run` si quieres revisar el resumen
sin escribir nada. Si aparece algun `SKIP-INFEASIBLE`, revisa
`fix_dispatch/upstream_floor_rows.csv` y detente (ver seccion 6).

### Paso 1 -- resolver cada escenario (BAU, INV, OPT, VGB)

El pipeline (`t1_confection/B2_Executing_OG_Model.py`, config actual:
`solver: cplex`, `storage_delay_active/open_pwrbck_active/reserve_margin_xlsx_active: True`)
resuelve asi para el archivo original. Para el FLOORED.txt, corre el mismo
encadenamiento de comandos sustituyendo el archivo de datos, **desde el
directorio `t1_confection/`** (`cd t1_confection` una sola vez). Los cuatro
bloques siguientes son identicos salvo el escenario: copia y pega completo el
bloque del escenario que vas a resolver (uno a la vez).

**BAU:**

```
REM 1) Generar la matriz LP a partir del datafile FLOORED
glpsol -m osemosys_fast_preprocessed_storage_delay.txt -d Executables\BAU_0\Pre_processed_BAU_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt --wlp Executables\BAU_0\Pre_processed_BAU_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_output.lp --check

REM 2) Resolver con CPLEX (mismos threads/seed que usa el pipeline: 12 / 12345)
cplex -c "read Executables\BAU_0\Pre_processed_BAU_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_output.lp" "set threads 12" "set randomseed 12345" "set parallel 1" "optimize" "write Executables\BAU_0\Pre_processed_BAU_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_output.sol"

REM 3) Convertir la solucion a CSVs otoole (crear la carpeta de salida primero)
mkdir ..\fix_dispatch\solved_FLOORED\BAU\Outputs
otoole results cplex csv Executables\BAU_0\Pre_processed_BAU_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_output.sol ..\fix_dispatch\solved_FLOORED\BAU\Outputs csv A2_Outputs_Params_otoole\BAU Miscellaneous\conversion_format.yaml 2> Executables\BAU_0\Pre_processed_BAU_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_output.log
```

**INV:**

```
REM 1) Generar la matriz LP a partir del datafile FLOORED
glpsol -m osemosys_fast_preprocessed_storage_delay.txt -d Executables\INV_0\Pre_processed_INV_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt --wlp Executables\INV_0\Pre_processed_INV_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_output.lp --check

REM 2) Resolver con CPLEX (mismos threads/seed que usa el pipeline: 12 / 12345)
cplex -c "read Executables\INV_0\Pre_processed_INV_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_output.lp" "set threads 12" "set randomseed 12345" "set parallel 1" "optimize" "write Executables\INV_0\Pre_processed_INV_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_output.sol"

REM 3) Convertir la solucion a CSVs otoole (crear la carpeta de salida primero)
mkdir ..\fix_dispatch\solved_FLOORED\INV\Outputs
otoole results cplex csv Executables\INV_0\Pre_processed_INV_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_output.sol ..\fix_dispatch\solved_FLOORED\INV\Outputs csv A2_Outputs_Params_otoole\INV Miscellaneous\conversion_format.yaml 2> Executables\INV_0\Pre_processed_INV_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_output.log
```

**OPT:**

```
REM 1) Generar la matriz LP a partir del datafile FLOORED
glpsol -m osemosys_fast_preprocessed_storage_delay.txt -d Executables\OPT_0\Pre_processed_OPT_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt --wlp Executables\OPT_0\Pre_processed_OPT_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_output.lp --check

REM 2) Resolver con CPLEX (mismos threads/seed que usa el pipeline: 12 / 12345)
cplex -c "read Executables\OPT_0\Pre_processed_OPT_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_output.lp" "set threads 12" "set randomseed 12345" "set parallel 1" "optimize" "write Executables\OPT_0\Pre_processed_OPT_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_output.sol"

REM 3) Convertir la solucion a CSVs otoole (crear la carpeta de salida primero)
mkdir ..\fix_dispatch\solved_FLOORED\OPT\Outputs
otoole results cplex csv Executables\OPT_0\Pre_processed_OPT_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_output.sol ..\fix_dispatch\solved_FLOORED\OPT\Outputs csv A2_Outputs_Params_otoole\OPT Miscellaneous\conversion_format.yaml 2> Executables\OPT_0\Pre_processed_OPT_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_output.log
```

**VGB:**

```
REM 1) Generar la matriz LP a partir del datafile FLOORED
glpsol -m osemosys_fast_preprocessed_storage_delay.txt -d Executables\VGB_0\Pre_processed_VGB_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt --wlp Executables\VGB_0\Pre_processed_VGB_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_output.lp --check

REM 2) Resolver con CPLEX (mismos threads/seed que usa el pipeline: 12 / 12345)
cplex -c "read Executables\VGB_0\Pre_processed_VGB_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_output.lp" "set threads 12" "set randomseed 12345" "set parallel 1" "optimize" "write Executables\VGB_0\Pre_processed_VGB_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_output.sol"

REM 3) Convertir la solucion a CSVs otoole (crear la carpeta de salida primero)
mkdir ..\fix_dispatch\solved_FLOORED\VGB\Outputs
otoole results cplex csv Executables\VGB_0\Pre_processed_VGB_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_output.sol ..\fix_dispatch\solved_FLOORED\VGB\Outputs csv A2_Outputs_Params_otoole\VGB Miscellaneous\conversion_format.yaml 2> Executables\VGB_0\Pre_processed_VGB_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_output.log
```

Notas:
- Estos comandos son el mismo encadenamiento que usa `main_executer()` en
  `B2_Executing_OG_Model.py` (lineas ~890-970), solo que apuntando al
  datafile FLOORED en vez del original, y con un prefijo de salida
  `_FLOORED_output` para no pisar los resultados de la corrida original (que
  quedan intactos en el mismo folder).
- Revisa el `.log` si CPLEX termina con error o "infeasible" -- ver seccion 6.
- Tiempo de corrida: no esta documentado con precision en este repo. Es el
  mismo tamano de matriz que una corrida normal de un escenario (el piso
  anade restricciones puntuales, no cambia la escala del problema), asi que
  espera aproximadamente el mismo tiempo que una corrida normal de cada
  escenario.

### Paso 2 -- armar el CSV combinado (inputs+outputs) para los 4 escenarios

El CSV final de 89 columnas (`Future,Scenario,REGION,YEAR,TECHNOLOGY,...`) lo
arma la funcion `concatenate_all_scenarios()` en `B2_Executing_OG_Model.py`
(lineas ~1153-1312): toma `<ESC>_Input.csv` y `<ESC>_Output.csv` por
escenario y les agrega las columnas `Future`/`Scenario`.

Usa tu flujo habitual de concatenacion apuntado a las salidas FLOORED de
`fix_dispatch/solved_FLOORED/<ESC>/Outputs` (que generaste en el Paso 1) para
producir un CSV combinado en el mismo formato que el CSV base. Guardalo como:

```
fix_dispatch/solved_FLOORED/RELAC_TX_FLOORED_Combined_Inputs_Outputs.csv
```

Si prefieres, corre primero `concatenate_relac.py` por escenario (asi es como
se genera cada `<ESC>_Output.csv` normalmente; el script agrega el `.csv` al
segundo argumento), **desde la raiz del repo**:

```
python concatenate_files/concatenate_relac.py fix_dispatch/solved_FLOORED/BAU/Outputs fix_dispatch/solved_FLOORED/BAU/BAU_Output
python concatenate_files/concatenate_relac.py fix_dispatch/solved_FLOORED/INV/Outputs fix_dispatch/solved_FLOORED/INV/INV_Output
python concatenate_files/concatenate_relac.py fix_dispatch/solved_FLOORED/OPT/Outputs fix_dispatch/solved_FLOORED/OPT/OPT_Output
python concatenate_files/concatenate_relac.py fix_dispatch/solved_FLOORED/VGB/Outputs fix_dispatch/solved_FLOORED/VGB/VGB_Output
```

y luego el paso de union de escenarios que ya usas para el dashboard.

## 4. Como verificar

**Antes de resolver** (opcional pero recomendado, es una compuerta de solo
lectura sobre los insumos, no requiere corrida del modelo):

```
python fix_dispatch/preflight_separation.py
```

Compara el piso fosil como porcentaje de la demanda electrica (identica en
los 4 escenarios) entre BAU-vs-OPT e INV-vs-VGB. Falla (exit code 1) si
BAU/INV llegara a superar a OPT/VGB en algun (tecnologia, ano), o si la
brecha se invierte despues de 2035. Si este script ya paso en la sesion en
que se genero `candidate_floors.csv`, no hace falta volver a correrlo salvo
que hayas tocado los CFs.

**Despues de resolver:**

```
python fix_dispatch/test_outputs.py --csv fix_dispatch/solved_FLOORED/RELAC_TX_FLOORED_Combined_Inputs_Outputs.csv
```

El script corre 4 chequeos de solo lectura (no modifica nada):

1. **Cumplimiento de piso**: para cada fila de `candidate_floors.csv`,
   verifica `TotalTechnologyAnnualActivity >= floor_PJ`.
2. **CF objetivo**: para cada tecnologia de la flota fosil floreada, compara
   el CF real (`actividad / (capacidad x 31.536)`) contra el CF contratado
   (`contracted_CF` en `candidate_floors.csv`), con 10% de tolerancia.
3. **Separacion de escenarios**: generacion fosil total, participacion
   renovable, costo total del sistema, emisiones CO2, y numero de
   tecnologias despachables activas (CF > 5%) -- BAU vs OPT lado a lado.
4. **Capacidad ociosa**: repite el diagnostico de CF < 5% despues de 2026
   sobre toda la flota floreada -- ya no deberian aparecer ociosas.

Corrido contra el CSV base (sin piso), el chequeo 1 falla en la mayoria de
filas (el bug confirmado); el chequeo 4 muestra las plantas forzadas
ociosas. Eso es lo esperado del CSV base. Con tu corrida FLOORED, ambos deben
pasar (ver criterios de exito). Tambien existe `--gate` para correr la
compuerta de aceptacion completa (6 chequeos, ver el docstring de
`test_outputs.py`).

## 5. Criterios de exito

- [ ] El modelo resuelve sin errores de infactibilidad (los 4 escenarios).
- [ ] Todas las restricciones de piso se respetan: `TotalTechnologyAnnualActivity >= floor_PJ`
      para cada (escenario, tecnologia, ano) en `candidate_floors.csv` (chequeo 1 = 0 FAIL).
- [ ] Las tecnologias floreadas operan a CF >= 90% de su `contracted_CF`
      despues de 2026 (chequeo 2 = 0 BELOW_TARGET).
- [ ] Ningun despacho de backstop (si el backstop aparece generando, los
      pisos son demasiado agresivos, revisar antes de reportar exito).
- [ ] BAU/INV y OPT/VGB muestran diferencias materiales en: generacion fosil
      total (PJ/ano), participacion renovable (%), y costo total del sistema
      (chequeo 3), consistentes con la direccion confirmada por
      `preflight_separation.py` (BAU/INV convergen con OPT/VGB cerca del
      2027-2030 y quedan por debajo despues, con la brecha ampliandose hasta
      2050).
- [ ] Las tecnologias forzadas de la flota floreada YA NO aparecen como
      inactivas (CF < 5%) en el diagnostico de capacidad ociosa (chequeo 4 =
      0 filas).

## 6. Que hacer si falla

- **Infactible al resolver (CPLEX/GLPK reporta infeasible):** revisa cual
  piso esta atado. `write_floors.py` ya filtro los pisos que el chequeo de
  factibilidad (`feasibility.py`) marca como imposibles ANTES de escribirlos,
  asi que una infactibilidad real en el solver indica una interaccion no
  capturada por ese chequeo (p.ej. margen de reserva, restriccion de
  transmision). No intentes depurarlo tu mismo: reporta con el mensaje de
  infactibilidad del solver y el `.log` correspondiente.
- **El backstop despacha:** los pisos son demasiado agresivos para la
  capacidad/demanda disponible ese ano. Reporta con la salida de
  `test_outputs.py` (chequeo 3, revisa si `PWRBCK*` aparece con actividad > 0).
- **Cualquier otro fallo en los criterios de exito:** no depures, reporta con
  la salida completa de `test_outputs.py` (los 4 CSVs que produce:
  `test_floor_compliance.csv`, `test_cf_targets.csv`,
  `test_scenario_separation.csv`, `test_idle_capacity.csv`) y el `.log` del
  solver.

## 7. Nota sobre la calidad de los CF

Cada tecnologia de la flota floreada tiene una etiqueta `cf_source` y
`cf_quality` en `candidate_floors.csv`:

- `plan_grounded` (`grounded` o `stated`): CF calculado o declarado
  directamente en el plan nacional de expansion de esa tecnologia (ver
  `cf_table_full.py` en la carpeta de trabajo `_Dataset_Power` para el
  detalle pais por pais y la trazabilidad completa de cada numero).
- `historical_implied` (`historical`): CF que ya implica el piso 2023-2026
  existente de esa misma tecnologia (dato del propio modelo, no de un plan
  externo).
- `fuel_fallback` (`proxy`): mediana regional por tipo de combustible,
  usada solo cuando no hay ni plan nacional ni piso historico para esa
  tecnologia.

Los `proxy` son la categoria mas debil: se recomienda revisarlos con el PI
antes de tomar los resultados de esa tecnologia como definitivos. En
particular, ningun pais con flota fosil quedo sin ningun numero (todos caen
al menos en `fuel_fallback`), pero algunos paises (p.ej. Peru) no tienen
ningun dato de plan nacional utilizable en la carpeta de trabajo y dependen
enteramente de `historical_implied` o `fuel_fallback`.

Cuando lleguen valores calibrados adicionales: se edita
`PLAN_GROUNDED` en `fix_dispatch/make_candidates.py` y se re-corre ese
script, se vuelve a correr `preflight_separation.py` para confirmar que
BAU/INV sigue sin superar a OPT/VGB, y se vuelve a correr `write_floors.py`.
Nada mas del pipeline cambia.
