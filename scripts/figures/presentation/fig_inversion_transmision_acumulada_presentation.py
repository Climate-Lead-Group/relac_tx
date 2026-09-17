"""
fig_inversion_transmision_acumulada_presentation.py — PACK PRESENTACIÓN de
fig_inversion_transmision_acumulada.py. Mismo dato y misma lógica de
cómputo; solo cambia la presentación visual para diapositivas: letra más
grande, escenarios (grupos) más juntos y sin holgura excesiva en los
extremos del eje X. Sin leyenda ni barras apiladas en esta figura (color =
escenario, identificado en el eje X) -> los cambios 3 y 4 del pack no
aplican aquí.

Ver fig_inversion_transmision_acumulada.py para la documentación completa
del cómputo (idéntica aquí, sin cambios).

Uso:
    PYTHONUTF8=1 python Figures_Presentation/fig_inversion_transmision_acumulada_presentation.py
    PYTHONUTF8=1 python Figures_Presentation/fig_inversion_transmision_acumulada_presentation.py --periods 2026 2030 2031 2040 2041 2050
    PYTHONUTF8=1 python Figures_Presentation/fig_inversion_transmision_acumulada_presentation.py --scenarios BAC ISR
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
    classify_tech_type,
)
from figures.common import report_style as rs


def compute(periods: list[tuple[int, int]], scenarios: list[str]) -> dict[tuple[int, int], dict[str, float]]:
    """{periodo: {scenario: MUSD}} acumulado dentro de cada periodo."""
    df = rs.load(["CapitalInvestment"], scenarios=scenarios)
    df = df[~df["TECHNOLOGY"].astype(str).str.contains("BCK", na=False)]
    df = df[df["Scenario"].isin(scenarios)]
    df = df[df["TECHNOLOGY"].apply(classify_tech_type) == "Transmisión"]

    per = (
        df.groupby(["Scenario", "YEAR", "TECHNOLOGY"])["CapitalInvestment"]
        .max()
        .reset_index()
        .dropna(subset=["CapitalInvestment"])
    )
    adj = per["TECHNOLOGY"].str.startswith(("PWRTRN", "RNWTRN"))
    per["val"] = per["CapitalInvestment"].where(~adj, per["CapitalInvestment"] / 1.2)

    out: dict[tuple[int, int], dict[str, float]] = {}
    for p in periods:
        sub = per[(per["YEAR"] >= p[0]) & (per["YEAR"] <= p[1])]
        g = sub.groupby("Scenario")["val"].sum()
        out[p] = {sc: float(g.get(sc, 0.0)) for sc in scenarios if sc in g.index}
    return out


def build_figure(data: dict, scenarios: list[str], periods: list[tuple[int, int]]):
    scenarios = [s for s in scenarios if any(s in data.get(p, {}) for p in periods)]
    group_centers, sub_positions = rs.grouped_bar_layout(
        len(scenarios), len(periods), group_step=0.80)
    colors = [rs.scenario_color(s) for s in scenarios]

    per_period_vals = [[data.get(p, {}).get(s, 0.0) for s in scenarios] for p in periods]
    all_vals = [v for vals in per_period_vals for v in vals]
    ymax = max(all_vals) * 1.16 if all_vals else 1.0

    fig, ax = rs.new_ax(figsize=(9.6, 5.2))
    for pi, vals in enumerate(per_period_vals):
        x = sub_positions[pi]
        ax.bar(x, vals, 0.22, color=colors, zorder=3)
        for xi, v in zip(x, vals):
            ax.text(xi, v + ymax * 0.015, rs.eu(v), ha="center", va="bottom",
                    fontsize=10, fontweight="bold", color=rs.COLOR_TOTAL)

    ax.set_ylim(0, ymax)
    rs.set_grouped_xlim(ax, group_centers, len(periods))
    rs.add_group_xticks(ax, [rs.period_label(p) for p in periods], sub_positions,
                         fontsize=9.5, rotation=45)
    rs.add_group_labels(ax, group_centers, rs.scenario_ticklabels(scenarios), y=-0.22, fontsize=11)
    rs.apply_report_style(ax, "Inversión en transmisión acumulada [MUSD]",
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

    print("Inversión en transmisión acumulada por tramo [MUSD]:")
    for p in periods:
        print(f" {rs.period_label(p)}:")
        for sc in args.scenarios:
            if sc in data.get(p, {}):
                print(f"  {SCENARIO_ALIAS.get(sc, sc):8s} ({sc}): {rs.eu(data[p][sc])}")

    fig = build_figure(data, args.scenarios, periods)
    os.makedirs(FIGURES_PRESENTATION_DIR, exist_ok=True)
    base = args.out or os.path.join(
        FIGURES_PRESENTATION_DIR, f"fig_inversion_transmision_{periods[0][0]}_{periods[-1][1]}_presentation"
    )
    png = rs.save(fig, base)
    print(f"OK -> {png}")


if __name__ == "__main__":
    main()
