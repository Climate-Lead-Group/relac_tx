"""
fig_combustibles_fosiles_2050.py — Consumo de combustibles fósiles por
escenario, acumulado por tramo [millones de BEP] (figura de reporte,
Entregable 2).

Equivalente estático del chart_08a del dashboard, acumulado (no anual) en cada
tramo del horizonte (por defecto report_style.ACCUMULATED_PERIODS =
2026-2030 / 2031-2040 / 2041-2050) y filtrado a los escenarios core. Mide la
actividad (TotalTechnologyAnnualActivity, en PJ) de las tecnologías de
extracción/importación fósiles MIN* (classify_min_fossil: COA/COG/GAS/OIL/PET/
OTH; excluye URN), sumada año a año dentro de cada tramo, y convertida a
barriles equivalentes de petróleo (BEP) para el reporte. Barras agrupadas por
escenario, con una sub-barra por tramo dentro de cada grupo
(report_style.grouped_bar_layout); color por escenario (paleta del reporte:
rs.SCENARIO_COLORS, igual que fig_almacenamiento_2050.py), constante entre
tramos. Más red adecuada -> menos respaldo fósil.

Conversión PJ -> BEP (convención IEA, no hay un factor propio de OLADE/del
proyecto): 1 tep (tonelada equivalente de petróleo) = 41,868 GJ; 1 tep ≈ 7,33
bep -> 1 bep ≈ 5,7119 GJ. Se reporta en MILLONES de bep (MBEP), igual que el
resto del reporte usa millones de USD (MUSD) para cifras grandes: el factor
1 PJ = 10^6 GJ hace que "PJ / GJ_PER_BEP" dé directamente millones de bep (el
10^6 se cancela exactamente entre "P" de PJ y "M" de millones).

Uso:
    python scripts/figures/report/fig_combustibles_fosiles_2050.py
    python scripts/figures/report/fig_combustibles_fosiles_2050.py --periods 2026 2030 2031 2040 2041 2050
    python scripts/figures/report/fig_combustibles_fosiles_2050.py --scenarios BAC ISR
"""

from __future__ import annotations

import argparse
import os
import sys

# Solo scripts/ entra en sys.path; todo se importa como paquete (spec 2026-09-16 §3).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from figures.common.dashboard_config import FIGURES_DIR, SCENARIO_ALIAS, classify_min_fossil
from figures.common import report_style as rs

# IEA: 1 tep = 41,868 GJ; 1 tep ≈ 7,33 bep (barriles equivalentes de petróleo).
GJ_PER_TEP = 41.868
BEP_PER_TEP = 7.33
GJ_PER_BEP = GJ_PER_TEP / BEP_PER_TEP  # ≈ 5,7119 GJ/bep

# PJ (10^15 J) / (GJ/bep) (10^9 J/bep) = 10^6 bep = 1 millón de bep -> el
# factor de escala es exactamente 1/GJ_PER_BEP, sin necesidad de otro término.
MBEP_PER_PJ = 1.0 / GJ_PER_BEP


def compute(periods: list[tuple[int, int]], scenarios: list[str]) -> dict[tuple[int, int], dict[str, float]]:
    """{periodo: {scenario: PJ}} acumulado dentro de cada periodo."""
    df = rs.load(["TotalTechnologyAnnualActivity"], scenarios=scenarios)
    df = df.dropna(subset=["TotalTechnologyAnnualActivity"])
    df = df[df["Scenario"].isin(scenarios)]
    df = df[df["TECHNOLOGY"].map(classify_min_fossil).notna()]

    out: dict[tuple[int, int], dict[str, float]] = {}
    for p in periods:
        y0, y1 = p
        sub = df[(df["YEAR"] >= y0) & (df["YEAR"] <= y1)]
        g = sub.groupby("Scenario")["TotalTechnologyAnnualActivity"].sum()
        out[p] = {sc: float(g.get(sc, 0.0)) for sc in scenarios if sc in g.index}
    return out


def build_figure(data: dict, scenarios: list[str], periods: list[tuple[int, int]]):
    scenarios = [s for s in scenarios if any(s in data.get(p, {}) for p in periods)]
    group_centers, sub_positions = rs.grouped_bar_layout(len(scenarios), len(periods))
    colors = [rs.scenario_color(s) for s in scenarios]

    per_period_vals = [[data.get(p, {}).get(s, 0.0) * MBEP_PER_PJ for s in scenarios] for p in periods]
    all_vals = [v for vals in per_period_vals for v in vals]
    ymax = max(all_vals) * 1.16 if all_vals else 1.0

    fig, ax = rs.new_ax(figsize=(9.6, 5.6))
    for pi, vals in enumerate(per_period_vals):
        x = sub_positions[pi]
        ax.bar(x, vals, 0.22, color=colors, zorder=3)
        for xi, v in zip(x, vals):
            ax.text(xi, v + ymax * 0.015, rs.eu(v), ha="center", va="bottom",
                    fontsize=8, fontweight="bold", color=rs.COLOR_TOTAL)

    ax.set_ylim(0, ymax)
    rs.add_group_xticks(ax, [rs.period_label(p) for p in periods], sub_positions,
                         fontsize=7.5, rotation=45)
    rs.add_group_labels(ax, group_centers, rs.scenario_ticklabels(scenarios), y=-0.22)
    rs.apply_report_style(ax, "Consumo de combustibles fósiles acumulado por tramo [MBEP]",
                          european_y=True)
    fig.tight_layout()
    return fig


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--periods", nargs="+", type=int, default=None,
                     help="Años y0 y1 y0 y1 ... (pares); por defecto 2026 2030 2031 2040 2041 2050")
    ap.add_argument("--scenarios", nargs="+", default=rs.CORE_SCENARIOS)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    periods = rs.periods_from_flat_years(args.periods)

    data = compute(periods, args.scenarios)
    if not data:
        raise SystemExit(f"Sin datos para {periods} / {args.scenarios}")

    print("Consumo de combustibles fósiles acumulado por tramo [MBEP] (PJ entre paréntesis):")
    for p in periods:
        print(f" {rs.period_label(p)}:")
        for sc in args.scenarios:
            if sc in data.get(p, {}):
                pj = data[p][sc]
                print(f"  {SCENARIO_ALIAS.get(sc, sc):8s} ({sc}): {rs.eu(pj * MBEP_PER_PJ)} ({rs.eu(pj)} PJ)")

    fig = build_figure(data, args.scenarios, periods)
    os.makedirs(FIGURES_DIR, exist_ok=True)
    base = args.out or os.path.join(FIGURES_DIR, f"fig_combustibles_fosiles_{periods[0][0]}_{periods[-1][1]}")
    png = rs.save(fig, base)
    print(f"OK -> {png}")


if __name__ == "__main__":
    main()
