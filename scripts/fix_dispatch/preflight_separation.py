"""
preflight_separation.py  --  Phase D preflight scenario-separation gate
(read-only, INPUT SIDE ONLY, no model solve).

Fossil dispatch floor (candidate_floors.csv) as a SHARE of electricity
demand (SpecifiedAnnualDemand), per scenario. Demand is IDENTICAL across all
four scenarios (a model constraint), so any BAU-vs-OPT or INV-vs-VGB
difference in this share is pure floor effect, not a demand artifact. This
is the check the earlier post-solve gates could not provide:
test_outputs.scenario_separation needs a solved TotalTechnologyAnnualActivity
and is not demand-normalized, so it could not catch the Phase D inversion
(BAU floors MORE fossil than OPT before 2035, found by this same style of
demand-share analysis run ad hoc during Phase D triage).

PI decision (2026-07-03): OPT/VGB carry the higher floor at every year (OPT
is the committed ceiling); BAU/INV converge with OPT near-term (2027-2035)
then wind down below it. No inversion, no mid-horizon convergence dead-zone.

Asserts (exit code 1 with a clear message on failure, 0 on pass):
  (a) no (tech, year) where the BAU floor_PJ exceeds the OPT floor_PJ for the
      same tech, and likewise INV vs VGB.
  (b) OPT system-wide share >= BAU system-wide share at 2040 and 2050
      (likewise VGB vs INV).
  (c) non-crossing gap: for every year >= 2035, OPT share >= BAU share
      (likewise VGB vs INV).

Usage:
  python preflight_separation.py
  python preflight_separation.py --candidates FILE
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> scripts/
from common import relac_paths as P

import pandas as pd

from floor_effect import TechPhysics

HERE = Path(__file__).resolve().parent
DEFAULT_CANDIDATES = P.CANDIDATE_FLOORS

REPORT_YEARS = [2030, 2040, 2050]
PAIRS = [("BAU", "OPT"), ("INV", "VGB")]
NONCROSS_FROM = 2035          # PI decision: no crossing from this year on
FLOOR_TOL = 1e-3              # PJ; covers the 4-decimal rounding in candidate_floors.csv
SHARE_TOL = 1e-6              # dimensionless share


def load_candidates(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, comment="#")
    required = {"Scenario", "TECHNOLOGY", "country", "YEAR", "floor_PJ"}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f"{path.name} missing required columns: {missing}")
    df["YEAR"] = df["YEAR"].astype(int)
    return df


def load_demand() -> dict[tuple[str, int], float]:
    """SpecifiedAnnualDemand is identical across scenarios; load once from BAU."""
    return TechPhysics("BAU").demand


def per_country_share(cand: pd.DataFrame, demand: dict) -> pd.DataFrame:
    g = cand.groupby(["Scenario", "country", "YEAR"], as_index=False)["floor_PJ"].sum()
    g["demand_PJ"] = [demand.get((c, y)) for c, y in zip(g["country"], g["YEAR"])]
    g["share"] = g["floor_PJ"] / g["demand_PJ"]
    return g


def system_share(cand: pd.DataFrame, demand: dict) -> pd.DataFrame:
    total_demand_by_year: dict[int, float] = {}
    for (_country, year), val in demand.items():
        total_demand_by_year[year] = total_demand_by_year.get(year, 0.0) + val

    g = cand.groupby(["Scenario", "YEAR"], as_index=False)["floor_PJ"].sum()
    g["demand_PJ"] = [total_demand_by_year.get(y) for y in g["YEAR"]]
    g["share"] = g["floor_PJ"] / g["demand_PJ"]
    return g.sort_values(["Scenario", "YEAR"]).reset_index(drop=True)


def _pct(x) -> str:
    if x is None or pd.isna(x):
        return "--"
    return f"{100*x:.1f}%"


def print_pair_report(pair, system_df: pd.DataFrame, country_df: pd.DataFrame):
    a, b = pair
    print(f"\n{'='*78}")
    print(f"{a} vs {b}  --  system-wide fossil floor as a share of electricity demand")
    print("=" * 78)
    sys_a = system_df[system_df.Scenario == a].set_index("YEAR")["share"]
    sys_b = system_df[system_df.Scenario == b].set_index("YEAR")["share"]
    print(f"  {'year':<6}{a + '_share':>12}{b + '_share':>12}{'gap(' + b + '-' + a + ')':>16}")
    for y in REPORT_YEARS:
        va, vb = sys_a.get(y), sys_b.get(y)
        gap = (vb - va) if (va is not None and vb is not None) else None
        print(f"  {y:<6}{_pct(va):>12}{_pct(vb):>12}{_pct(gap):>16}")

    print(f"\n  Top per-country divergences ({b} share minus {a} share, by |gap|):")
    for y in REPORT_YEARS:
        ca = country_df[(country_df.Scenario == a) & (country_df.YEAR == y)].set_index("country")["share"]
        cb = country_df[(country_df.Scenario == b) & (country_df.YEAR == y)].set_index("country")["share"]
        countries = sorted(set(ca.index) | set(cb.index))
        diffs = []
        for c in countries:
            va = ca.get(c) or 0.0
            vb = cb.get(c) or 0.0
            diffs.append((c, va, vb, vb - va))
        diffs.sort(key=lambda t: -abs(t[3]))
        print(f"    {y}:")
        for c, va, vb, d in diffs[:5]:
            print(f"      {c:<5} {a}={_pct(va):>8}  {b}={_pct(vb):>8}  gap={_pct(d):>8}")


def assert_no_inversion(cand: pd.DataFrame, a: str, b: str, tol: float = FLOOR_TOL):
    fa = cand[cand.Scenario == a].groupby(["TECHNOLOGY", "YEAR"])["floor_PJ"].sum()
    fb = cand[cand.Scenario == b].groupby(["TECHNOLOGY", "YEAR"])["floor_PJ"].sum()
    idx = fa.index.union(fb.index)
    fa = fa.reindex(idx, fill_value=0.0)
    fb = fb.reindex(idx, fill_value=0.0)
    diff = fa - fb
    bad = diff[diff > tol]
    return [(t, y, fa[(t, y)], fb[(t, y)]) for (t, y) in bad.index]


def assert_system_share_at(system_df: pd.DataFrame, a: str, b: str, years, tol: float = SHARE_TOL):
    sys_a = system_df[system_df.Scenario == a].set_index("YEAR")["share"]
    sys_b = system_df[system_df.Scenario == b].set_index("YEAR")["share"]
    fails = []
    for y in years:
        va, vb = sys_a.get(y), sys_b.get(y)
        if va is None or vb is None or pd.isna(va) or pd.isna(vb):
            continue
        if vb + tol < va:
            fails.append((y, va, vb))
    return fails


def assert_noncrossing(system_df: pd.DataFrame, a: str, b: str, from_year: int, tol: float = SHARE_TOL):
    sys_a = system_df[system_df.Scenario == a].set_index("YEAR")["share"]
    sys_b = system_df[system_df.Scenario == b].set_index("YEAR")["share"]
    fails = []
    for y in sorted(set(sys_a.index) & set(sys_b.index)):
        if y < from_year:
            continue
        va, vb = sys_a[y], sys_b[y]
        if pd.isna(va) or pd.isna(vb):
            continue
        if vb + tol < va:
            fails.append((y, va, vb))
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", type=str, default=str(DEFAULT_CANDIDATES))
    args = ap.parse_args()

    cand = load_candidates(Path(args.candidates))
    demand = load_demand()
    country_df = per_country_share(cand, demand)
    system_df = system_share(cand, demand)

    print(f"Loaded {len(cand)} candidate floor rows from {args.candidates}")
    print(f"Loaded demand for {len({c for c, _y in demand})} countries "
          f"x {len({y for _c, y in demand})} years (from BAU SpecifiedAnnualDemand)")

    for pair in PAIRS:
        print_pair_report(pair, system_df, country_df)

    failures = []
    for a, b in PAIRS:
        for t, y, va, vb in assert_no_inversion(cand, a, b):
            failures.append(f"(a) INVERSION {a}>{b}: {t} {y}: {a}={va:.4g} PJ > {b}={vb:.4g} PJ")
        for y, va, vb in assert_system_share_at(system_df, a, b, [2040, 2050]):
            failures.append(f"(b) SYSTEM SHARE {y}: {a}={_pct(va)} > {b}={_pct(vb)} "
                             f"(expected {b} >= {a})")
        for y, va, vb in assert_noncrossing(system_df, a, b, NONCROSS_FROM):
            failures.append(f"(c) CROSSING at {y}: {a}={_pct(va)} > {b}={_pct(vb)} "
                             f"(expected {b} >= {a} for every year >= {NONCROSS_FROM})")

    print("\n" + "=" * 78)
    if failures:
        print(f"FAIL  ({len(failures)} violation(s))")
        print("=" * 78)
        for f in failures[:60]:
            print(f"  {f}")
        if len(failures) > 60:
            print(f"  ... and {len(failures) - 60} more")
        sys.exit(1)
    else:
        print("PASS  -- no inversions, OPT/VGB system share >= BAU/INV at 2040 and 2050, "
              f"non-crossing gap from {NONCROSS_FROM} on.")
        print("=" * 78)
        sys.exit(0)


if __name__ == "__main__":
    main()
