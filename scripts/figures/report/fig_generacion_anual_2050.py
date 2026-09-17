"""
fig_generacion_anual_2050.py — Figura de reporte (Entregable 2, "Generación
anual por escenario en 2030/2040/2050 (TWh) y participación renovable").

Reproduce la Figura 55 del Entregable 2 como figura ESTÁTICA y trazable, leyendo
del mismo oráculo que el dashboard (RELAC_TX_Combined_Inputs_Outputs.csv via
dashboard_config) — NO es un recorte manual del dashboard.

Equivalente estático, en estilo de reporte, del "chart02 – Generación Anual [TWh]"
de build_dashboard_nonsupplied.py, filtrado a un set de años y a los 4
escenarios core. Barras agrupadas por escenario, con una sub-barra apilada
(Renovable / No Renovable) por año dentro de cada grupo
(report_style.grouped_bar_layout).

Fuente de datos : ProductionByTechnology (PJ) -> /3.6 -> TWh
Clasificación   : classify_tech_generation (Renovable / No Renovable), idéntica al dashboard
Escenarios      : BAC->OPT, ISR->ETT (SCENARIO_ALIAS; solo estos dos desde 2026-09-16)

Uso:
    python scripts/figures/report/fig_generacion_anual_2050.py
    python scripts/figures/report/fig_generacion_anual_2050.py --years 2030 2040 2045
    python scripts/figures/report/fig_generacion_anual_2050.py --scenarios BAC ISR
"""

from __future__ import annotations

import argparse
import os
import sys

# Solo scripts/ entra en sys.path; todo se importa como paquete (spec 2026-09-16 §3).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from figures.common.dashboard_config import (
    FIGURES_DIR,
    SCENARIO_ALIAS,
    classify_tech_generation,
)
from figures.common import report_style as rs


def compute_generation(years: list[int], scenarios: list[str]) -> dict[int, dict[str, dict]]:
    """{year: {scenario: {'ren','no_ren','total','pct'}}} (TWh).

    Misma lógica que chart02: ProductionByTechnology (PJ) sumado a nivel de
    timeslice por tech-año, /3.6 a TWh, clasificado Renovable/No Renovable.
    """
    df = rs.load(["ProductionByTechnology"], scenarios=scenarios)
    df = df.dropna(subset=["ProductionByTechnology"])
    df = df[df["ProductionByTechnology"] != 0]
    df = df[(df["YEAR"].isin(years)) & (df["Scenario"].isin(scenarios))]

    df["TechGroup"] = df["TECHNOLOGY"].apply(classify_tech_generation)
    df = df[df["TechGroup"].isin(["Renovable", "No Renovable"])]
    df["TWh"] = df["ProductionByTechnology"] / 3.6

    grouped = df.groupby(["Scenario", "YEAR", "TechGroup"])["TWh"].sum().unstack(fill_value=0.0)

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
    group_centers, sub_positions = rs.grouped_bar_layout(len(scenarios), len(years))

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
                    fontsize=8, fontweight="bold", color=rs.COLOR_TOTAL)
            if r > ymax * 0.05:
                ax.text(xi, r / 2, f"{pct}%", ha="center", va="center",
                        fontsize=7.5, fontweight="bold", color=rs.COLOR_LABEL_ON_BAR)

    ax.set_ylim(0, ymax)
    rs.add_year_xticks(ax, years, sub_positions)
    rs.add_group_labels(ax, group_centers, rs.scenario_ticklabels(scenarios))
    rs.apply_report_style(ax, "Generación anual [TWh]", european_y=True)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.1), ncol=2,
              frameon=False, fontsize=9)
    fig.tight_layout()
    return fig


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--years", nargs="+", type=int, default=rs.MULTI_YEARS)
    ap.add_argument("--scenarios", nargs="+", default=rs.CORE_SCENARIOS)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    data = compute_generation(args.years, args.scenarios)
    if not data:
        raise SystemExit(f"Sin datos de generación para {args.years} / {args.scenarios}")

    print(f"Generación anual {rs.years_label(args.years)} [TWh]:")
    for year in args.years:
        print(f" {year}:")
        for sc in args.scenarios:
            if sc in data.get(year, {}):
                d = data[year][sc]
                print(f"  {SCENARIO_ALIAS.get(sc, sc):8s} ({sc}): total={rs.eu(d['total'])}  "
                      f"renovable={d['pct']}%")

    fig = build_figure(data, args.scenarios, args.years)
    os.makedirs(FIGURES_DIR, exist_ok=True)
    base = args.out or os.path.join(FIGURES_DIR, "fig_generacion_anual_2050")
    png = rs.save(fig, base)
    print(f"OK -> {png}")


if __name__ == "__main__":
    main()
