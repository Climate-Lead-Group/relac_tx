# scripts/tests — documentation checker and repo regression tests

Plain scripts, not a pytest suite: each `test_*.py` file has a `main()` guarded by
`if __name__ == "__main__":` and is meant to be run directly with `python`, not collected by
pytest. `pytest` is not configured for this repo, but if it were pointed at this folder it would
still collect `test_scenario_subset.py`'s six top-level `test_*` functions (`test_constants_consistent`
and others, lines 62-141) — they are plain functions with `assert` statements, runnable either way.
`check_docs.py` enforces the folder README / docstring convention described in `AGENTS.md`; the
other five `test_*.py` files are functional regression checks for specific parts of the pipeline
and figures code, driven by `main()`/`assert` only. Run each one directly with `python`; exit code
0 means pass.

## Scripts

| Script | What it does | Reads | Writes | Run |
|---|---|---|---|---|
| `check_docs.py` | Stdlib-only checker: every folder under `CODE_ROOTS` with tracked `.py` files has a `README.md` with the required sections and a `## Scripts` table listing every tracked `.py`; every tracked module (except `EXEMPT_FILES`/`__init__.py`) has a real module docstring; public defs in library modules (or modules imported by >= `LIBRARY_IMPORTERS` others) or long function bodies have docstrings | tracked `.py` files under `scripts/`, `README.md` files under `scripts/`, `inputs/`, `outputs/` | stdout report only | `python scripts/tests/check_docs.py` (full check, exit 1 on findings); `--summary` (coverage per folder, exit 0); `--paths scripts/common scripts/pipeline` (restrict to given paths); `--compare-ast main` (docstring-only diff vs a git ref); `--selftest` (built-in fixture tests) |
| `test_b2_chain_helper.py` | Regression: `B2_Executing_OG_Model.chain_suffixes`/`chained_base` reproduce the current patcher-chain filename suffixes (`StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_VEGCON`, and the `upto=` truncation used by `run_open_pwrbck_patcher`) | — (imports `B2_Executing_OG_Model` directly, no files) | — | `python scripts/tests/test_b2_chain_helper.py` |
| `test_docs_consistency.py` | Checks that user docs (`docs/*.md` at the root only, plus `README.md`) don't drift from the code: every `scripts/**/*.py` path cited exists; every `--flag` cited on the same line as a script exists in that script's argparse; every top-level key of `Config_MOMF_T1_AB.yaml` appears in some user doc | `docs/*.md`, `README.md`, `inputs/config/Config_MOMF_T1_AB.yaml`, the cited `scripts/**/*.py` files | stdout report only | `python scripts/tests/test_docs_consistency.py` (exit 0 = OK) |
| `test_outputs.py` | Post-run: validates a combined inputs+outputs CSV against `candidate_floors.csv` (floor compliance, CF targets, BAU-vs-OPT scenario separation, idle capacity after 2026); `--gate` runs a pass/fail acceptance gate instead of the four diagnostic checks | a combined `RELAC_TX_*_Combined_Inputs_Outputs.csv` (path/flag), `inputs/tx_chain/fix_dispatch/candidate_floors.csv` | stdout report; in non-`--gate` mode also writes `outputs/fix_dispatch/test_floor_compliance.csv`, `test_cf_targets.csv`, `test_scenario_separation.csv`, `test_idle_capacity.csv` (tracked) | `python scripts/tests/test_outputs.py [--gate] [--cf-basis fleet\|total]`; **do not run without an existing solved combined CSV to point at** |
| `test_relac_paths.py` | Asserts every path constant in `common/relac_paths.py` that is exercised here points at something that actually exists in the repo (post-restructure), plus a few derived-path identities (`executables_dir`, `FIGURES_DASHBOARD`, …) | the files/dirs listed in `MUST_EXIST` (repo-wide) | — (also calls `P.ensure_output_dirs()`, which creates missing output folders) | `python scripts/tests/test_relac_paths.py` |
| `test_scenario_subset.py` | Regression for `figures/common/dashboard_config.py` / `report_style.py`'s scenario-subset caching (`ensure_scenario_subset`, `subset_is_current`, `load_column(scenarios=...)`) against a small synthetic CSV | a synthetic CSV built in a temp dir; on import, `dashboard_config` also autodetects scenarios from the real combined CSV (`outputs/Figures/.scenarios_cache.json`, slow on first run) | temp-dir Parquet/JSON only | `python scripts/tests/test_scenario_subset.py` |

## How to run

From the repo root, in the `OG-MOMF-env` environment:

```bash
python scripts/tests/check_docs.py                      # documentation checker; must exit 0
# repo tests that are safe to run with no other setup (see AGENTS.md "Canonical commands"):
python scripts/tests/test_relac_paths.py
python scripts/tests/test_docs_consistency.py
python scripts/tests/test_b2_chain_helper.py
python scripts/tests/test_scenario_subset.py
```

`test_outputs.py` is deliberately left out of that list: it needs a solved combined CSV to point
at (see its row above) and, in non-`--gate` mode, overwrites the 4 tracked CSVs under
`outputs/fix_dispatch/` — do not run it without an existing solved combined CSV already on disk;
it does not generate one itself.

## Gotchas

- No pytest framework is configured for this repo: every file here is meant to be run as a plain
  script with `main()` (or top-level asserts) guarded by `if __name__ == "__main__":`;
  `assert`/`SystemExit`/nonzero return is the failure signal. `test_scenario_subset.py` is the one
  exception whose functions pytest would actually collect if pointed here (see above).
- `test_outputs.py` reads a solved combined CSV — never run it as part of a routine documentation
  or code-search task; it is meant to be pointed at the output of an actual solve.
- `test_relac_paths.py` calls `P.ensure_output_dirs()`, which creates missing folders under
  `outputs/` as a side effect of "just checking" the paths.
- `test_scenario_subset.py` imports `figures/common/dashboard_config.py`, which autodetects
  scenarios from the real combined CSV on first import (~1 minute the first time).
- `check_docs.py` is portable/stdlib-only by design (see its own module docstring); the `CONFIG`
  block at its top is the only part meant to change when copying it to another repo.
- `test_scenario_subset.py`'s own docstring says it can be run "(or pytest; exit 0 = OK)"; unlike
  the other five files, it does define six top-level `test_*` functions, so `pytest` would in fact
  collect and run them (its `Usage:` line is not misleading). `python
  scripts/tests/test_scenario_subset.py` remains the way this repo actually runs it, since pytest
  is not configured here.
