# Plan: portar Reserve Margin y Storage de OSTRAM a Relac

Branch destino: `feature/reserve-margin-and-storage` (creada desde `main` @ `f07a368`).
Branch fuente OSTRAM: `test_branch_detective` (donde viven `patch_storage_delay.py` y los demás).

## Contexto rápido

OSTRAM tiene 5 banderas en YAML que controlan 6 parches encadenados aplicados por `B2_Executing_OG_Model.py` sobre el datafile preprocesado (y, en un caso, también sobre el modelo OSeMOSYS):

- `inject_DaysInDayType` (siempre corre, corrige bug que falsea storage)
- `strip_storage_active` (elimina storage; destructivo)
- `storage_delay_active` (bloquea storage los primeros N años; no destructivo, mutuamente excluyente con strip)
- `open_pwrbck_active` (abre caps de PWRBCK de 0 → 9999)
- `reserve_margin_repair_active` (legacy, dejar OFF)
- `reserve_margin_xlsx_active` (parche careful con fallbacks desde Excel)

El datafile resultante final lleva sufijos encadenados, p.ej.:
`Pre_processed_BAU_0_StorageDelayN5_OpenBCK_RMCarefulXLSX.txt`

Compatibilidad con el modelo OSeMOSYS de Relac: verificada — `osemosys_fast_preprocessed.txt` de Relac tiene `ResidualStorageCapacity` (L128), `ReserveMarginTagTechnology` (L150), `NewStorageCapacity` (L249), `SI3_TotalNewStorage` (L477) y `RM3_ReserveMargin_Constraint` (L545) en las mismas posiciones que OSTRAM.

## Pasos del port

### 1. Copiar archivos desde OSTRAM (7 archivos)

Todos van a `relac_tx/t1_confection/`:

| Origen (OSTRAM/t1_confection/) | Destino (relac_tx/t1_confection/) | Modificación necesaria |
|---|---|---|
| `inject_DaysInDayType.py` | igual | Ninguna |
| `strip_storage.py` | igual | Verificar convención de naming `<STORAGE> → PWR + storage[:-2]` aplica en Relac |
| `patch_storage_delay.py` | igual | Misma verificación de naming |
| `open_pwrbck_caps.py` | igual | Ninguna |
| `patch_reserve_margin_repair_careful.py` | igual | Ninguna |
| `patch_reserve_margin_repair_careful_xlsx.py` | igual | Ninguna |
| `firm_capacity_fallbacks_by_cr.xlsx` | igual | Validar códigos `CR` contra el `set REGION` de Relac y prefijos PWRPET/PWROIL/PWRNGS |

### 2. Editar `B2_Executing_OG_Model.py` de Relac

Tomar como referencia: `OSTRAM/t1_confection/B2_Executing_OG_Model.py`.

Cambios a portar (en este orden):

1. **Helpers de entorno** (si Relac no los tiene): `ensure_env_tool_paths`, `get_env_executable` (L24-55 de B2 OSTRAM).
2. **Funciones nuevas** (copiar las 6 funciones completas):
   - `run_days_in_day_type_patcher` (L204-229)
   - `run_strip_storage_patcher` (L231-277)
   - `run_storage_delay_patcher` (L279-358)
   - `run_open_pwrbck_patcher` (L360-419)
   - `run_reserve_margin_repair_patcher` (L421-498)
   - `run_reserve_margin_xlsx_patcher` (L499-590)
3. **Cadena de sufijos** dentro de `main_executer` (L662-730): bloques que añaden `_StorageDelayN5`/`_NoStorage`/`_OpenBCK`/`_RMRepair`/`_RMCarefulXLSX` al `data_file` y `output_file` según las banderas activas.
4. **Lógica de precedencia de storage_delay** en `__main__` (L1264-1274): si `storage_delay_active=True`, fuerza `strip_storage_active=False`, cambia `params['osemosys_model']` al modelo parcheado y cambia `params['prefix_final_files']`.
5. **Invocaciones secuenciales** en el bucle de escenarios (L1316-1322): después de `run_preprocessing_script`, llamar las 6 funciones en orden.
6. **`export_root_datafile`** (L947-992): replicar la lógica que arma el `source_name` con la cadena de sufijos y elige `export_name` según `storage_delay_active`.
7. **`active_output_csv_candidates`** (L995-1028) y su uso dentro de `concatenate_all_scenarios`: necesario para que el concatenador final encuentre el CSV con sufijos encadenados (`Pre_processed_BAU_0_..._RMCarefulXLSX_output.csv`) en vez del nombre vanilla.

