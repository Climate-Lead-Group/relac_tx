#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_summary.py
Step 6: one row per country per tier, plus a compact terminal table.

Run: python build_summary.py
Reads: candidate_floors.csv
Writes: candidate_floors_summary.csv
"""
import csv
from collections import defaultdict

SRC = "candidate_floors.csv"
OUT_CSV = "candidate_floors_summary.csv"

OUT_COLUMNS = ["tier", "country", "n_techs", "n_rows", "total_forced_GW", "total_floor_PJ_2050",
               "year_min", "year_max", "cf_stated_pct", "cf_derived_pct", "cf_proxy_pct",
               "filtered_available", "scenario_source"]


def is_proxy(basis):
    return basis.startswith("proxy") or basis.startswith("mixed:")


def main():
    with open(SRC, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    countries_with_filtered = {r["country"] for r in rows if r["tier"] == "FILTERED"}

    # one representative Scenario per tier avoids double counting (BAU==INV, OPT==VGB)
    groups = defaultdict(list)
    for r in rows:
        rep_scenario = "BAU" if r["tier"] == "FILTERED" else "OPT"
        if r["Scenario"] != rep_scenario:
            continue
        groups[(r["tier"], r["country"])].append(r)

    summary_rows = []
    for (tier, country), grp in sorted(groups.items()):
        techs = {r["TECHNOLOGY"] for r in grp}
        years = [int(r["YEAR"]) for r in grp]
        cf_basis_counts = defaultdict(int)
        # count basis at the (TECHNOLOGY) level, not per year-row, to reflect the
        # underlying source mix rather than how many years it happens to span
        seen_tech_basis = {}
        for r in grp:
            seen_tech_basis[r["TECHNOLOGY"]] = r["cf_basis"]
        n_stated = sum(1 for b in seen_tech_basis.values() if b == "stated" or b.startswith("mixed:stated"))
        n_derived = sum(1 for b in seen_tech_basis.values() if b == "derived")
        n_proxy = sum(1 for b in seen_tech_basis.values() if is_proxy(b))
        n_tech_total = len(seen_tech_basis) or 1

        total_floor_2050 = sum(float(r["floor_PJ"]) for r in grp if int(r["YEAR"]) == 2050)
        total_gw_2050 = sum(float(r["forced_GW"]) for r in grp if int(r["YEAR"]) == 2050)
        scenario_sources = sorted({r["scenario_source"] for r in grp})
        scenario_source_report = scenario_sources[0] if len(scenario_sources) == 1 else f"{len(scenario_sources)} scenario sources"

        summary_rows.append({
            "tier": tier, "country": country, "n_techs": len(techs), "n_rows": len(grp),
            "total_forced_GW": round(total_gw_2050, 3), "total_floor_PJ_2050": round(total_floor_2050, 2),
            "year_min": min(years), "year_max": max(years),
            "cf_stated_pct": round(100 * n_stated / n_tech_total, 1),
            "cf_derived_pct": round(100 * n_derived / n_tech_total, 1),
            "cf_proxy_pct": round(100 * n_proxy / n_tech_total, 1),
            "filtered_available": country in countries_with_filtered,
            "scenario_source": scenario_source_report,
        })

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUT_COLUMNS)
        w.writeheader()
        w.writerows(summary_rows)

    print(f"Wrote {OUT_CSV}: {len(summary_rows)} rows\n")

    print(f"{'Country':8} {'FILTERED GW':>12} {'FULL GW':>10}  Top techs (FULL, by GW)")
    print("-" * 80)
    full_by_country = {r["country"]: r for r in summary_rows if r["tier"] == "FULL"}
    filt_by_country = {r["country"]: r for r in summary_rows if r["tier"] == "FILTERED"}
    tech_gw = defaultdict(lambda: defaultdict(float))
    for r in rows:
        if r["tier"] == "FULL" and r["Scenario"] == "OPT" and int(r["YEAR"]) == 2050:
            tech_gw[r["country"]][r["fuel"]] += float(r["forced_GW"])

    for country in sorted(full_by_country):
        full_gw = full_by_country[country]["total_forced_GW"]
        filt_gw = filt_by_country[country]["total_forced_GW"] if country in filt_by_country else 0.0
        top3 = sorted(tech_gw[country].items(), key=lambda kv: -kv[1])[:3]
        top3_str = ", ".join(f"{t}:{g:.1f}" for t, g in top3)
        print(f"{country:8} {filt_gw:>12.2f} {full_gw:>10.2f}  {top3_str}")

    print(f"\n{len(countries_with_filtered)} of 17 countries have a FILTERED tier: {sorted(countries_with_filtered)}")
    full_only = sorted(set(full_by_country) - countries_with_filtered)
    print(f"{len(full_only)} are FULL-only: {full_only}")


if __name__ == "__main__":
    main()
