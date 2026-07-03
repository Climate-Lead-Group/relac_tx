"""
write_floors.py  --  writer: produce floored COPIES of the preprocessed txt.

Reads fix_dispatch/candidate_floors.csv (THE swappable input -- see the header
comment in that file / make_candidates.py). Changing floor values means
editing candidate_floors.csv and re-running this script; nothing else in this
pipeline changes.

For each (scenario, tech, year) candidate row:
    final_floor = max(existing_floor_in_original_txt, candidate_floor_PJ)
i.e. a candidate can only RAISE a floor, never lower one (protects legitimate
2023-2026 fleet floors, e.g. MEX ~830 PJ). feasible_floor() gates every raise;
an infeasible candidate is skipped and logged loudly, never written.

Writes, per scenario, a COPY next to the original (never edits the original):
    t1_confection/Executables/<SCEN>_0/
        Pre_processed_<SCEN>_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt
The copy is byte-identical to the original EXCEPT inside the
TotalTechnologyAnnualActivityLowerLimit param block, where changed/new rows
are surgically replaced or appended. No duplicate tech-year rows (GLPK errors
on dupes). CRLF line endings preserved throughout.

Also emits fix_dispatch/upstream_floor_rows.csv: the final written floor rows
in the upstream otoole shape (REGION,TECHNOLOGY,YEAR,VALUE, one section per
scenario) for later manual promotion into t1_confection/OG_csvs_inputs -- NOT
wired into the pipeline by this script.

Usage:
  python write_floors.py                        # all scenarios present in the CSV
  python write_floors.py --scenarios BAU OPT     # just BAU and OPT
  python write_floors.py --dry-run               # compute + report, write nothing
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

import relac_io as io
from feasibility import Feasibility

HERE = Path(__file__).resolve().parent
CANDIDATES_CSV = HERE / "candidate_floors.csv"
UPSTREAM_OUT = HERE / "upstream_floor_rows.csv"

_PARAM_DECL_LOWER = re.compile(
    r"^\s*param\s+default\s+(\S+)\s*:\s*TotalTechnologyAnnualActivityLowerLimit\s*:=\s*$"
)
VALUE_TOL = 1e-4


def _fmt(x: float) -> str:
    """Match the file's own style: variable decimals, no padding, no trailing zeros."""
    s = f"{x:.4f}".rstrip("0").rstrip(".")
    return s if s else "0"


def load_candidates(scenarios: list[str]) -> pd.DataFrame:
    df = pd.read_csv(CANDIDATES_CSV, comment="#")
    required = {"Scenario", "TECHNOLOGY", "YEAR", "floor_PJ"}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f"{CANDIDATES_CSV.name} missing required columns: {missing}")
    return df[df["Scenario"].isin(scenarios)].reset_index(drop=True)


def find_lower_limit_block(lines: list[str]) -> tuple[int, int, float]:
    """Return (decl_idx, terminator_idx, default_value) for the LowerLimit block.

    decl_idx is the 'param default D : TotalTechnologyAnnualActivityLowerLimit :='
    line; terminator_idx is the line that is exactly ';' closing the block.
    Data rows are lines[decl_idx+1 : terminator_idx].
    """
    decl_idx = None
    default_val = None
    for i, line in enumerate(lines):
        m = _PARAM_DECL_LOWER.match(line)
        if m:
            decl_idx = i
            default_val = float(m.group(1))
            break
    if decl_idx is None:
        raise ValueError("TotalTechnologyAnnualActivityLowerLimit block not found")
    term_idx = None
    for j in range(decl_idx + 1, len(lines)):
        if lines[j].strip() == ";":
            term_idx = j
            break
    if term_idx is None:
        raise ValueError("TotalTechnologyAnnualActivityLowerLimit block never terminates")
    return decl_idx, term_idx, default_val


