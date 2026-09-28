# scripts/common — shared path, config and validation helpers

Library modules imported by nearly every script. `relac_paths.py` is the single source of truth
for the `inputs/ scripts/ outputs/` layout (see the root `README.md`); scripts add `scripts/` to
`sys.path` and do `from common import relac_paths as P`.

## Scripts

| Script | What it does | Reads | Writes | Run |
|---|---|---|---|---|
| `relac_paths.py` | Defines every repo path constant (`INPUTS`, `OUTPUTS`, `A1_OUTPUTS`, …) and helpers to resolve scenario folders | — | — | library only |
| `Z_AUX_config_loader.py` | Loads `Config_country_codes.yaml` once (cached) and exposes accessor functions for country/ISO mappings, OLADE name mappings, technology-type helpers and per-run flags (e.g. `get_enable_dsptrn`, `get_force_empty_max_capacity_investment_pwr`) used across A0–A3 and the D-tools | `inputs/config/Config_country_codes.yaml` | — | library only |
| `_xlsx_validation_core.py` | Shared indexing and math for the V1/V2/V3 upper-bound and activity-vs-capacity checks used by `B1b_Pre_solver_validation.py` (row indexing of "Secondary"/"Demand Techs" sheets, `AvailabilityFactor`/`YearSplit`/`CapacityToActivityUnit` loaders, max-activity computation) | A-O workbooks (via the caller) | — | library only |

## How to run

Not executable. Test the path layout with `python scripts/tests/test_relac_paths.py`.

## Gotchas

- Any new script must import paths from `relac_paths.py`; never hard-code `inputs/…`.
- YAML paths are relative to the repo root regardless of the current working directory.
