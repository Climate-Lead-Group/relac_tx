"""
make_candidates.py  --  generate candidate dispatch floors (read-only).

Floors the FULL fossil fleet (relac_io.nonren_floor_techs), not the old
11-tech WORKING_SET. WORKING_SET excluded any tech that already had a
2023-2026 floor -- but those floors stop at 2026, so large fleets behind a
legacy floor (BRA/MEX/ARG gas, etc.) went completely unfloored from 2027 on.
This file floors 2027-2050 on a whole-fleet (residual + forced) basis and
freezes 2023-2026 untouched (no candidate rows emitted for those years).

Two scenario profiles (PI decision, 2026-07-03):

  COMMITTED = {OPT, VGB}  -- "use what you build": CF = plan_grounded ->
    historical_implied -> fuel fallback, held FLAT 2027-2050. These
    scenarios also force ~3x more fossil capacity than BAU/INV.

  PERMISSIVE = {BAU, INV} -- "let the fleet wind down": CF anchored to the
    SAME committed CF as COMMITTED (plan_grounded -> historical_implied ->
    fallback), held flat through HOLD_UNTIL, then declines linearly to
    min(committed, KEEP_WARM) by 2050. Anchoring to the committed CF (not to
    historical_implied directly) guarantees BAU_cf <= OPT_cf for every tech
    and year: no BAU/OPT inversion, and near-term (2027-2030) BAU converges
    with OPT (Phase D, 2026-07-03; HOLD_UNTIL/KEEP_WARM widened 2026-07-03
    to increase separation, see the constants below).

historical_implied_cf() reads each tech's own frozen 2023-2026 floor and
residual capacity, so it is feasible by construction (the floor is already
in the model) and gives a natural continuous seam into 2027 for BAU/INV.

Floor value: floor_PJ(tech, year) = total_available_capacity(tech, year)
             * CapacityToActivityUnit * CF(tech, scenario, year)
where total_available_capacity = ResidualCapacity + cumulative forced builds
(feasibility.Feasibility.total_available_capacity).

Writes inputs/tx_chain/fix_dispatch/candidate_floors.csv. Every downstream script
(write_floors.py, input_comparison_report, test_outputs.py) reads floors
from candidate_floors.csv ONLY. To change a CF: edit PLAN_GROUNDED or
CF_BY_FUEL_FALLBACK below and re-run this script, then re-run write_floors.py.

CF provenance: cf_table_working_set.py in the _Dataset_Power working folder
(Phase A; to be widened by a Phase B in-folder research pass).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> scripts/
from common import relac_paths as P

import pandas as pd

import relac_io as io
from feasibility import Feasibility

HERE = Path(__file__).resolve().parent
OUT = P.CANDIDATE_FLOORS

# Plan-grounded per-tech CF and quality tier, from cf_table_full.py in the
# _Dataset_Power working folder (Phase B/C: 37 techs, whole-fleet basis,
# reconciled against the Phase A 11-tech forced-tranche calibration; see
# that file's module docstring for the full reconciliation record, including
# which Phase A numbers were superseded, which were deliberately kept over
# a Phase B alternative, and the tech-name corrections found along the way).
PLAN_GROUNDED = {
    "PWRNGSMEXXX": (0.45, "grounded"),
    "PWROILMEXXX": (0.0883, "proxy"),
    "PWRCOABRAXX": (0.20, "grounded"),
    "PWRNGSBRAXX": (0.12, "grounded"),
    "PWRCOAARGXX": (0.37, "proxy"),
    "PWRNGSARGXX": (0.37, "grounded"),
    "PWRPETARGXX": (0.33, "grounded"),
    "PWRCOACHLXX": (0.35, "proxy"),
    "PWRNGSCHLXX": (0.30, "proxy"),
    "PWROILCHLXX": (0.03, "proxy"),
    "PWRCOACOLXX": (0.28, "grounded"),
    "PWRNGSCOLXX": (0.15, "grounded"),
    "PWRPETCOLXX": (0.01, "grounded"),
    "PWRNGSECUXX": (0.2055, "grounded"),
    "PWROILECUXX": (0.437, "grounded"),
    "PWRPETECUXX": (0.30, "grounded"),
    "PWRCOADOMXX": (0.70, "grounded"),
    "PWRNGSDOMXX": (0.53, "grounded"),
    "PWROILDOMXX": (0.35, "grounded"),
    "PWRNGSBOLXX": (0.36, "grounded"),
    "PWRNGSHNDXX": (0.78, "stated"),
    "PWROILHNDXX": (0.35, "grounded"),
    "PWRPETHNDXX": (0.35, "grounded"),
    "PWRNGSNICXX": (0.1372, "proxy"),
    "PWROILNICXX": (0.1372, "grounded"),
    "PWRCOAPANXX": (0.01, "grounded"),
    "PWRNGSPANXX": (0.35, "grounded"),
    "PWROILPANXX": (0.02, "grounded"),
    "PWRNGSSLVXX": (0.15, "grounded"),
    "PWROILSLVXX": (0.30, "grounded"),
    "PWRCOAGTMXX": (0.50, "grounded"),
    "PWRNGSGTMXX": (0.15, "proxy"),
    "PWROILGTMXX": (0.08, "grounded"),
    "PWRPETGTMXX": (0.10, "proxy"),
    "PWROILCRIXX": (0.03, "grounded"),
    "PWRPETURYXX": (0.045, "grounded"),
    "PWRPETBRBXX": (0.10, "proxy"),
    "PWRNGSPERXX": (0.2779, "proxy"),
}

# Fuel-level fallback for any tech with neither a plan-grounded nor a
# historical-implied CF. NGS/OIL/PET are the 17-country regional medians
# from fill_cf_gaps.py; COA is that same script's regional median for coal;
# GAS/COG mirror NGS (no techs currently exist on those two codes).
CF_BY_FUEL_FALLBACK = {
    "NGS": 0.2779, "OIL": 0.0883, "PET": 0.10, "COA": 0.85,
    "GAS": 0.2779, "COG": 0.2779,
}

COMMITTED = {"OPT", "VGB"}    # forced+residual fleet, flat plan-grounded CF
PERMISSIVE = {"BAU", "INV"}   # residual+forced fleet, declining CF

FIRST_FLOOR_YEAR = 2027       # 2023-2026 stay frozen (no candidate rows)
LAST = io.LAST_YEAR           # 2050
HOLD_UNTIL = 2030             # PERMISSIVE CF held flat through this year
KEEP_WARM = 0.05              # PERMISSIVE CF floor at the 2050 horizon end

STATUS = "CALIBRATED - pending PI sign-off"
HEADER_COMMENT = (
    "# THE SWAPPABLE INPUT of the dispatch-floor pipeline. write_floors.py,\n"
    "# input_comparison_report and test_outputs.py read floors from THIS FILE\n"
    "# ONLY. Floors the full fossil fleet (relac_io.nonren_floor_techs), on a\n"
    "# residual+forced basis, 2027-2050 only (2023-2026 frozen). COMMITTED\n"
    "# scenarios (OPT,VGB) use a flat plan-grounded/historical CF; PERMISSIVE\n"
    "# scenarios (BAU,INV) start at the committed plan-grounded/historical CF\n"
    "# and decline after HOLD_UNTIL=2030 to KEEP_WARM=0.05 by 2050. To change\n"
    "# a CF: edit PLAN_GROUNDED / CF_BY_FUEL_FALLBACK\n"
    "# in make_candidates.py and re-run it, then re-run write_floors.py.\n"
)


def historical_implied_cf(feas: Feasibility, tech: str) -> float | None:
    """CF implied by this tech's own frozen 2023-2026 floor: the most recent
    year with both a nonzero existing floor and nonzero residual capacity.
    Scenario-independent by construction (2023-2026 is symmetric).

    Rejects (falls through to the next hierarchy tier) any result outside
    (0, 1]: for a small number of techs (found: PWRPETHNDXX, PWRPETCRIXX)
    the original extraction pipeline set the frozen floor against a capacity
    basis other than this tech's current whole-residual-fleet reading (e.g.
    a specific committed project's own capacity), so dividing by residual
    here overstates the implied CF past what is physically meaningful."""
    c2a = feas.c2a_of(tech)
    for year in (2026, 2025, 2024, 2023):
        floor_pj = feas.lower.get((tech, year))
        if not floor_pj:
            continue
        resid_gw = feas.residual(tech, year)
        if resid_gw <= 0:
            continue
        cf = float(floor_pj) / (resid_gw * c2a)
        if 0.0 < cf <= 1.0:
            return cf
    return None


def permissive_cf(start: float, year: int) -> float:
    """Flat at `start` through HOLD_UNTIL, then linear down to
    min(start, KEEP_WARM) by LAST. Already-low peakers (start < KEEP_WARM)
    are never pushed up -- the target is a min, not a fixed floor."""
    target = min(start, KEEP_WARM)
    if year <= HOLD_UNTIL:
        return start
    if year >= LAST:
        return target
    frac = (year - HOLD_UNTIL) / (LAST - HOLD_UNTIL)
    return start + (target - start) * frac


def build() -> pd.DataFrame:
    # historical_implied is read off the frozen 2023-2026 block, which is
    # identical across scenarios by the model's own symmetry constraint, so
    # it is computed once against a single anchor scenario and reused.
    anchor = Feasibility(io.SCENARIOS[0])
    historical: dict[str, float | None] = {}

    rows = []
    for scen in io.SCENARIOS:
        feas = Feasibility(scen)
        for tech in io.nonren_floor_techs(scen):
            p = io.parse_tech(tech)
            fuel = p["fuel"]
            c2a = feas.c2a_of(tech)

            if tech not in historical:
                historical[tech] = historical_implied_cf(anchor, tech)
            hist = historical[tech]
            plan_cf, plan_quality = PLAN_GROUNDED.get(tech, (None, None))
            fallback = CF_BY_FUEL_FALLBACK.get(fuel, 0.10)

            # Committed CF = the OPT/VGB ceiling: plan_grounded -> historical -> fallback.
            # Computed for every tech; PERMISSIVE (BAU/INV) is anchored to THIS
            # value and only declines from it, so BAU can never exceed OPT.
            if plan_cf is not None:
                committed_cf, cf_source, cf_quality = plan_cf, "plan_grounded", plan_quality
            elif hist is not None:
                committed_cf, cf_source, cf_quality = hist, "historical_implied", "historical"
            else:
                committed_cf, cf_source, cf_quality = fallback, "fuel_fallback", "proxy"
            profile = "COMMITTED" if scen in COMMITTED else "PERMISSIVE"

            forced_years = sorted(y for (t, y), v in feas.mincapinv.items() if t == tech and v > 0)
            commissioning_year = min(forced_years) if forced_years else None

            for year in range(FIRST_FLOOR_YEAR, LAST + 1):
                cap = feas.total_available_capacity(tech, year)
                if cap <= 0:
                    continue
                cf = committed_cf if scen in COMMITTED else permissive_cf(committed_cf, year)
                floor = cap * c2a * cf
                rows.append(dict(
                    Scenario=scen, TECHNOLOGY=tech, country=p["country"], fuel=fuel,
                    YEAR=year,
                    fleet_GW=round(cap, 4),
                    forced_GW=round(feas.cumulative_forced_capacity(tech, year), 4),
                    residual_GW=round(feas.residual(tech, year), 4),
                    contracted_CF=round(cf, 4),
                    cf_source=cf_source,
                    cf_quality=cf_quality,
                    floor_PJ=round(floor, 4),
                    profile=profile,
                    status=STATUS,
                    commissioning_year=commissioning_year,
                ))
    return (pd.DataFrame(rows)
            .sort_values(["Scenario", "TECHNOLOGY", "YEAR"])
            .reset_index(drop=True))


def main():
    df = build()
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        f.write(HEADER_COMMENT)
        df.to_csv(f, index=False)
    print(f"Wrote {OUT.name}: {len(df)} candidate floors "
          f"({df['TECHNOLOGY'].nunique()} techs, scenarios {sorted(df['Scenario'].unique())})")
    print(df.groupby(["Scenario", "profile"]).size().to_string())
    print("\ncf_source mix:")
    print(df.groupby("cf_source").size().to_string())


if __name__ == "__main__":
    main()
