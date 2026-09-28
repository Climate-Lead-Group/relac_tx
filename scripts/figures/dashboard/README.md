# scripts/figures/dashboard — interactive dashboard

Plotly dashboard that replicates the appearance of the project's Tableau dashboards (titles, axes,
colours, legends) as a single standalone HTML file. See `scripts/figures/README.md`.

## Scripts

| Script | What it does | Reads | Writes | Run |
|---|---|---|---|---|
| `build_dashboard.py` | Generates all dashboard charts. Each chart is a `chart_NN()` function registered in the `CHARTS` dict (charts `01`-`15`, with `08A`/`08B` as sub-charts of `08`) combined into one HTML file, plus three extra tabs (`16` Transmission Maps, `17` Dispatch, `18` RES Diagram) embedded as `<iframe srcdoc=...>` built from the two `Z_AUX_generate_*` modules below | `outputs/RELAC_TX_Combined_Inputs_Outputs.csv` (via `figures.common.dashboard_config`) | `outputs/Figures/Dashboard/dashboard.html` (+ `chart*.png` with `--png`) | `python scripts/figures/dashboard/build_dashboard.py [01 03 ...] [--png]` |
| `Z_AUX_generate_RES_diagram.py` | Generates the standalone Sankey-style Reference Energy System (RES) diagram (primary resources -> generation -> transmission -> dispatch, per country/region); consumed by `build_dashboard.py` as tab `18` via `generate_html` | `A1_Outputs_BAU/A-O_AR_Model_Base_Year.xlsx` (`dashboard_config.RES_BASE_YEAR_XLSX`), country-codes YAML | standalone HTML (also embeddable) | `python scripts/figures/dashboard/Z_AUX_generate_RES_diagram.py` |
| `Z_AUX_generate_transmission_maps.py` | Generates the two standalone map/dispatch views (Transmission Capacity, Transmission Flow, Load-Capacity Ratio maps; stacked-area Dispatch chart); consumed by `build_dashboard.py` as tabs `16`/`17` via `generate_html`/`generate_dispatch_html` | `outputs/RELAC_TX_Combined_Inputs_Outputs.csv`, `centerpoints.csv` | standalone HTML (also embeddable) | `python scripts/figures/dashboard/Z_AUX_generate_transmission_maps.py` |

## How to run

From the repo root, with the `OG-MOMF-env` environment active:

```bash
python scripts/figures/dashboard/build_dashboard.py            # all charts + tabs 16-18
python scripts/figures/dashboard/build_dashboard.py 01         # chart 01 only (debugging)
python scripts/figures/dashboard/build_dashboard.py 01 03 04   # a subset (debugging)
python scripts/figures/dashboard/build_dashboard.py --png      # also write static chart*.png
```

Tabs `16`/`17`/`18` are always regenerated as part of a full dashboard build (they are not
individually selectable by chart number); a failure building one of them only prints a warning and
skips that tab, it does not stop the rest of the dashboard.

## Gotchas

- `build_dashboard_tmp.py` in this folder is an **untracked scratch copy** (not committed, not in
  `git ls-files`, not part of the documented pipeline) — ignore it; it is not listed in the table
  above and must not be relied on.
- Static PNGs (`chart*.png`) are opt-in via `--png`; running the script without it only produces
  `dashboard.html`.
- Tabs `16`/`17` read the same combined CSV as the numbered charts (one load shared between the two);
  tab `18` reads its own base-year xlsx instead, not the combined CSV.
