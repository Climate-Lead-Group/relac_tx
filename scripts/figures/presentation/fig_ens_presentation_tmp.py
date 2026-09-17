"""
fig_ens_presentation_tmp.py — SCRIPT TEMPORAL (pack presentación). Variante
de fig_ens_tmp.py: figura con SOLO la Energía no Suministrada (ENS) en TWh,
acumulada por tramo y por escenario (una barra por escenario/tramo, color por
escenario, sin leyenda de componentes).

Cómputo (idéntico a fig_ens_tmp.py):
  - ENS = producción del backstop (techs con "BCK") vía ProductionByTechnology,
    en PJ (suma de timeslices/fuels, como chart_15 del dashboard y los demás
    scripts *_ens_tmp), acumulada dentro de cada tramo y convertida a TWh con
    el factor de chart_11 (1 PJ = 0,277778 TWh).
  - La ENS aquí es energía (TWh), no dinero: NO interviene ningún VOLL.

La presentación visual (letra grande, grupos juntos vía group_step +
rs.set_grouped_xlim) es la heredada del resto del pack presentación.

Uso:
    PYTHONUTF8=1 python Figures_Presentation/fig_ens_presentation_tmp.py
    PYTHONUTF8=1 python Figures_Presentation/fig_ens_presentation_tmp.py --periods 2026 2030 2031 2040 2041 2050
    PYTHONUTF8=1 python Figures_Presentation/fig_ens_presentation_tmp.py --scenarios BAC ISR
"""

from __future__ import annotations

import argparse
import os
import sys

# Solo scripts/ entra en sys.path; todo se importa como paquete (spec 2026-09-16 §3).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from figures.common.dashboard_config import FIGURES_PRESENTATION_DIR, SCENARIO_ALIAS
from figures.common import report_style as rs

PJ_PER_TWH = 0.277778  # PJ -> TWh (misma constante que chart_11)


def compute(periods: list[tuple[int, int]], scenarios: list[str]) -> dict[tuple[int, int], dict[str, dict]]:
    """{periodo: {scenario: {'twh','pj'}}} — ENS acumulada dentro de cada
    tramo (producción BCK). Incluye entradas en 0.0 para escenarios presentes
    en el CSV pero sin BCK en el tramo."""
    prod = rs.load(["ProductionByTechnology"], scenarios=scenarios)
    prod = prod[prod["Scenario"].isin(scenarios)]
    present = set(prod["Scenario"].unique())

    bck = prod[prod["TECHNOLOGY"].astype(str).str.contains("BCK", na=False)]

    out: dict[tuple[int, int], dict[str, dict]] = {}
    for p in periods:
        y0, y1 = p
        e = bck[(bck["YEAR"] >= y0) & (bck["YEAR"] <= y1)] \
            .groupby("Scenario")["ProductionByTechnology"].sum()
        for sc in scenarios:
            if sc not in present:
                continue
            pj = float(e.get(sc, 0.0))
            out.setdefault(p, {})[sc] = {"pj": pj, "twh": pj * PJ_PER_TWH}
    return out


def build_figure(data: dict, scenarios: list[str], periods: list[tuple[int, int]]):
    scenarios = [s for s in scenarios if any(s in data.get(p, {}) for p in periods)]
    group_centers, sub_positions = rs.grouped_bar_layout(
        len(scenarios), len(periods), group_step=0.80)
    colors = [rs.scenario_color(s) for s in scenarios]

    per_period_vals = [[data.get(p, {}).get(s, {}).get("twh", 0.0) for s in scenarios]
                       for p in periods]
    all_vals = [v for vals in per_period_vals for v in vals]
    ymax = max(all_vals) * 1.16 if all_vals and max(all_vals) > 0 else 1.0

    fig, ax = rs.new_ax(figsize=(9.6, 7.4))
    for pi, vals in enumerate(per_period_vals):
        x = sub_positions[pi]
        ax.bar(x, vals, 0.22, color=colors, zorder=3)
        for xi, v in zip(x, vals):
            ax.text(xi, v + ymax * 0.015, rs.eu(v, 1), ha="center", va="bottom",
                    fontsize=10, fontweight="bold", color=rs.COLOR_TOTAL)

    ax.set_ylim(0, ymax)
    rs.set_grouped_xlim(ax, group_centers, len(periods))
    rs.add_group_xticks(ax, [rs.period_label(p) for p in periods], sub_positions,
                         fontsize=9.5, rotation=45)
    rs.add_group_labels(ax, group_centers, rs.scenario_ticklabels(scenarios), y=-0.22, fontsize=11)
    rs.apply_report_style(ax, "Energía no Suministrada acumulada por tramo [TWh]",
                          european_y=True, fontsize=13)
    fig.tight_layout()
    return fig


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--periods", nargs="+", type=int, default=None,
                     help="Años y0 y1 y0 y1 ... (pares); por defecto 2026 2030 2031 2040 2041 2050")
    ap.add_argument("--scenarios", nargs="+", default=rs.PRESENTATION_SCENARIOS)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    periods = rs.periods_from_flat_years(args.periods)

    data = compute(periods, args.scenarios)
    if not data:
        raise SystemExit(f"Sin datos para {periods} / {args.scenarios}")

    print("Energía no Suministrada (producción BCK) acumulada por tramo [TWh] (PJ entre paréntesis):")
    for p in periods:
        print(f" {rs.period_label(p)}:")
        for sc in args.scenarios:
            if sc in data.get(p, {}):
                d = data[p][sc]
                print(f"  {SCENARIO_ALIAS.get(sc, sc):8s} ({sc}): {rs.eu(d['twh'], 2)} "
                      f"({rs.eu(d['pj'], 2)} PJ)")

    fig = build_figure(data, args.scenarios, periods)
    os.makedirs(FIGURES_PRESENTATION_DIR, exist_ok=True)
    base = args.out or os.path.join(
        FIGURES_PRESENTATION_DIR,
        f"fig_ens_{periods[0][0]}_{periods[-1][1]}_presentation_tmp")
    png = rs.save(fig, base)
    print(f"OK -> {png}")


if __name__ == "__main__":
    main()
