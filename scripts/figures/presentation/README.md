# scripts/figures/presentation — presentation figures (slide pack)

19 static presentation figures (`fig_*_presentation*.py`) plus their master `run_figures.py`. Each is
a "presentation pack" of its `report/` counterpart: same data and same computation, only the visual
style changes for slides (bigger fonts, tighter scenario groups, single-row legends, in-bar value
labels where relevant). Defaults to `report_style.PRESENTATION_SCENARIOS` (= `CORE_SCENARIOS`,
BAC+ISR). See `scripts/figures/README.md`.

## Scripts

| Script | What it does | Reads | Writes | Run |
|---|---|---|---|---|
| `run_figures.py` | Master: runs the enabled `fig_*.py` in `run_figures.yaml`, in file order, in the same process, after building/reusing the BAC+ISR Parquet subset | `run_figures.yaml` | `outputs/Figures/Presentation/**` (delegates to the fig scripts) | `python scripts/figures/presentation/run_figures.py [--only fig_x ...] [--list]` |
| `fig_almacenamiento_2050_presentation.py` | Presentation pack of `report/fig_almacenamiento_2050.py` (storage capacity by scenario, 2030/2040/2050 [GW]): larger fonts, tighter scenario groups | `TotalCapacityAnnual` | `fig_almacenamiento_2050_presentation.png` | `python scripts/figures/presentation/fig_almacenamiento_2050_presentation.py [--years ...] [--scenarios BAC ISR] [--out base]` |
| `fig_capacidad_generacion_2050_presentation.py` | Presentation pack of `report/fig_capacidad_generacion_2050.py` (generation capacity, Renewable/Non-renewable, 2030/2040/2050 [GW]) | `TotalCapacityAnnual` | `fig_capacidad_generacion_2050_presentation.png` | `python scripts/figures/presentation/fig_capacidad_generacion_2050_presentation.py [--years ...] [--scenarios BAC ISR] [--out base]` |
| `fig_capacidad_generacion_tecnologia_2050_presentation.py` | Variant of `fig_capacidad_generacion_2050_presentation.py` that breaks each Renewable/Non-renewable bar down further by individual tech family (`classify_source_family`/`SOURCE_FAMILY_NAMES`: Solar PV, Hydro, Onshore Wind, Coal, Natural Gas, etc.); bar totals match the 2-colour figure exactly | `TotalCapacityAnnual` | `fig_capacidad_generacion_tecnologia_2050_presentation.png` | `python scripts/figures/presentation/fig_capacidad_generacion_tecnologia_2050_presentation.py [--years ...] [--scenarios BAC ISR] [--out base]` |
| `fig_capacidad_transmision_2050_presentation.py` | Presentation pack of `report/fig_capacidad_transmision_2050.py` (transmission capacity by line group, 2030/2040/2050 [GW]); legend reflowed into 2 rows | `TotalCapacityAnnual`, `AccumulatedNewCapacity`, `AccumulatedTotalAnnualMinCapacityInvestment` | `fig_capacidad_transmision_2050_presentation.png` | `python scripts/figures/presentation/fig_capacidad_transmision_2050_presentation.py [--years ...] [--scenarios BAC ISR] [--out base]` |
| `fig_capacidad_transmision_2050_presentation_tmp.py` | TEMPORARY: presentation pack of `report/fig_capacidad_transmision_2050_tmp.py` (RP line `cummax` correction); writes to a `_tmp`-suffixed output | same as `fig_capacidad_transmision_2050_presentation.py` | `fig_capacidad_transmision_2050_presentation_tmp.png` | `python scripts/figures/presentation/fig_capacidad_transmision_2050_presentation_tmp.py [--years ...] [--scenarios BAC ISR] [--out base]` |
| `fig_combustibles_fosiles_2050_presentation.py` | Presentation pack of `report/fig_combustibles_fosiles_2050.py` (fossil fuel consumption by period [million BOE]) | `TotalTechnologyAnnualActivity` | `fig_combustibles_fosiles_<p0>_<p1>_presentation.png` | `python scripts/figures/presentation/fig_combustibles_fosiles_2050_presentation.py [--periods ...] [--scenarios BAC ISR] [--out base]` |
| `fig_combustibles_fosiles_ens_presentation_tmp.py` | TEMPORARY: presentation pack of `report/fig_combustibles_fosiles_ens_tmp.py` (adds ENS to fossil consumption, no VOLL) | `TotalTechnologyAnnualActivity`, `ProductionByTechnology` | `fig_combustibles_fosiles_ens_<p0>_<p1>_presentation_tmp.png` | `python scripts/figures/presentation/fig_combustibles_fosiles_ens_presentation_tmp.py [--periods ...] [--scenarios BAC ISR] [--out base]` |
| `fig_costo_no_inversion_presentation.py` | Presentation pack of `report/fig_costo_no_inversion.py` (total system cost / "cost of non-investment" by period [USD billions]); per-component value labels added inside each bar segment | `CapitalInvestment`, `OperatingCost` | `fig_costo_no_inversion_<p0>_<p1>_presentation.png` | `python scripts/figures/presentation/fig_costo_no_inversion_presentation.py [--periods ...] [--scenarios BAC ISR] [--ref ...] [--out base]` |
| `fig_costo_no_inversion_ens_presentation_tmp.py` | TEMPORARY: presentation pack of `report/fig_costo_no_inversion_ens_tmp.py` (adds ENS at VOLL 1,750 USD/MWh inside "Combustible") | `CapitalInvestment`, `OperatingCost`, `ProductionByTechnology` | `fig_costo_no_inversion_ens_<p0>_<p1>_presentation_tmp.png` | `python scripts/figures/presentation/fig_costo_no_inversion_ens_presentation_tmp.py [--periods ...] [--scenarios BAC ISR] [--out base]` |
| `fig_costo_unitario_presentation.py` | Presentation pack of `report/fig_costo_unitario.py` (unit system cost, 2030/2040/2050 [USD/MWh]); per-component value labels added | `CapitalInvestment`, `OperatingCost`, `ProductionByTechnology` | `fig_costo_unitario_presentation.png` | `python scripts/figures/presentation/fig_costo_unitario_presentation.py [--years ...] [--scenarios BAC ISR] [--ref ...] [--out base]` |
| `fig_costo_unitario_ens_presentation_tmp.py` | TEMPORARY: presentation pack of `report/fig_costo_unitario_ens_tmp.py` (adds ENS at VOLL 1,750 USD/MWh inside "Combustible"); `--den-sin-bck` to divide by served energy only | `CapitalInvestment`, `OperatingCost`, `ProductionByTechnology` | `fig_costo_unitario_ens_presentation_tmp.png` | `python scripts/figures/presentation/fig_costo_unitario_ens_presentation_tmp.py [--years ...] [--scenarios BAC ISR] [--den-sin-bck] [--out base]` |
| `fig_diversidad_fuentes_presentation.py` | Presentation pack of `report/fig_diversidad_fuentes.py` (effective number of sources, 1/HHI, 2030/2040/2050) | `ProductionByTechnology` | `fig_diversidad_fuentes_presentation.png` | `python scripts/figures/presentation/fig_diversidad_fuentes_presentation.py [--years ...] [--scenarios BAC ISR] [--out base]` |
| `fig_ens_presentation_tmp.py` | TEMPORARY: presentation pack of `report/fig_ens_tmp.py` (ENS only [TWh] by period, no VOLL) | `ProductionByTechnology` | `fig_ens_<p0>_<p1>_presentation_tmp.png` | `python scripts/figures/presentation/fig_ens_presentation_tmp.py [--periods ...] [--scenarios BAC ISR] [--out base]` |
| `fig_generacion_anual_2050_presentation.py` | Presentation pack of `report/fig_generacion_anual_2050.py` (annual generation [TWh] + renewable share, 2030/2040/2050) | `ProductionByTechnology` | `fig_generacion_anual_2050_presentation.png` | `python scripts/figures/presentation/fig_generacion_anual_2050_presentation.py [--years ...] [--scenarios BAC ISR] [--out base]` |
| `fig_inversion_transmision_acumulada_presentation.py` | Presentation pack of `report/fig_inversion_transmision_acumulada.py` (accumulated transmission investment by period [MUSD]) | `CapitalInvestment` | `fig_inversion_transmision_<p0>_<p1>_presentation.png` | `python scripts/figures/presentation/fig_inversion_transmision_acumulada_presentation.py [--periods ...] [--scenarios BAC ISR] [--out base]` |
| `fig_km_lineas_acumulados_presentation.py` | Presentation pack of `report/fig_km_lineas_acumulados.py` (accumulated transmission km by line group from `--y0` to 2030/2040/2050); per-segment value labels added | `NewCapacity`, `CapacityAndDistances.xlsx` | `fig_km_lineas_<y0>_<ymax>_presentation.png` | `python scripts/figures/presentation/fig_km_lineas_acumulados_presentation.py [--y0 ...] [--years ...] [--scenarios BAC ISR] [--out base]` |
| `fig_participacion_renovable_presentation.py` | Presentation pack of `report/fig_participacion_renovable.py` (renewable share [%] trajectory, 2025-2050); legend reflowed to one row (2 scenarios: BAC/ISR) | `ProductionByTechnology` | `fig_participacion_renovable_presentation.png` | `python scripts/figures/presentation/fig_participacion_renovable_presentation.py [--years ...] [--scenarios BAC ISR] [--out base]` |
| `fig_seguridad_energetica_2050_presentation.py` | Presentation pack of `report/fig_seguridad_energetica_2050.py` (energy security, native vs. imported [%], 2030/2040/2050); needs the OLADE balance | `UseByTechnology`, `ProductionByTechnology`, OLADE balance xlsx | `fig_seguridad_energetica_2050_presentation.png` | `python scripts/figures/presentation/fig_seguridad_energetica_2050_presentation.py [--years ...] [--scenarios BAC ISR] [--out base]` |
| `fig_seguridad_energetica_trayectoria_presentation.py` | Presentation pack of `report/fig_seguridad_energetica_trayectoria.py` (native energy share [%] trajectory, 2025-2050); legend reflowed to one row (2 scenarios: BAC/ISR); needs the OLADE balance | `UseByTechnology`, `ProductionByTechnology`, OLADE balance xlsx | `fig_seguridad_energetica_trayectoria_presentation.png` | `python scripts/figures/presentation/fig_seguridad_energetica_trayectoria_presentation.py [--years ...] [--scenarios BAC ISR] [--out base]` |

