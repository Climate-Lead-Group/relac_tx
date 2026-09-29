# scripts/experimental — exploratory scripts outside the pipeline

Not part of the A3 -> B1 -> B2 pipeline; nothing here is imported or invoked by
`scripts/pipeline/`, `dvc.yaml` or any `Config_MOMF_T1_*.yaml`. One output file is still live
data, though: `flujos_energia_estimados_optimizacion.xlsx` (written by
`estimar_flujos_optimizacion.py`) is read by `scripts/tools/Z_AUX_D1b_set_trn_limits_from_flows.py`,
which `scripts/pipeline/D2_update_secondary_techs.py` imports — see Gotchas. The only sub-folder,
`matriz_balance/`, estimates bilateral electricity flows between the 19 LAC countries from OLADE's
aggregate country totals plus manually-collected bilateral data, using four independent estimation
methods (proportional-to-OLADE, averaged, RAS bi-proportional, constrained optimization). Process
notes (pre-dating the `inputs/scripts/outputs` restructure; paths in it are stale) are in
`docs/dev/experimental/matriz_balance_README_PROCESO.md`. This README also documents
`matriz_balance/` per `COVERED_BY_PARENT` in `scripts/tests/check_docs.py`.

## Scripts

| Script | What it does | Reads | Writes | Run |
|---|---|---|---|---|
| `matriz_balance/datos_flujos_internet.py` | Data-only module: a hardcoded `DATOS_INTERNET` dict of manually-collected bilateral flow observations (year, country pair) -> `{energia (GWh), notas, fuente}`, with source URLs in comments | — | — | library only (imported by `generar_tabla_flujos_energia.py`); not run directly |
| `matriz_balance/generar_matriz_electricidad.py` | Master script: extracts production/import/export from the OLADE workbook (37 sheets, one per country/year), detects per-year units (GWh in 2021, PJ in 2023) and converts to GWh (`PJ_TO_GWH=277.778`), then builds the per-country/year matrix; runs at import time (no `main()`/`__main__` guard) | `inputs/reference/Matriz Balance energético/OLADE - Matriz de balance energético - Anual.xlsx` | `inputs/reference/Matriz Balance energético/Matriz_Completa_Con_Produccion.xlsx` (intermediate), `.../Matriz_ImportExport_PorPais.xlsx` | `python scripts/experimental/matriz_balance/generar_matriz_electricidad.py` |
| `matriz_balance/generar_tabla_flujos_energia.py` | Builds the bilateral-flows table (year, country pair, GWh, notas, fuente) for the 20 known interconnections, filled from `datos_flujos_internet.DATOS_INTERNET` | `datos_flujos_internet.py` (import), optionally `inputs/reference/Matriz Balance energético/Matriz_Bilateral_Electricidad.xlsx` | `inputs/reference/Matriz Balance energético/flujos_energia_interconexiones.xlsx` | `python scripts/experimental/matriz_balance/generar_tabla_flujos_energia.py` |
| `matriz_balance/estimar_flujos_desde_olade.py` | Method 1: distributes each country's OLADE import/export totals across its neighbors in proportion to the bilateral flows table (prioritizes matching imports; penalizes Mexico's difference against US trade) | `.../flujos_energia_interconexiones.xlsx`, `.../Matriz_ImportExport_PorPais.xlsx` | `.../flujos_energia_estimados_olade_final.xlsx` | `python scripts/experimental/matriz_balance/estimar_flujos_desde_olade.py` |
| `matriz_balance/estimar_flujos_promedio.py` | Method 2: averages the export-based and import-based OLADE-consistent estimates to balance the error between the two | `.../flujos_energia_interconexiones.xlsx`, `.../Matriz_ImportExport_PorPais.xlsx` | `.../flujos_energia_estimados_promedio.xlsx` | `python scripts/experimental/matriz_balance/estimar_flujos_promedio.py` |
| `matriz_balance/estimar_flujos_ras.py` | Method 3: RAS bi-proportional iterative adjustment (`MAX_ITERATIONS=500`, `TOLERANCE=0.01` GWh) to match both import and export OLADE totals simultaneously | `.../flujos_energia_interconexiones.xlsx`, `.../Matriz_ImportExport_PorPais.xlsx` | `.../flujos_energia_estimados_ras.xlsx` | `python scripts/experimental/matriz_balance/estimar_flujos_ras.py` |
| `matriz_balance/estimar_flujos_optimizacion.py` | Method 4: constrained optimization (`scipy.optimize.lsq_linear`) using a gravity-model prior, with OLADE totals as soft (penalized) constraints rather than hard ones, since OLADE's own neighbor-to-neighbor figures can be internally inconsistent; does not use the bilateral flows table, only OLADE aggregates; 17 verified interconnections | `.../Matriz_ImportExport_PorPais.xlsx` | `.../flujos_energia_estimados_optimizacion.xlsx` | `python scripts/experimental/matriz_balance/estimar_flujos_optimizacion.py` |

