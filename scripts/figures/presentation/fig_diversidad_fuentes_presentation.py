"""
fig_diversidad_fuentes_presentation.py — PACK PRESENTACIÓN de
fig_diversidad_fuentes.py. Mismo dato y misma lógica de cómputo; solo
cambia la presentación visual para diapositivas: letra más grande,
escenarios (grupos) más juntos y sin holgura excesiva en los extremos del
eje X. Sin leyenda ni barras apiladas en esta figura (color = escenario,
identificado en el eje X) -> los cambios 3 y 4 del pack no aplican aquí.

Ver fig_diversidad_fuentes.py para la documentación completa del cómputo
(idéntica aquí, sin cambios).

Uso:
    PYTHONUTF8=1 python Figures_Presentation/fig_diversidad_fuentes_presentation.py
    PYTHONUTF8=1 python Figures_Presentation/fig_diversidad_fuentes_presentation.py --years 2030 2040 2050
"""

from __future__ import annotations

import argparse
import os
import sys

# Solo scripts/ entra en sys.path; todo se importa como paquete (spec 2026-09-16 §3).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from figures.common.dashboard_config import (
    FIGURES_PRESENTATION_DIR,
    SCENARIO_ALIAS,
    classify_source_family,
)
from figures.common import report_style as rs


def compute(years: list[int], scenarios: list[str]) -> dict[int, dict[str, float]]:
    """{year: {scenario: nº efectivo de fuentes (1/HHI)}}."""
    df = rs.load(["ProductionByTechnology"], scenarios=scenarios)
    df = df.dropna(subset=["ProductionByTechnology"])
    df = df[df["ProductionByTechnology"] != 0]
    df = df[(df["YEAR"].isin(years)) & (df["Scenario"].isin(scenarios))]

    df["Fuente"] = df["TECHNOLOGY"].apply(classify_source_family)
    df = df[df["Fuente"].notna()]

    fam = (
        df.groupby(["Scenario", "YEAR", "Fuente"])["ProductionByTechnology"]
        .sum()
        .reset_index()
    )
    fam = fam[fam["ProductionByTechnology"] > 0]

    out: dict[int, dict[str, float]] = {}
    for (sc, yr), g in fam.groupby(["Scenario", "YEAR"]):
        total = g["ProductionByTechnology"].sum()
        if total <= 0:
            continue
        shares = g["ProductionByTechnology"].values / total
        hhi = float((shares ** 2).sum())
        if hhi > 0:
            out.setdefault(int(yr), {})[sc] = 1.0 / hhi
    return out


def build_figure(data: dict, scenarios: list[str], years: list[int]):
    scenarios = [s for s in scenarios if any(s in data.get(y, {}) for y in years)]
    group_centers, sub_positions = rs.grouped_bar_layout(
        len(scenarios), len(years), group_step=0.80)
    colors = [rs.scenario_color(s) for s in scenarios]

    per_year_vals = [[data.get(y, {}).get(s, 0.0) for s in scenarios] for y in years]
    all_vals = [v for vals in per_year_vals for v in vals]
    ymax = max(all_vals) * 1.16 if all_vals else 1.0

    fig, ax = rs.new_ax(figsize=(9.6, 4.8))
    for yi, vals in enumerate(per_year_vals):
        x = sub_positions[yi]
        ax.bar(x, vals, 0.22, color=colors, zorder=3)
        for xi, v in zip(x, vals):
            ax.text(xi, v + ymax * 0.015, rs.eu(v, 1), ha="center", va="bottom",
                    fontsize=10, fontweight="bold", color=rs.COLOR_TOTAL)

    ax.set_ylim(0, ymax)
    rs.set_grouped_xlim(ax, group_centers, len(years))
    rs.add_year_xticks(ax, years, sub_positions, fontsize=9.5)
    rs.add_group_labels(ax, group_centers, rs.scenario_ticklabels(scenarios), fontsize=11)
    rs.apply_report_style(ax, "Nº efectivo de fuentes (1/HHI)", fontsize=13)
    fig.tight_layout()
    return fig


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--years", nargs="+", type=int, default=rs.MULTI_YEARS)
    ap.add_argument("--scenarios", nargs="+", default=rs.PRESENTATION_SCENARIOS)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    data = compute(args.years, args.scenarios)
    if not data:
        raise SystemExit(f"Sin datos para {args.years} / {args.scenarios}")

    print("Nº efectivo de fuentes (1/HHI):")
    for year in args.years:
        print(f" {year}:")
        for sc in args.scenarios:
            if sc in data.get(year, {}):
                print(f"  {SCENARIO_ALIAS.get(sc, sc):8s} ({sc}): {rs.eu(data[year][sc], 2)}")

    fig = build_figure(data, args.scenarios, args.years)
    os.makedirs(FIGURES_PRESENTATION_DIR, exist_ok=True)
    base = args.out or os.path.join(FIGURES_PRESENTATION_DIR, "fig_diversidad_fuentes_presentation")
    png = rs.save(fig, base)
    print(f"OK -> {png}")


if __name__ == "__main__":
    main()
