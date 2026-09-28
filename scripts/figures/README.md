# scripts/figures — static figures and dashboard

Code for the report/presentation figures and the dashboard. Outputs go to `outputs/Figures/`
(never next to the script). Spec: `docs/superpowers/specs/2026-09-16-figures-into-scripts-outputs-design.md`.

```
scripts/figures/
├─ run_all.py / run_all.yaml        overall master: report -> presentation -> dashboard -> tablas
├─ Z_AUX_make_tablas_xlsx.py        Tablas_Completas_Resultados.xlsx (T1-T9 + Resumen, 14 scenarios,
│                                   regional level); `tablas` branch of run_all, runs in a subprocess
├─ common/
│   ├─ dashboard_config.py          data (combined CSV), paths, scenario aliases and colours,
│   │                               load_column(scenarios=), Parquet subset (ensure_scenario_subset)
│   ├─ report_style.py              matplotlib style, CORE_SCENARIOS = ["BAC", "ISR"], rs.load, rs.save
│   └─ fig_runner.py                shared logic of the per-folder masters
├─ dashboard/                       build_dashboard.py (plotly) + Z_AUX_* (Tx maps, dispatch, RES)
├─ report/                          fig_*.py (21) + run_figures.py + run_figures.yaml
└─ presentation/                    fig_*_presentation*.py (19) + run_figures.py + run_figures.yaml

outputs/Figures/
├─ Dashboard/                       dashboard.html (+ chart*.png with --png)
├─ Report/                          fig_*.png (+ fig_km_lineas_existentes_tmp_*.csv)
├─ Presentation/                    fig_*.png
├─ Tablas_Completas_Resultados.xlsx regional report tables (`tablas` branch)
├─ .tablas_xlsx_reduced.pkl         cache of the CSV reduction for the tables (keyed by CSV mtime)
├─ _subset_BAC-ISR.parquet/.json    CSV subset for the static figures (regenerates itself)
└─ .scenarios_cache.json            scenarios auto-detected from the CSV
```

## Scripts

| Script | What it does | Reads | Writes | Run |
|---|---|---|---|---|
| `run_all.py` | Overall master: runs `report` -> `presentation` -> `dashboard` -> `tablas` per `run_all.yaml`, building/reusing the BAC+ISR Parquet subset first (step 0) | `run_all.yaml`, `outputs/RELAC_TX_Combined_Inputs_Outputs.csv` | `outputs/Figures/**` | `python scripts/figures/run_all.py` |
| `Z_AUX_make_tablas_xlsx.py` | Builds `Tablas_Completas_Resultados.xlsx` with region-level results (no country split) for the 9 report indicators (T1-T9); reduces the full CSV by chunks and caches the reduction in a pickle | `outputs/RELAC_TX_Combined_Inputs_Outputs.csv`, `inputs/**/CapacityAndDistances.xlsx` | `outputs/Figures/Tablas_Completas_Resultados.xlsx`, `outputs/Figures/.tablas_xlsx_reduced.pkl` | `PYTHONUTF8=1 python scripts/figures/Z_AUX_make_tablas_xlsx.py` |
| `common/` | Shared library (paths, colours, scenario aliases, Parquet subset, matplotlib style) — see [`common/README.md`](common/README.md) | — | — | library only, imported by every fig script |
| `dashboard/` | Plotly dashboard (charts + map/dispatch/RES iframes) — see [`dashboard/README.md`](dashboard/README.md) | — | — | `python scripts/figures/dashboard/build_dashboard.py` |
| `report/` | 21 report figures + master — see [`report/README.md`](report/README.md) | — | — | `python scripts/figures/report/run_figures.py` |
| `presentation/` | 19 presentation figures + master — see [`presentation/README.md`](presentation/README.md) | — | — | `python scripts/figures/presentation/run_figures.py` |

## How to run (from the repo root, with the `OG-MOMF-env` environment active)

| What | Command |
|---|---|
| Everything (per `run_all.yaml`) | `python scripts/figures/run_all.py` |
| Only some branches | `python scripts/figures/run_all.py --only report presentation` |
| See what it would do | `python scripts/figures/run_all.py --list` |
| Report figures (per its YAML) | `python scripts/figures/report/run_figures.py` |
| Only some figures | `python scripts/figures/report/run_figures.py --only fig_almacenamiento_2050 fig_costo_unitario` |
| A single figure | `python scripts/figures/report/fig_almacenamiento_2050.py [--years ...] [--scenarios BAC ISR] [--out base]` |
| Dashboard only | `python scripts/figures/dashboard/build_dashboard.py` (all charts) or `... 01 03` (a subset, debugging only) |
| Tablas xlsx only | `python scripts/figures/run_all.py --only tablas` or `PYTHONUTF8=1 python scripts/figures/Z_AUX_make_tablas_xlsx.py` |

