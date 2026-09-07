"""
validate_constraints.py  --  STEP 1 read-only input validator.

Reads (never writes) the authoritative inputs and flags, per scenario:

  FORCED_NO_FLOOR          TotalAnnualMinCapacityInvestment > 0 in a year > 2026
                           with no TotalTechnologyAnnualActivityLowerLimit that year.
  FLOOR_ENDS_BEFORE_LIFE   tech with both a forced build and a floor, where the floor's
                           last year < first_forced_year + OperationalLife.
  FLOOR_CF_IMPLAUSIBLE     existing floor whose implied CF = floor/(Cap_max*C2A) > 1 or < 0.
  FLOOR_INFEASIBLE         existing floor that fails feasible_floor (exceeds a binding ceiling).
  FLOOR_NEAR_CAP           existing floor within 5% of its binding ceiling.
  ORPHAN_FLOOR             floor > 0 for a tech-year with no capacity path (Cap_max == 0).
  SCENARIO_ASYMMETRY       any txt parameter whose 2023-2026 values differ across BAU/INV/OPT/VGB.
  PIPELINE_MISMATCH        floors / forced builds parsed from the txt disagree with the
                           same columns in the combined CSV.

Outputs:  outputs/fix_dispatch/validation_report.txt   (readable)
          outputs/fix_dispatch/validation_flags.csv    (machine-readable)

Sources:  limits + forced builds -> preprocessed txt (authoritative)
          OperationalLife/ResidualCapacity/C2A/Max*/AF -> feasibility model
          combined CSV columns -> pipeline-integrity cross-check only
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> scripts/
from common import relac_paths as P

import pandas as pd

import relac_io as io
from feasibility import Feasibility, NEAR_CAP_FRAC

HERE = Path(__file__).resolve().parent
REPORT_TXT = P.FIX_DISPATCH_OUT / "validation_report.txt"
FLAGS_CSV = P.FIX_DISPATCH_OUT / "validation_flags.csv"

VALUE_TOL = 1e-4      # tolerance for value equality (PJ / GW)
AFTER = 2026          # "after 2026" boundary


def _country_fuel(tech: str):
    p = io.parse_tech(tech)
    return p["country"], p["fuel"]


def _category(tech: str) -> str:
    p = io.parse_tech(tech)
    if p["is_fossil"]:
        return "fossil"
    if p["is_nuclear"]:
        return "nuclear"
    if p["is_renewable"]:
        return "renewable"
    if p["is_storage"]:
        return "storage"
    if p["kind"] in ("tx", "interconnector"):
        return "transmission"
    return "other"


def collect_flags():
    flags = []  # dict rows

    def add(scenario, check, tech, year, severity, detail, va=None, vb=None):
        country, fuel = _country_fuel(tech)
        flags.append(dict(scenario=scenario, check=check, tech=tech,
                          country=country, fuel=fuel,
                          year=(None if year is None else int(year)),
                          severity=severity, value_a=va, value_b=vb, detail=detail))

    # ---- per-scenario, txt-based checks -----------------------------------
    feas = {}
    txt_lower = {}       # scen -> {(tech,year): floor}
    txt_forced = {}      # scen -> {(tech,year): mci}
    txt_upper = {}
    txt_all_params = {}  # scen -> {param: {(tech,year): val}}
    SYM_PARAMS = ["TotalTechnologyAnnualActivityLowerLimit",
                  "TotalTechnologyAnnualActivityUpperLimit",
                  "TotalAnnualMinCapacityInvestment",
                  "TotalAnnualMaxCapacity",
                  "TotalAnnualMaxCapacityInvestment",
                  "AvailabilityFactor"]

    for scen in io.SCENARIOS:
        f = Feasibility(scen)
        feas[scen] = f
        mp = io.parse_mathprog(scen, SYM_PARAMS)
        lower = io.to_lookup(mp["TotalTechnologyAnnualActivityLowerLimit"], ["TECHNOLOGY", "YEAR"])
        forced = io.to_lookup(mp["TotalAnnualMinCapacityInvestment"], ["TECHNOLOGY", "YEAR"])
        upper = io.to_lookup(mp["TotalTechnologyAnnualActivityUpperLimit"], ["TECHNOLOGY", "YEAR"])
        txt_lower[scen], txt_forced[scen], txt_upper[scen] = lower, forced, upper
        txt_all_params[scen] = {p: io.to_lookup(mp[p], ["TECHNOLOGY", "YEAR"]) for p in SYM_PARAMS}

        # floor-year coverage per tech
        floor_years = {}
        for (t, y) in lower:
            if lower[(t, y)] > VALUE_TOL:
                floor_years.setdefault(t, set()).add(y)
        forced_years = {}
        for (t, y) in forced:
            if forced[(t, y)] > VALUE_TOL:
                forced_years.setdefault(t, set()).add(y)

        # (1) FORCED_NO_FLOOR
        for t, yrs in forced_years.items():
            for y in sorted(yrs):
                if y > AFTER and lower.get((t, y), 0.0) <= VALUE_TOL:
                    add(scen, "FORCED_NO_FLOOR", t, y, "WARN",
                        f"forced build {forced[(t,y)]:.4g} GW in {y} (>2026) with no dispatch floor",
                        va=forced[(t, y)], vb=0.0)

        # (2) FLOOR_ENDS_BEFORE_LIFE  (techs with both a forced build and a floor)
        for t in sorted(set(forced_years) & set(floor_years)):
            life = feas[scen].operational_life(t)
            first_forced = min(forced_years[t])
            last_forced = max(forced_years[t])
            floor_last = max(floor_years[t])
            need_through = int(first_forced + life)  # per the brief
            if floor_last < need_through:
                add(scen, "FLOOR_ENDS_BEFORE_LIFE", t, floor_last, "WARN",
                    f"floor ends {floor_last}; first forced {first_forced}, last forced {last_forced}, "
                    f"life {life:.0f} -> capacity persists to ~{int(last_forced+life-1)}; "
                    f"unfloored tail {floor_last+1}-{need_through-1}",
                    va=floor_last, vb=need_through - 1)

        # (3/4/5) per existing floor: CF plausibility, feasibility, orphan
        for (t, y), val in lower.items():
            if val <= VALUE_TOL:
                continue
            v = feas[scen].feasible_floor(t, y, val)
            # implausible CF
            if v.implied_CF is not None and (v.implied_CF > 1.0 or v.implied_CF < 0.0):
                add(scen, "FLOOR_CF_IMPLAUSIBLE", t, y, "ERROR",
                    f"implied CF {v.implied_CF:.3f} vs Cap_max {v.cap_max_GW:.4g} GW "
                    f"({v.cap_source})", va=val, vb=v.implied_CF)
            # orphan: no capacity path at all
            if v.cap_max_GW is not None and v.cap_max_GW <= VALUE_TOL:
                add(scen, "ORPHAN_FLOOR", t, y, "ERROR",
                    f"floor {val:.4g} PJ but Cap_max = 0 GW (no residual, no permitted investment)",
                    va=val, vb=0.0)
            elif not v.feasible:
                add(scen, "FLOOR_INFEASIBLE", t, y, "ERROR",
                    f"floor {val:.4g} PJ exceeds binding ceiling {v.ceiling_PJ:.4g} PJ ({v.binding})",
                    va=val, vb=v.ceiling_PJ)
            elif v.near_cap:
                add(scen, "FLOOR_NEAR_CAP", t, y, "WARN",
                    f"floor {val:.4g} PJ within {NEAR_CAP_FRAC:.0%} of ceiling {v.ceiling_PJ:.4g} PJ "
                    f"({v.binding}); headroom {v.headroom_frac:.1%}", va=val, vb=v.ceiling_PJ)

    # ---- (6) SCENARIO_ASYMMETRY 2023-2026 (compare the 4 txt files) --------
    for param in SYM_PARAMS:
        # union of all (tech,year) keys with year in 2023-2026 across scenarios
        keys = set()
        for scen in io.SCENARIOS:
            for (t, y) in txt_all_params[scen][param]:
                if y in io.SYMMETRY_YEARS:
                    keys.add((t, y))
        for (t, y) in sorted(keys):
            vals = {scen: txt_all_params[scen][param].get((t, y)) for scen in io.SCENARIOS}
            present = [v for v in vals.values() if v is not None]
            distinct = {round(float(v), 6) for v in present}
            if len(distinct) > 1 or len(present) != len(io.SCENARIOS):
                detail = "; ".join(f"{s}={'--' if vals[s] is None else round(float(vals[s]),4)}"
                                   for s in io.SCENARIOS)
                add("ALL", f"SCENARIO_ASYMMETRY:{param}", t, y, "WARN",
                    f"{param} differs across scenarios in {y}: {detail}")

    # ---- (7) PIPELINE_MISMATCH: txt vs combined CSV -----------------------
    combined = io.extract_combined([
        "TotalTechnologyAnnualActivityLowerLimit",
        "TotalAnnualMinCapacityInvestment",
    ])
    comb_lower = combined["TotalTechnologyAnnualActivityLowerLimit"]
    comb_forced = combined["TotalAnnualMinCapacityInvestment"]

    def comb_lookup(df):
        out = {}
        for row in df[["Scenario", "TECHNOLOGY", "YEAR", "VALUE"]].itertuples(index=False, name=None):
            out[(row[0], row[1], int(row[2]))] = float(row[3])
        return out

    cl = comb_lookup(comb_lower)
    cf = comb_lookup(comb_forced)

    pipeline_summary = {}
    for label, txt_map, comb_map in [
        ("TotalTechnologyAnnualActivityLowerLimit", txt_lower, cl),
        ("TotalAnnualMinCapacityInvestment", txt_forced, cf),
    ]:
        n_mismatch = 0
        for scen in io.SCENARIOS:
            # txt side (authoritative, non-zero)
            for (t, y), v in txt_map[scen].items():
                if v <= VALUE_TOL:
                    continue
                cv = comb_map.get((scen, t, y))
                if cv is None or cv <= VALUE_TOL:
                    add(scen, f"PIPELINE_MISMATCH:{label}", t, y, "ERROR",
                        f"txt has {v:.4g} but combined CSV has {'absent' if cv is None else cv}",
                        va=v, vb=cv)
                    n_mismatch += 1
                elif abs(cv - v) > max(VALUE_TOL, 1e-3 * abs(v)):
                    add(scen, f"PIPELINE_MISMATCH:{label}", t, y, "ERROR",
                        f"value differs txt {v:.6g} vs combined {cv:.6g}", va=v, vb=cv)
                    n_mismatch += 1
            # combined side that the txt lacks (non-zero in combined only)
            for (scen2, t, y), cv in comb_map.items():
                if scen2 != scen or cv <= VALUE_TOL:
                    continue
                if txt_map[scen].get((t, y), 0.0) <= VALUE_TOL:
                    add(scen, f"PIPELINE_MISMATCH:{label}", t, y, "WARN",
                        f"combined CSV has {cv:.4g} but txt has none (explicit-zero or extra row)",
                        va=None, vb=cv)
                    n_mismatch += 1
        pipeline_summary[label] = n_mismatch

    return flags, feas, txt_lower, txt_forced, pipeline_summary


def write_outputs(flags, feas, txt_lower, txt_forced, pipeline_summary):
    df = pd.DataFrame(flags, columns=["scenario", "check", "tech", "country", "fuel",
                                      "year", "severity", "value_a", "value_b", "detail"])
    df.to_csv(FLAGS_CSV, index=False)

    lines = []
    W = lines.append
    W("=" * 78)
    W("RELAC dispatch-floor input validation  (STEP 1, read-only)")
    W("Sources: limits+forced builds = preprocessed txt (authoritative);")
    W("         caps/life/residual = A2 otoole CSVs; cross-check = combined CSV.")
    W("=" * 78)

    # summary by check
    W("\nSUMMARY  (flag counts by check)")
    W("-" * 78)
    if len(df):
        base = df.copy()
        base["check_base"] = base["check"].str.split(":").str[0]
        by = base.groupby(["check_base", "severity"]).size().sort_values(ascending=False)
        for (chk, sev), n in by.items():
            W(f"  {chk:<28} {sev:<6} {n:>6}")
    else:
        W("  (no flags)")

    # per-scenario headline: forced-no-floor
    W("\nFORCED_NO_FLOOR by scenario (the core diagnosis)")
    W("-" * 78)
    for scen in io.SCENARIOS:
        sub = df[(df.scenario == scen) & (df.check == "FORCED_NO_FLOOR")]
        gw = float(sub["value_a"].fillna(0).sum())
        techs = sorted(sub["tech"].unique())
        W(f"  {scen}: {len(sub):>3} forced builds unfloored after {AFTER}, "
          f"{gw:6.2f} GW across {len(techs)} techs")

    # fuel-category breakdown -- isolates the fossil concern from normal
    # transmission/storage forced builds (which need no activity floor).
    W("\nFORCED_NO_FLOOR forced GW by fuel category  (fossil = the concern;")
    W("renewable/nuclear self-dispatch or run low by design; tx/storage need no floor)")
    W("-" * 78)
    cats = ["fossil", "renewable", "nuclear", "storage", "transmission", "other"]
    W(f"  {'scenario':<8} " + " ".join(f"{c:>12}" for c in cats))
    fnf = df[df.check == "FORCED_NO_FLOOR"].copy()
    fnf["cat"] = fnf["tech"].map(_category)
    for scen in io.SCENARIOS:
        row = fnf[fnf.scenario == scen].groupby("cat")["value_a"].sum()
        W(f"  {scen:<8} " + " ".join(f"{float(row.get(c, 0.0)):>12.2f}" for c in cats))

    # fossil-fleet anchor reconciliation (full flooring universe, not the
    # old 11-tech WORKING_SET; forced-only GW so the totals stay comparable
    # to earlier reports even though the floor basis itself is now fleet-wide)
    W("\nFOSSIL-FLEET forced totals (all forced years, GW)")
    W("-" * 78)
    for scen in io.SCENARIOS:
        floor_techs = io.nonren_floor_techs(scen)
        per = {}
        for t in floor_techs:
            s = sum(v for (tt, y), v in txt_forced[scen].items() if tt == t and v > VALUE_TOL)
            if s > VALUE_TOL:
                per[t] = s
        tot = sum(per.values())
        mex = per.get("PWRNGSMEXXX", 0.0)
        share = (mex / tot * 100) if tot else 0.0
        W(f"  {scen}: total {tot:6.3f} GW | MEX {mex:.3f} ({share:.0f}%) | "
          f"{len(per)} of {len(floor_techs)} floor-universe techs forced")

    # fossil-fleet table (per scenario)
    W("\nFOSSIL-FLEET floor-universe techs: floor coverage vs forced years")
    W("-" * 78)
    W(f"  {'scenario':<8} {'tech':<12} {'forced yrs':<22} {'floor yrs':<14} {'life':<5} status")
    for scen in io.SCENARIOS:
        for t in io.nonren_floor_techs(scen):
            fyrs = sorted(y for (tt, y), v in txt_forced[scen].items()
                          if tt == t and v > VALUE_TOL)
            lyrs = sorted(y for (tt, y), v in txt_lower[scen].items()
                          if tt == t and v > VALUE_TOL)
            if not fyrs and not lyrs:
                continue
            life = feas[scen].operational_life(t)
            floor_span = f"{min(lyrs)}-{max(lyrs)}" if lyrs else "none"
            forced_span = ",".join(str(y) for y in fyrs) if fyrs else "none"
            unfloored = [y for y in fyrs if y > AFTER and txt_lower[scen].get((t, y), 0) <= VALUE_TOL]
            status = "forced-no-floor" if unfloored else ("OK" if lyrs else "no floor")
            W(f"  {scen:<8} {t:<12} {forced_span:<22} {floor_span:<14} {life:<5.0f} {status}")

    # scenario symmetry
    W("\nSCENARIO SYMMETRY 2023-2026 (txt files compared directly)")
    W("-" * 78)
    sym = df[df["check"].str.startswith("SCENARIO_ASYMMETRY")]
    if len(sym) == 0:
        W("  OK: all txt parameters identical across BAU/INV/OPT/VGB for 2023-2026.")
    else:
        by = sym["check"].value_counts()
        for chk, n in by.items():
            W(f"  {chk.split(':',1)[1]:<45} {n:>5} asymmetric tech-years")
        W("  detail:")
        for _, r in sym.iterrows():
            W(f"    {r.tech} {r.year}: {r.detail.split(': ',1)[-1]}")

    # pipeline integrity
    W("\nPIPELINE INTEGRITY (txt vs combined CSV)")
    W("-" * 78)
    for label, n in pipeline_summary.items():
        W(f"  {label:<45} {n:>6} mismatched tech-years")

    # detail listing for ERRORs
    errs = df[df.severity == "ERROR"]
    W(f"\nERROR-level detail ({len(errs)} rows; first 60)")
    W("-" * 78)
    for _, r in errs.head(60).iterrows():
        W(f"  [{r.scenario}] {r.check} {r.tech} {r.year}: {r.detail}")

    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return df, "\n".join(lines)


def main():
    flags, feas, txt_lower, txt_forced, pipeline_summary = collect_flags()
    df, report = write_outputs(flags, feas, txt_lower, txt_forced, pipeline_summary)
    print(report)
    print(f"\nWrote {FLAGS_CSV.name} ({len(df)} flags) and {REPORT_TXT.name}")


if __name__ == "__main__":
    main()
