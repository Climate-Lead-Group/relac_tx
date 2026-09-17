"""
fig_km_lineas_acumulados_presentation.py — PACK PRESENTACIÓN de
fig_km_lineas_acumulados.py. Mismo dato y misma lógica de cómputo; solo
cambia la presentación visual para diapositivas:

  1. Letra más grande (ylabel, ticks, labels de grupo, leyenda, valores).
  2. Escenarios (grupos) más juntos: `group_step` reducido en
     rs.grouped_bar_layout (ver report_style.py).
  3. Leyenda en una sola fila (ncol = nº de categorías presentes).
  4. Valor de CADA tramo anotado dentro de su segmento de barra (además del
     total encima), copiando el formato de fig_km_lineas_existentes_tmp.py.

Ver fig_km_lineas_acumulados.py para la documentación de la fórmula de
cómputo (idéntica aquí, sin cambios).

Uso:
    PYTHONUTF8=1 python Figures_Presentation/fig_km_lineas_acumulados_presentation.py
    PYTHONUTF8=1 python Figures_Presentation/fig_km_lineas_acumulados_presentation.py --y0 2026 --years 2030 2040 2050 --scenarios BAC ISR
"""

from __future__ import annotations

import argparse
import os
import sys

# Solo scripts/ entra en sys.path; todo se importa como paquete (spec 2026-09-16 §3).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from figures.common.dashboard_config import (
    FIGURES_PRESENTATION_DIR,
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
    group_centers, sub_positions = rs.grouped_bar_layout(
        len(scenarios), len(years), group_step=0.80)

    cats = [(n, c) for n, c in CATEGORIES
            if any(data[y][s][n] > 1e-9 for y in years for s in scenarios if s in data.get(y, {}))]
    all_totals = [data[y][s]["total"] for y in years for s in scenarios if s in data.get(y, {})]
    ymax = max(all_totals) * 1.16 if all_totals else 1.0
    min_label_h = ymax * 0.035  # tramos más finos que esto no llevan etiqueta interna

    fig, ax = rs.new_ax(figsize=(10.6, 5.4))
    for yi, year in enumerate(years):
        x = sub_positions[yi]
        bottoms = [0.0] * len(scenarios)
        for name, color in cats:
            vals = [data.get(year, {}).get(s, {}).get(name, 0.0) for s in scenarios]
            ax.bar(x, vals, 0.22, bottom=bottoms, color=color, zorder=3,
                   label=name if yi == 0 else None)
            for xi, b, v in zip(x, bottoms, vals):
                if v >= min_label_h:
                    ax.text(xi, b + v / 2, rs.eu(v), ha="center", va="center",
                            fontsize=9, color=rs.COLOR_LABEL_ON_BAR, zorder=4)
            bottoms = [b + v for b, v in zip(bottoms, vals)]

        totals = [data.get(year, {}).get(s, {}).get("total", 0.0) for s in scenarios]
        for xi, tot in zip(x, totals):
            ax.text(xi, tot + ymax * 0.015, rs.eu(tot), ha="center", va="bottom",
                    fontsize=10.5, fontweight="bold", color=rs.COLOR_TOTAL)

    ax.set_ylim(0, ymax)
    rs.set_grouped_xlim(ax, group_centers, len(years))
    rs.add_year_xticks(ax, years, sub_positions, fontsize=9.5)
    rs.add_group_labels(ax, group_centers, rs.scenario_ticklabels(scenarios), fontsize=11)
    rs.apply_report_style(
        ax, f"Kilómetros de líneas acumulados desde {y0} [km]",
        european_y=True, fontsize=13)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.16), ncol=len(cats),
              frameon=False, fontsize=10.5)
    fig.tight_layout()
    return fig


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--y0", type=int, default=2026)
    ap.add_argument("--years", nargs="+", type=int, default=rs.MULTI_YEARS)
    ap.add_argument("--scenarios", nargs="+", default=rs.PRESENTATION_SCENARIOS)
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
    os.makedirs(FIGURES_PRESENTATION_DIR, exist_ok=True)
    base = args.out or os.path.join(
        FIGURES_PRESENTATION_DIR, f"fig_km_lineas_{args.y0}_{max(args.years)}_presentation")
    png = rs.save(fig, base)
    print(f"OK -> {png}")


if __name__ == "__main__":
    main()