### 3. Editar `Config_MOMF_T1_AB.yaml` de Relac

Tomar como referencia: `OSTRAM/t1_confection/Config_MOMF_T1_AB.yaml` L77-167.

Añadir 5 bloques completos:

- `storage_delay_*` (master switch OFF por defecto)
- `strip_storage_*` (master switch OFF)
- `open_pwrbck_*`
- `reserve_margin_repair_*` (legacy, OFF)
- `reserve_margin_xlsx_*`

Por seguridad iniciar todos los master switches en `False`. Activar gradualmente al probar.

### 4. Verificaciones previas a la primera corrida

- `pip show openpyxl` en el env activo (necesario para el patcher XLSX).
- Inspeccionar `set STORAGE` y `set TECHNOLOGY` en algún `Pre_processed_<SCEN>_0.txt` de Relac para confirmar la convención de nombres `<STORAGE> → PWR + storage[:-2]`. Si difiere, ajustar `storage_to_tech()` en `strip_storage.py` y `patch_storage_delay.py`.
- Abrir `firm_capacity_fallbacks_by_cr.xlsx` y verificar:
  - La hoja se llama `fallbacks`.
  - Los códigos `CR` cubren las regiones de Relac.
  - Hay valores para los prefijos PWRPET/PWROIL/PWRNGS donde se espera reemplazar centinelas.
- Inspeccionar uno de los CSV `TotalAnnualMaxCapacity.csv` y `TotalAnnualMaxCapacityInvestment.csv` de Relac para ver si los centinelas `0` y `9999` existen (si no, el patcher careful no hace nada).

### 5. Plan de activación gradual

Una vez portado, encender flags en este orden para aislar problemas:

1. **Baseline + DaysInDayType solo**: todos los `*_active` en False. Confirmar que la corrida sigue dando los mismos números que `main` (`inject_DaysInDayType` corre siempre — si esto cambia outputs, es porque Relac estaba afectado por el bug 28-vs-365 igual que OSTRAM).
2. **+ Reserve Margin**: `reserve_margin_xlsx_active: True` + `open_pwrbck_active: True`. Confirmar que el LP es factible y los reserve margins se cumplen.
3. **Decidir camino de storage**:
   - Para diagnóstico extremo: `strip_storage_active: True, strip_storage_mode: all`.
   - Para corrida productiva: `storage_delay_active: True, storage_delay_first_n_years: 5`.

### 6. Commits sugeridos

Para que la rama quede revisable:

1. `Copy reserve-margin and storage patchers from OSTRAM` — los 7 archivos nuevos (.py + .xlsx) sin tocar nada más.
2. `Add reserve-margin and storage YAML config blocks` — solo el YAML.
3. `Wire patcher chain into B2` — los cambios a B2_Executing_OG_Model.py.
4. (Opcional) `Activate DaysInDayType injector by default` — si decides empezar con ese flag prendido.

## Artefactos de referencia

- Análisis completo de RM y Storage en OSTRAM (de la sesión previa): conversación con Claude del 2026-05-15.
- B2 OSTRAM con todos los hooks ya cableados: `OSTRAM/t1_confection/B2_Executing_OG_Model.py`.
- YAML OSTRAM con los 5 bloques: `OSTRAM/t1_confection/Config_MOMF_T1_AB.yaml` L77-167.

---

## Prompt para abrir la próxima sesión

> Estoy en la rama `feature/reserve-margin-and-storage` del repo `relac_tx`. Necesito portar desde OSTRAM (`C:\Users\ClimateLeadGroup\Desktop\CLG_repositories\OSTRAM`, branch `test_branch_detective`) los features de Reserve Margin y Storage. El plan completo está en `docs/plan_port_reserve_margin_and_storage_from_OSTRAM.md`. Quiero ejecutar los pasos 1, 2 y 3 del plan (copiar los 7 archivos, ajustar B2 y agregar los bloques al YAML), haciendo un commit separado por cada paso del 6 del plan. Para los pasos 4 y 5 (verificaciones y activación gradual) yo te guío después. Antes de empezar, confirmá que estás parado en `feature/reserve-margin-and-storage` y que el working tree está limpio.
