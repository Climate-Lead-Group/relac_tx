"""A3_process.py
==============
Orchestrator for the A3 modification workflow in relac_tx, multi-scenario aware.

For each scenario folder under `A1_Outputs/A1_Outputs_<scenario>/`, this
orchestrator runs two steps in order against the scenario's
`A-O_Parametrization.xlsx`:

  1. `add_max_cap_investment_lid_rule.py` — fills MaxCapInv placeholders with
     calibrated lid values (uniform mode with relac_tx-specific
     zero_is_placeholder_in_lid_rows fix; see lid_rule.yaml).
  2. `B1b_Pre_solver_validation.py --auto-fix-all` — reconciles any residual
     inconsistencies the lid leaves behind, in particular V3 cases where the
     calibrated ActivityLowerLimit exceeds the capacity that the lid permits
     (e.g. PWRPETHNDXX 2023). B1b lowers the floor to `max_activity * 0.99`
     so the LP is feasible without un-capping the lid.

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

DEFAULT_RULES_SCRIPT = "add_max_cap_investment_lid_rule.py"
B1B_VALIDATOR = T1_CONFECTION / "B1b_Pre_solver_validation.py"

PYTHON = sys.executable


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
                     force_overwrite: bool = False) -> None:
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

    cmd = [PYTHON, rs_path, "--input-dir", input_dir]
    if force_overwrite:
        cmd.append("--force-overwrite")
    run_subproc(cmd, label=f"{rules_script} ({scenario})")

    if skip_validation:
        print("  [SKIP] B1b validation step skipped (--skip-validation)")
        return

    if not B1B_VALIDATOR.is_file():
        sys.exit(f"ERROR: B1b validator not found: {B1B_VALIDATOR}")

    print(f"  validator     : {B1B_VALIDATOR.name} (--auto-fix-all)")
    run_subproc(
        [PYTHON, B1B_VALIDATOR, "--xlsx", paramfile, "--auto-fix-all"],
        label=f"B1b_Pre_solver_validation ({scenario})",
    )


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

    t_start = time.time()
    banner("A3 workflow — relac_tx")
    print(f"  scenarios       : {scenarios}")
    print(f"  rules_script    : {args.rules_script}")
    print(f"  skip-validation : {args.skip_validation}")
    print(f"  force-overwrite : {args.force_overwrite}")

    for scen in scenarios:
        run_for_scenario(
            scen, args.rules_script, args.skip_validation,
            force_overwrite=args.force_overwrite,
        )

    elapsed = time.time() - t_start
    banner(f"DONE in {elapsed:.1f}s — {len(scenarios)} scenario(s) processed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
