"""
fig_costo_unitario_presentation.py — PACK PRESENTACIÓN de
fig_costo_unitario.py. Mismo dato y misma lógica de cómputo; solo cambia
la presentación visual para diapositivas:

  1. Letra más grande (ylabel, ticks, labels de grupo, leyenda, valores).
  2. Escenarios (grupos) más juntos, y menos holgura en los extremos del
     eje X (group_step + rs.set_grouped_xlim).
  3. Leyenda en una sola fila (ya lo estaba: 3 entradas con ncol=3; se deja
     explícito y con letra más grande).
  4. Valor de CADA componente (CAPEX anualizado, O&M, Combustible)
     anotado dentro de su tramo de barra (el original solo mostraba el
     total y el delta vs. referencia), copiando el formato de
     fig_km_lineas_existentes_tmp.py.

Ver fig_costo_unitario.py para la documentación completa del cómputo
(idéntica aquí, sin cambios).

Uso:
    PYTHONUTF8=1 python Figures_Presentation/fig_costo_unitario_presentation.py
    PYTHONUTF8=1 python Figures_Presentation/fig_costo_unitario_presentation.py --years 2030 2040 2050
    PYTHONUTF8=1 python Figures_Presentation/fig_costo_unitario_presentation.py --scenarios BAC ISR --ref BAC
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
from pipeline.Z_AUX_capital_annualization_script import (
    ASSET_LIFETIME,
    DISCOUNT_RATE,
    calculate_crf,
)

COMPONENTS = [
    ("CAPEX anualizado", rs.COLOR_CAPEX),
    ("O&M", rs.COLOR_OM),
    ("Combustible", rs.COLOR_COMBUSTIBLE),
]

# Texto de leyenda (solo visual) para cada componente; por defecto el mismo
# nombre del componente. "CAPEX anualizado" se acorta a "CAPEX" en la
# leyenda -- el dato y el print de consola siguen usando el nombre completo.
LEGEND_LABEL = {"CAPEX anualizado": "CAPEX"}

PJ_PER_TWH = 0.277778  # PJ -> TWh (misma constante que chart_11)


def compute(years: list[int], scenarios: list[str]) -> dict[int, dict[str, dict]]:
    """{year: {scenario: {'CAPEX anualizado','O&M','Combustible','total'}}} (USD/MWh).
    Misma métrica que el chart_11 (ver docstring del script original)."""
    def no_bck(df):
        return df[~df["TECHNOLOGY"].astype(str).str.contains("BCK", na=False)]

    cost_cols = ["CapitalInvestment", "OperatingCost"]
    costs = no_bck(rs.load(cost_cols, scenarios=scenarios))
    costs = costs[costs["Scenario"].isin(scenarios)]
    per = costs.groupby(["Scenario", "YEAR", "TECHNOLOGY"])[cost_cols].max().reset_index()

    pery = per[per["YEAR"].isin(years)].copy()
    pery["TechType"] = pery["TECHNOLOGY"].apply(classify_tech_type)
    is_infra = pery["TechType"].notna()
    op = pery["OperatingCost"].fillna(0)
    pery["O&M"] = op.where(is_infra, 0.0)
    pery["Combustible"] = op.where(~is_infra, 0.0)
    num = pery.groupby(["Scenario", "YEAR"])[["O&M", "Combustible"]].sum()

    crf = calculate_crf(DISCOUNT_RATE, ASSET_LIFETIME)
    inv = per[per["CapitalInvestment"].fillna(0) > 0]
    ann: dict[tuple[str, int], float] = {}
    for y in years:
        window = inv[(inv["YEAR"] > y - ASSET_LIFETIME) & (inv["YEAR"] <= y)]
        for sc, val in window.groupby("Scenario")["CapitalInvestment"].sum().items():
            ann[(sc, y)] = float(val) * crf

    prod = no_bck(rs.load(["ProductionByTechnology"], scenarios=scenarios))
    prod = prod[(prod["YEAR"].isin(years)) & (prod["Scenario"].isin(scenarios))]
    den = prod.groupby(["Scenario", "YEAR"])["ProductionByTechnology"].sum() * PJ_PER_TWH

    out: dict[int, dict[str, dict]] = {}
    for year in years:
        for sc in scenarios:
            key = (sc, year)
            if key not in num.index or key not in den.index:
                continue
            twh = float(den.loc[key])
            if twh <= 0:
                continue
            row = {
                "CAPEX anualizado": ann.get(key, 0.0) / twh,
                "O&M": float(num.at[key, "O&M"]) / twh,
                "Combustible": float(num.at[key, "Combustible"]) / twh,
            }
            row["total"] = sum(row[c] for c, _ in COMPONENTS)
            out.setdefault(year, {})[sc] = row
    return out


def build_figure(data: dict, scenarios: list[str], years: list[int], ref: str = "BAC"):
    scenarios = [s for s in scenarios if any(s in data.get(y, {}) for y in years)]
    group_centers, sub_positions = rs.grouped_bar_layout(
        len(scenarios), len(years), group_step=0.80)

    per_year = []
    all_totals = []
    for year in years:
        totals = [data.get(year, {}).get(s, {}).get("total", 0.0) for s in scenarios]
        ref_total = data.get(year, {}).get(ref, {}).get("total")
        per_year.append((totals, ref_total))
        all_totals += totals
    ymax = max(all_totals) * 1.22 if all_totals else 1.0
    min_label_h = ymax * 0.035  # tramos más finos que esto no llevan etiqueta interna

    fig, ax = rs.new_ax(figsize=(10.4, 5.4))
    for yi, year in enumerate(years):
        x = sub_positions[yi]
        bottoms = [0.0] * len(scenarios)
        for comp, color in COMPONENTS:
            vals = [data.get(year, {}).get(s, {}).get(comp, 0.0) for s in scenarios]
            ax.bar(x, vals, 0.22, bottom=bottoms, color=color, zorder=3,
                   label=LEGEND_LABEL.get(comp, comp) if yi == 0 else "_nolegend_")
            for xi, b, v in zip(x, bottoms, vals):
                if v >= min_label_h:
                    ax.text(xi, b + v / 2, rs.eu(v, 1), ha="center", va="center",
                            fontsize=8.5, color=rs.COLOR_LABEL_ON_BAR, zorder=4)
            bottoms = [b + v for b, v in zip(bottoms, vals)]

        totals, ref_total = per_year[yi]
        for xi, s, tot in zip(x, scenarios, totals):
            ax.text(xi, tot + ymax * 0.015, rs.eu(tot, 1), ha="center", va="bottom",
                    fontsize=9.5, fontweight="bold", color=rs.COLOR_TOTAL)
            if ref_total is not None and s != ref:
                ax.text(xi, tot + ymax * 0.065, f"({rs.signed_eu(tot - ref_total, 1)})",
                        ha="center", va="bottom", fontsize=8.5, fontweight="bold",
                        color=rs.COLOR_COMBUSTIBLE)

    ax.set_ylim(0, ymax)
    rs.set_grouped_xlim(ax, group_centers, len(years))
    rs.add_year_xticks(ax, years, sub_positions, fontsize=9.5)
    rs.add_group_labels(ax, group_centers, rs.scenario_ticklabels(scenarios), fontsize=11)
    rs.apply_report_style(ax, "Costo unitario del sistema [USD/MWh]", european_y=True, fontsize=13)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.12), ncol=len(COMPONENTS),
              frameon=False, fontsize=10.5)
    fig.tight_layout()
    return fig


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--years", nargs="+", type=int, default=rs.MULTI_YEARS)
    ap.add_argument("--scenarios", nargs="+", default=rs.PRESENTATION_SCENARIOS)
    ap.add_argument("--ref", default="BAC", help="Escenario de referencia para el diferencial.")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    data = compute(args.years, args.scenarios)
    if not data:
        raise SystemExit(f"Sin datos de costo para {args.years} / {args.scenarios}")

    print(f"Costo unitario del sistema {rs.years_label(args.years)} [USD/MWh]:")
    for year in args.years:
        print(f" {year}:")
        ref_total = data.get(year, {}).get(args.ref, {}).get("total")
        for sc in args.scenarios:
            if sc in data.get(year, {}):
                d = data[year][sc]
                delta = f"  Δ vs {SCENARIO_ALIAS.get(args.ref, args.ref)}={rs.signed_eu(d['total'] - ref_total, 1)}" \
                    if (ref_total is not None and sc != args.ref) else ""
                comps = "  ".join(f"{c}={rs.eu(d[c], 1)}" for c, _ in COMPONENTS)
                print(f"  {SCENARIO_ALIAS.get(sc, sc):8s} ({sc}): total={rs.eu(d['total'], 1)}  [{comps}]{delta}")

    fig = build_figure(data, args.scenarios, args.years, ref=args.ref)
    os.makedirs(FIGURES_PRESENTATION_DIR, exist_ok=True)
    base = args.out or os.path.join(FIGURES_PRESENTATION_DIR, "fig_costo_unitario_presentation")
    png = rs.save(fig, base)
    print(f"OK -> {png}")


if __name__ == "__main__":
    main()
