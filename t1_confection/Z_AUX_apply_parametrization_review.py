"""
Apply Parametrization Review adjustments to A-O_Parametrization.xlsx

Reads the two review files produced by the audit pipeline and applies
their Conservar_con_ajuste / Quitar actions onto the target sheets of
A-O_Parametrization.xlsx (BAU only).

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

Usage:
    python t1_confection/Z_AUX_apply_parametrization_review.py              # dry-run (default)
    python t1_confection/Z_AUX_apply_parametrization_review.py --apply      # write + timestamped backup
"""
import argparse
import math
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import openpyxl

PARAM_NAME = "TotalAnnualMinCapacityInvestment"
REVIEW_SHEET = "Review_MinCapInvestment"
APPLIED_ACTIONS = {"Conservar_con_ajuste", "Quitar"}

BAU_DIR = Path(__file__).parent / "A1_Outputs" / "A1_Outputs_BAU"
PARAM_XLSX = BAU_DIR / "A-O_Parametrization.xlsx"

SOURCES = [
    (BAU_DIR / "A-O_Parametrization_Review_PWR.xlsx", "Secondary Techs"),
    (BAU_DIR / "A-O_Parametrization_Review_Tx.xlsx",  "Demand Techs"),
]


def norm_str(v):
    return str(v).strip() if v is not None else ""


def is_empty_number(v):
    if v is None or v == "":
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    return False


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


def index_target_sheet(wb, sheet_name: str):
    """Return (ws, cols, year_col_map, tech_to_row) for the target sheet,
    filtered to rows whose Parameter == PARAM_NAME."""
    ws = wb[sheet_name]
    header = {norm_str(c.value): i for i, c in enumerate(ws[1], 1) if c.value is not None}
    for required in ("Tech", "Parameter", "Projection.Mode"):
        if required not in header:
            raise RuntimeError(f"Column '{required}' missing in sheet '{sheet_name}'")
    cols = {
        "tech": header["Tech"],
        "parameter": header["Parameter"],
        "proj_mode": header["Projection.Mode"],
    }
    year_col_map = {}
    for name, col in header.items():
        if name.isdigit():
            year_col_map[int(name)] = col

    tech_to_row = {}
    dup_warnings = []
    for r in range(2, ws.max_row + 1):
        tech = ws.cell(r, cols["tech"]).value
        param = ws.cell(r, cols["parameter"]).value
        if not tech or not param:
            continue
        if norm_str(param) != PARAM_NAME:
            continue
        key = norm_str(tech).upper()
        if key in tech_to_row:
            dup_warnings.append((key, tech_to_row[key], r))
        else:
            tech_to_row[key] = r
    return ws, cols, year_col_map, tech_to_row, dup_warnings


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--dry-run", action="store_true", help="Report only, do not write (default)")
    grp.add_argument("--apply", action="store_true", help="Write changes and create timestamped backup")
    args = ap.parse_args()
    apply_changes = bool(args.apply)  # default: dry-run

    if not PARAM_XLSX.exists():
        raise SystemExit(f"Parametrization file not found: {PARAM_XLSX}")

    # 1. Load both review files
    reviews = []
    per_source = defaultdict(lambda: defaultdict(int))
    for review_path, target_sheet in SOURCES:
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

    # 2. Open Parametrization once; build per-sheet index
    print(f"\n[OPEN] {PARAM_XLSX}")
    wb = openpyxl.load_workbook(PARAM_XLSX)
    sheet_ctx = {}
    for sheet_name in {s for _, s in SOURCES}:
        if sheet_name not in wb.sheetnames:
            raise SystemExit(f"Target sheet '{sheet_name}' not found in {PARAM_XLSX.name}")
        ws, cols, ymap, tech_to_row, dup_warnings = index_target_sheet(wb, sheet_name)
        sheet_ctx[sheet_name] = (ws, cols, ymap, tech_to_row)
        print(f"[INDEX] '{sheet_name}': {len(tech_to_row)} techs with Parameter='{PARAM_NAME}', "
              f"years {min(ymap) if ymap else '-'}..{max(ymap) if ymap else '-'}")
        if dup_warnings:
            print(f"         [WARN] {len(dup_warnings)} duplicate tech rows (used first occurrence)")

    # 3. Plan / apply writes
    matched = []
    unmatched = []
    first_per_sheet = defaultdict(list)
    for rv in reviews:
        ws, cols, ymap, tech_to_row = sheet_ctx[rv["target_sheet"]]
        row = tech_to_row.get(rv["tech"])
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
    print(f"\n[SUMMARY] reviews loaded = {len(reviews)}   matched = {len(matched)}   unmatched = {len(unmatched)}")
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

    # 5. Save
    if apply_changes:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = PARAM_XLSX.with_name(f"A-O_Parametrization.backup_{ts}.xlsx")
        shutil.copy2(PARAM_XLSX, backup)
        print(f"\n[BACKUP] {backup.name}")
        wb.save(PARAM_XLSX)
        print(f"[SAVE]   {PARAM_XLSX.name}  ({len(matched)} writes)")
    else:
        print(f"\n[DRY-RUN] No changes written. Re-run with --apply to persist.")


if __name__ == "__main__":
    main()
