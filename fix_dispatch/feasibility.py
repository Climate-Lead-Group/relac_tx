"""
feasibility.py  --  shared feasibility model for dispatch floors.

feasible_floor(tech, year, floor_PJ) answers: can this technology physically
deliver at least `floor_PJ` of annual generation in `year`, given the capacity
ceilings and availability the model actually imposes?

It is a NECESSARY-condition check (a generous upper bound on producible energy):
  1. floor_PJ <= Cap_max * CapacityToActivityUnit * AvailabilityFactor
     where Cap_max = the binding (min) of
        - TotalAnnualMaxCapacity(tech, year)                         [txt]
        - ResidualCapacity(tech, year) + cumulative
          TotalAnnualMaxCapacityInvestment(tech, <=year)            [txt + otoole]
     default -1 means "unbounded" for the Max* parameters.
  2. floor_PJ <= TotalTechnologyAnnualActivityUpperLimit(tech, year) if present  [txt]

Sources:
  - TotalAnnualMaxCapacity, TotalAnnualMaxCapacityInvestment, AvailabilityFactor,
    TotalTechnologyAnnualActivityUpperLimit, TotalAnnualMinCapacityInvestment  -> preprocessed txt
  - ResidualCapacity, CapacityToActivityUnit, OperationalLife                  -> A2 otoole CSVs
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict

import relac_io as io

# parameters pulled from the authoritative preprocessed txt
_TXT_PARAMS = [
    "TotalAnnualMaxCapacity",
    "TotalAnnualMaxCapacityInvestment",
    "AvailabilityFactor",
    "TotalTechnologyAnnualActivityUpperLimit",
    "TotalAnnualMinCapacityInvestment",
    "TotalTechnologyAnnualActivityLowerLimit",
]

NEAR_CAP_FRAC = 0.05  # flag floors within 5% of the binding ceiling


@dataclass
class FloorVerdict:
    scenario: str
    tech: str
    year: int
    floor_PJ: float
    feasible: bool
    binding: str            # which ceiling is tightest ('unbounded' if none)
    ceiling_PJ: float | None
    headroom_PJ: float | None
    headroom_frac: float | None
    near_cap: bool
    cap_max_GW: float | None
    cap_source: str
    availability: float
    c2a: float
    max_energy_PJ: float | None
    upper_limit_PJ: float | None
    implied_CF: float | None   # floor / (cap_max * c2a)

    def as_row(self) -> dict:
        return asdict(self)


class Feasibility:
    def __init__(self, scenario: str):
        self.scenario = scenario
        mp = io.parse_mathprog(scenario, _TXT_PARAMS)
        self.maxcap = io.to_lookup(mp["TotalAnnualMaxCapacity"], ["TECHNOLOGY", "YEAR"])
        self.maxcapinv = io.to_lookup(mp["TotalAnnualMaxCapacityInvestment"], ["TECHNOLOGY", "YEAR"])
        self.avail = io.to_lookup(mp["AvailabilityFactor"], ["TECHNOLOGY", "YEAR"])
        self.upper = io.to_lookup(mp["TotalTechnologyAnnualActivityUpperLimit"], ["TECHNOLOGY", "YEAR"])
        self.mincapinv = io.to_lookup(mp["TotalAnnualMinCapacityInvestment"], ["TECHNOLOGY", "YEAR"])
        self.lower = io.to_lookup(mp["TotalTechnologyAnnualActivityLowerLimit"], ["TECHNOLOGY", "YEAR"])

        resid = io.load_otoole(scenario, "ResidualCapacity")
        self.resid = io.to_lookup(resid, ["TECHNOLOGY", "YEAR"]) if len(resid) else {}

        c2a = io.load_otoole(scenario, "CapacityToActivityUnit")
        self.c2a = {}
        if len(c2a):
            for row in c2a[["TECHNOLOGY", "VALUE"]].itertuples(index=False, name=None):
                self.c2a[row[0]] = float(row[1])

        ol = io.load_otoole(scenario, "OperationalLife")
        self.oplife = {}
        if len(ol):
            for row in ol[["TECHNOLOGY", "VALUE"]].itertuples(index=False, name=None):
                self.oplife[row[0]] = float(row[1])

    # -- primitive accessors -------------------------------------------------
    def c2a_of(self, tech: str) -> float:
        return self.c2a.get(tech, io.C2A_DEFAULT)

    def availability(self, tech: str, year: int) -> float:
        return float(self.avail.get((tech, year), 1.0))

    def operational_life(self, tech: str) -> float:
        return float(self.oplife.get(tech, 30.0))

    def residual(self, tech: str, year: int) -> float:
        return float(self.resid.get((tech, year), 0.0))

    # -- capacity ceiling ----------------------------------------------------
    def _resid_plus_cuminv(self, tech: str, year: int):
        """ResidualCapacity(year) + cumulative MaxCapacityInvestment(<=year).

        Returns None (unbounded) if any relevant year permits unbounded
        investment (default/-1). Returns a finite GW ceiling otherwise.
        """
        total = 0.0
        for y in range(io.FIRST_YEAR, year + 1):
            v = self.maxcapinv.get((tech, y))
            if v is None or v == -1:
                return None  # unbounded investment allowed -> capacity unbounded
            total += float(v)
        return self.residual(tech, year) + total

    def capacity_upper_bound(self, tech: str, year: int):
        """(cap_GW or None, source-string). None => unbounded."""
        bounds = []
        mc = self.maxcap.get((tech, year))
        if mc is not None and mc != -1:
            bounds.append((float(mc), "TotalAnnualMaxCapacity"))
        b2 = self._resid_plus_cuminv(tech, year)
        if b2 is not None:
            bounds.append((b2, "ResidualCapacity+cumMaxCapacityInvestment"))
        if not bounds:
            return None, "unbounded"
        cap, src = min(bounds, key=lambda x: x[0])
        return cap, src

    def cumulative_forced_capacity(self, tech: str, year: int, apply_life: bool = True) -> float:
        """Sum of TotalAnnualMinCapacityInvestment builds in force during `year`.

        If apply_life, a build in year b counts only while b <= year < b+OperationalLife.
        """
        life = self.operational_life(tech)
        total = 0.0
        for (t, b), v in self.mincapinv.items():
            if t != tech or b > year:
                continue
            if apply_life and year >= b + life:
                continue
            total += float(v)
        return total

    def total_available_capacity(self, tech: str, year: int, apply_life: bool = True) -> float:
        """Residual + cumulative forced capacity, in GW: the whole fleet a
        fleet-basis dispatch floor multiplies against, as opposed to the
        forced-only tranche."""
        return self.residual(tech, year) + self.cumulative_forced_capacity(tech, year, apply_life)

    # -- the check -----------------------------------------------------------
    def feasible_floor(self, tech: str, year: int, floor_PJ: float) -> FloorVerdict:
        c2a = self.c2a_of(tech)
        af = self.availability(tech, year)
        cap, cap_src = self.capacity_upper_bound(tech, year)
        max_energy = None if cap is None else cap * c2a * af

        upper = self.upper.get((tech, year))
        if upper is not None and float(upper) == -1:
            upper = None
        upper = None if upper is None else float(upper)

        ceilings = []
        if max_energy is not None:
            ceilings.append((max_energy, "capacity(" + cap_src + ")"))
        if upper is not None:
            ceilings.append((upper, "TotalTechnologyAnnualActivityUpperLimit"))

        tiny = 1e-9
        if ceilings:
            ceil_val, binding = min(ceilings, key=lambda x: x[0])
            headroom = ceil_val - floor_PJ
            headroom_frac = (headroom / ceil_val) if ceil_val > 0 else (
                0.0 if floor_PJ <= 0 else -math.inf)
            feasible = floor_PJ <= ceil_val + tiny
            near_cap = feasible and headroom_frac <= NEAR_CAP_FRAC
        else:
            ceil_val = None
            binding = "unbounded"
            headroom = None
            headroom_frac = None
            feasible = True
            near_cap = False

        implied_cf = None
        if cap is not None and cap > 0:
            implied_cf = floor_PJ / (cap * c2a)

        return FloorVerdict(
            scenario=self.scenario, tech=tech, year=int(year), floor_PJ=float(floor_PJ),
            feasible=bool(feasible), binding=binding, ceiling_PJ=ceil_val,
            headroom_PJ=headroom, headroom_frac=headroom_frac, near_cap=bool(near_cap),
            cap_max_GW=cap, cap_source=cap_src, availability=af, c2a=c2a,
            max_energy_PJ=max_energy, upper_limit_PJ=upper, implied_CF=implied_cf,
        )


if __name__ == "__main__":
    f = Feasibility("OPT")
    for tech, yr in [("PWRNGSMEXXX", 2028), ("PWRNGSPERXX", 2031), ("PWRPETECUXX", 2029)]:
        cap, src = f.capacity_upper_bound(tech, yr)
        fwd = f.feasible_floor(tech, yr, 30.0)  # arbitrary 30 PJ probe
        print(f"{tech} {yr}: cap={cap} ({src}) af={f.availability(tech,yr)} "
              f"cumForced={f.cumulative_forced_capacity(tech,yr):.3f} GW "
              f"-> feasible@30PJ={fwd.feasible} binding={fwd.binding} "
              f"ceiling={None if fwd.ceiling_PJ is None else round(fwd.ceiling_PJ,1)}")
