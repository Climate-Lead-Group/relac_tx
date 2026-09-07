"""
floor_effect.py  --  STEP 2 deterministic floor-effect calculator (read-only, no solve).

Given candidate floors (scenario, tech, year, floor_PJ) it computes ONLY what a
TotalTechnologyAnnualActivityLowerLimit mathematically GUARANTEES, and leaves
everything the optimizer freely chooses explicitly unresolved. This is a partial
energy balance, NOT a dispatch prediction. It does not model transmission flows.

Per candidate floor it reports:
  - forced generation (PJ)          = the floor value            [GUARANTEED MIN]
  - implied capacity factor         = floor / (capacity_GW * C2A)
        against cumulative forced capacity AND against the feasibility Cap_max
  - feasibility (feasible_floor)    : feasible?, binding ceiling, headroom
  - implied fuel input (PJ)         = floor * (IAR/OAR)          [GUARANTEED MIN]
        (fuel SOURCE / mode left to optimizer; flagged if efficiency missing)
  - implied CO2                     = floor * (EAR/OAR)          [range if mode-dependent]
  - demand share                    = floor / country ELC demand [activity basis, approx]

Everything not derivable from the floor alone is labelled "left to optimizer."

Sources: efficiency (OAR/IAR), emissions (EAR), demand (SpecifiedAnnualDemand)
         from the A2 otoole per-scenario CSVs; caps/availability/life from the
         feasibility model (preprocessed txt + otoole CSVs).

Usage:
  python floor_effect.py                      # demo on existing working-set floors
  python floor_effect.py --candidates FILE    # FILE: scenario,tech,year,floor_PJ
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> scripts/
from common import relac_paths as P

import pandas as pd

import relac_io as io
from feasibility import Feasibility

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = P.FIX_DISPATCH_OUT / "floor_effect_report.csv"

RATIO_CONSISTENT = 1.01  # max/min below this => treat a per-mode ratio as single-valued


class TechPhysics:
    """Per-scenario efficiency / emission / demand model, from A2 otoole CSVs."""

    def __init__(self, scenario: str):
        self.scenario = scenario
        oar = io.load_otoole(scenario, "OutputActivityRatio")
        iar = io.load_otoole(scenario, "InputActivityRatio")
        ear = io.load_otoole(scenario, "EmissionActivityRatio")
        dem = io.load_otoole(scenario, "SpecifiedAnnualDemand")

        # (tech, mode, year) -> summed coefficient ; also fuel/emission name sets
        self.oar = self._sum_by(oar, "FUEL")
        self.iar = self._sum_by(iar, "FUEL")
        self.ear = self._sum_by(ear, "EMISSION")
        self.in_fuels = self._names(iar, "FUEL")
        self.emissions = self._names(ear, "EMISSION")

        # country electricity demand: SpecifiedAnnualDemand[ELC<country>XX03, year]
        self.demand = {}
        if len(dem):
            for r in dem[["FUEL", "YEAR", "VALUE"]].itertuples(index=False, name=None):
                fuel, year, val = r
                if isinstance(fuel, str) and fuel.startswith("ELC") and fuel.endswith("03"):
                    country = fuel[3:6]
                    self.demand[(country, int(year))] = float(val)

    @staticmethod
    def _sum_by(df, dim):
        out = defaultdict(float)
        if df is None or len(df) == 0:
            return out
        for r in df[["TECHNOLOGY", "MODE_OF_OPERATION", "YEAR", "VALUE"]].itertuples(index=False, name=None):
            tech, mode, year, val = r
            out[(tech, int(mode), int(year))] += float(val)
        return out

    @staticmethod
    def _names(df, dim):
        out = defaultdict(set)
        if df is None or len(df) == 0:
            return out
        for r in df[["TECHNOLOGY", "YEAR", dim]].itertuples(index=False, name=None):
            out[(r[0], int(r[1]))].add(r[2])
        return out

    def _modes(self, tech, year):
        return sorted({m for (t, m, y) in self.oar if t == tech and y == year})

    def per_output_ratio(self, table, tech, year):
        """Return (value, lo, hi, mode_dependent, available) for ratio table/OAR per mode."""
        modes = self._modes(tech, year)
        ratios = []
        for m in modes:
            oar = self.oar.get((tech, m, year), 0.0)
            num = table.get((tech, m, year), 0.0)
            if oar > 0:
                ratios.append(num / oar)
        if not ratios:
            return None, None, None, False, False
        lo, hi = min(ratios), max(ratios)
        mode_dep = (lo > 0 and hi / lo > RATIO_CONSISTENT) or (lo == 0 and hi > 0)
        val = sum(ratios) / len(ratios)
        return val, lo, hi, mode_dep, True

    def efficiency(self, tech, year):
        """Electricity-out per fuel-in (OAR/IAR), mode-averaged; None if unavailable."""
        modes = self._modes(tech, year)
        effs = []
        for m in modes:
            oar = self.oar.get((tech, m, year), 0.0)
            iar = self.iar.get((tech, m, year), 0.0)
            if iar > 0:
                effs.append(oar / iar)
        if not effs:
            return None
        return sum(effs) / len(effs)

    def country_demand(self, country, year):
        return self.demand.get((country, int(year)))


def evaluate(candidates: pd.DataFrame) -> pd.DataFrame:
    rows = []
    phys_cache, feas_cache = {}, {}
    for scen in candidates["scenario"].unique():
        phys_cache[scen] = TechPhysics(scen)
        feas_cache[scen] = Feasibility(scen)

    for c in candidates.itertuples(index=False):
        scen, tech, year, floor = c.scenario, c.tech, int(c.year), float(c.floor_PJ)
        phys, feas = phys_cache[scen], feas_cache[scen]
        p = io.parse_tech(tech)

        v = feas.feasible_floor(tech, year, floor)
        cum_forced = feas.cumulative_forced_capacity(tech, year)
        cf_forced = floor / (cum_forced * feas.c2a_of(tech)) if cum_forced > 0 else None

        # fuel input = floor * (IAR/OAR)
        fr, fr_lo, fr_hi, fr_modedep, fr_ok = phys.per_output_ratio(phys.iar, tech, year)
        if fr_ok:
            fuel_pj = floor * fr
            fuel_lo, fuel_hi = floor * fr_lo, floor * fr_hi
            fuel_flag = "mode-dependent(range)" if fr_modedep else "ok"
        else:
            fuel_pj = floor            # brief: report fuel = generation, flag missing
            fuel_lo = fuel_hi = None
            fuel_flag = "MISSING_EFFICIENCY:fuel=generation"

        # CO2 = floor * (EAR/OAR)
        er, er_lo, er_hi, er_modedep, er_ok = phys.per_output_ratio(phys.ear, tech, year)
        if er_ok:
            co2 = floor * er
            co2_lo, co2_hi = floor * er_lo, floor * er_hi
            co2_flag = "mode-dependent(range)" if er_modedep else "ok"
        else:
            co2 = None
            co2_lo = co2_hi = None
            co2_flag = "NOT_COMPUTED:no_EAR"

        eff = phys.efficiency(tech, year)
        demand = phys.country_demand(p["country"], year) if p["country"] else None
        share = (floor / demand) if demand else None

        rows.append(dict(
            scenario=scen, tech=tech, country=p["country"], fuel=p["fuel"],
            category=_category(p), year=year,
            floor_PJ=round(floor, 4),
            cum_forced_GW=round(cum_forced, 4),
            cap_max_GW=(None if v.cap_max_GW is None else round(v.cap_max_GW, 4)),
            implied_CF_vs_forced=(None if cf_forced is None else round(cf_forced, 4)),
            implied_CF_vs_capmax=(None if v.implied_CF is None else round(v.implied_CF, 4)),
            availability=v.availability,
            feasible=v.feasible, binding=v.binding,
            ceiling_PJ=(None if v.ceiling_PJ is None else round(v.ceiling_PJ, 3)),
            headroom_frac=(None if v.headroom_frac is None else round(v.headroom_frac, 4)),
            efficiency_out_per_in=(None if eff is None else round(eff, 4)),
            fuel_input_PJ=(None if fuel_pj is None else round(fuel_pj, 3)),
            fuel_input_PJ_lo=(None if fuel_lo is None else round(fuel_lo, 3)),
            fuel_input_PJ_hi=(None if fuel_hi is None else round(fuel_hi, 3)),
            fuel_flag=fuel_flag,
            input_fuels=";".join(sorted(phys.in_fuels.get((tech, year), []))),
            CO2=(None if co2 is None else round(co2, 4)),
            CO2_lo=(None if co2_lo is None else round(co2_lo, 4)),
            CO2_hi=(None if co2_hi is None else round(co2_hi, 4)),
            CO2_flag=co2_flag,
            country_demand_PJ=(None if demand is None else round(demand, 2)),
            demand_share=(None if share is None else round(share, 4)),
        ))
    return pd.DataFrame(rows)


def _category(p):
    if p["is_fossil"]:
        return "fossil"
    if p["is_nuclear"]:
        return "nuclear"
    if p["is_renewable"]:
        return "renewable"
    if p["is_storage"]:
        return "storage"
    return "other"


def demo_candidates() -> pd.DataFrame:
    """Existing fossil-fleet floors as candidates (to exercise the calculator)."""
    rows = []
    for scen in io.SCENARIOS:
        mp = io.parse_mathprog(scen, ["TotalTechnologyAnnualActivityLowerLimit"])
        lower = io.to_lookup(mp["TotalTechnologyAnnualActivityLowerLimit"], ["TECHNOLOGY", "YEAR"])
        floor_techs = set(io.nonren_floor_techs(scen))
        for (t, y), v in lower.items():
            if t in floor_techs and v > 0:
                rows.append(dict(scenario=scen, tech=t, year=int(y), floor_PJ=float(v)))
    return pd.DataFrame(rows).sort_values(["scenario", "tech", "year"]).reset_index(drop=True)


def print_aggregates(res: pd.DataFrame):
    print("\n" + "=" * 78)
    print("FLOOR-EFFECT: guaranteed-minimum consequences of the candidate floors")
    print("(all values are GUARANTEED MINIMUMS forced by the floor; fuel source,")
    print(" mode mix, and any generation above the floor are LEFT TO OPTIMIZER)")
    print("=" * 78)

    print("\nForced generation (PJ, guaranteed min) per scenario x year:")
    g = res.groupby(["scenario", "year"])["floor_PJ"].sum().unstack("year").fillna(0).round(1)
    with pd.option_context("display.max_columns", None, "display.width", 200):
        print(g)

    print("\nForced generation (PJ) per scenario x country (sum over years):")
    gc = res.groupby(["scenario", "country"])["floor_PJ"].sum().unstack("country").fillna(0).round(1)
    with pd.option_context("display.max_columns", None, "display.width", 200):
        print(gc)

    print("\nForced generation (PJ) per scenario x fuel (sum over years):")
    gf = res.groupby(["scenario", "fuel"])["floor_PJ"].sum().unstack("fuel").fillna(0).round(1)
    with pd.option_context("display.max_columns", None, "display.width", 200):
        print(gf)

    print("\nGuaranteed CO2 (sum over years) and any infeasible candidates:")
    co2 = res.groupby("scenario")["CO2"].sum(min_count=1).round(1)
    print(co2.to_string())
    infe = res[~res["feasible"]]
    print(f"\nInfeasible candidate floors: {len(infe)}")
    if len(infe):
        for _, r in infe.head(20).iterrows():
            print(f"  [{r.scenario}] {r.tech} {r.year}: floor {r.floor_PJ} PJ > ceiling "
                  f"{r.ceiling_PJ} PJ ({r.binding})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", type=str, default=None,
                    help="CSV with columns scenario,tech,year,floor_PJ")
    ap.add_argument("--out", type=str, default=str(DEFAULT_OUT))
    args = ap.parse_args()

    if args.candidates:
        cand = pd.read_csv(args.candidates, comment="#")  # skip header comment line(s)
        missing = {"scenario", "tech", "year", "floor_PJ"} - set(cand.columns)
        if missing:
            raise SystemExit(f"candidates CSV missing columns: {missing}")
        src = f"candidates file {args.candidates}"
    else:
        cand = demo_candidates()
        src = "DEMO on existing working-set floors (no candidate file given)"

    print(f"Evaluating {len(cand)} candidate floors  [{src}]")
    res = evaluate(cand)
    res.to_csv(args.out, index=False)
    print_aggregates(res)
    print(f"\nWrote {args.out} ({len(res)} rows)")


if __name__ == "__main__":
    main()
