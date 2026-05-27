"""
Apply Parametrization Review adjustments to A-O_Parametrization.xlsx

Reads the review files produced by the audit pipeline and applies
their Conservar_con_ajuste / Quitar actions onto the target sheets of
A-O_Parametrization.xlsx for each scenario.

Scenarios processed (BAU, INV):
    Review_PWR -> 'Secondary Techs'
    Review_Tx  -> 'Demand Techs'
    Missing review files are skipped with a warning.

Mapping:
    A-O_Parametrization_Review_PWR.xlsx  ->  'Secondary Techs'
    A-O_Parametrization_Review_Tx.xlsx   ->  'Demand Techs'

Parameter targeted: TotalAnnualMinCapacityInvestment.
Match key: (Tech, Parameter) -> row; Year -> column (dynamic from header).

Actions:
    - Conservar               : no-op
    - Conservar_con_ajuste    : write Value_GW_Sugerido; set Projection.Mode = 'User defined'
    - Quitar                  : clear the year cell (None);   set Projection.Mode = 'User defined'

Omisiones_Detectadas (Review_Tx only) are ignored.

Post-write consistency sweep (independent of review actions):
    After applying review writes, scan every (Tech, Year) on each target
    sheet and enforce:
    1. PER-YEAR: If TotalAnnualMaxCapacityInvestment is numeric and <=
       TotalAnnualMinCapacityInvestment(y) > 0, set it to min(y) * 1.01.
    2. CUMULATIVE: If TotalAnnualMaxCapacity(y) is numeric and <=
       ResidualCapacity(y) + Sum(min(y') for y' in [y-OperationalLife+1, y]),
       set it to (Residual + accumulated_min) * 1.01. The cumulative window
       reflects the OSeMOSYS TotalCapacityAnnual constraint, which sums
       every prior new investment whose plant is still operational.
       OperationalLife is read from 'Fixed Horizon Parameters'; missing
       techs default to DEFAULT_OPLIFE. Missing ResidualCapacity is treated
       as 0; empty max cells are left untouched (= unbounded).
    Both adjustments also set Projection.Mode = 'User defined' on the
    affected row. The sweep covers ALL rows, including those whose min was
    not changed by the review (e.g. action = Conservar).

Usage:
    python t1_confection/Z_AUX_apply_parametrization_review.py              # dry-run (default)
    python t1_confection/Z_AUX_apply_parametrization_review.py --apply      # write + timestamped backup
"""
import argparse
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import openpyxl

# Shared validation core (constants, sheet indexing, op_life loader, sweep)
sys.path.insert(0, str(Path(__file__).parent))
from _xlsx_validation_core import (  # noqa: E402
    PARAM_NAME, MAX_PARAM_NAME, RESIDUAL_PARAM, MAX_TOTAL_PARAM,
    OPLIFE_SHEET, OPLIFE_PARAM, DEFAULT_OPLIFE, MAX_MULTIPLIER,
    norm_str, is_empty_number,
    index_target_sheet, load_operational_life, consistency_sweep,
)

REVIEW_SHEET = "Review_MinCapInvestment"
APPLIED_ACTIONS = {"Conservar_con_ajuste", "Quitar"}

OUTPUTS_DIR = Path(__file__).parent / "A1_Outputs"

# Each scenario lists the (review_filename, target_sheet) pairs to apply.
# Both PWR and Tx reviews are applied in any scenario where the file is
# present; missing review files are skipped with a warning (see load step).
SCENARIOS = [
    {
        "name": "BAU",
        "dir": OUTPUTS_DIR / "A1_Outputs_BAU",
        "sources": [
            ("A-O_Parametrization_Review_PWR.xlsx", "Secondary Techs"),
            ("A-O_Parametrization_Review_Tx.xlsx",  "Demand Techs"),
        ],
    },
    {
        "name": "INV",
        "dir": OUTPUTS_DIR / "A1_Outputs_INV",
        "sources": [
            ("A-O_Parametrization_Review_PWR.xlsx", "Secondary Techs"),
            ("A-O_Parametrization_Review_Tx.xlsx",  "Demand Techs"),
        ],
    },
]


