"""Experimental presentation pack: fossil fuel use plus unserved energy (ENS).

Presentation variant of report/fig_combustibles_fosiles_ens_tmp.py: adds ENS (backstop
production via ProductionByTechnology, in PJ; no VOLL involved) directly to the fossil
figure, one bar per scenario/period. Visual styling (larger fonts, tighter groups) is
inherited from fig_combustibles_fosiles_2050_presentation.py.

Inputs:
    TotalTechnologyAnnualActivity, ProductionByTechnology (combined CSV); periods default
    to report_style.ACCUMULATED_PERIODS; scenarios default to
    report_style.PRESENTATION_SCENARIOS (= CORE_SCENARIOS, BAC+ISR).
Outputs:
    outputs/Figures/Presentation/fig_combustibles_fosiles_ens_<p0>_<p1>_presentation_tmp.png
    (via report_style.save)
Usage:
    python scripts/figures/presentation/fig_combustibles_fosiles_ens_presentation_tmp.py
    [--periods 2026 2030 2031 2040 2041 2050] [--scenarios BAC ISR] [--out base]
Notes:
    - Experimental variant, listed as false in run_figures.yaml (skipped unless --only).
"""

from __future__ import annotations

import argparse
import os
import sys

# Solo scripts/ entra en sys.path; todo se importa como paquete (spec 2026-09-16 §3).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from figures.common.dashboard_config import FIGURES_PRESENTATION_DIR, SCENARIO_ALIAS, classify_min_fossil
from figures.common import report_style as rs

# IEA: 1 tep = 41,868 GJ; 1 tep ≈ 7,33 bep (barriles equivalentes de petróleo).
GJ_PER_TEP = 41.868
BEP_PER_TEP = 7.33
GJ_PER_BEP = GJ_PER_TEP / BEP_PER_TEP  # ≈ 5,7119 GJ/bep

MBEP_PER_PJ = 1.0 / GJ_PER_BEP


def compute(periods: list[tuple[int, int]], scenarios: list[str]) -> dict[tuple[int, int], dict[str, dict]]:
    """{period: {scenario: {'total','ens'}}} in PJ, accumulated within each
    period.
    """
    df = rs.load(["TotalTechnologyAnnualActivity"], scenarios=scenarios)
    df = df.dropna(subset=["TotalTechnologyAnnualActivity"])
    df = df[df["Scenario"].isin(scenarios)]
    df = df[df["TECHNOLOGY"].map(classify_min_fossil).notna()]

    # ENS: producción del backstop en PJ (suma de timeslices/fuels, como
    # chart_15 del dashboard).
    prod = rs.load(["ProductionByTechnology"], scenarios=scenarios)
    prod = prod[prod["Scenario"].isin(scenarios)]
    bck = prod[prod["TECHNOLOGY"].astype(str).str.contains("BCK", na=False)]

    out: dict[tuple[int, int], dict[str, dict]] = {}
    for p in periods:
        y0, y1 = p
        sub = df[(df["YEAR"] >= y0) & (df["YEAR"] <= y1)]
        g = sub.groupby("Scenario")["TotalTechnologyAnnualActivity"].sum()
        e = bck[(bck["YEAR"] >= y0) & (bck["YEAR"] <= y1)] \
            .groupby("Scenario")["ProductionByTechnology"].sum()
        out[p] = {}
        for sc in scenarios:
            if sc not in g.index and sc not in e.index:
                continue
            ens = float(e.get(sc, 0.0))
            out[p][sc] = {"total": float(g.get(sc, 0.0)) + ens, "ens": ens}
    return out


def build_figure(data: dict, scenarios: list[str], periods: list[tuple[int, int]]):
    scenarios = [s for s in scenarios if any(s in data.get(p, {}) for p in periods)]
    group_centers, sub_positions = rs.grouped_bar_layout(
        len(scenarios), len(periods), group_step=0.80)
    colors = [rs.scenario_color(s) for s in scenarios]

    per_period_vals = [[data.get(p, {}).get(s, {}).get("total", 0.0) * MBEP_PER_PJ for s in scenarios]
                       for p in periods]
    all_vals = [v for vals in per_period_vals for v in vals]
    ymax = max(all_vals) * 1.16 if all_vals else 1.0

    fig, ax = rs.new_ax(figsize=(9.6, 7.4))
    for pi, vals in enumerate(per_period_vals):
        x = sub_positions[pi]
        ax.bar(x, vals, 0.22, color=colors, zorder=3)
        for xi, v in zip(x, vals):
            ax.text(xi, v + ymax * 0.015, rs.eu(v), ha="center", va="bottom",
                    fontsize=10, fontweight="bold", color=rs.COLOR_TOTAL)

    ax.set_ylim(0, ymax)
    rs.set_grouped_xlim(ax, group_centers, len(periods))
    rs.add_group_xticks(ax, [rs.period_label(p) for p in periods], sub_positions,
                         fontsize=9.5, rotation=45)
    rs.add_group_labels(ax, group_centers, rs.scenario_ticklabels(scenarios), y=-0.22, fontsize=11)
    rs.apply_report_style(ax, "Combustibles fósiles + ENS acumulado por tramo [MBEP]",
                          european_y=True, fontsize=13)
    fig.tight_layout()
    return fig


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--periods", nargs="+", type=int, default=None,
                     help="Años y0 y1 y0 y1 ... (pares); por defecto 2026 2030 2031 2040 2041 2050")
    ap.add_argument("--scenarios", nargs="+", default=rs.PRESENTATION_SCENARIOS)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    periods = rs.periods_from_flat_years(args.periods)

    data = compute(periods, args.scenarios)
    if not data:
        raise SystemExit(f"Sin datos para {periods} / {args.scenarios}")

    print("Consumo de combustibles fósiles + ENS acumulado por tramo [MBEP] (PJ entre paréntesis):")
    for p in periods:
        print(f" {rs.period_label(p)}:")
        for sc in args.scenarios:
            if sc in data.get(p, {}):
                d = data[p][sc]
                print(f"  {SCENARIO_ALIAS.get(sc, sc):8s} ({sc}): {rs.eu(d['total'] * MBEP_PER_PJ)} "
                      f"({rs.eu(d['total'])} PJ, de los cuales ENS={rs.eu(d['ens'])} PJ)")

    fig = build_figure(data, args.scenarios, periods)
    os.makedirs(FIGURES_PRESENTATION_DIR, exist_ok=True)
    base = args.out or os.path.join(
        FIGURES_PRESENTATION_DIR,
        f"fig_combustibles_fosiles_ens_{periods[0][0]}_{periods[-1][1]}_presentation_tmp")
    png = rs.save(fig, base)
    print(f"OK -> {png}")


if __name__ == "__main__":
    main()
