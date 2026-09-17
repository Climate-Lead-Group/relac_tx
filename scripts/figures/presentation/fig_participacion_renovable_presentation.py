"""
fig_participacion_renovable_presentation.py — PACK PRESENTACIÓN de
fig_participacion_renovable.py. Mismo dato y misma lógica de cómputo; solo
cambia la presentación visual para diapositivas: letra más grande y
leyenda en una sola fila (ncol = nº de escenarios; el original usaba
ncol=2, que con 4 escenarios quedaba en 2 filas; ahora son 2: BAC/ISR). Es un gráfico de LÍNEAS
(trayectoria por año, sin barras agrupadas por escenario) -> los cambios 2
y 4 del pack (espaciado entre columnas de escenario / etiquetas dentro de
barra apilada) no aplican aquí.

Ver fig_participacion_renovable.py para la documentación completa del
cómputo (idéntica aquí, sin cambios).

Uso:
    PYTHONUTF8=1 python Figures_Presentation/fig_participacion_renovable_presentation.py
    PYTHONUTF8=1 python Figures_Presentation/fig_participacion_renovable_presentation.py --years 2025 2030 2035 2040 2045 2050
    PYTHONUTF8=1 python Figures_Presentation/fig_participacion_renovable_presentation.py --scenarios BAC ISR
"""

from __future__ import annotations

import argparse
import os
import sys

# Solo scripts/ entra en sys.path; todo se importa como paquete (spec 2026-09-16 §3).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from figures.common.dashboard_config import (
    FIGURES_PRESENTATION_DIR,
    ALL_YEARS,
    SCENARIO_ALIAS,
    classify_tech_generation,
)
from figures.common import report_style as rs

# Todos los años del horizonte desde 2025 (2023-2024 se excluyen: calibración).
DEFAULT_YEARS = [y for y in ALL_YEARS if y >= 2025]


def compute(years: list[int], scenarios: list[str]) -> dict[str, dict[int, float]]:
    """{scenario: {año: % renovable}} sobre la generación total."""
    df = rs.load(["ProductionByTechnology"], scenarios=scenarios)
    df = df.dropna(subset=["ProductionByTechnology"])
    df = df[df["ProductionByTechnology"] != 0]
    df = df[(df["YEAR"].isin(years)) & (df["Scenario"].isin(scenarios))]

    df["TechGroup"] = df["TECHNOLOGY"].apply(classify_tech_generation)
    df = df[df["TechGroup"].isin(["Renovable", "No Renovable"])]

    g = (
        df.groupby(["Scenario", "YEAR", "TechGroup"])["ProductionByTechnology"]
        .sum()
        .unstack(fill_value=0.0)
    )
    ren = g["Renovable"] if "Renovable" in g.columns else 0.0
    total = g.sum(axis=1)
    pct = (ren / total * 100).dropna()

    out: dict[str, dict[int, float]] = {}
    for (sc, year), v in pct.items():
        if sc in scenarios:
            out.setdefault(sc, {})[int(year)] = float(v)
    return out


def build_figure(data: dict, scenarios: list[str], years: list[int]):
    scenarios = [s for s in scenarios if s in data]

    fig, ax = rs.new_ax(figsize=(9.6, 4.8))
    for sc in scenarios:
        ys = [y for y in years if y in data[sc]]
        vals = [data[sc][y] for y in ys]
        label = SCENARIO_ALIAS.get(sc, sc)
        sub = rs.SCENARIO_SUBLABEL.get(sc)
        if sub:
            label = f"{label} · {sub}"
        ax.plot(ys, vals, color=rs.scenario_color(sc), label=label,
                linewidth=2.4, marker="o", markersize=4.5, zorder=3)

    # Eje Y fino (cada 2 pp) y eje X con TODOS los años, rotados.
    all_vals = [v for sc in scenarios for v in data[sc].values()]
    lo = (int(min(all_vals)) // 2) * 2 - 2
    hi = -(-int(max(all_vals)) // 2) * 2 + 2
    ax.set_ylim(lo, hi)
    from matplotlib.ticker import FuncFormatter, MultipleLocator
    ax.yaxis.set_major_locator(MultipleLocator(2))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _pos: f"{v:.0f}%"))
    ax.set_xticks(years)
    ax.set_xticklabels([str(y) for y in years], fontsize=9.5, rotation=45, ha="right")

    rs.apply_report_style(ax, "Participación renovable en la generación [%]", fontsize=13)
    ax.legend(loc="upper left", ncol=len(scenarios), frameon=False, fontsize=10.5)
    fig.tight_layout()
    return fig


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--years", nargs="+", type=int, default=DEFAULT_YEARS)
    ap.add_argument("--scenarios", nargs="+", default=rs.PRESENTATION_SCENARIOS)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    data = compute(args.years, args.scenarios)
    if not data:
        raise SystemExit(f"Sin datos para {args.years} / {args.scenarios}")

    print("Participación renovable en la generación [%]:")
    for sc in args.scenarios:
        if sc in data:
            traj = "  ".join(f"{y}={data[sc][y]:.1f}%" for y in args.years if y in data[sc])
            print(f"  {SCENARIO_ALIAS.get(sc, sc):8s} ({sc}): {traj}")

    fig = build_figure(data, args.scenarios, args.years)
    os.makedirs(FIGURES_PRESENTATION_DIR, exist_ok=True)
    base = args.out or os.path.join(FIGURES_PRESENTATION_DIR, "fig_participacion_renovable_presentation")
    png = rs.save(fig, base)
    print(f"OK -> {png}")


if __name__ == "__main__":
    main()
