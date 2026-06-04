"""A3_process.py
==============
Orchestrator for the A3 modification workflow in relac_tx, multi-scenario aware.

For each scenario folder under `A1_Outputs/A1_Outputs_<scenario>/`, this
orchestrator runs three steps in order against the scenario's
`A-O_Parametrization.xlsx`:

  1. `add_max_cap_investment_lid_rule.py` — fills MaxCapInv placeholders with
     calibrated lid values (uniform mode with relac_tx-specific
     zero_is_placeholder_in_lid_rows fix; see lid_rule.yaml).
  2. `extend_lowerlimits_pwr.py` — extends the 2024 value of
     TotalTechnologyAnnualActivityLowerLimit for PWR techs flat through 2050
     in sheet "Secondary Techs", so the calibration floor does not expire and
     the optimizer cannot dump thermal generation in 2025+.
  3. `B1b_Pre_solver_validation.py --auto-fix-all` — reconciles any residual
     inconsistencies the lid leaves behind, in particular V3 cases where the
     calibrated ActivityLowerLimit exceeds the capacity that the lid permits
     (e.g. PWRPETHNDXX 2023). B1b lowers the floor to `max_activity * 0.99`
     so the LP is feasible without un-capping the lid. This V3 feasibility
     relaxation runs for EVERY scenario (see gating below).

LowerLimit gating
-----------------
Two operations touch the LowerLimit, and they are gated differently:

  * Step 2 (extend_lowerlimits_pwr.py) *imposes* the calibration floor and is
    OPT-IN per scenario via the `lowerlimit_scenarios` map in lid_rule.yaml.
    Each scenario's value also sets the SCOPE of types the floor is imposed on:
    `all` (every PWR tech) or a named group / explicit list of type codes
    (chars 4-6 of the tech code), passed to the extend script as
    --include-types. For a scenario NOT in the map, step 2 is skipped. If the
    key is absent/empty, NO scenario gets the floor extended. (OPT uses the
    `renewable` group so non-renewable PWR techs keep their relaxed floor.)
  * B1b's V3 fix only *relaxes* an existing floor when it would otherwise make
    the LP infeasible (it never raises it). It is a feasibility safeguard, so
    it runs ALWAYS, regardless of the allowlist — A3 never passes `--skip-v3`.
    (`--skip-v3` still exists on B1b for manual standalone use.)

The MaxCapacityInvestment lid (step 1) and B1b's V1/V2 fixes also always run
for every scenario regardless.

Historical-year cutoff (MODIFY_FROM_YEAR = 2026)
------------------------------------------------
All three per-scenario steps receive --modify-from-year 2026, so they only
modify cells from 2026 onward. Years 2023-2025 are historical/observed and are
kept identical across scenarios by sync_historical_from_bau.py, which must be
run BEFORE this orchestrator (it copies BAU's 2023-2025 columns into INV and
OPT). B1b still *reports* pre-2026 inconsistencies but does not auto-fix them.

Final BAU harmonization (historical_sync_through)
-------------------------------------------------
As its LAST step, after every per-scenario step has run, this orchestrator pins
each scenario listed under `historical_sync_through` in lid_rule.yaml to BAU for
years 2023..<through> (inclusive) by invoking sync_historical_from_bau.py
--apply. Because it runs last, it OVERRIDES anything the lid rule, the lowerlimit
extension, B1b, or the BAU-only D3 caps left in that window for the target
scenario. Current map: OPT->2025 (historical only; OPT optimization unchanged),
INV->2030 (INV mirrors BAU through 2030, diverging only from 2031, exactly where
D4_load_dsptrn_max_cap_inv.py begins capping). Only year-value cells are copied
(Projection.Mode is left intact). Disable with --skip-historical-sync.

The pre-stage pipeline that OSTRAM runs (template materialization,
fix_rnwbio, scripts 1-5, c2a patch, trn residual fixes, etc.) is not needed
in relac_tx because the A1 outputs already come out of A1/A2 in final shape.

The lid script writes a JSON change log inside each scenario dir
(`lid_rule_changes_<ts>.json`) but does NOT make a folder-level backup —
recovery is via git. B1b makes its own timestamped backup file alongside the
xlsx.

Usage:
    python t1_confection/A3_process.py                  # runs all scenarios
    python t1_confection/A3_process.py --scenario BAU   # runs just BAU
    python t1_confection/A3_process.py --scenario BAU,INV
    python t1_confection/A3_process.py --list           # show discovered scenarios
    python t1_confection/A3_process.py --skip-validation # skip B1b auto-fix step
    python t1_confection/A3_process.py --skip-historical-sync # skip final BAU harmonization
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

T1_CONFECTION = Path(__file__).resolve().parent
A3_PROCESS_DIR = T1_CONFECTION / "A3_process"
RULES_SCRIPTS_DIR = A3_PROCESS_DIR / "rules_scripts"
A1_OUTPUTS_DIR = T1_CONFECTION / "A1_Outputs"
SCENARIO_PREFIX = "A1_Outputs_"

# Source scenario for the final BAU harmonization pass (must match
# SOURCE_SCENARIO in sync_historical_from_bau.py).
SOURCE_SCENARIO = "BAU"

DEFAULT_RULES_SCRIPT = "add_max_cap_investment_lid_rule.py"
EXTEND_LL_SCRIPT = "extend_lowerlimits_pwr.py"
B1B_VALIDATOR = T1_CONFECTION / "B1b_Pre_solver_validation.py"
SYNC_HIST_SCRIPT = T1_CONFECTION / "sync_historical_from_bau.py"
LID_RULE_YAML = RULES_SCRIPTS_DIR / "lid_rule.yaml"

# Historical-year cutoff: every per-scenario A3 step (lid, extend, B1b) only
# modifies cells from this year onward. Years 2023-2025 are historical/observed
# and are kept identical across scenarios by sync_historical_from_bau.py (run
# before A3), so A3's per-scenario steps must not touch them. Passed to all
# three steps via --modify-from-year.
#
# NOTE: this is independent of the final BAU harmonization pass (see
# `historical_sync_through` in lid_rule.yaml and run_historical_sync below),
# which DELIBERATELY rewrites the harmonized window — including 2026+ for INV —
# to match BAU after every per-scenario step has run.
MODIFY_FROM_YEAR = 2026

PYTHON = sys.executable


def load_lowerlimit_scenarios() -> dict[str, set[str] | None]:
    """Read the per-scenario LowerLimit scope map from lid_rule.yaml.

    Returns a dict {scenario: include_types}, where include_types is either
    None (= extend the floor for ALL PWR techs) or a set of 3-char type codes
    (= extend only techs whose type, chars 4-6 of the code, is in the set).
    A scenario NOT present in the dict does not get the floor extended (opt-in).

    Resolution of each `lowerlimit_scenarios` value:
      - "all" (case-insensitive)      -> None
      - a name in lowerlimit_tech_groups -> set(that group's types)
      - a YAML list of codes          -> set(those codes)

    Backward-compat: a plain YAML list (old format) is read as each scenario
    mapping to None ("all").

    Returns {} when the file is missing, the key is absent/empty, or PyYAML is
    unavailable — i.e. opt-in default is "no scenario gets LowerLimit extend".
    """
    if not LID_RULE_YAML.is_file():
        return {}
    try:
        import yaml  # type: ignore
    except ImportError:
        print(f"  [WARN] PyYAML not installed; cannot read lowerlimit_scenarios "
              f"from {LID_RULE_YAML.name}. Treating scope map as empty.")
        return {}
    with open(LID_RULE_YAML, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    groups_raw = cfg.get("lowerlimit_tech_groups") or {}
    if not isinstance(groups_raw, dict):
        sys.exit(
            f"ERROR: lowerlimit_tech_groups in {LID_RULE_YAML.name} must be a "
            f"mapping, got {type(groups_raw).__name__}."
        )
    groups = {
        str(name).strip(): {str(t).strip().upper() for t in (types or []) if str(t).strip()}
        for name, types in groups_raw.items()
    }

    raw = cfg.get("lowerlimit_scenarios")
    if not raw:
        return {}

    # Old format: a plain list of scenario names -> all map to None ("all").
    if isinstance(raw, list):
        return {str(s).strip(): None for s in raw if str(s).strip()}

    if not isinstance(raw, dict):
        sys.exit(
            f"ERROR: lowerlimit_scenarios in {LID_RULE_YAML.name} must be a "
            f"list or mapping, got {type(raw).__name__}."
        )

    scope: dict[str, set[str] | None] = {}
    for scen, val in raw.items():
        name = str(scen).strip()
        if not name:
            continue
        if isinstance(val, str):
            if val.strip().lower() == "all":
                scope[name] = None
            elif val.strip() in groups:
                scope[name] = set(groups[val.strip()])
            else:
                sys.exit(
                    f"ERROR: lowerlimit_scenarios[{name}] = '{val}' in "
                    f"{LID_RULE_YAML.name} is neither 'all' nor a known group "
                    f"in lowerlimit_tech_groups ({sorted(groups)})."
                )
        elif isinstance(val, list):
            scope[name] = {str(t).strip().upper() for t in val if str(t).strip()}
        else:
            sys.exit(
                f"ERROR: lowerlimit_scenarios[{name}] in {LID_RULE_YAML.name} "
                f"must be 'all', a group name, or a list; got "
                f"{type(val).__name__}."
            )
    return scope


def load_historical_sync_through() -> dict[str, int]:
    """Read the per-scenario BAU-harmonization cutoff from lid_rule.yaml.

    Returns {scenario: through_year}: the target scenario's year columns from
    2023 through `through_year` (inclusive) are copied from BAU as A3's final
    step. A scenario not listed is not harmonized.

    Returns {} when the file/key is missing or PyYAML is unavailable — i.e. the
    safe default is "harmonize nothing" (A3 behaves as before this feature).
    """
    if not LID_RULE_YAML.is_file():
        return {}
    try:
        import yaml  # type: ignore
    except ImportError:
        print(f"  [WARN] PyYAML not installed; cannot read historical_sync_through "
              f"from {LID_RULE_YAML.name}. No BAU harmonization will run.")
        return {}
    with open(LID_RULE_YAML, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    raw = cfg.get("historical_sync_through")
    if not raw:
        return {}
    if not isinstance(raw, dict):
        sys.exit(
            f"ERROR: historical_sync_through in {LID_RULE_YAML.name} must be a "
            f"mapping {{scenario: year}}, got {type(raw).__name__}."
        )
    out: dict[str, int] = {}
    for scen, year in raw.items():
        name = str(scen).strip()
        if not name:
            continue
        if not isinstance(year, int) or isinstance(year, bool):
            sys.exit(
                f"ERROR: historical_sync_through[{name}] in {LID_RULE_YAML.name} "
                f"must be an integer year, got {year!r}."
            )
        out[name] = year
    return out


def banner(msg: str) -> None:
    bar = "=" * 78
    print(f"\n{bar}\n{msg}\n{bar}")


def discover_scenarios() -> list[str]:
    """Discover real scenario folders under A1_Outputs/.

    Excludes any legacy `_PRE_LID_<ts>` / `_POST_LID_<ts>` backup folders that
    may still linger from before the no-backup default — they share the
    `A1_Outputs_` prefix and would otherwise pollute the scenario list (and
    trigger downstream B1/B2 invocations on backup data).
    """
    if not A1_OUTPUTS_DIR.is_dir():
        return []
    return sorted(
        p.name[len(SCENARIO_PREFIX):]
        for p in A1_OUTPUTS_DIR.iterdir()
        if p.is_dir()
        and p.name.startswith(SCENARIO_PREFIX)
        and "_PRE_LID_" not in p.name
        and "_POST_LID_" not in p.name
    )


def parse_cli_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="A3_process.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--scenario", default=None,
        help="Comma-separated scenario name(s) (e.g. 'BAU' or 'BAU,INV'). "
             "Defaults to all discovered scenarios under A1_Outputs/.",
    )
    p.add_argument(
        "--rules-script", default=DEFAULT_RULES_SCRIPT,
        help=f"Rules script under {RULES_SCRIPTS_DIR.name}/ to invoke "
             f"(default: {DEFAULT_RULES_SCRIPT}).",
    )
    p.add_argument(
        "--list", action="store_true",
        help="List discovered scenarios and exit.",
    )
    p.add_argument(
        "--skip-validation", action="store_true",
        help="Skip the B1b_Pre_solver_validation auto-fix step that runs after "
             "the lid script. Useful for debugging the lid output in isolation.",
    )
    p.add_argument(
        "--force-overwrite", action="store_true",
        help="Pass --force-overwrite to the lid script so that prior positive "
             "lid values in MaxCapInv cells are overwritten by the new lid. "
             "Use when iterating on the lid schedule without restoring the "
             "xlsx between runs.",
    )
    p.add_argument(
        "--skip-historical-sync", action="store_true",
        help="Skip the final BAU harmonization pass (historical_sync_through in "
             "lid_rule.yaml) that pins each listed scenario's early years to BAU "
             "after all per-scenario steps run.",
    )
    return p.parse_args()


def run_subproc(cmd: list, label: str) -> None:
    cmd_str = " ".join(str(c) for c in cmd)
    print(f"    $ {cmd_str}")
    res = subprocess.run(
        [str(c) for c in cmd],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        if res.stdout:
            print("--- stdout ---")
            print(res.stdout[-3000:])
        if res.stderr:
            print("--- stderr ---")
            print(res.stderr[-3000:])
        sys.exit(f"FAILED: {label}")
    tail = [l for l in (res.stdout or "").strip().splitlines() if l.strip()]
    for line in tail[-8:]:
        print(f"    {line}")


def run_for_scenario(scenario: str, rules_script: str,
                     skip_validation: bool,
                     force_overwrite: bool = False,
                     apply_lowerlimit: bool = False,
                     include_types: set[str] | None = None) -> None:
    input_dir = A1_OUTPUTS_DIR / f"{SCENARIO_PREFIX}{scenario}"
    if not input_dir.is_dir():
        sys.exit(f"ERROR: scenario folder not found: {input_dir}")
    paramfile = input_dir / "A-O_Parametrization.xlsx"
    if not paramfile.is_file():
        sys.exit(f"ERROR: A-O_Parametrization.xlsx not found in {input_dir}")
    demandfile = input_dir / "A-O_Demand.xlsx"
    if not demandfile.is_file():
        sys.exit(f"ERROR: A-O_Demand.xlsx not found in {input_dir}")

    rs_path = RULES_SCRIPTS_DIR / rules_script
    if not rs_path.is_file():
        sys.exit(f"ERROR: rules_script not found: {rs_path}")

    banner(f"Scenario: {scenario}")
    print(f"  input-dir     : {input_dir}")
    print(f"  rules_script  : {rules_script}")

    cmd = [PYTHON, rs_path, "--input-dir", input_dir,
           "--modify-from-year", MODIFY_FROM_YEAR]
    if force_overwrite:
        cmd.append("--force-overwrite")
    run_subproc(cmd, label=f"{rules_script} ({scenario})")

    scope_desc = "ALL PWR" if include_types is None else f"types {sorted(include_types)}"
    print(f"  lowerlimit    : extend={'ENABLED' if apply_lowerlimit else 'SKIPPED'} "
          f"(per lowerlimit_scenarios in {LID_RULE_YAML.name}"
          f"{', scope=' + scope_desc if apply_lowerlimit else ''}); "
          f"B1b V3 feasibility relaxation always ON")

    if apply_lowerlimit:
        extend_ll_path = RULES_SCRIPTS_DIR / EXTEND_LL_SCRIPT
        if not extend_ll_path.is_file():
            sys.exit(f"ERROR: {EXTEND_LL_SCRIPT} not found at {extend_ll_path}")
        print(f"  extend_ll     : {EXTEND_LL_SCRIPT} (scope={scope_desc})")
        ext_cmd = [PYTHON, extend_ll_path, "--input-dir", input_dir,
                   "--modify-from-year", MODIFY_FROM_YEAR]
        if force_overwrite:
            ext_cmd.append("--force-overwrite")
        if include_types is not None:
            ext_cmd += ["--include-types", ",".join(sorted(include_types))]
        run_subproc(ext_cmd, label=f"{EXTEND_LL_SCRIPT} ({scenario})")
    else:
        print(f"  [SKIP] {EXTEND_LL_SCRIPT} skipped "
              f"({scenario} not in lowerlimit_scenarios)")

    if skip_validation:
        print("  [SKIP] B1b validation step skipped (--skip-validation)")
        return

    if not B1B_VALIDATOR.is_file():
        sys.exit(f"ERROR: B1b validator not found: {B1B_VALIDATOR}")

    # V3 (the feasibility relaxation that lowers an infeasible ActivityLowerLimit
    # to max_activity * 0.99) runs for EVERY scenario regardless of the allowlist.
    # The allowlist only gates step 2 (extend), i.e. whether the floor is imposed
    # — not whether an existing floor is relaxed to keep the LP feasible.
    b1b_cmd = [PYTHON, B1B_VALIDATOR, "--xlsx", paramfile, "--auto-fix-all",
               "--modify-from-year", MODIFY_FROM_YEAR]
    print(f"  validator     : {B1B_VALIDATOR.name} (--auto-fix-all, "
          f"--modify-from-year {MODIFY_FROM_YEAR})")
    run_subproc(
        b1b_cmd,
        label=f"B1b_Pre_solver_validation ({scenario})",
    )


def run_historical_sync(scenario: str, through_year: int) -> None:
    """Pin `scenario`'s year columns 2023..through_year to BAU (A3 final step).

    Invokes sync_historical_from_bau.py --apply for a single target scenario.
    The sync source is always the current BAU workbook on disk; it does a
    positional copy of year cells only and aborts (non-zero exit) on any
    structural mismatch, which run_subproc turns into a hard failure.
    """
    if not SYNC_HIST_SCRIPT.is_file():
        sys.exit(f"ERROR: historical-sync script not found: {SYNC_HIST_SCRIPT}")
    years = ",".join(str(y) for y in range(2023, through_year + 1))
    cmd = [PYTHON, SYNC_HIST_SCRIPT, "--apply",
           "--scenarios", scenario, "--years", years]
    print(f"  harmonize     : {scenario} <- BAU for 2023-{through_year}")
    run_subproc(cmd, label=f"historical_sync ({scenario} <- BAU, 2023-{through_year})")


def main() -> int:
    args = parse_cli_args()

    if not A3_PROCESS_DIR.is_dir():
        sys.exit(f"ERROR: A3_process folder missing: {A3_PROCESS_DIR}")
    if not RULES_SCRIPTS_DIR.is_dir():
        sys.exit(f"ERROR: rules_scripts folder missing: {RULES_SCRIPTS_DIR}")

    discovered = discover_scenarios()
    if args.list:
        print("Discovered scenarios under A1_Outputs/:")
        for s in discovered:
            print(f"  - {s}")
        return 0
    if not discovered:
        sys.exit(f"ERROR: no scenarios found under {A1_OUTPUTS_DIR}")

    if args.scenario:
        requested = [s.strip() for s in args.scenario.split(",") if s.strip()]
        unknown = [s for s in requested if s not in discovered]
        if unknown:
            sys.exit(
                f"ERROR: unknown scenario(s) {unknown}. "
                f"Available: {discovered}"
            )
        scenarios = requested
    else:
        scenarios = discovered

    ll_scope = load_lowerlimit_scenarios()
    ll_summary = {
        s: ("all" if t is None else sorted(t)) for s, t in ll_scope.items()
    }

    hist_sync = {} if args.skip_historical_sync else load_historical_sync_through()

    t_start = time.time()
    banner("A3 workflow — relac_tx")
    print(f"  scenarios            : {scenarios}")
    print(f"  modify_from_year     : {MODIFY_FROM_YEAR} (cells before it untouched)")
    print(f"  rules_script         : {args.rules_script}")
    print(f"  skip-validation      : {args.skip_validation}")
    print(f"  force-overwrite      : {args.force_overwrite}")
    print(f"  lowerlimit_scenarios : {ll_summary or '(none — opt-in)'}")
    if args.skip_historical_sync:
        print(f"  historical_sync      : SKIPPED (--skip-historical-sync)")
    else:
        print(f"  historical_sync      : "
              f"{ {s: f'2023-{y}' for s, y in hist_sync.items()} or '(none)'}")

    for scen in scenarios:
        run_for_scenario(
            scen, args.rules_script, args.skip_validation,
            force_overwrite=args.force_overwrite,
            apply_lowerlimit=(scen in ll_scope),
            include_types=ll_scope.get(scen),
        )

    # Final step: pin each harmonized scenario's early years to BAU. Runs after
    # every per-scenario step so it overrides the lid / extend / B1b output and
    # the BAU-only D3 caps in the harmonized window. Only scenarios processed in
    # THIS run are harmonized; BAU is the source and is skipped as a target.
    sync_targets = [
        s for s in scenarios
        if s in hist_sync and s != SOURCE_SCENARIO
    ]
    if sync_targets:
        banner("Final harmonization — pin early years to BAU")
        if SOURCE_SCENARIO not in scenarios:
            print(f"  [NOTE] {SOURCE_SCENARIO} not in this run; harmonizing against "
                  f"the existing {SOURCE_SCENARIO} workbook on disk.")
        for scen in sync_targets:
            run_historical_sync(scen, hist_sync[scen])

    elapsed = time.time() - t_start
    banner(f"DONE in {elapsed:.1f}s — {len(scenarios)} scenario(s) processed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
