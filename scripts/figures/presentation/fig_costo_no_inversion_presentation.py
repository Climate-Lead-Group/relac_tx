"""
fig_costo_no_inversion_presentation.py — PACK PRESENTACIÓN de
fig_costo_no_inversion.py. Mismo dato y misma lógica de cómputo; solo
cambia la presentación visual para diapositivas:

  1. Letra más grande (ylabel, ticks, labels de grupo, leyenda, valores).
  2. Escenarios (grupos) más juntos, y menos holgura en los extremos del
     eje X (group_step + rs.set_grouped_xlim).
  3. Leyenda en una sola fila (ya lo estaba: 3 entradas con ncol=3; se deja
     explícito y con letra más grande).
  4. Valor de CADA componente (CAPEX, O&M, Combustible; la Energía no
     Suministrada se ignora) anotado dentro de su tramo de barra (el original solo
     mostraba el total y el delta vs. referencia), copiando el formato de
     fig_km_lineas_existentes_tmp.py.

Ver fig_costo_no_inversion.py para la documentación completa del cómputo
(idéntica aquí, sin cambios).

Uso:
    PYTHONUTF8=1 python Figures_Presentation/fig_costo_no_inversion_presentation.py
    PYTHONUTF8=1 python Figures_Presentation/fig_costo_no_inversion_presentation.py --periods 2026 2030 2031 2040 2041 2050
    PYTHONUTF8=1 python Figures_Presentation/fig_costo_no_inversion_presentation.py --scenarios BAC ISR --ref BAC
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

# (nombre, color, mostrar_en_leyenda). La Energía no Suministrada (ENS, backstop
# BCK valorado al VOLL) se IGNORA por completo: no se calcula, no se apila y no
# entra en `total`.
COMPONENTS = [
    ("CAPEX", rs.COLOR_CAPEX, True),
    ("O&M", rs.COLOR_OM, True),
    ("Combustible", rs.COLOR_COMBUSTIBLE, True),
]

MUSD_PER_BILLON = 1_000_000.0  # 1 billón (10^12 USD) = 1.000.000 MUSD (10^6 USD c/u)


def compute(periods: list[tuple[int, int]], scenarios: list[str]) -> dict[tuple[int, int], dict[str, dict]]:
    """{periodo: {scenario: {'CAPEX','O&M','Combustible','total'}}}
    (MUSD) acumulado dentro de cada periodo. Réplica de la lógica de costo del chart_14."""
    cols = ["CapitalInvestment", "OperatingCost"]
    df = rs.load(cols, scenarios=scenarios)
    df = df[df["Scenario"].isin(scenarios)]

    per = df.groupby(["Scenario", "YEAR", "TECHNOLOGY"])[cols].max().reset_index()
    per["TechType"] = per["TECHNOLOGY"].apply(classify_tech_type)
    is_bck = per["TECHNOLOGY"].astype(str).str.contains("BCK", na=False)
    is_infra = per["TechType"].notna() & ~is_bck

    capex = per["CapitalInvestment"].fillna(0)
    adj = per["TECHNOLOGY"].str.startswith(("PWRTRN", "RNWTRN"))
    capex = capex.where(~adj, capex / 1.2)
    op = per["OperatingCost"].fillna(0)

    per["CAPEX"] = capex.where(is_infra, 0.0)
    per["O&M"] = op.where(is_infra, 0.0)
    per["Combustible"] = op.where(~is_infra & ~is_bck, 0.0)

    out: dict[tuple[int, int], dict[str, dict]] = {}
    for p in periods:
        y0, y1 = p
        pper = per[(per["YEAR"] >= y0) & (per["YEAR"] <= y1)]
        infra = pper.groupby("Scenario")[["CAPEX", "O&M", "Combustible"]].sum()

        for sc in scenarios:
            if sc not in infra.index:
                continue
            row = {c: float(infra.at[sc, c]) for c in ("CAPEX", "O&M", "Combustible")}
            row["total"] = sum(row[c] for c, _, _ in COMPONENTS)
            out.setdefault(p, {})[sc] = row
    return out


def build_figure(data: dict, scenarios: list[str], periods: list[tuple[int, int]], ref: str = "BAC"):
    scenarios = [s for s in scenarios if any(s in data.get(p, {}) for p in periods)]
    group_centers, sub_positions = rs.grouped_bar_layout(
        len(scenarios), len(periods), group_step=0.80)

    per_period = []
    all_totals = []
    for p in periods:
        totals = [data.get(p, {}).get(s, {}).get("total", 0.0) / MUSD_PER_BILLON for s in scenarios]
        ref_total = data.get(p, {}).get(ref, {}).get("total")
        ref_total = ref_total / MUSD_PER_BILLON if ref_total is not None else None
        per_period.append((totals, ref_total))
        all_totals += totals
    ymax = max(all_totals) * 1.22 if all_totals else 1.0
    min_label_h = ymax * 0.035  # tramos más finos que esto no llevan etiqueta interna

    fig, ax = rs.new_ax(figsize=(10.6, 5.6))
    legend_cats = [(c, col) for c, col, show in COMPONENTS if show]
    for pi, p in enumerate(periods):
        x = sub_positions[pi]
        bottoms = [0.0] * len(scenarios)
        for comp, color, show_legend in COMPONENTS:
            vals = [data.get(p, {}).get(s, {}).get(comp, 0.0) / MUSD_PER_BILLON for s in scenarios]
            label = comp if (show_legend and pi == 0) else "_nolegend_"
            ax.bar(x, vals, 0.22, bottom=bottoms, color=color, label=label, zorder=3)
            for xi, b, v in zip(x, bottoms, vals):
                if v >= min_label_h:
                    ax.text(xi, b + v / 2, rs.eu(v, 1), ha="center", va="center",
                            fontsize=8.5, color=rs.COLOR_LABEL_ON_BAR, zorder=4)
            bottoms = [b + v for b, v in zip(bottoms, vals)]

        totals, ref_total = per_period[pi]
        for xi, s, tot in zip(x, scenarios, totals):
            ax.text(xi, tot + ymax * 0.015, rs.eu(tot, 2), ha="center", va="bottom",
                    fontsize=9.5, fontweight="bold", color=rs.COLOR_TOTAL)
            if ref_total is not None and s != ref:
                delta = tot - ref_total
                ax.text(xi, tot + ymax * 0.08, f"({rs.signed_eu(delta, 2)})", ha="center",
                        va="bottom", fontsize=8.5, fontweight="bold", color=rs.COLOR_COMBUSTIBLE)

    ax.set_ylim(0, ymax)
    rs.set_grouped_xlim(ax, group_centers, len(periods))
    rs.add_group_xticks(ax, [rs.period_label(p) for p in periods], sub_positions,
                         fontsize=9.5, rotation=45)
    rs.add_group_labels(ax, group_centers, rs.scenario_ticklabels(scenarios), y=-0.22, fontsize=11)
    rs.apply_report_style(ax, "Costo total del sistema, acumulado por tramo [BUSD]",
                          european_y=True, fontsize=13)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.14), ncol=len(legend_cats),
              frameon=False, fontsize=10.5)
    fig.tight_layout()
    return fig


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--periods", nargs="+", type=int, default=None,
                     help="Años y0 y1 y0 y1 ... (pares); por defecto 2026 2030 2031 2040 2041 2050")
    ap.add_argument("--scenarios", nargs="+", default=rs.PRESENTATION_SCENARIOS)
    ap.add_argument("--ref", default="BAC", help="Escenario de referencia para el diferencial.")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    periods = rs.periods_from_flat_years(args.periods)

    data = compute(periods, args.scenarios)
    if not data:
        raise SystemExit(f"Sin datos para {periods} / {args.scenarios}")

    print("Costo total del sistema acumulado por tramo [BUSD]:")
    for p in periods:
        print(f" {rs.period_label(p)}:")
        ref_total = data.get(p, {}).get(args.ref, {}).get("total")
        for sc in args.scenarios:
            if sc in data.get(p, {}):
                tot = data[p][sc]["total"]
                delta = f"  Δ vs {SCENARIO_ALIAS.get(args.ref, args.ref)}={rs.signed_eu((tot - ref_total) / MUSD_PER_BILLON, 2)}" \
                    if (ref_total is not None and sc != args.ref) else ""
                print(f"  {SCENARIO_ALIAS.get(sc, sc):8s} ({sc}): total={rs.eu(tot / MUSD_PER_BILLON, 2)}{delta}")

    fig = build_figure(data, args.scenarios, periods, ref=args.ref)
    os.makedirs(FIGURES_PRESENTATION_DIR, exist_ok=True)
    base = args.out or os.path.join(FIGURES_PRESENTATION_DIR, f"fig_costo_no_inversion_{periods[0][0]}_{periods[-1][1]}_presentation")
    png = rs.save(fig, base)
    print(f"OK -> {png}")


if __name__ == "__main__":
    main()
