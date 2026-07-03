"""
test_outputs.py  --  post-run test script (read-only).

Validates a combined inputs+outputs CSV (baseline OR a new solve) against the
floors in candidate_floors.csv. Four checks, run in this order:

  1. FLOOR COMPLIANCE   for every (scenario, tech, year) in candidate_floors.csv:
                         TotalTechnologyAnnualActivity >= floor_PJ ?
  2. CF TARGETS          realized CF vs contracted_CF, flagged if realized <
                         contracted_CF * 0.9 (10% solver tolerance). CF basis
                         is controlled by --cf-basis (see below).
  3. SCENARIO SEPARATION fossil generation, renewable share, system cost, CO2,
                         count of active (CF>5%) dispatchable techs -- BAU vs OPT
  4. IDLE CAPACITY       CF<5% after 2026, basis controlled by --cf-basis.

--cf-basis {forced,total}  (default forced)
  forced: CF = activity / (forced_GW * C2A), where forced_GW is the cumulative
          MinCapacityInvestment build (from candidate_floors.csv). This is the
          basis that actually reflects whether the FLOOR achieved its target --
          it only ever applies where a floor exists. Checks 2 and 4 are scoped
          to candidate_floors.csv rows under this basis.
  total:  CF = activity / (TotalCapacityAnnual * C2A), i.e. the plant's whole
          fleet including any residual/legacy capacity the floor does not
          control. A plant can read as idle here even when its forced sliver
          is running exactly at the contracted CF, if a large unfloored
          residual fleet sits behind it. Check 4 under this basis is a
          NODE-LEVEL idle check (includes residual fleet), not a floor-
          performance check -- do not read it as "the floor failed."

Pointed at the BASELINE (pre-fix) combined CSV, check 1 is EXPECTED TO FAIL for
post-2026 rows -- that confirms the bug (forced-no-floor) this whole pipeline
exists to fix. Pointed at a new solve of the FLOORED.txt copies, those rows
should PASS.

--gate  run the FLOOR-FIX GATE instead of the four diagnostic checks above:
  a pass/fail acceptance gate (6 checks, forced-capacity basis, scoped to
  scenarios actually present in the outputs) plus a Tier-2 informational
  residual diagnostic that does not affect the gate verdict. Exit code 0 if
  the gate passes, 1 otherwise.

Usage:
  python test_outputs.py                            # baseline combined CSV (default)
  python test_outputs.py --csv NEW_COMBINED.csv      # a new solve's combined CSV
  python test_outputs.py --csv NEW.csv --cf-basis total   # node-level idle incl. residual
  python test_outputs.py --csv NEW.csv --gate        # FLOOR-FIX GATE (pass/fail)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

import relac_io as io

HERE = Path(__file__).resolve().parent
CANDIDATES_CSV = HERE / "candidate_floors.csv"
AFTER = 2026
C2A = io.C2A_DEFAULT
CF_TOLERANCE = 0.9   # realized CF must be >= contracted_CF * this, else flag
IDLE_CF = 0.05
ALL_SCENARIOS = io.SCENARIOS  # ["BAU", "INV", "OPT", "VGB"]

OUTPUT_PARAMS = [
    "TotalCapacityAnnual",
    "TotalTechnologyAnnualActivity",
    "TotalDiscountedCost",
    "AnnualEmissions",
    "ResidualCapacity",
]


def load_outputs(csv_path: Path, tag: str) -> dict:
    ext = io.extract_combined(OUTPUT_PARAMS, csv_path=csv_path, cache_tag=tag)

    def by_scen_tech_year(df):
        out = {}
        if len(df):
            for r in df[["Scenario", "TECHNOLOGY", "YEAR", "VALUE"]].itertuples(index=False, name=None):
                out[(r[0], r[1], int(r[2]))] = float(r[3])
        return out

    cap = by_scen_tech_year(ext["TotalCapacityAnnual"])
    act = by_scen_tech_year(ext["TotalTechnologyAnnualActivity"])
    resid = by_scen_tech_year(ext["ResidualCapacity"])

    cost, emis = {}, {}
    if len(ext["TotalDiscountedCost"]):
        for s, g in ext["TotalDiscountedCost"].groupby("Scenario"):
            cost[s] = float(g["VALUE"].sum())
    if len(ext["AnnualEmissions"]):
        for s, g in ext["AnnualEmissions"].groupby("Scenario"):
            emis[s] = float(g["VALUE"].sum())

    return dict(cap=cap, act=act, cost=cost, emis=emis, resid=resid, act_df=ext["TotalTechnologyAnnualActivity"])


def activity_or_zero(out: dict, scen: str, tech: str, year: int):
    """Activity if present, else 0.0 if the plant has capacity that year, else None (never built)."""
    a = out["act"].get((scen, tech, year))
    if a is not None:
        return a
    if out["cap"].get((scen, tech, year)) is not None:
        return 0.0
    return None


def check_floor_compliance(cand: pd.DataFrame, out: dict) -> pd.DataFrame:
    rows = []
    for r in cand.itertuples(index=False):
        scen, tech, year, floor = r.Scenario, r.TECHNOLOGY, int(r.YEAR), float(r.floor_PJ)
        act = activity_or_zero(out, scen, tech, year)
        tol = max(1e-2, 1e-4 * abs(floor))
        if act is None:
            status = "MISSING (tech not built in output)"
            ok = False
        else:
            ok = act >= floor - tol
            status = "PASS" if ok else "FAIL_BELOW_FLOOR"
        rows.append(dict(scenario=scen, tech=tech, year=year, floor_PJ=round(floor, 3),
                         activity_PJ=(None if act is None else round(act, 3)),
                         status=status, ok=ok))
    return pd.DataFrame(rows)


def check_cf_targets(cand: pd.DataFrame, out: dict, basis: str = "forced") -> pd.DataFrame:
    """basis='forced': CF = activity / (forced_GW * C2A) -- floor-performance basis.
    basis='total':  CF = activity / (TotalCapacityAnnual * C2A) -- includes residual fleet."""
    rows = []
    for r in cand.itertuples(index=False):
        scen, tech, year = r.Scenario, r.TECHNOLOGY, int(r.YEAR)
        cap = float(r.forced_GW) if basis == "forced" else out["cap"].get((scen, tech, year))
        act = activity_or_zero(out, scen, tech, year)
        realized_cf = (act / (cap * C2A)) if (cap and act is not None) else None
        target = float(r.contracted_CF)
        threshold = target * CF_TOLERANCE
        if realized_cf is None:
            status = "MISSING"
        elif realized_cf < threshold:
            status = "BELOW_TARGET"
        else:
            status = "OK"
        rows.append(dict(scenario=scen, tech=tech, year=year, cf_basis=basis,
                         contracted_CF=target, realized_CF=(None if realized_cf is None else round(realized_cf, 4)),
                         threshold=round(threshold, 4), status=status))
    return pd.DataFrame(rows)


def check_idle_capacity(cand: pd.DataFrame, out: dict, basis: str = "forced") -> pd.DataFrame:
    """basis='forced': scoped to candidate_floors.csv rows (years a floor exists),
    cap = forced_GW. This is the floor-performance idle check.
    basis='total': scans EVERY year the tech has output capacity (floored or not),
    cap = TotalCapacityAnnual. This is a node-level idle check that includes
    whatever residual/legacy fleet the floor does not control -- it is not a
    floor-performance measure and can flag years before any floor applies."""
    rows = []
    if basis == "forced":
        for r in cand.itertuples(index=False):
            scen, tech, year = r.Scenario, r.TECHNOLOGY, int(r.YEAR)
            if year <= AFTER:
                continue
            cap = float(r.forced_GW)
            act = activity_or_zero(out, scen, tech, year)
            cf = (act / (cap * C2A)) if (cap and act is not None) else None
            if cf is not None and cf < IDLE_CF:
                rows.append(dict(scenario=scen, tech=tech, year=year, cf_basis=basis,
                                 cap_GW=round(cap, 3), activity_PJ=round(act, 3), CF=round(cf, 4)))
    else:
        for scen in cand["Scenario"].unique():
            for tech in cand[cand.Scenario == scen]["TECHNOLOGY"].unique():
                years = sorted({y for (s, t, y) in out["cap"] if s == scen and t == tech and y > AFTER})
                for y in years:
                    cap = out["cap"].get((scen, tech, y))
                    act = activity_or_zero(out, scen, tech, y)
                    cf = (act / (cap * C2A)) if (cap and act is not None) else None
                    if cf is not None and cf < IDLE_CF:
                        rows.append(dict(scenario=scen, tech=tech, year=y, cf_basis=basis,
                                         cap_GW=round(cap, 3), activity_PJ=round(act, 3), CF=round(cf, 4)))
    return pd.DataFrame(rows)


def scenario_separation(out: dict) -> pd.DataFrame:
    df = out["act_df"]
    rows = []
    for scen, g in df.groupby("Scenario"):
        plants = g[g["TECHNOLOGY"].map(lambda t: io.parse_tech(t)["kind"] == "plant")]
        fossil = plants[plants["TECHNOLOGY"].map(lambda t: io.parse_tech(t)["is_fossil"])]
        renewable = plants[plants["TECHNOLOGY"].map(lambda t: io.parse_tech(t)["is_renewable"])]
        total_act = plants["VALUE"].sum()
        fossil_by_year = fossil.groupby("YEAR")["VALUE"].sum()
        n_years = fossil_by_year.index.nunique() or 1
        dispatchable = plants[plants["TECHNOLOGY"].map(
            lambda t: io.parse_tech(t)["is_fossil"] or io.parse_tech(t)["is_nuclear"] or io.parse_tech(t)["is_storage"])]
        disp_cf = {}
        for tech, gg in dispatchable.groupby("TECHNOLOGY"):
            cap_vals = [out["cap"].get((scen, tech, y)) for y in gg["YEAR"].unique()]
            cap_vals = [c for c in cap_vals if c]
            if not cap_vals:
                continue
            mean_cf = gg["VALUE"].sum() / (sum(cap_vals) * C2A) if sum(cap_vals) else 0.0
            disp_cf[tech] = mean_cf
        n_active = sum(1 for cf in disp_cf.values() if cf > IDLE_CF)

        rows.append(dict(
            scenario=scen,
            total_fossil_PJ=round(fossil["VALUE"].sum(), 1),
            fossil_PJ_per_yr_avg=round(fossil["VALUE"].sum() / n_years, 1),
            renewable_share_pct=round(100 * renewable["VALUE"].sum() / total_act, 1) if total_act else None,
            total_system_cost=out["cost"].get(scen),
            total_CO2=out["emis"].get(scen),
            n_active_dispatchable_techs=n_active,
            n_dispatchable_techs_total=len(disp_cf),
        ))
    return pd.DataFrame(rows).sort_values("scenario")


def _fmt(x):
    return "--" if x is None or pd.isna(x) else f"{x:,.1f}"


def check_no_backstop(out: dict, present: list[str]) -> dict:
    """PWRBCK* (backstop) activity should be exactly 0 wherever it is dispatched."""
    nonzero = {k: v for k, v in out["act"].items()
              if k[0] in present and k[1].startswith("PWRBCK") and abs(v) > 1e-6}
    return nonzero


def residual_idle_gw_years(out: dict, cand_all: pd.DataFrame, present: list[str]) -> float:
    """Sum of residual (non-forced) capacity, in GW-years, that sits at an
    implied CF < 5% across working-set node-years after AFTER. Mirrors the
    Step-3 residual quantification from the artifact-verification session:
    the floor (if any) is assumed served first, residual takes the rest."""
    floor_lookup = {(r.Scenario, r.TECHNOLOGY, int(r.YEAR)): float(r.floor_PJ)
                    for r in cand_all.itertuples(index=False)}
    total = 0.0
    for (s, t, y), total_gw in out["cap"].items():
        if s not in present or t not in io.WORKING_SET or y <= AFTER:
            continue
        residual_gw = out["resid"].get((s, t, y), 0.0)
        if residual_gw <= 0:
            continue
        act = activity_or_zero(out, s, t, y) or 0.0
        floor_pj = floor_lookup.get((s, t, y), 0.0)
        residual_implied_act = max(0.0, act - floor_pj)
        residual_cf = residual_implied_act / (residual_gw * C2A)
        if residual_cf < IDLE_CF:
            total += residual_gw
    return total


def run_gate(cand_all: pd.DataFrame, out: dict) -> bool:
    present = sorted({s for (s, _t, _y) in out["cap"]} & set(ALL_SCENARIOS))
    not_solved = [s for s in ALL_SCENARIOS if s not in present]
    print(f"Scenarios present in outputs: {present}")
    if not_solved:
        print(f"NOT SOLVED (excluded from the gate, not a fail): {not_solved}")

    cand = cand_all[cand_all.Scenario.isin(present) & (cand_all.forced_GW > 0)].copy()
    results = {}

    print()
    # 1. Feasibility: complete outputs for every scenario present.
    incomplete = []
    for s in present:
        has_cap = any(k[0] == s for k in out["cap"])
        has_act = any(k[0] == s for k in out["act"])
        has_cost = s in out["cost"]
        if not (has_cap and has_act and has_cost):
            incomplete.append(s)
    results["1"] = len(present) > 0 and not incomplete
    print(f"1. Feasibility (complete outputs): {'PASS' if results['1'] else 'FAIL'}"
          + (f"  incomplete: {incomplete}" if incomplete else ""))

    # 2. Floors respected.
    fc = check_floor_compliance(cand, out)
    n_fail2 = int((~fc["ok"]).sum())
    results["2"] = n_fail2 == 0
    print(f"2. Floors respected (activity >= floor_PJ): {'PASS' if results['2'] else 'FAIL'}"
          f"  ({n_fail2} FAIL/MISSING of {len(fc)})")

    # 3. CF target, forced-capacity basis.
    cf = check_cf_targets(cand, out, basis="forced")
    n_below3 = int((cf.status == "BELOW_TARGET").sum())
    results["3"] = n_below3 == 0
    print(f"3. CF target (forced basis >= 0.9x contracted_CF): {'PASS' if results['3'] else 'FAIL'}"
          f"  ({n_below3} BELOW_TARGET of {len(cf)})")

    # 4. No backstop dispatch.
    backstop = check_no_backstop(out, present)
    results["4"] = len(backstop) == 0
    print(f"4. No backstop dispatch (PWRBCK* activity == 0): {'PASS' if results['4'] else 'FAIL'}"
          f"  ({len(backstop)} nonzero rows)")
    for k, v in list(backstop.items())[:10]:
        print(f"    {k}: {v:.4f} PJ")

    # 5. Scenario separation, BAU vs OPT, expected direction.
    if {"BAU", "OPT"}.issubset(set(present)):
        sep = scenario_separation(out)
        b = sep[sep.scenario == "BAU"].iloc[0]
        o = sep[sep.scenario == "OPT"].iloc[0]
        cond_fossil = o.total_fossil_PJ > b.total_fossil_PJ
        cond_renew = o.renewable_share_pct is not None and b.renewable_share_pct is not None \
            and o.renewable_share_pct <= b.renewable_share_pct
        cond_cost = (o.total_system_cost or 0) > (b.total_system_cost or 0)
        results["5"] = bool(cond_fossil and cond_renew and cond_cost)
        print(f"5. Scenario separation (OPT forces more fossil): {'PASS' if results['5'] else 'FAIL'}"
              f"  (fossil OPT>BAU={cond_fossil}, renew_share OPT<=BAU={cond_renew}, "
              f"cost OPT>BAU={cond_cost})")
    else:
        results["5"] = False
        print("5. Scenario separation: FAIL (need both BAU and OPT solved to compare)")

    # 6. No floored plant idle, forced-capacity basis.
    idle = check_idle_capacity(cand, out, basis="forced")
    results["6"] = len(idle) == 0
    print(f"6. No floored plant idle (forced CF >= {IDLE_CF:.0%}): {'PASS' if results['6'] else 'FAIL'}"
          f"  ({len(idle)} idle rows)")

    n_pass = sum(results.values())
    verdict = n_pass == 6
    print("\n" + "=" * 78)
    print(f"FLOOR-FIX GATE: {'PASS' if verdict else 'FAIL'} ({n_pass}/6)")
    print("=" * 78)

    print("\n--- SEPARATE ISSUE (informational, does not affect the gate) ---")
    gw_years_idle = residual_idle_gw_years(out, cand_all, present)
    print(f"Residual GW-years at CF < 5% behind the working-set nodes: {gw_years_idle:.1f}")
    print("Retirement-profile issue, not addressed by floors. Pending separate workstream.")

    return verdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=str, default=None,
                    help="Combined inputs+outputs CSV (default: baseline found in repo root)")
    ap.add_argument("--cf-basis", choices=["forced", "total"], default="forced",
                    help="CF denominator for checks 2 and 4: 'forced' (floor performance, "
                         "default) or 'total' (node-level, includes residual fleet)")
    ap.add_argument("--gate", action="store_true",
                    help="Run the FLOOR-FIX GATE (6 pass/fail checks) instead of the four "
                         "diagnostic checks. Exit code 0 on PASS, 1 on FAIL.")
    args = ap.parse_args()

    csv_path = Path(args.csv) if args.csv else io.find_combined_csv()
    tag = "test_outputs_" + csv_path.stem
    print(f"Combined CSV: {csv_path.name}")

    cand = pd.read_csv(CANDIDATES_CSV, comment="#")
    out = load_outputs(csv_path, tag)

    if args.gate:
        passed = run_gate(cand, out)
        sys.exit(0 if passed else 1)

    print(f"CF basis: {args.cf_basis}")

    print("\n" + "=" * 78)
    print("CHECK 1: FLOOR COMPLIANCE  (TotalTechnologyAnnualActivity >= floor_PJ)")
    print("=" * 78)
    fc = check_floor_compliance(cand, out)
    fc.to_csv(HERE / "test_floor_compliance.csv", index=False)
    n_fail = int((~fc["ok"]).sum())
    print(f"  {len(fc)} candidate floor rows checked. {len(fc) - n_fail} PASS, {n_fail} FAIL/MISSING.")
    if n_fail:
        by_scen = fc[~fc.ok].groupby("scenario").size()
        print(f"  Failures by scenario:\n{by_scen.to_string()}")
        print(f"\n  First 15 failures:")
        for _, r in fc[~fc.ok].head(15).iterrows():
            print(f"    [{r.scenario}] {r.tech} {r.year}: floor {r.floor_PJ} activity {r.activity_PJ} ({r.status})")
    else:
        print("  OK: every candidate floor is respected in this run.")

    print("\n" + "=" * 78)
    print(f"CHECK 2: CF TARGETS  (basis={args.cf_basis}; realized CF >= contracted_CF * {CF_TOLERANCE})")
    print("=" * 78)
    cf = check_cf_targets(cand, out, basis=args.cf_basis)
    cf.to_csv(HERE / "test_cf_targets.csv", index=False)
    n_below = int((cf.status == "BELOW_TARGET").sum())
    n_missing = int((cf.status == "MISSING").sum())
    print(f"  {len(cf)} rows checked. OK: {(cf.status=='OK').sum()}  BELOW_TARGET: {n_below}  MISSING: {n_missing}")
    if n_below:
        print("\n  First 15 below-target:")
        for _, r in cf[cf.status == "BELOW_TARGET"].head(15).iterrows():
            print(f"    [{r.scenario}] {r.tech} {r.year}: realized {r.realized_CF} vs contracted {r.contracted_CF} "
                  f"(threshold {r.threshold})")

    print("\n" + "=" * 78)
    print("CHECK 3: SCENARIO SEPARATION (BAU vs OPT at minimum)")
    print("=" * 78)
    sep = scenario_separation(out)
    sep.to_csv(HERE / "test_scenario_separation.csv", index=False)
    with pd.option_context("display.width", 200):
        print(sep.to_string(index=False))
    if {"BAU", "OPT"}.issubset(set(sep["scenario"])):
        b = sep[sep.scenario == "BAU"].iloc[0]
        o = sep[sep.scenario == "OPT"].iloc[0]
        print("\n  BAU vs OPT deltas:")
        for col in ["total_fossil_PJ", "renewable_share_pct", "total_system_cost", "total_CO2",
                    "n_active_dispatchable_techs"]:
            bv, ov = b[col], o[col]
            if bv is None or ov is None or pd.isna(bv) or pd.isna(ov):
                print(f"    {col}: BAU={_fmt(bv)}  OPT={_fmt(ov)}  (cannot compute delta)")
                continue
            pct = 100 * (ov - bv) / bv if bv else float("inf")
            print(f"    {col}: BAU={_fmt(bv)}  OPT={_fmt(ov)}  delta={_fmt(ov-bv)} ({pct:+.1f}%)")

    print("\n" + "=" * 78)
    if args.cf_basis == "forced":
        print(f"CHECK 4: IDLE CAPACITY (forced basis -- floor performance), "
              f"CF < {IDLE_CF:.0%} after {AFTER}")
    else:
        print(f"CHECK 4: NODE-LEVEL IDLE (total basis -- includes residual fleet), "
              f"CF < {IDLE_CF:.0%} after {AFTER}")
    print("=" * 78)
    idle = check_idle_capacity(cand, out, basis=args.cf_basis)
    idle.to_csv(HERE / "test_idle_capacity.csv", index=False)
    if len(idle) == 0:
        print("  OK: no working-set plant is idle (CF < 5%) after 2026 in this run.")
    else:
        print(f"  {len(idle)} idle (tech, year) rows remain among working-set plants (post-2026):")
        by_tech = idle.groupby(["scenario", "tech"]).size()
        print(by_tech.to_string())

    print(f"\nWrote test_floor_compliance.csv, test_cf_targets.csv, "
          f"test_scenario_separation.csv, test_idle_capacity.csv")


if __name__ == "__main__":
    main()
