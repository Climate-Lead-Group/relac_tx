"""Presentation variant of report/fig_capacidad_transmision_2050.py (transmission capacity).

Same data and computation as the report figure (stacked by line group); slide styling
changes: larger fonts, scenario groups spaced closer together, less X-axis margin. Legend
reflowed to 2 rows instead of 1 (5 series in one row grew the figure too wide); the legend
order (not the stacking order, which is unchanged) is rearranged so "Líneas Existentes"
(shortest label) and "Líneas Repotenciadas No Planificadas" (longest) share the 2-entry row,
minimizing total legend width. Each category's value is now annotated inside its bar
segment (the report figure only showed the bar total).

Inputs:
    TotalCapacityAnnual, AccumulatedNewCapacity, AccumulatedTotalAnnualMinCapacityInvestment
    (combined CSV); scenarios default to report_style.PRESENTATION_SCENARIOS (= BAC+ISR).
Outputs:
    outputs/Figures/Presentation/fig_capacidad_transmision_2050_presentation.png (via
    report_style.save)
Usage:
    python scripts/figures/presentation/fig_capacidad_transmision_2050_presentation.py
    [--years 2030 2040 2050] [--scenarios BAC ISR] [--out base]
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
    classify_line_group,
)
from figures.common import report_style as rs

# Factores fijos de ajuste (ver docstring del script original).
FACTOR_REPOTENCIADAS = 2.25
FACTOR_EXISTENTES = 1.25

# Orden de apilado (de abajo hacia arriba) y color de cada categoría.
CATEGORIES = [
    ("Líneas Existentes", rs.COLOR_LINEAS_EXISTENTES),
    ("Líneas Nuevas Planificadas", rs.COLOR_LINEAS_NUEVAS_PLAN),
    ("Líneas Repotenciadas Planificadas", rs.COLOR_LINEAS_REPO_PLAN),
    ("Líneas Nuevas No Planificadas", rs.COLOR_LINEAS_NUEVAS_NOPLAN),
    ("Líneas Repotenciadas No Planificadas", rs.COLOR_LINEAS_REPO_NOPLAN),
]

# Orden de la LEYENDA (no el de apilado, que es CATEGORIES arriba). Con
# ncol=3 y 5 entradas, matplotlib llena la leyenda por columnas: fila
# superior = índices 0,2,4 (3 entradas); fila inferior = índices 1,3 (2
# entradas). Este orden deja "Líneas Existentes" (la más corta) y "Líneas
# Repotenciadas No Planificadas" (la más larga) juntas en la fila de 2.
LEGEND_ORDER = [
    "Líneas Nuevas Planificadas",
    "Líneas Existentes",
    "Líneas Repotenciadas Planificadas",
    "Líneas Repotenciadas No Planificadas",
    "Líneas Nuevas No Planificadas",
]

_COLS = [
    "AccumulatedNewCapacity",
    "TotalCapacityAnnual",
    "AccumulatedTotalAnnualMinCapacityInvestment",
]


def compute(years: list[int], scenarios: list[str]) -> dict[int, dict[str, dict]]:
    """{year: {scenario: {categoria: GW, ..., 'total': GW}}}."""
    df = rs.load(_COLS, scenarios=scenarios)
    df["LineGroup"] = df["TECHNOLOGY"].apply(classify_line_group)
    df = df[df["LineGroup"].notna()]
    df = df[(df["YEAR"].isin(years)) & (df["Scenario"].isin(scenarios))]

    per_tech = (
        df.groupby(["Scenario", "YEAR", "TECHNOLOGY", "LineGroup"])[_COLS].max().reset_index()
    )
    g = per_tech.groupby(["Scenario", "YEAR", "LineGroup"])[_COLS].sum()
    present = set(zip(df["Scenario"], df["YEAR"]))

    out: dict[int, dict[str, dict]] = {}
    for year in years:
        for sc in scenarios:
            if (sc, year) not in present:
                continue

            def val(group: str, col: str) -> float:
                k = (sc, year, group)
                return float(g.at[k, col]) if k in g.index else 0.0

            acc_new_plan = val("PLAN", "AccumulatedNewCapacity")
            tca_plan = val("PLAN", "TotalCapacityAnnual")
            tca_nli = val("NLI", "TotalCapacityAnnual")
            tca_rpo = val("RPO", "TotalCapacityAnnual")
            acc_min_rpo = val("RPO", "AccumulatedTotalAnnualMinCapacityInvestment")

            repot_plan = acc_min_rpo * FACTOR_REPOTENCIADAS
            repot_noplan = (tca_rpo - acc_min_rpo) * FACTOR_REPOTENCIADAS

            existentes = (tca_plan - acc_new_plan) - tca_rpo * FACTOR_EXISTENTES

            cats = {
                "Líneas Existentes": existentes,
                "Líneas Nuevas Planificadas": acc_new_plan,
                "Líneas Repotenciadas Planificadas": repot_plan,
                "Líneas Nuevas No Planificadas": tca_nli,
                "Líneas Repotenciadas No Planificadas": repot_noplan,
            }
            cats["total"] = sum(cats.values())
            out.setdefault(year, {})[sc] = cats
    return out


def build_figure(data: dict, scenarios: list[str], years: list[int]):
    """Draw the grouped bar chart and return the Figure.

    Plots installed transmission capacity (stacked by line group).

    Args:
        data: nested dict from compute(), keyed by year then scenario.
        scenarios: scenario codes to draw, in display order.
        years: years to show as sub-bars within each scenario group.

    Returns:
        The matplotlib Figure; the caller saves it via report_style.save.
    """
    scenarios = [s for s in scenarios if any(s in data.get(y, {}) for y in years)]
    group_centers, sub_positions = rs.grouped_bar_layout(
        len(scenarios), len(years), group_step=0.80)

    cats = [(n, c) for n, c in CATEGORIES
            if any(abs(data[y][s][n]) > 1e-9 for y in years for s in scenarios if s in data.get(y, {}))]

    all_totals = [data[y][s]["total"] for y in years for s in scenarios if s in data.get(y, {})]
    ymax = max(all_totals) * 1.18 if all_totals else 1.0
    min_label_h = ymax * 0.035  # tramos más finos que esto no llevan etiqueta interna

    fig, ax = rs.new_ax(figsize=(9.2, 5.9))
    bar_handles: dict[str, object] = {}
    for yi, year in enumerate(years):
        x = sub_positions[yi]
        bottoms = [0.0] * len(scenarios)
        for name, color in cats:
            vals = [data.get(year, {}).get(s, {}).get(name, 0.0) for s in scenarios]
            bars = ax.bar(x, vals, 0.22, bottom=bottoms, color=color, zorder=3)
            if yi == 0:
                bar_handles[name] = bars
            for xi, b, v in zip(x, bottoms, vals):
                if v >= min_label_h:
                    ax.text(xi, b + v / 2, rs.eu(v), ha="center", va="center",
                            fontsize=8.5, color=rs.COLOR_LABEL_ON_BAR, zorder=4)
            bottoms = [b + v for b, v in zip(bottoms, vals)]

        totals = [data.get(year, {}).get(s, {}).get("total", 0.0) for s in scenarios]
        for xi, tot in zip(x, totals):
            ax.text(xi, tot + ymax * 0.015, rs.eu(tot), ha="center", va="bottom",
                    fontsize=10, fontweight="bold", color=rs.COLOR_TOTAL)

    ax.set_ylim(0, ymax)
    rs.set_grouped_xlim(ax, group_centers, len(years))
    rs.add_year_xticks(ax, years, sub_positions, fontsize=9.5)
    rs.add_group_labels(ax, group_centers, rs.scenario_ticklabels(scenarios), fontsize=11)
    rs.apply_report_style(ax, "Capacidad instalada de transmisión [GW]",
                          european_y=True, fontsize=13)
    legend_names = [n for n in LEGEND_ORDER if n in bar_handles]
    legend_ncol = -(-len(legend_names) // 2)  # ceil(n/2) -> siempre 2 filas
    ax.legend([bar_handles[n] for n in legend_names], legend_names,
              loc="upper center", bbox_to_anchor=(0.5, 1.28), ncol=legend_ncol,
              frameon=False, fontsize=10)
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

    print(f"Capacidad instalada de transmisión {rs.years_label(args.years)} [GW]:")
    for year in args.years:
        print(f" {year}:")
        for sc in args.scenarios:
            if sc in data.get(year, {}):
                d = data[year][sc]
                detail = "  ".join(f"{n}={rs.eu(d[n])}" for n, _ in CATEGORIES
                                   if abs(d[n]) > 1e-9)
                print(f"  {SCENARIO_ALIAS.get(sc, sc):8s} ({sc}): total={rs.eu(d['total'])}  |  {detail}")

    fig = build_figure(data, args.scenarios, args.years)
    os.makedirs(FIGURES_PRESENTATION_DIR, exist_ok=True)
    base = args.out or os.path.join(FIGURES_PRESENTATION_DIR, "fig_capacidad_transmision_2050_presentation")
    png = rs.save(fig, base)
    print(f"OK -> {png}")


if __name__ == "__main__":
    main()
