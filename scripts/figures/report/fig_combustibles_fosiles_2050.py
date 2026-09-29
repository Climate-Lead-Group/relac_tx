"""Plot fossil fuel consumption by scenario, accumulated per period [million BOE].

Static equivalent of dashboard chart_08a: sums TotalTechnologyAnnualActivity (PJ) of the
fossil extraction/import technologies MIN* (classify_min_fossil: COA/COG/GAS/OIL/PET/OTH;
excludes URN) year by year within each period, then converts to barrels of oil equivalent
(BOE, IEA convention: 1 bep = 5.7119 GJ) for the report. Grouped bars by scenario, one
sub-bar per period; color by scenario, constant across periods.

Inputs:
    TotalTechnologyAnnualActivity (combined CSV); periods default to
    report_style.ACCUMULATED_PERIODS (2026-2030/2031-2040/2041-2050); scenarios default to
    report_style.CORE_SCENARIOS (BAC+ISR).
Outputs:
    outputs/Figures/Report/fig_combustibles_fosiles_<p0>_<p1>.png (via report_style.save)
Usage:
    python scripts/figures/report/fig_combustibles_fosiles_2050.py
    [--periods 2026 2030 2031 2040 2041 2050] [--scenarios BAC ISR] [--out base]
"""

from __future__ import annotations

import argparse
import os
import sys

# Solo scripts/ entra en sys.path; todo se importa como paquete (spec 2026-09-16 §3).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from figures.common.dashboard_config import FIGURES_DIR, SCENARIO_ALIAS, classify_min_fossil
from figures.common import report_style as rs

# IEA: 1 tep = 41,868 GJ; 1 tep ≈ 7,33 bep (barriles equivalentes de petróleo).
GJ_PER_TEP = 41.868
BEP_PER_TEP = 7.33
GJ_PER_BEP = GJ_PER_TEP / BEP_PER_TEP  # ≈ 5,7119 GJ/bep

# PJ (10^15 J) / (GJ/bep) (10^9 J/bep) = 10^6 bep = 1 millón de bep -> el
# factor de escala es exactamente 1/GJ_PER_BEP, sin necesidad de otro término.
MBEP_PER_PJ = 1.0 / GJ_PER_BEP


def compute(periods: list[tuple[int, int]], scenarios: list[str]) -> dict[tuple[int, int], dict[str, float]]:
    """{period: {scenario: PJ}}, accumulated within each period."""
    df = rs.load(["TotalTechnologyAnnualActivity"], scenarios=scenarios)
    df = df.dropna(subset=["TotalTechnologyAnnualActivity"])
    df = df[df["Scenario"].isin(scenarios)]
    df = df[df["TECHNOLOGY"].map(classify_min_fossil).notna()]

    out: dict[tuple[int, int], dict[str, float]] = {}
    for p in periods:
        y0, y1 = p
        sub = df[(df["YEAR"] >= y0) & (df["YEAR"] <= y1)]
        g = sub.groupby("Scenario")["TotalTechnologyAnnualActivity"].sum()
        out[p] = {sc: float(g.get(sc, 0.0)) for sc in scenarios if sc in g.index}
    return out


def build_figure(data: dict, scenarios: list[str], periods: list[tuple[int, int]]):
    scenarios = [s for s in scenarios if any(s in data.get(p, {}) for p in periods)]
    group_centers, sub_positions = rs.grouped_bar_layout(len(scenarios), len(periods))
    colors = [rs.scenario_color(s) for s in scenarios]

    per_period_vals = [[data.get(p, {}).get(s, 0.0) * MBEP_PER_PJ for s in scenarios] for p in periods]
    all_vals = [v for vals in per_period_vals for v in vals]
    ymax = max(all_vals) * 1.16 if all_vals else 1.0

    fig, ax = rs.new_ax(figsize=(9.6, 5.6))
    for pi, vals in enumerate(per_period_vals):
        x = sub_positions[pi]
        ax.bar(x, vals, 0.22, color=colors, zorder=3)
        for xi, v in zip(x, vals):
            ax.text(xi, v + ymax * 0.015, rs.eu(v), ha="center", va="bottom",
                    fontsize=8, fontweight="bold", color=rs.COLOR_TOTAL)

    ax.set_ylim(0, ymax)
    rs.add_group_xticks(ax, [rs.period_label(p) for p in periods], sub_positions,
                         fontsize=7.5, rotation=45)
    rs.add_group_labels(ax, group_centers, rs.scenario_ticklabels(scenarios), y=-0.22)
    rs.apply_report_style(ax, "Consumo de combustibles fósiles acumulado por tramo [MBEP]",
                          european_y=True)
    fig.tight_layout()
    return fig


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--periods", nargs="+", type=int, default=None,
                     help="Años y0 y1 y0 y1 ... (pares); por defecto 2026 2030 2031 2040 2041 2050")
    ap.add_argument("--scenarios", nargs="+", default=rs.CORE_SCENARIOS)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    periods = rs.periods_from_flat_years(args.periods)

    data = compute(periods, args.scenarios)
    if not data:
        raise SystemExit(f"Sin datos para {periods} / {args.scenarios}")

    print("Consumo de combustibles fósiles acumulado por tramo [MBEP] (PJ entre paréntesis):")
    for p in periods:
        print(f" {rs.period_label(p)}:")
        for sc in args.scenarios:
            if sc in data.get(p, {}):
                pj = data[p][sc]
                print(f"  {SCENARIO_ALIAS.get(sc, sc):8s} ({sc}): {rs.eu(pj * MBEP_PER_PJ)} ({rs.eu(pj)} PJ)")

    fig = build_figure(data, args.scenarios, periods)
    os.makedirs(FIGURES_DIR, exist_ok=True)
    base = args.out or os.path.join(FIGURES_DIR, f"fig_combustibles_fosiles_{periods[0][0]}_{periods[-1][1]}")
    png = rs.save(fig, base)
    print(f"OK -> {png}")


if __name__ == "__main__":
    main()
