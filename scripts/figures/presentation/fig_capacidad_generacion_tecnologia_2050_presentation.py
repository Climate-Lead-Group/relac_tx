"""
fig_capacidad_generacion_tecnologia_2050_presentation.py — Variante de
fig_capacidad_generacion_2050_presentation.py que, en lugar de apilar solo
Renovable / No Renovable, desglosa cada tramo en sus tecnologías individuales
(familia PWR de 6 letras, misma clasificación que classify_source_family /
SOURCE_FAMILY_NAMES: Solar Fotovoltaica, Hidroeléctrica, Eólica Terrestre,
Carbón, Gas Natural, etc.).

Mismo filtro base que el original (TotalCapacityAnnual, classify_tech_generation
para quedarse solo con filas Renovable/No Renovable) — el total de cada barra
coincide exactamente con el del gráfico de 2 colores. Dentro de eso se agrupa
además por familia de tecnología para el desglose.

Apilado: abajo las sub-tecnologías renovables (orden de RENEWABLE_CODES),
arriba las no renovables (orden de NON_RENEWABLE_CODES) — conserva la
intuición visual ren/no-ren del gráfico original. Solo se dibujan/aparecen en
leyenda las tecnologías con capacidad > 0 en los años/escenarios pedidos.

Etiquetas: total en GW encima de cada barra (igual que el original); dentro
de cada segmento solo se etiqueta el valor si el segmento supera ~8% de la
barra (evita saturar con 16 etiquetas ilegibles) — los segmentos chicos se
identifican solo por la leyenda.

Uso:
    PYTHONUTF8=1 python Figures_Presentation/fig_capacidad_generacion_tecnologia_2050_presentation.py
    PYTHONUTF8=1 python Figures_Presentation/fig_capacidad_generacion_tecnologia_2050_presentation.py --years 2030 2040 2050 --scenarios BAC ISR
"""

from __future__ import annotations

import argparse
import os
import sys

# Solo scripts/ entra en sys.path; todo se importa como paquete (spec 2026-09-16 §3).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from figures.common.dashboard_config import (
    FIGURES_PRESENTATION_DIR,
    NON_RENEWABLE_CODES,
    RENEWABLE_CODES,
    SCENARIO_ALIAS,
    SOURCE_FAMILY_NAMES,
    classify_tech_generation,
)
from figures.common import report_style as rs

# Orden fijo de apilado: renovables (abajo) luego no renovables (arriba),
# mismo orden que dashboard_config.RENEWABLE_CODES / NON_RENEWABLE_CODES.
TECH_ORDER = RENEWABLE_CODES + NON_RENEWABLE_CODES

# Un color fijo por familia de tecnología: tonos teal/verde para renovables
# (ancla en rs.COLOR_RENOVABLE), tonos gris/azul/café/violeta para no
# renovables (ancla en rs.COLOR_NO_RENOVABLE). Local a este script — no toca
# dashboard_config.py ni report_style.py.
TECH_COLORS = {
    # Renovables
    "PWRHYD": "#23978E",  # Hidroeléctrica — teal (ancla, mismo tono que "Renovable")
    "PWRSPV": "#5BAE72",  # Solar Fotovoltaica — verde
    "PWRWON": "#2E8B8B",  # Eólica Terrestre — teal-azulado
    "PWRWOF": "#1B6F72",  # Eólica Marina — teal oscuro
    "PWRBIO": "#7C9A3C",  # Biomasa — verde oliva
    "PWRGEO": "#8FBF8F",  # Geotérmica — verde salvia claro
    "PWRCSP": "#B5A642",  # Solar CSP — dorado/khaki (distingue de la PV)
    "PWRWAS": "#4F7942",  # Residuos — verde bosque
    # No renovables
    "PWRNGS": "#6699CC",  # Gas Natural — azul (mismo tono que COLORS_FOSSIL_FUEL)
    "PWRCOA": "#595959",  # Carbón — gris oscuro (mismo tono que COLORS_FOSSIL_FUEL)
    "PWROIL": "#B07D3C",  # Petróleo/Diésel — ámbar/café (mismo tono que COLORS_FOSSIL_FUEL)
    "PWRPET": "#8B5A2B",  # Petcoke — café oscuro
    "PWRCOG": "#909090",  # Cogeneración — gris medio
    "PWRURN": "#7A6C8C",  # Nuclear — violeta grisáceo
    "PWRCSS": "#4A5A66",  # Carbón con CCS — gris azulado oscuro
    "PWROTH": "#BEBEBE",  # Otros — gris claro
}