## How to run

From the repo root, in the `OG-MOMF-env` environment (needs `pandas`, `openpyxl`, and `scipy` for
`estimar_flujos_optimizacion.py`):

```bash
python scripts/experimental/matriz_balance/generar_matriz_electricidad.py      # step 1: OLADE -> per-country matrix
python scripts/experimental/matriz_balance/generar_tabla_flujos_energia.py     # step 2: bilateral flows table
python scripts/experimental/matriz_balance/estimar_flujos_desde_olade.py       # step 3a: OLADE-consistent estimate
python scripts/experimental/matriz_balance/estimar_flujos_promedio.py          # step 3b: averaged estimate
python scripts/experimental/matriz_balance/estimar_flujos_ras.py               # step 3c: RAS estimate
python scripts/experimental/matriz_balance/estimar_flujos_optimizacion.py      # step 3d: optimization estimate
```

## Order / dependencies

1. `generar_matriz_electricidad.py` reads the raw OLADE workbook and writes
   `Matriz_ImportExport_PorPais.xlsx`.
2. `generar_tabla_flujos_energia.py` (using `datos_flujos_internet.py`) writes
   `flujos_energia_interconexiones.xlsx`, independently of step 1.
3. `estimar_flujos_desde_olade.py`, `estimar_flujos_promedio.py` and `estimar_flujos_ras.py` each
   read both files from steps 1-2 and write their own estimate; they are alternative methods, not
   a chain — none depends on another's output.
4. `estimar_flujos_optimizacion.py` only needs step 1's output (`Matriz_ImportExport_PorPais.xlsx`).

## Gotchas

- Nothing here is called by `scripts/pipeline/`, `dvc.yaml` or any `Config_MOMF_T1_*.yaml` (checked
  by grep); treat every script as a manual, standalone analysis tool. One exception on the data
  side: `flujos_energia_estimados_optimizacion.xlsx`, the output of
  `estimar_flujos_optimizacion.py`, is read by the live D1b/D2 chain
  (`scripts/tools/Z_AUX_D1b_set_trn_limits_from_flows.py:~500`, imported by
  `scripts/pipeline/D2_update_secondary_techs.py`) — re-running `estimar_flujos_optimizacion.py`
  changes what `D2_update_secondary_techs.py` writes into `Secondary_Techs_Editor.xlsx` downstream.
- All reads/writes go to `inputs/reference/Matriz Balance energético/`
  (`common.relac_paths.MATRIZ_BALANCE`), not `outputs/experimental/`: `relac_paths.EXPERIMENTAL_OUT`
  is defined but unused by any script in this folder today.
- `generar_matriz_electricidad.py` has no `if __name__ == "__main__":` guard — importing it runs
  the whole extraction and overwrites its output files as a side effect.
- The four `estimar_flujos_*.py` methods are independent, not a pipeline: they produce different
  `flujos_energia_estimados_*.xlsx` files side by side for comparison, not a single "correct" one.
- `docs/dev/experimental/matriz_balance_README_PROCESO.md` predates the `inputs/scripts/outputs`
  restructure and still shows the old `t1_confection/...` paths; treat its narrative as valid and
  its literal paths as stale.