Times measured on 2026-09-17 (6-scenario CSV, 605 MB): building the Parquet ~25 s (once; reused
after that), report ~14 s (14 figures), presentation ~10 s (14 figures), dashboard ~3.5 min (17
charts + tabs 16-18; reads the full CSV). Total run_all ~4.5 min.
Tablas xlsx (17-scenario CSV, 1.5 GB): ~5 min the first time (reduces the CSV by chunks and caches
it in `.tablas_xlsx_reduced.pkl`), seconds on later runs until the CSV changes.

## Order / dependencies

Fixed order per `run_all.yaml`: `report` -> `presentation` -> `dashboard` -> `tablas`. Step 0
(shared by `report` and `presentation`, via `fig_runner.step0_subset`) builds/reuses the BAC+ISR
Parquet subset before any figure runs; the dashboard is always built in full (all charts + tabs
16-18) and never receives a subset from `run_all`; `tablas` runs in its own subprocess so it never
overlaps in memory with the fig_*.py processes.

## Gotchas

### On/off YAML

`report/run_figures.yaml` and `presentation/run_figures.yaml`: one key per module (`fig_x`, without
`.py`); the order in the file is the execution order.

```yaml
fig_almacenamiento_2050: true                                    # generate
fig_ens_tmp: false                                               # skip
fig_costo_unitario: {enabled: true, args: ["--years", "2030", "2050"]}   # with CLI args
```

The master warns if a key has no matching `.py`, or if a `fig_*.py` exists on disk but is missing
from the YAML (so new figures are not forgotten). `--only a b` runs only those, ignoring their
`true/false`. At the end it prints a table `script | status (OK/AVISO/ERROR/OMITIDO) | seconds |
output` and returns exit code 1 if any script errored (a `SystemExit("Sin datos ...")` counts as a
warning, not an error).

`run_all.yaml`: `report`, `presentation`, `dashboard`, `tablas` -> `true|false`.

### Scenarios

Static figures: only **BAC** (alias OPT) and **ISR** (alias ETT) — `report_style.CORE_SCENARIOS`.
Any figure accepts `--scenarios` with other codes; if one of them is outside the Parquet subset it
falls back to the full CSV (slower) with a warning. Dashboard: all scenarios in the CSV,
auto-detected. Aliases in `dashboard_config.SCENARIO_ALIAS`.

Dashboard run has 14 scenarios with report aliases OPT/ETT/PLAN (`dashboard_config.SCENARIO_ALIAS`,
`Z_AUX_make_tablas_xlsx.py` header): family OPT (BAC base plus BSR/BFA/BFB/BRA/BRB), family ETT (ISR
base plus INV/IFA/IFB/IRA/IRB), OPC (PLAN) and VSR (ETT-GP).

### Parquet subset

`dashboard_config.ensure_scenario_subset(["BAC", "ISR"])` writes `outputs/Figures/_subset_BAC-ISR.parquet`
(all CSV columns, only the rows for those scenarios; ~1.3 M rows, ~10 MB) and a `.json` sidecar with
`csv_mtime`, `csv_size`, `scenarios`, `rows`, `built_at`. It is rebuilt automatically when the CSV
changes (mtime or size); the masters do this as **step 0** and print whether they reused or rebuilt
it. To force a rebuild: delete both `_subset_*` files. Requires `pyarrow` (in `environment.yaml`).
Test: `python scripts/tests/test_scenario_subset.py`.

### Colours by tech type

Generation blue `#4e79a7`, transmission `#e15759`, storage `#76b7b2` (`dashboard_config.COLORS_TECH_TYPE`,
used across the dashboard).

### `--png`

The dashboard's static PNGs are opt-in: running `build_dashboard.py` never "downloads" images on its
own; pass `--png` to also write `chart*.png` next to `dashboard.html`.

### Adding a figure

1. Copy a `fig_*.py` from the folder and keep the contract: `def main(argv=None)`, `args =
   ap.parse_args(argv)`, data via `rs.load([...], scenarios=scenarios)`, output `base = args.out or
   os.path.join(FIGURES_DIR, "fig_x")` and `png = rs.save(fig, base)`; print `OK -> <png>` (the
   master uses it in the summary table). No module-level work: the master imports the module and
   calls `main(args)`.
2. Register it in the folder's `run_figures.yaml`.

### Import rule

The ONLY directory that goes on `sys.path` is `scripts/`. Everything is imported as a package:
`from common import relac_paths as P`, `from figures.common import report_style as rs`,
`from figures.common.dashboard_config import ...`, `from pipeline.Z_AUX_capital_annualization_script import ...`.
Never insert `scripts/figures/` or `scripts/figures/common/` (it would collide with `scripts/common/`).
