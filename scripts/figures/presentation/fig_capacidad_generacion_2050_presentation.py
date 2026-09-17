"""
fig_capacidad_generacion_2050_presentation.py — PACK PRESENTACIÓN de
fig_capacidad_generacion_2050.py. Mismo dato y misma lógica de cómputo;
solo cambia la presentación visual para diapositivas: letra más grande,
escenarios (grupos) más juntos y sin holgura excesiva en los extremos del
eje X. La leyenda (2 entradas: Renovable / No Renovable) y la etiqueta de
% renovable dentro del tramo ya venían en una sola fila / dentro de barra
en el original — se mantienen, solo con letra más grande.

Ver fig_capacidad_generacion_2050.py para la documentación completa del
cómputo (idéntica aquí, sin cambios).

Uso:
    PYTHONUTF8=1 python Figures_Presentation/fig_capacidad_generacion_2050_presentation.py
    PYTHONUTF8=1 python Figures_Presentation/fig_capacidad_generacion_2050_presentation.py --years 2030 2040 2050 --scenarios BAC ISR
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
    classify_tech_generation,
)
from figures.common import report_style as rs


def compute(years: list[int], scenarios: list[str]) -> dict[int, dict[str, dict]]:
    """{year: {scenario: {'ren','no_ren','total','pct'}}} (GW)."""
    df = rs.load(["TotalCapacityAnnual"], scenarios=scenarios)
    df = df.dropna(subset=["TotalCapacityAnnual"])
    df = df[df["TotalCapacityAnnual"] != 0]
    df = df[(df["YEAR"].isin(years)) & (df["Scenario"].isin(scenarios))]

    df["TechGroup"] = df["TECHNOLOGY"].apply(classify_tech_generation)
    df = df[df["TechGroup"].isin(["Renovable", "No Renovable"])]
    df = df.drop_duplicates(subset=["Scenario", "YEAR", "TECHNOLOGY"])

    grouped = (
        df.groupby(["Scenario", "YEAR", "TechGroup"])["TotalCapacityAnnual"]
        .sum()
        .unstack(fill_value=0.0)
    )

    out: dict[int, dict[str, dict]] = {}
    for year in years:
        for sc in scenarios:
            key = (sc, year)
            if key not in grouped.index:
                continue
            ren = float(grouped.at[key, "Renovable"]) if "Renovable" in grouped.columns else 0.0
            no_ren = float(grouped.at[key, "No Renovable"]) if "No Renovable" in grouped.columns else 0.0
            total = ren + no_ren
            pct = round(ren / total * 100) if total else 0
            out.setdefault(year, {})[sc] = {"ren": ren, "no_ren": no_ren, "total": total, "pct": pct}
    return out


def build_figure(data: dict, scenarios: list[str], years: list[int]):
    scenarios = [s for s in scenarios if any(s in data.get(y, {}) for y in years)]
    group_centers, sub_positions = rs.grouped_bar_layout(
        len(scenarios), len(years), group_step=0.80)

    per_year = []
    all_totals = []
    for year in years:
        ren = [data.get(year, {}).get(s, {}).get("ren", 0.0) for s in scenarios]
        no_ren = [data.get(year, {}).get(s, {}).get("no_ren", 0.0) for s in scenarios]
        totals = [r + n for r, n in zip(ren, no_ren)]
        pcts = [data.get(year, {}).get(s, {}).get("pct", 0) for s in scenarios]
        per_year.append((ren, no_ren, totals, pcts))
        all_totals += totals
    ymax = max(all_totals) * 1.18 if all_totals else 1.0

    fig, ax = rs.new_ax(figsize=(9.6, 5.0))
    for yi, (ren, no_ren, totals, pcts) in enumerate(per_year):
        x = sub_positions[yi]
        ax.bar(x, ren, 0.22, color=rs.COLOR_RENOVABLE, zorder=3,
               label="Renovable" if yi == 0 else None)
        ax.bar(x, no_ren, 0.22, bottom=ren, color=rs.COLOR_NO_RENOVABLE, zorder=3,
               label="No Renovable" if yi == 0 else None)
        for xi, tot, pct, r in zip(x, totals, pcts, ren):
            ax.text(xi, tot + ymax * 0.015, rs.eu(tot), ha="center", va="bottom",
                    fontsize=10, fontweight="bold", color=rs.COLOR_TOTAL)
            if r > ymax * 0.05:
                ax.text(xi, r / 2, f"{pct}%", ha="center", va="center",
                        fontsize=9, fontweight="bold", color=rs.COLOR_LABEL_ON_BAR)

    ax.set_ylim(0, ymax)
    rs.set_grouped_xlim(ax, group_centers, len(years))
    rs.add_year_xticks(ax, years, sub_positions, fontsize=9.5)
    rs.add_group_labels(ax, group_centers, rs.scenario_ticklabels(scenarios), fontsize=11)
    rs.apply_report_style(ax, "Capacidad instalada de generación [GW]",
                          european_y=True, fontsize=13)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.1), ncol=2,
              frameon=False, fontsize=10.5)
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

    print(f"Capacidad instalada de generación {rs.years_label(args.years)} [GW]:")
    for year in args.years:
        print(f" {year}:")
        for sc in args.scenarios:
            if sc in data.get(year, {}):
                d = data[year][sc]
                print(f"  {SCENARIO_ALIAS.get(sc, sc):8s} ({sc}): total={rs.eu(d['total'])}  "
                      f"ren={rs.eu(d['ren'])} ({d['pct']}%)  no_ren={rs.eu(d['no_ren'])}")

    fig = build_figure(data, args.scenarios, args.years)
    os.makedirs(FIGURES_PRESENTATION_DIR, exist_ok=True)
    base = args.out or os.path.join(FIGURES_PRESENTATION_DIR, "fig_capacidad_generacion_2050_presentation")
    png = rs.save(fig, base)
    print(f"OK -> {png}")


if __name__ == "__main__":
    main()
