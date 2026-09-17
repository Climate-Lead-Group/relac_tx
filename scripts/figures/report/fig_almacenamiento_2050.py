"""
fig_almacenamiento_2050.py — Capacidad instalada de almacenamiento por
escenario en 2030/2040/2050 [GW] (figura de reporte, Entregable 2).

Equivalente estático del chart_03 del dashboard ("Capacidad Instalada de
Almacenamiento [GW]") agregando los tipos (SDS corta duración + LDS larga
duración; BDS si algún día aparece) en un solo total por escenario. Parámetro
TotalCapacityAnnual: una fila por tech-año repetida por timeslice -> dedup por
Scenario/YEAR/TECHNOLOGY antes de sumar. Barras agrupadas por escenario, con
una sub-barra por año dentro de cada grupo (report_style.grouped_bar_layout);
color por escenario (paleta del reporte: rs.SCENARIO_COLORS), constante entre
años. Más red -> menos almacenamiento requerido (y viceversa en los
escenarios de Tx restringida).

Uso:
    python scripts/figures/report/fig_almacenamiento_2050.py
    python scripts/figures/report/fig_almacenamiento_2050.py --years 2030 2040 2050 --scenarios BAC ISR
"""

from __future__ import annotations

import argparse
import os
import sys

# Solo scripts/ entra en sys.path; todo se importa como paquete (spec 2026-09-16 §3).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from figures.common.dashboard_config import FIGURES_DIR, SCENARIO_ALIAS
from figures.common import report_style as rs

_STORAGE_PREFIXES = ("PWRSDS", "PWRLDS", "PWRBDS")


def compute(years: list[int], scenarios: list[str]) -> dict[int, dict[str, float]]:
    """{year: {scenario: GW}}."""
    df = rs.load(["TotalCapacityAnnual"], scenarios=scenarios)
    df = df.dropna(subset=["TotalCapacityAnnual"])
    df = df[df["TotalCapacityAnnual"] != 0]
    df = df[(df["YEAR"].isin(years)) & (df["Scenario"].isin(scenarios))]
    df = df[df["TECHNOLOGY"].str.startswith(_STORAGE_PREFIXES)]
    df = df.drop_duplicates(subset=["Scenario", "YEAR", "TECHNOLOGY"])

    g = df.groupby(["Scenario", "YEAR"])["TotalCapacityAnnual"].sum()
    out: dict[int, dict[str, float]] = {}
    for year in years:
        for sc in scenarios:
            key = (sc, year)
            if key in g.index:
                out.setdefault(year, {})[sc] = float(g.at[key])
    return out


def build_figure(data: dict, scenarios: list[str], years: list[int]):
    scenarios = [s for s in scenarios if any(s in data.get(y, {}) for y in years)]
    group_centers, sub_positions = rs.grouped_bar_layout(len(scenarios), len(years))
    colors = [rs.scenario_color(s) for s in scenarios]

    per_year_vals = [[data.get(year, {}).get(s, 0.0) for s in scenarios] for year in years]
    all_vals = [v for vals in per_year_vals for v in vals]
    ymax = max(all_vals) * 1.16 if all_vals else 1.0

    fig, ax = rs.new_ax(figsize=(9.6, 4.8))
    for yi, vals in enumerate(per_year_vals):
        x = sub_positions[yi]
        ax.bar(x, vals, 0.22, color=colors, zorder=3)
        for xi, v in zip(x, vals):
            ax.text(xi, v + ymax * 0.015, rs.eu(v, 1), ha="center", va="bottom",
                    fontsize=8, fontweight="bold", color=rs.COLOR_TOTAL)

    ax.set_ylim(0, ymax)
    rs.add_year_xticks(ax, years, sub_positions)
    rs.add_group_labels(ax, group_centers, rs.scenario_ticklabels(scenarios))
    rs.apply_report_style(ax, "Capacidad instalada de almacenamiento [GW]")
    fig.tight_layout()
    return fig


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--years", nargs="+", type=int, default=rs.MULTI_YEARS)
    ap.add_argument("--scenarios", nargs="+", default=rs.CORE_SCENARIOS)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    data = compute(args.years, args.scenarios)
    if not data:
        raise SystemExit(f"Sin datos para {args.years} / {args.scenarios}")

    print(f"Capacidad instalada de almacenamiento {rs.years_label(args.years)} [GW]:")
    for year in args.years:
        print(f" {year}:")
        for sc in args.scenarios:
            if sc in data.get(year, {}):
                print(f"  {SCENARIO_ALIAS.get(sc, sc):8s} ({sc}): {rs.eu(data[year][sc], 1)}")

    fig = build_figure(data, args.scenarios, args.years)
    os.makedirs(FIGURES_DIR, exist_ok=True)
    base = args.out or os.path.join(FIGURES_DIR, "fig_almacenamiento_2050")
    png = rs.save(fig, base)
    print(f"OK -> {png}")


if __name__ == "__main__":
    main()