def process_scenario(scenario: str, cand: pd.DataFrame, dry_run: bool) -> dict:
    orig_path = io.executable_txt(scenario)
    raw = orig_path.read_bytes()
    if b"\n" in raw.replace(b"\r\n", b""):
        raise ValueError(f"{orig_path.name}: unexpected bare-LF line ending; refusing to edit")
    text = raw.decode("utf-8")
    lines = text.split("\r\n")

    # Round-trip safety check: our split/join must reproduce the file exactly
    # before we touch anything, otherwise "every other block byte-identical"
    # cannot be guaranteed.
    if "\r\n".join(lines).encode("utf-8") != raw:
        raise ValueError(f"{orig_path.name}: split/join round-trip mismatch; refusing to edit")

    # Safety net: back up the original once before producing the floored copy.
    # We never write to orig_path itself, but a .bak guards against any
    # accidental future edit of the "original" mistaken for scratch space.
    bak_path = orig_path.with_name(orig_path.name + ".bak")
    if not dry_run and not bak_path.exists():
        bak_path.write_bytes(raw)

    decl_idx, term_idx, default_val = find_lower_limit_block(lines)

    existing = {}  # (tech, year) -> (line_idx, value)
    for i in range(decl_idx + 1, term_idx):
        toks = lines[i].split()
        if len(toks) != 4:
            continue
        region, tech, year, value = toks
        existing[(tech, int(float(year)))] = (i, float(value))

    feas = Feasibility(scenario)

    replaced, inserted, unchanged, skipped_infeasible = [], [], [], []
    detail = []  # full per-row record, for reporting (deliverable 3) independent of writing
    new_lines_for_block = []

    for row in cand.itertuples(index=False):
        tech, year, cand_floor = row.TECHNOLOGY, int(row.YEAR), float(row.floor_PJ)
        prior = existing.get((tech, year))
        existing_val = prior[1] if prior else default_val
        final = max(existing_val, cand_floor)
        is_change = final > existing_val + VALUE_TOL

        # Feasibility is evaluated for every row (not just changed ones) so the
        # comparison report can show it for the full working-set table.
        verdict = feas.feasible_floor(tech, year, final)

        rec = dict(tech=tech, year=year, country=io.tech_country(tech), fuel=io.tech_fuel(tech),
                   existing_floor_PJ=existing_val, candidate_floor_PJ=cand_floor, final_floor_PJ=final,
                   forced_GW=getattr(row, "forced_GW", None), contracted_CF=getattr(row, "contracted_CF", None),
                   feasible=verdict.feasible, binding=verdict.binding, ceiling_PJ=verdict.ceiling_PJ,
                   headroom_frac=verdict.headroom_frac)

        if not is_change:
            rec["change"] = "unchanged"
            unchanged.append((tech, year, existing_val))
            detail.append(rec)
            continue

        if not verdict.feasible:
            print(f"  [SKIP-INFEASIBLE] {scenario} {tech} {year}: "
                  f"final floor {final:.4g} PJ > binding ceiling "
                  f"{verdict.ceiling_PJ:.4g} PJ ({verdict.binding})")
            rec["change"] = "skipped_infeasible"
            skipped_infeasible.append((tech, year, existing_val, cand_floor, final,
                                       verdict.binding, verdict.ceiling_PJ))
            detail.append(rec)
            continue

        value_str = _fmt(final)
        if prior:
            line_idx = prior[0]
            lines[line_idx] = f"GLOBAL {tech} {year} {value_str}"
            rec["change"] = "raised"
            replaced.append((tech, year, existing_val, final))
        else:
            new_lines_for_block.append(f"GLOBAL {tech} {year} {value_str}")
            rec["change"] = "new"
            inserted.append((tech, year, final))
        detail.append(rec)

    if new_lines_for_block:
        lines[term_idx:term_idx] = new_lines_for_block

    out_path = io.floored_txt(scenario)
    if not dry_run:
        out_path.write_bytes("\r\n".join(lines).encode("utf-8"))

    return dict(
        scenario=scenario, orig_path=orig_path, out_path=out_path,
        replaced=replaced, inserted=inserted, unchanged=unchanged,
        skipped_infeasible=skipped_infeasible, detail=detail,
    )


