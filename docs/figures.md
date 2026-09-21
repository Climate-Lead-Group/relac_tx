# Figures and Dashboard

All result graphics are produced from the final combined CSV (`outputs/RELAC_TX_Combined_Inputs_Outputs.csv`) by the scripts under `scripts/figures/`. Nothing here is part of the DVC pipeline: run it after B2 has finished.

## Layout

| Folder | Contents | Output (`outputs/Figures/`) |
|---|---|---|
| `scripts/figures/report/` | `fig_*.py` static report figures (Entregable 2) + `run_figures.py` + `run_figures.yaml` | `Report/fig_*.png` |
| `scripts/figures/presentation/` | Same figures in presentation style + `run_figures.py` + `run_figures.yaml` | `Presentation/fig_*_presentation.png` |
| `scripts/figures/dashboard/` | `build_dashboard.py` (interactive Plotly dashboard), `Z_AUX_generate_transmission_maps.py`, `Z_AUX_generate_RES_diagram.py` | `Dashboard/dashboard.html` |
| `scripts/figures/common/` | `dashboard_config.py` (scenario aliases, colours, families), `fig_runner.py`, `report_style.py` | — |
| `scripts/figures/Z_AUX_make_tablas_xlsx.py` | Regional result tables for the 14 solved scenarios | `Tablas_Completas_Resultados.xlsx` |
| `scripts/figures/run_all.py` + `run_all.yaml` | Master runner: report → presentation → dashboard → tablas | all of the above |

Paths are centralised in `scripts/common/relac_paths.py` (`FIGURES`, `FIGURES_REPORT`, `FIGURES_PRESENTATION`, `FIGURES_DASHBOARD`, `FIGURES_SCRIPTS`). Everything under `outputs/Figures/Dashboard/`, `Report/` and `Presentation/` is regenerable and git-ignored.

## Running

```bash
python scripts/figures/run_all.py                 # every branch enabled in run_all.yaml
python scripts/figures/run_all.py --list          # show branches and their state
python scripts/figures/run_all.py --only report presentation
python scripts/figures/report/run_figures.py      # only the report figures listed in report/run_figures.yaml
python scripts/figures/dashboard/build_dashboard.py        # dashboard.html only
python scripts/figures/dashboard/build_dashboard.py --png  # also export one PNG per chart
```

`run_all.py` first builds (or reuses) a Parquet subset of the combined CSV for the BAC and ISR scenarios; report, presentation and dashboard then run in-process, and `tablas` runs in a subprocess because it streams the full CSV in chunks. A failing branch does not stop the others; the exit code is 1 if any branch failed.

`run_all.yaml` switches whole branches (`report`, `presentation`, `dashboard`, `tablas`: `true`/`false`). Each `run_figures.yaml` switches individual figures; the long form passes arguments:

```yaml
fig_almacenamiento_2050: {enabled: true, args: ["--years", "2030", "2050"]}
```

Figures ending in `_tmp` are exploratory (energy-not-served variants) and ship disabled.

## Report figures (`report/run_figures.yaml`, shipped enabled)

| Script | Figure |
|---|---|
| `fig_capacidad_generacion_2050` | Installed generation capacity by scenario in 2030/2040/2050 [GW], renewable vs non-renewable |
| `fig_generacion_anual_2050` | Annual generation by scenario in 2030/2040/2050 [TWh] and renewable share |
| `fig_participacion_renovable` | Renewable share of generation [%], 2025–2050 |
| `fig_capacidad_transmision_2050` | Installed transmission capacity in 2030/2040/2050 [GW], stacked by line group |
| `fig_km_lineas_acumulados` | Cumulative transmission kilometres to 2030/2040/2050 [km], by line group |
| `fig_inversion_transmision_acumulada` | Cumulative transmission investment per period [MUSD] |
| `fig_almacenamiento_2050` | Installed storage capacity in 2030/2040/2050 [GW] |
| `fig_combustibles_fosiles_2050` | Fossil fuel consumption, cumulative per period [million BOE] |
| `fig_costo_no_inversion` | Total system cost and "cost of non-investment", cumulative per period [billion USD] |
| `fig_costo_no_inversion_tope` | Same, including the transmission-cap ("tope") case |
| `fig_costo_unitario` | Unit system cost [MUSD/TWh] (static version of dashboard chart 11) |
| `fig_diversidad_fuentes` | Effective number of generation sources (1/HHI) in 2030/2040/2050 |
| `fig_seguridad_energetica_2050` | Energy security in 2030/2040/2050: domestic vs imported primary energy [%] |
| `fig_seguridad_energetica_trayectoria` | Domestic energy share [%], trajectory 2025–2050 |

## Dashboard charts

`dashboard.html` is a single self-contained Plotly page with scenario, country and period filters. Scenarios are auto-detected from the `Scenario` column of the combined CSV; display names come from `SCENARIO_ALIAS` in `dashboard_config.py` (see {doc}`study/scenarios`).

| Tab | Title |
|---|---|
| 01 | Installed generation capacity [GW] |
| 02 | Annual generation [TWh] |
| 03 | Installed storage capacity [GW] |
| 04 | Installed transmission capacity [GW] |
| 05 | Total investment [MUSD] |
| 06 | Investment in lines [MUSD] |
| 07 | Average annual cost CAPEX+OPEX [MUSD/yr] |
| 08 | CO₂ emissions [Mt] |
| 08A | Fossil fuel consumption [PJ] |
| 08B | Fossil fuel consumption by fuel type [PJ] |
| 09 | Average annual capital investment by country [MUSD/yr] (maps) |
| 10 | Transmission line kilometres [km] |
| 11 | Annualised cost per unit of energy [MUSD/TWh] |
| 12 | Energy security — imported vs domestic [%] |
| 13 | Resilience — effective number of sources (1/HHI) |
| 14 | Total system cost including fuel [MUSD/yr] |
| 15 | Energy not served [MUSD] (backstop output valued at 1500 USD/MWh) |
| 16 | Transmission maps (iframe) |
| 17 | Dispatch (iframe) |
| 18 | RES diagram (iframe) |

Colours are fixed per technology type across the whole dashboard: generation blue `#4e79a7`, transmission `#e15759`, storage `#76b7b2`.