def load_review_rows(review_path: Path, target_sheet: str):
    """Return list of dicts for rows whose Action is in APPLIED_ACTIONS."""
    wb = openpyxl.load_workbook(review_path, read_only=True, data_only=True)
    if REVIEW_SHEET not in wb.sheetnames:
        raise RuntimeError(f"Sheet '{REVIEW_SHEET}' not found in {review_path.name}")
    ws = wb[REVIEW_SHEET]
    header = {norm_str(c.value): i for i, c in enumerate(ws[1], 1) if c.value}
    # Both reviews have a 'Tech' column with the FULL 11-char code
    # (e.g. PWRHYDARGXX, PWRTRNBOLXX) that matches the target sheets.
    # Review_PWR also has 'TechCode' = short 3-char code (HYD, SPV...), which
    # does NOT match. Review_Tx has 'TechCategory' = short prefix (PWRTRN).
    # Always prefer 'Tech'.
    tech_col = header.get("Tech")
    if tech_col is None:
        raise RuntimeError(f"Column 'Tech' not found in {review_path.name}")
    required = ["Year", "Action", "Value_GW_Sugerido"]
    for k in required:
        if k not in header:
            raise RuntimeError(f"Column '{k}' missing in {review_path.name}")
    year_col = header["Year"]
    action_col = header["Action"]
    sug_col = header["Value_GW_Sugerido"]

    rows = []
    for r_idx, row_vals in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        def v(c):
            return row_vals[c - 1] if c - 1 < len(row_vals) else None

        action = norm_str(v(action_col))
        if action not in APPLIED_ACTIONS:
            continue
        tech_raw = v(tech_col)
        year_raw = v(year_col)
        if tech_raw is None or year_raw is None:
            continue
        try:
            year = int(float(year_raw))
        except (TypeError, ValueError):
            continue
        rows.append({
            "source": review_path.name,
            "target_sheet": target_sheet,
            "review_row": r_idx,
            "tech": norm_str(tech_raw).upper(),
            "year": year,
            "action": action,
            "value": v(sug_col),
        })
    wb.close()
    return rows