def write_upstream_rows(results: list[dict]):
    rows = []
    for r in results:
        for tech, year, final in r["inserted"]:
            rows.append(dict(scenario=r["scenario"], REGION="GLOBAL", TECHNOLOGY=tech,
                             YEAR=year, VALUE=final, change="new"))
        for tech, year, before, final in r["replaced"]:
            rows.append(dict(scenario=r["scenario"], REGION="GLOBAL", TECHNOLOGY=tech,
                             YEAR=year, VALUE=final, change="raised"))
    df = pd.DataFrame(rows, columns=["scenario", "REGION", "TECHNOLOGY", "YEAR", "VALUE", "change"])
    df = df.sort_values(["scenario", "TECHNOLOGY", "YEAR"]).reset_index(drop=True)
    with open(UPSTREAM_OUT, "w", newline="", encoding="utf-8") as f:
        f.write("# Upstream-format rows (REGION,TECHNOLOGY,YEAR,VALUE per otoole convention).\n")
        f.write("# NOT wired into t1_confection/OG_csvs_inputs -- for later manual promotion only.\n")
        df.to_csv(f, index=False)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", nargs="+", default=None,
                    help="Subset of scenarios to process (default: all present in candidate_floors.csv)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Compute and report, write no files")
    args = ap.parse_args()

    all_cand = pd.read_csv(CANDIDATES_CSV, comment="#")
    scenarios = args.scenarios or sorted(all_cand["Scenario"].unique(), key=io.SCENARIOS.index)

    print(f"candidate_floors.csv: {len(all_cand)} rows total")
    print(f"Processing scenarios: {scenarios}" + (" [DRY RUN]" if args.dry_run else ""))

    results = []
    for scen in scenarios:
        cand = load_candidates([scen])
        print(f"\n--- {scen} --- ({len(cand)} candidate rows)")
        res = process_scenario(scen, cand, args.dry_run)
        results.append(res)
        n_r, n_i, n_u, n_s = (len(res["replaced"]), len(res["inserted"]),
                              len(res["unchanged"]), len(res["skipped_infeasible"]))
        print(f"  raised: {n_r}  new: {n_i}  unchanged: {n_u}  skipped(infeasible): {n_s}")
        if not args.dry_run:
            print(f"  wrote: {res['out_path'].relative_to(io.REPO)}")

    if not args.dry_run:
        udf = write_upstream_rows(results)
        print(f"\nWrote {UPSTREAM_OUT.name}: {len(udf)} upstream-format rows "
              f"(scenarios: {sorted(udf['scenario'].unique()) if len(udf) else []})")

    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    tot_r = sum(len(r["replaced"]) for r in results)
    tot_i = sum(len(r["inserted"]) for r in results)
    tot_u = sum(len(r["unchanged"]) for r in results)
    tot_s = sum(len(r["skipped_infeasible"]) for r in results)
    print(f"  total raised (existing floor increased): {tot_r}")
    print(f"  total new (no prior floor row):           {tot_i}")
    print(f"  total unchanged (existing already >= candidate): {tot_u}")
    print(f"  total skipped (infeasible, NOT written):  {tot_s}")
    if tot_s:
        print("\n  SKIPPED INFEASIBLE (review before proceeding):")
        for r in results:
            for tech, year, before, cand, final, binding, ceiling in r["skipped_infeasible"]:
                print(f"    [{r['scenario']}] {tech} {year}: candidate {cand:.4g} PJ -> "
                      f"final {final:.4g} PJ exceeds {binding} ceiling {ceiling:.4g} PJ")


if __name__ == "__main__":
    main()
