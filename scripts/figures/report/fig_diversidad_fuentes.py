"""
fig_diversidad_fuentes.py — Nº efectivo de fuentes de generación (1/HHI) por
escenario en 2030/2040/2050 (figura de reporte, Entregable 2).

Equivalente estático del chart_13 del dashboard ("Resiliencia — diversidad de
fuentes"):
  - Generación anual (ProductionByTechnology, suma sobre países y timeslices)
    por FAMILIA de fuente (classify_source_family: código PWR de 6 letras;
    excluye almacenamiento, líneas y backstop).
  - HHI = Σ shareᵢ² sobre las familias; Nº efectivo de fuentes = 1/HHI.
Más alto = matriz más diversa (ninguna fuente domina; una amenaza cualquiera
alcanza solo una porción limitada del suministro).

Barras agrupadas por escenario, con una sub-barra por año dentro de cada grupo
(report_style.grouped_bar_layout); color por escenario (paleta del reporte:
rs.SCENARIO_COLORS, igual que fig_almacenamiento_2050.py), constante entre años.

Uso:
    python scripts/figures/report/fig_diversidad_fuentes.py
    python scripts/figures/report/fig_diversidad_fuentes.py --years 2030 2040 2050
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
    group_centers, sub_positions = rs.grouped_bar_layout(len(scenarios), len(years))
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
                    fontsize=8, fontweight="bold", color=rs.COLOR_TOTAL)

    ax.set_ylim(0, ymax)
    rs.add_year_xticks(ax, years, sub_positions)
    rs.add_group_labels(ax, group_centers, rs.scenario_ticklabels(scenarios))
    rs.apply_report_style(ax, "Nº efectivo de fuentes (1/HHI)")
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

    print("Nº efectivo de fuentes (1/HHI):")
    for year in args.years:
        print(f" {year}:")
        for sc in args.scenarios:
            if sc in data.get(year, {}):
                print(f"  {SCENARIO_ALIAS.get(sc, sc):8s} ({sc}): {rs.eu(data[year][sc], 2)}")

    fig = build_figure(data, args.scenarios, args.years)
    os.makedirs(FIGURES_DIR, exist_ok=True)
    base = args.out or os.path.join(FIGURES_DIR, "fig_diversidad_fuentes")
    png = rs.save(fig, base)
    print(f"OK -> {png}")


if __name__ == "__main__":
    main()
