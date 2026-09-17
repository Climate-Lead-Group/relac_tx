"""
fig_km_lineas_acumulados.py — Kilómetros de líneas de transmisión acumulados
desde `y0` hasta 2030/2040/2050 [km] por escenario, apilados por grupo de
línea (figura de reporte, Entregable 2).

Equivalente estático del chart_10 del dashboard ("Kilómetros de Líneas [km]"),
acumulado (no anual) en la ventana [y0, año]. Misma fórmula que la hoja Tableau
"Lineas_km":
  km = (NewCapacity / Capacity) * Distancia, con Distancia RNW para techs RNW*
  y Distancia NRNW para PWR/TRN, y ×1,25 para repotenciadas (RPO).
Capacity y Distancia vienen de CapacityAndDistances.xlsx (por Scenario+país).
Solo líneas (classify_tech_type == "Transmisión"): los interconectores puros
quedan fuera (no son tipo Transmisión ni casan país). NewCapacity por tech-año
vía max sobre timeslices (mismo gotcha que el dashboard). Grupos =
classify_line_group_raw (Planificadas / Nuevas No Planificadas /
Repotenciadas No Planificadas).

Barras agrupadas por escenario, con una sub-barra apilada por año dentro de
cada grupo (report_style.grouped_bar_layout); cada sub-barra es el acumulado
DESDE `y0` HASTA ese año (ventanas anidadas [y0,2030] ⊂ [y0,2040] ⊂ [y0,2050],
no tramos discretos): lectura de "km construidos a la fecha".

Uso:
    python scripts/figures/report/fig_km_lineas_acumulados.py
    python scripts/figures/report/fig_km_lineas_acumulados.py --y0 2026 --years 2030 2040 2050 --scenarios BAC ISR
"""

from __future__ import annotations

import argparse
import os
import sys

# Solo scripts/ entra en sys.path; todo se importa como paquete (spec 2026-09-16 §3).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd

from figures.common.dashboard_config import (
    FIGURES_DIR,
    COUNTRY_ISO3_BY_NAME,
    SCENARIO_ALIAS,
    classify_line_group_raw,
    classify_tech_type,
    load_capacity_and_distances,
)
from figures.common import report_style as rs

# Orden de apilado (de abajo hacia arriba) y color de cada grupo de línea.
CATEGORIES = [
    ("Líneas Planificadas", rs.COLOR_LINEAS_PLANIFICADAS),
    ("Líneas Nuevas No Planificadas", rs.COLOR_LINEAS_NUEVAS_NOPLAN),
    ("Líneas Repotenciadas No Planificadas", rs.COLOR_LINEAS_REPO_NOPLAN),
]

# ISO3 -> nombre de país (el xlsx de capacidades/distancias usa el nombre).
_COUNTRY_NAMES = {iso3: name for name, iso3 in COUNTRY_ISO3_BY_NAME.items()}


def compute(y0: int, years: list[int], scenarios: list[str]) -> dict[int, dict[str, dict]]:
    """{year: {scenario: {grupo: km, ..., 'total': km}}} acumulado en [y0, year]."""
    y1 = max(years)
    df = rs.load(["NewCapacity"], scenarios=scenarios)
    df = df[(df["YEAR"] >= y0) & (df["YEAR"] <= y1) & (df["Scenario"].isin(scenarios))]
    df = df[df["TECHNOLOGY"].apply(classify_tech_type) == "Transmisión"]
    df["Country"] = df["TECHNOLOGY"].str[6:9].map(_COUNTRY_NAMES)

    per = (
        df.groupby(["Scenario", "YEAR", "TECHNOLOGY", "Country"])["NewCapacity"]
        .max()
        .reset_index()
        .dropna(subset=["NewCapacity", "Country"])
    )

    cd = load_capacity_and_distances()
    per = per.merge(cd, on=["Scenario", "Country"], how="inner")

    is_rnw = per["TECHNOLOGY"].str.startswith("RNW")
    dist = per["Distance RNW"].where(is_rnw, per["Distance NRNW"])
    factor = per["TECHNOLOGY"].str.contains("RPO", regex=False).map(
        {True: 1.25, False: 1.0}
    )
    per["km"] = (per["NewCapacity"] / per["Capacity"]) * dist * factor

    per["LG"] = per["TECHNOLOGY"].apply(classify_line_group_raw)
    per = per[per["LG"].notna()]

    out: dict[int, dict[str, dict]] = {}
    for year in years:
        sub = per[per["YEAR"] <= year]
        g = sub.groupby(["Scenario", "LG"])["km"].sum().unstack(fill_value=0.0)
        for sc in scenarios:
            if sc not in g.index:
                continue
            row = {name: float(g.at[sc, name]) if name in g.columns else 0.0
                   for name, _ in CATEGORIES}
            row["total"] = sum(row[name] for name, _ in CATEGORIES)
            out.setdefault(year, {})[sc] = row
    return out


