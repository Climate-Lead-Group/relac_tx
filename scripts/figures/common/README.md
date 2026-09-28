# scripts/figures/common — shared figures library

Library imported by every `fig_*.py` in `report/` and `presentation/`, by the two per-folder
`run_figures.py` masters (via `fig_runner`), and by `dashboard/build_dashboard.py` (via
`dashboard_config`). Not runnable on its own. See `scripts/figures/README.md`.

## Scripts

| Script | What it does | Reads | Writes | Run |
|---|---|---|---|---|
| `dashboard_config.py` | Data oracle: paths, reference years/scenarios, scenario aliases and colours (`SCENARIO_ALIAS`, `COLORS_SCENARIO`, `COLORS_TECH_TYPE`), tech classifiers (`classify_tech_generation`, `classify_tech_type`, `classify_source_family`, ...), and the combined-CSV loader `load_column(columns, extra_dims=None, scenarios=None)` with its Parquet subset helpers (`ensure_scenario_subset`, `subset_is_current`, `subset_paths`) | `outputs/RELAC_TX_Combined_Inputs_Outputs.csv`, `inputs/**/CapacityAndDistances.xlsx`, `inputs/**/centerpoints.csv`, OLADE balance xlsx | `outputs/Figures/_subset_BAC-ISR.parquet` + `.json`, `outputs/Figures/.scenarios_cache.json` | library only |
| `report_style.py` | Matplotlib style shared by all report/presentation figures: palette (`SCENARIO_COLORS`, `COLOR_CAPEX`/`COLOR_OM`/`COLOR_COMBUSTIBLE`/`COLOR_ENS`), `CORE_SCENARIOS = ["BAC", "ISR"]`, `rs.load(columns, extra_dims=None, scenarios=None)` (wraps `dashboard_config.load_column`, defaults to `CORE_SCENARIOS`), `rs.save(fig, base_path)` (writes only the PNG), axis/legend helpers (`grouped_bar_layout`, `european_yaxis`, `apply_report_style`) | — (delegates data access to `dashboard_config`) | PNG via `rs.save` (path chosen by the caller) | library only |
| `fig_runner.py` | Shared logic of the two folder masters (`report/run_figures.py`, `presentation/run_figures.py`): reads the on/off YAML (`read_yaml`), validates it against the `fig_*.py` on disk (`validate`), runs each enabled figure in-process (`run_one`) sharing `dashboard_config.load_column`'s in-memory cache, builds/reuses the BAC+ISR Parquet subset first (`step0_subset`), and drives a whole folder (`run_folder`) | `report/run_figures.yaml` or `presentation/run_figures.yaml` | — (delegates to the fig scripts it runs) | library only |

## How to run

Library only; imported by every fig script. Nothing here is invoked directly from the command line.

## Gotchas

- The BAC+ISR Parquet subset (`dashboard_config.ensure_scenario_subset`) is keyed on the combined
  CSV's mtime and size (`_csv_signature`), not on its content: touching the CSV without changing its
  data still triggers a rebuild, and replacing it with same-mtime content silently keeps the stale
  subset. Delete `outputs/Figures/_subset_*` to force a rebuild.
- `dashboard_config.SCENARIOS` is auto-detected from the CSV's `Scenario` column and cached in
  `outputs/Figures/.scenarios_cache.json` (also keyed by CSV mtime); if the CSV is missing or
  unreadable it falls back to the 14-scenario list `_SCEN_14` hardcoded at the top of the module.
- `report_style.py` imports `SCENARIO_ALIAS` from `dashboard_config` but keeps its own,
  report-specific `SCENARIO_COLORS` (different from `dashboard_config.COLORS_SCENARIO`): as of
  2026-08-18 the report alias OPT/PLAN maps to BAC/OPC (the "capped" scenarios), not BAU/OPT.
