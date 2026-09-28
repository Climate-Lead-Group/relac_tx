# scripts/tests — documentation checker and repo regression tests

Plain scripts with a `main()` and `assert` statements, not pytest: each `test_*.py` file has no
`test_*` functions for pytest to collect, only a `main()` guarded by `if __name__ == "__main__":`.
`check_docs.py` enforces the folder README / docstring convention described in `AGENTS.md`; the
six `test_*.py` files are functional regression checks for specific parts of the pipeline and
figures code. Run each one directly with `python`; exit code 0 means pass.

## Scripts

| Script | What it does | Reads | Writes | Run |
|---|---|---|---|---|
| `check_docs.py` | Stdlib-only checker: every folder under `CODE_ROOTS` with tracked `.py` files has a `README.md` with the required sections and a `## Scripts` table listing every tracked `.py`; every tracked module (except `EXEMPT_FILES`/`__init__.py`) has a real module docstring; public defs in library modules (or modules imported by >= `LIBRARY_IMPORTERS` others) or long function bodies have docstrings | tracked `.py` files under `scripts/`, `README.md` files under `scripts/`, `inputs/`, `outputs/` | stdout report only | `python scripts/tests/check_docs.py` (full check, exit 1 on findings); `--summary` (coverage per folder, exit 0); `--paths scripts/common scripts/pipeline` (restrict to given paths); `--compare-ast main` (docstring-only diff vs a git ref); `--selftest` (built-in fixture tests) |
| `test_b2_chain_helper.py` | Regression: `B2_Executing_OG_Model.chain_suffixes`/`chained_base` reproduce the current patcher-chain filename suffixes (`StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_VEGCON`, and the `upto=` truncation used by `run_open_pwrbck_patcher`) | — (imports `B2_Executing_OG_Model` directly, no files) | — | `python scripts/tests/test_b2_chain_helper.py` |
| `test_D2_fixes.py` | Verifies `D2_update_secondary_techs.py`'s fixes: reads each scenario's `A-O_Parametrization.xlsx` and compares 2025 `LowerLimit` sums per fuel against `EXPECTED_LOWER_LIMITS_2025` (20% informational tolerance) | `inputs/A1_Outputs/A1_Outputs_<scenario>/A-O_Parametrization.xlsx` | — | `python scripts/tests/test_D2_fixes.py` (run after `D2_update_secondary_techs.py`) |
| `test_docs_consistency.py` | Checks that user docs (`docs/*.md` at the root only, plus `README.md`) don't drift from the code: every `scripts/**/*.py` path cited exists; every `--flag` cited on the same line as a script exists in that script's argparse; every top-level key of `Config_MOMF_T1_AB.yaml` appears in some user doc | `docs/*.md`, `README.md`, `inputs/config/Config_MOMF_T1_AB.yaml`, the cited `scripts/**/*.py` files | stdout report only | `python scripts/tests/test_docs_consistency.py` (exit 0 = OK) |
| `test_outputs.py` | Post-run, read-only: validates a combined inputs+outputs CSV against `candidate_floors.csv` (floor compliance, CF targets, BAU-vs-OPT scenario separation, idle capacity after 2026); `--gate` runs a pass/fail acceptance gate instead of the four diagnostic checks | a combined `RELAC_TX_*_Combined_Inputs_Outputs.csv` (path/flag), `inputs/tx_chain/fix_dispatch/candidate_floors.csv` | stdout report only | `python scripts/tests/test_outputs.py [--gate] [--cf-basis fleet\|total]`; **do not run without an existing solved combined CSV to point at** |
| `test_relac_paths.py` | Asserts every path constant in `common/relac_paths.py` that is exercised here points at something that actually exists in the repo (post-restructure), plus a few derived-path identities (`executables_dir`, `FIGURES_DASHBOARD`, …) | the files/dirs listed in `MUST_EXIST` (repo-wide) | — (also calls `P.ensure_output_dirs()`, which creates missing output folders) | `python scripts/tests/test_relac_paths.py` |
| `test_scenario_subset.py` | Regression for `figures/common/dashboard_config.py` / `report_style.py`'s scenario-subset caching (`ensure_scenario_subset`, `subset_is_current`, `load_column(scenarios=...)`) against a small synthetic CSV | a synthetic CSV built in a temp dir; on import, `dashboard_config` also autodetects scenarios from the real combined CSV (`outputs/Figures/.scenarios_cache.json`, slow on first run) | temp-dir Parquet/JSON only | `python scripts/tests/test_scenario_subset.py` |

## How to run

From the repo root, in the `OG-MOMF-env` environment:

```bash
python scripts/tests/check_docs.py                      # documentation checker; must exit 0
for t in scripts/tests/test_*.py; do python "$t"; done   # repo tests (see AGENTS.md "Canonical commands")
```

Each `test_*.py` can also be run individually, e.g. `python scripts/tests/test_relac_paths.py`.
`test_outputs.py` needs a solved combined CSV to point at (see its row above) — do not run it
without one already on disk; it does not generate one itself.

## Gotchas

- No pytest framework: every file here is a plain script with `main()` (or top-level asserts) and
  an `if __name__ == "__main__":` guard; `assert`/`SystemExit`/nonzero return is the failure
  signal, not pytest fixtures or `test_*` function discovery.
- `test_outputs.py` reads a solved combined CSV — never run it as part of a routine documentation
  or code-search task; it is meant to be pointed at the output of an actual solve.
- `test_relac_paths.py` calls `P.ensure_output_dirs()`, which creates missing folders under
  `outputs/` as a side effect of "just checking" the paths.
- `test_scenario_subset.py` imports `figures/common/dashboard_config.py`, which autodetects
  scenarios from the real combined CSV on first import (~1 minute the first time).
- `check_docs.py` is portable/stdlib-only by design (see its own module docstring); the `CONFIG`
  block at its top is the only part meant to change when copying it to another repo.
- `test_scenario_subset.py`'s own docstring says "Correr: ... (o pytest)"; since it defines no
  `test_*` function, `pytest` on it collects zero tests — `python scripts/tests/test_scenario_subset.py`
  is the way to actually run it.