def build_figure(data: dict, scenarios: list[str], y0: int, years: list[int]):
    scenarios = [s for s in scenarios if any(s in data.get(y, {}) for y in years)]
    group_centers, sub_positions = rs.grouped_bar_layout(len(scenarios), len(years))

    cats = [(n, c) for n, c in CATEGORIES
            if any(data[y][s][n] > 1e-9 for y in years for s in scenarios if s in data.get(y, {}))]
    all_totals = [data[y][s]["total"] for y in years for s in scenarios if s in data.get(y, {})]
    ymax = max(all_totals) * 1.16 if all_totals else 1.0

    fig, ax = rs.new_ax(figsize=(9.6, 5.0))
    for yi, year in enumerate(years):
        x = sub_positions[yi]
        bottoms = [0.0] * len(scenarios)
        for name, color in cats:
            vals = [data.get(year, {}).get(s, {}).get(name, 0.0) for s in scenarios]
            ax.bar(x, vals, 0.22, bottom=bottoms, color=color, zorder=3,
                   label=name if yi == 0 else None)
            bottoms = [b + v for b, v in zip(bottoms, vals)]

        totals = [data.get(year, {}).get(s, {}).get("total", 0.0) for s in scenarios]
        for xi, tot in zip(x, totals):
            ax.text(xi, tot + ymax * 0.015, rs.eu(tot), ha="center", va="bottom",
                    fontsize=8, fontweight="bold", color=rs.COLOR_TOTAL)

    ax.set_ylim(0, ymax)
    rs.add_year_xticks(ax, years, sub_positions)
    rs.add_group_labels(ax, group_centers, rs.scenario_ticklabels(scenarios))
    rs.apply_report_style(ax, f"Kilómetros de líneas acumulados desde {y0} [km]",
                          european_y=True)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.16), ncol=2,
              frameon=False, fontsize=8.5)
    fig.tight_layout()
    return fig


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--y0", type=int, default=2026)
    ap.add_argument("--years", nargs="+", type=int, default=rs.MULTI_YEARS)
    ap.add_argument("--scenarios", nargs="+", default=rs.CORE_SCENARIOS)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    data = compute(args.y0, args.years, args.scenarios)
    if not data:
        raise SystemExit(f"Sin datos para {args.y0}-{args.years} / {args.scenarios}")

    print(f"Kilómetros de líneas acumulados desde {args.y0} [km]:")
    for year in args.years:
        print(f" hasta {year}:")
        for sc in args.scenarios:
            if sc in data.get(year, {}):
                d = data[year][sc]
                detail = "  ".join(f"{n}={rs.eu(d[n])}" for n, _ in CATEGORIES)
                print(f"  {SCENARIO_ALIAS.get(sc, sc):8s} ({sc}): total={rs.eu(d['total'])}  |  {detail}")

    fig = build_figure(data, args.scenarios, args.y0, args.years)
    os.makedirs(FIGURES_DIR, exist_ok=True)
    base = args.out or os.path.join(FIGURES_DIR, f"fig_km_lineas_{args.y0}_{max(args.years)}")
    png = rs.save(fig, base)
    print(f"OK -> {png}")


if __name__ == "__main__":
    main()