## How to run

```bash
python scripts/figures/presentation/run_figures.py                 # all figures per run_figures.yaml
python scripts/figures/presentation/run_figures.py --only fig_x fig_y
python scripts/figures/presentation/fig_x_presentation.py [--years ...] [--scenarios BAC ISR] [--out base]
```

## Order / dependencies

Each `fig_*_presentation*.py` is a visual-only variant of its `report/` counterpart (same
computation; see the report figure's docstring for the full computation writeup). There is no
runtime dependency between `report/` and `presentation/` figures — both read the same combined CSV
independently — but they are conceptually paired for maintenance: a computation fix in a
`report/fig_x.py` should be mirrored in its `presentation/fig_x_presentation.py`.

## Gotchas

- `_tmp.py` scripts are experiments, not the official figures: they are present as keys in
  `run_figures.yaml` but set to `false` (checked against the YAML on 2026-09-28), so `run_figures.py`
  skips them unless called with `--only`.
- Every `fig_*.py`'s `main()` is intentionally undocumented — it is exempt in
  `scripts/tests/check_docs.py` (`EXEMPT_FUNCS` inside `FIG_GLOB` files); document the module
  docstring instead.
- The `_ens_..._tmp` figures value ENS at a VOLL of 1,750 USD/MWh fixed by hand for a specific run
  (2026-09-01); this is **not** the 1,500 USD/MWh VOLL used by dashboard chart_14/chart_15.
- `report_style.PRESENTATION_SCENARIOS` is currently just an alias of `CORE_SCENARIOS` (BAC+ISR); the
  separate name exists so the two folders can diverge later without touching every fig script.