def process_scenario(scenario, apply_changes):
    """Apply review writes + consistency sweep for a single scenario.

    Returns (n_matched, n_unmatched, n_max_adjusts, n_max_total_adjusts).
    """
    name = scenario["name"]
    scen_dir = scenario["dir"]
    param_xlsx = scen_dir / "A-O_Parametrization.xlsx"

    print(f"\n{'=' * 72}")
    print(f"=== SCENARIO: {name}    dir: {scen_dir}")
    print(f"{'=' * 72}")

    if not param_xlsx.exists():
        print(f"[SKIP] Parametrization file not found: {param_xlsx}")
        return 0, 0, 0, 0

    # 1. Load review files for this scenario
    sources_resolved = [(scen_dir / fname, sheet) for fname, sheet in scenario["sources"]]
    reviews = []
    per_source = defaultdict(lambda: defaultdict(int))
    for review_path, target_sheet in sources_resolved:
        if not review_path.exists():
            print(f"[WARN] Review file missing, skipping: {review_path.name}")
            continue
        rows = load_review_rows(review_path, target_sheet)
        reviews.extend(rows)
        for r in rows:
            per_source[review_path.name][r["action"]] += 1
        print(f"[LOAD] {review_path.name:48s} -> '{target_sheet}'  rows kept: {len(rows)}")
        for action, n in sorted(per_source[review_path.name].items()):
            print(f"         {action:28s} {n}")

    # Detect duplicate (tech, year) within the same source
    dup_review = defaultdict(list)
    for rv in reviews:
        dup_review[(rv["source"], rv["tech"], rv["year"])].append(rv["review_row"])
    dups = {k: v for k, v in dup_review.items() if len(v) > 1}
    if dups:
        print(f"\n[WARN] Duplicate (tech, year) entries in review sources (last-wins):")
        for (src, tech, yr), rrows in list(dups.items())[:10]:
            print(f"         {src}  {tech}  {yr}  review_rows={rrows}")

    # 2. Open Parametrization once; build per-sheet index. Only the sheets
    # listed in scenario['sources'] are indexed, so the consistency sweep
    # below only touches the sheets for which a review file was found.
    print(f"\n[OPEN] {param_xlsx}")
    wb = openpyxl.load_workbook(param_xlsx)
    oplife_map = load_operational_life(wb)
    print(f"[OPLIFE] loaded {len(oplife_map)} '{OPLIFE_PARAM}' entries from '{OPLIFE_SHEET}'  (default={DEFAULT_OPLIFE})")
    sheet_ctx = {}
    for sheet_name in {s for _, s in sources_resolved}:
        if sheet_name not in wb.sheetnames:
            raise SystemExit(f"Target sheet '{sheet_name}' not found in {param_xlsx.name}")
        ws, cols, ymap, tech_to_row_by_param, dup_warnings = index_target_sheet(wb, sheet_name)
        sheet_ctx[sheet_name] = (ws, cols, ymap, tech_to_row_by_param)
        min_rows = tech_to_row_by_param[PARAM_NAME]
        max_rows = tech_to_row_by_param[MAX_PARAM_NAME]
        res_rows = tech_to_row_by_param[RESIDUAL_PARAM]
        max_tot_rows = tech_to_row_by_param[MAX_TOTAL_PARAM]
        print(f"[INDEX] '{sheet_name}': {len(min_rows)} techs with '{PARAM_NAME}', "
              f"{len(max_rows)} with '{MAX_PARAM_NAME}', "
              f"{len(res_rows)} with '{RESIDUAL_PARAM}', "
              f"{len(max_tot_rows)} with '{MAX_TOTAL_PARAM}', "
              f"years {min(ymap) if ymap else '-'}..{max(ymap) if ymap else '-'}")
        if dup_warnings:
            print(f"         [WARN] {len(dup_warnings)} duplicate tech rows (used first occurrence)")

    # 3. Plan / apply writes
    matched = []
    unmatched = []
    first_per_sheet = defaultdict(list)
    for rv in reviews:
        ws, cols, ymap, tech_to_row_by_param = sheet_ctx[rv["target_sheet"]]
        min_tech_to_row = tech_to_row_by_param[PARAM_NAME]
        row = min_tech_to_row.get(rv["tech"])
        if row is None:
            unmatched.append({**rv, "reason": "tech not in target sheet"})
            continue
        col = ymap.get(rv["year"])
        if col is None:
            unmatched.append({**rv, "reason": f"year {rv['year']} not a column"})
            continue
        old = ws.cell(row, col).value
        if rv["action"] == "Conservar_con_ajuste":
            if is_empty_number(rv["value"]):
                unmatched.append({**rv, "reason": "empty Value_GW_Sugerido"})
                continue
            try:
                new = float(rv["value"])
            except (TypeError, ValueError):
                unmatched.append({**rv, "reason": f"non-numeric Value_GW_Sugerido: {rv['value']!r}"})
                continue
        else:  # Quitar
            new = None

        old_mode = ws.cell(row, cols["proj_mode"]).value
        if apply_changes:
            ws.cell(row, col).value = new
            ws.cell(row, cols["proj_mode"]).value = "User defined"

        record = {**rv, "row": row, "col": col, "old": old, "new": new, "old_mode": old_mode}
        matched.append(record)
        if len(first_per_sheet[rv["target_sheet"]]) < 5:
            first_per_sheet[rv["target_sheet"]].append(record)

    # 4. Report
    print(f"\n[SUMMARY {name}] reviews loaded = {len(reviews)}   matched = {len(matched)}   unmatched = {len(unmatched)}")
    by_sheet = defaultdict(lambda: {"matched": 0, "unmatched": 0})
    for rv in matched:
        by_sheet[rv["target_sheet"]]["matched"] += 1
    for rv in unmatched:
        by_sheet[rv["target_sheet"]]["unmatched"] += 1
    for sheet_name in sorted(by_sheet):
        c = by_sheet[sheet_name]
        print(f"          {sheet_name:20s} matched={c['matched']:>4}   unmatched={c['unmatched']:>4}")

    for sheet_name, recs in first_per_sheet.items():
        print(f"\n[SAMPLE writes] sheet '{sheet_name}':")
        for r in recs:
            old_disp = r["old"] if r["old"] is not None else "<empty>"
            new_disp = r["new"] if r["new"] is not None else "<empty>"
            print(f"  row {r['row']:>5}  {r['tech']:<14}  {r['year']}  "
                  f"{old_disp!r:>10} -> {new_disp!r:<10}  "
                  f"mode: {r['old_mode']!r} -> 'User defined'  [{r['action']}]")

    if unmatched:
        print(f"\n[UNMATCHED] {len(unmatched)} entries:")
        for u in unmatched:
            print(f"  {u['source']:48s} review_row={u['review_row']:>4}  "
                  f"tech={u['tech']:<14} year={u['year']}  action={u['action']:<22}  reason: {u['reason']}")

    # 4b. Consistency sweep (independent of review actions): scan every
    # (tech, year) where TotalAnnualMinCapacityInvestment is numeric and
    # enforce both upper-bound invariants. Only sheets in sheet_ctx are
    # swept, so INV (Secondary Techs only) cannot touch Demand Techs.
    max_adjusts = []
    max_total_adjusts = []
    for sheet_name, (ws, cols, ymap, tech_to_row_by_param) in sheet_ctx.items():
        ma, mta = consistency_sweep(ws, sheet_name, cols, ymap, tech_to_row_by_param, oplife_map, apply_changes)
        max_adjusts.extend(ma)
        max_total_adjusts.extend(mta)

    max_adjust_by_sheet = defaultdict(int)
    for a in max_adjusts:
        max_adjust_by_sheet[a["target_sheet"]] += 1
    print(f"\n[MAX-ADJUST {name}] {len(max_adjusts)} cells bumped to min * {MAX_MULTIPLIER:.2%} "
          f"(min >= {MAX_PARAM_NAME})")
    for sheet_name in sorted(max_adjust_by_sheet):
        print(f"          {sheet_name:20s} adjusted={max_adjust_by_sheet[sheet_name]:>4}")
    sample_max = defaultdict(list)
    for a in max_adjusts:
        if len(sample_max[a["target_sheet"]]) < 5:
            sample_max[a["target_sheet"]].append(a)
    for sheet_name, recs in sample_max.items():
        print(f"  sample '{sheet_name}':")
        for a in recs:
            print(f"    row {a['row']:>5}  {a['tech']:<14}  {a['year']}  "
                  f"old_max={a['old_max']!r} -> new_max={a['new_max']:.6g}  "
                  f"(min={a['min']:.6g})  mode: {a['old_mode']!r} -> 'User defined'")

    # 4c. Report TotalAnnualMaxCapacity adjustments (uses Residual + min)
    max_total_by_sheet = defaultdict(int)
    for a in max_total_adjusts:
        max_total_by_sheet[a["target_sheet"]] += 1
    print(f"\n[MAX-TOTAL-ADJUST {name}] {len(max_total_adjusts)} cells bumped to (Residual + min) * "
          f"{MAX_MULTIPLIER:.2%} ({MAX_TOTAL_PARAM} <= {RESIDUAL_PARAM} + {PARAM_NAME})")
    for sheet_name in sorted(max_total_by_sheet):
        print(f"          {sheet_name:20s} adjusted={max_total_by_sheet[sheet_name]:>4}")
    sample_mt = defaultdict(list)
    for a in max_total_adjusts:
        if len(sample_mt[a["target_sheet"]]) < 5:
            sample_mt[a["target_sheet"]].append(a)
    for sheet_name, recs in sample_mt.items():
        print(f"  sample '{sheet_name}':")
        for a in recs:
            print(f"    row {a['row']:>5}  {a['tech']:<14}  {a['year']}  "
                  f"old_max_tot={a['old_max_tot']!r} -> {a['new_max_tot']:.6g}  "
                  f"(residual={a['residual']:.6g}, "
                  f"acc_min[{a['window_start']}..{a['year']}]={a['accumulated_min']:.6g}, "
                  f"opLife={a['op_life']})  "
                  f"mode: {a['old_mode']!r} -> 'User defined'")

    # 5. Save
    if apply_changes:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = param_xlsx.with_name(f"A-O_Parametrization.backup_{ts}.xlsx")
        shutil.copy2(param_xlsx, backup)
        print(f"\n[BACKUP {name}] {backup.name}")
        wb.save(param_xlsx)
        print(f"[SAVE   {name}] {param_xlsx.name}  ({len(matched)} min writes, "
              f"{len(max_adjusts)} max-inv adjustments, {len(max_total_adjusts)} max-total adjustments)")
    else:
        print(f"\n[DRY-RUN {name}] No changes written. Re-run with --apply to persist.")

    return len(matched), len(unmatched), len(max_adjusts), len(max_total_adjusts)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--dry-run", action="store_true", help="Report only, do not write (default)")
    grp.add_argument("--apply", action="store_true", help="Write changes and create timestamped backup")
    ap.add_argument("--scenario", choices=[s["name"] for s in SCENARIOS] + ["ALL"],
                    default="ALL", help="Restrict to a single scenario (default: ALL)")
    args = ap.parse_args()
    apply_changes = bool(args.apply)  # default: dry-run

    scenarios_to_run = SCENARIOS if args.scenario == "ALL" else [s for s in SCENARIOS if s["name"] == args.scenario]

    totals = {"matched": 0, "unmatched": 0, "max_adj": 0, "max_tot_adj": 0}
    for scen in scenarios_to_run:
        m, u, ma, mta = process_scenario(scen, apply_changes)
        totals["matched"] += m
        totals["unmatched"] += u
        totals["max_adj"] += ma
        totals["max_tot_adj"] += mta

    print(f"\n{'=' * 72}")
    print(f"=== TOTAL across {len(scenarios_to_run)} scenario(s): "
          f"matched={totals['matched']}  unmatched={totals['unmatched']}  "
          f"max-inv={totals['max_adj']}  max-total={totals['max_tot_adj']}")
    print(f"{'=' * 72}")


if __name__ == "__main__":
    main()