def compute(years: list[int], scenarios: list[str]) -> dict[int, dict[str, dict]]:
    """{year: {scenario: {'by_tech': {code: gw}, 'ren','no_ren','total','pct'}}}."""
    df = rs.load(["TotalCapacityAnnual"], scenarios=scenarios)
    df = df.dropna(subset=["TotalCapacityAnnual"])
    df = df[df["TotalCapacityAnnual"] != 0]
    df = df[(df["YEAR"].isin(years)) & (df["Scenario"].isin(scenarios))]

    df["TechGroup"] = df["TECHNOLOGY"].apply(classify_tech_generation)
    df = df[df["TechGroup"].isin(["Renovable", "No Renovable"])]
    df = df.drop_duplicates(subset=["Scenario", "YEAR", "TECHNOLOGY"])
    df["TechFamily"] = df["TECHNOLOGY"].str[:6]

    grouped = (
        df.groupby(["Scenario", "YEAR", "TechFamily"])["TotalCapacityAnnual"]
        .sum()
        .reset_index()
    )

    out: dict[int, dict[str, dict]] = {}
    for year in years:
        for sc in scenarios:
            g = grouped[(grouped["Scenario"] == sc) & (grouped["YEAR"] == year)]
            if g.empty:
                continue
            by_tech = {row.TechFamily: float(row.TotalCapacityAnnual) for row in g.itertuples()}
            ren = sum(v for k, v in by_tech.items() if k in RENEWABLE_CODES)
            no_ren = sum(v for k, v in by_tech.items() if k in NON_RENEWABLE_CODES)
            total = ren + no_ren
            pct = round(ren / total * 100) if total else 0
            out.setdefault(year, {})[sc] = {
                "by_tech": by_tech, "ren": ren, "no_ren": no_ren,
                "total": total, "pct": pct,
            }
    return out


def build_figure(data: dict, scenarios: list[str], years: list[int]):
    scenarios = [s for s in scenarios if any(s in data.get(y, {}) for y in years)]
    group_centers, sub_positions = rs.grouped_bar_layout(
        len(scenarios), len(years), group_step=0.80)

    # Tecnologías realmente presentes (>0) en la selección, en TECH_ORDER.
    present = [
        code for code in TECH_ORDER
        if any(
            data.get(y, {}).get(s, {}).get("by_tech", {}).get(code, 0.0) > 0
            for y in years for s in scenarios
        )
    ]

    per_year = []
    all_totals = []
    for year in years:
        totals = [data.get(year, {}).get(s, {}).get("total", 0.0) for s in scenarios]
        per_year.append(totals)
        all_totals += totals
    ymax = max(all_totals) * 1.18 if all_totals else 1.0

    fig, ax = rs.new_ax(figsize=(9.6, 5.0))
    for yi, year in enumerate(years):
        x = sub_positions[yi]
        totals = per_year[yi]
        bottom = [0.0] * len(scenarios)
        for code in present:
            vals = [data.get(year, {}).get(s, {}).get("by_tech", {}).get(code, 0.0) for s in scenarios]
            ax.bar(x, vals, 0.22, bottom=bottom, color=TECH_COLORS[code], zorder=3,
                   label=SOURCE_FAMILY_NAMES[code] if yi == 0 else None)
            for xi, v, b in zip(x, vals, bottom):
                if v > ymax * 0.08:
                    ax.text(xi, b + v / 2, rs.eu(v), ha="center", va="center",
                            fontsize=8, fontweight="bold", color=rs.COLOR_LABEL_ON_BAR)
            bottom = [b + v for b, v in zip(bottom, vals)]
        for xi, tot in zip(x, totals):
            ax.text(xi, tot + ymax * 0.015, rs.eu(tot), ha="center", va="bottom",
                    fontsize=10, fontweight="bold", color=rs.COLOR_TOTAL)

    ax.set_ylim(0, ymax)
    rs.set_grouped_xlim(ax, group_centers, len(years))
    rs.add_year_xticks(ax, years, sub_positions, fontsize=9.5)
    rs.add_group_labels(ax, group_centers, rs.scenario_ticklabels(scenarios), fontsize=11)
    rs.apply_report_style(ax, "Capacidad instalada de generación [GW]",
                          european_y=True, fontsize=13)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.16), ncol=5,
              frameon=False, fontsize=8.5)
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

    print(f"Capacidad instalada de generación por tecnología {rs.years_label(args.years)} [GW]:")
    for year in args.years:
        print(f" {year}:")
        for sc in args.scenarios:
            if sc in data.get(year, {}):
                d = data[year][sc]
                print(f"  {SCENARIO_ALIAS.get(sc, sc):8s} ({sc}): total={rs.eu(d['total'])}  "
                      f"ren={rs.eu(d['ren'])} ({d['pct']}%)  no_ren={rs.eu(d['no_ren'])}")
                for code, gw in sorted(d["by_tech"].items(), key=lambda kv: -kv[1]):
                    if gw > 0:
                        print(f"      {SOURCE_FAMILY_NAMES.get(code, code):22s}: {rs.eu(gw)}")

    fig = build_figure(data, args.scenarios, args.years)
    os.makedirs(FIGURES_PRESENTATION_DIR, exist_ok=True)
    base = args.out or os.path.join(FIGURES_PRESENTATION_DIR, "fig_capacidad_generacion_tecnologia_2050_presentation")
    png = rs.save(fig, base)
    print(f"OK -> {png}")


if __name__ == "__main__":
    main()
