"""
fig_costo_unitario.py — Costo unitario del sistema por escenario en
2030/2040/2050 [USD/MWh] (figura de reporte, Entregable 2).

Equivalente estático, en estilo de reporte, del "chart11 – Costo Anualizado por
Energía [MUSD/TWh]" de build_dashboard_nonsupplied.py, filtrado a un set de años
y a los 4 escenarios core. Lee del mismo oráculo que el dashboard
(RELAC_TX_Combined_Inputs_Outputs.csv via dashboard_config) — NO es un recorte
manual del dashboard.

Métrica por (escenario, año):
  Costo unitario = (CAPEX anualizado + O&M + Combustible) / Producción total
donde:
  - CAPEX anualizado se calcula AL VUELO desde CapitalInvestment con la misma
    matemática de Z_AUX_capital_annualization_script.py (CRF con DISCOUNT_RATE
    6,39% y ASSET_LIFETIME 15 años, importados de ese script para evitar
    drift): pago anual = inversión×CRF, acumulando en el año Y los pagos de
    las inversiones de los años [Y-14, Y]. OJO: NO se usa la columna
    CapitalInvestmentAnnualized del CSV porque en el snapshot regenerado el
    2026-08-14 está vacía (toda en 0) — el chart_11 del dashboard, que sí la
    lee, subestima el costo en ese snapshot.
  - O&M / Combustible = OperatingCost, separado con classify_tech_type: techs de
    infraestructura (Generación/Transmisión/Almacenamiento) -> O&M; el resto
    (techs de suministro de combustible) -> Combustible. La suma de los tres
    componentes reproduce el ratio del chart_11.
  - Producción = SUM(ProductionByTechnology)·0,277778 [TWh], todas las techs.
  - Se EXCLUYE el backstop (BCK) de numerador y denominador: su OperatingCost es
    el penalty big-M artificial y su producción es energía NO suministrada;
    incluirlo distorsiona el ratio (mismo criterio que chart_11).
  - Mismo gotcha de max() por tech-año en los costos (valor repetido por fila).

Unidades: USD/MWh (numéricamente idéntico a MUSD/TWh: 10^6 USD / 10^6 MWh).

Uso:
    python scripts/figures/report/fig_costo_unitario.py
    python scripts/figures/report/fig_costo_unitario.py --years 2030 2040 2050
    python scripts/figures/report/fig_costo_unitario.py --scenarios BAC ISR --ref BAC
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

PJ_PER_TWH = 0.277778  # PJ -> TWh (misma constante que chart_11)


def compute(years: list[int], scenarios: list[str]) -> dict[int, dict[str, dict]]:
    """{year: {scenario: {'CAPEX anualizado','O&M','Combustible','total'}}} (USD/MWh).
    Misma métrica que el chart_11, con OperatingCost desglosado en O&M /
    Combustible vía classify_tech_type (como fig_costo_no_inversion) y el CAPEX
    anualizado recalculado al vuelo (ver docstring del módulo)."""
    def no_bck(df):
        return df[~df["TECHNOLOGY"].astype(str).str.contains("BCK", na=False)]

    # Costos SIN filtrar por año: el CAPEX anualizado de un año objetivo acumula
    # pagos de inversiones de hasta ASSET_LIFETIME-1 años atrás.
    cost_cols = ["CapitalInvestment", "OperatingCost"]
    costs = no_bck(rs.load(cost_cols, scenarios=scenarios))
    costs = costs[costs["Scenario"].isin(scenarios)]
    per = costs.groupby(["Scenario", "YEAR", "TECHNOLOGY"])[cost_cols].max().reset_index()

    # O&M / Combustible: solo los años objetivo.
    pery = per[per["YEAR"].isin(years)].copy()
    pery["TechType"] = pery["TECHNOLOGY"].apply(classify_tech_type)
    is_infra = pery["TechType"].notna()
    op = pery["OperatingCost"].fillna(0)
    pery["O&M"] = op.where(is_infra, 0.0)
    pery["Combustible"] = op.where(~is_infra, 0.0)
    num = pery.groupby(["Scenario", "YEAR"])[["O&M", "Combustible"]].sum()

    # CAPEX anualizado (misma matemática que Z_AUX_capital_annualization_script):
    # en el año Y se pagan las anualidades (inversión×CRF) de las inversiones
    # hechas en los años [Y-ASSET_LIFETIME+1, Y].
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
    group_centers, sub_positions = rs.grouped_bar_layout(len(scenarios), len(years))

    per_year = []
    all_totals = []
    for year in years:
        totals = [data.get(year, {}).get(s, {}).get("total", 0.0) for s in scenarios]
        ref_total = data.get(year, {}).get(ref, {}).get("total")
        per_year.append((totals, ref_total))
        all_totals += totals
    ymax = max(all_totals) * 1.2 if all_totals else 1.0

    fig, ax = rs.new_ax(figsize=(9.6, 5.0))
    for yi, year in enumerate(years):
        x = sub_positions[yi]
        bottoms = [0.0] * len(scenarios)
        for comp, color in COMPONENTS:
            vals = [data.get(year, {}).get(s, {}).get(comp, 0.0) for s in scenarios]
            ax.bar(x, vals, 0.22, bottom=bottoms, color=color, zorder=3,
                   label=comp if yi == 0 else "_nolegend_")
            bottoms = [b + v for b, v in zip(bottoms, vals)]

        totals, ref_total = per_year[yi]
        for xi, s, tot in zip(x, scenarios, totals):
            ax.text(xi, tot + ymax * 0.015, rs.eu(tot, 1), ha="center", va="bottom",
                    fontsize=7.5, fontweight="bold", color=rs.COLOR_TOTAL)
            if ref_total is not None and s != ref:
                ax.text(xi, tot + ymax * 0.065, f"({rs.signed_eu(tot - ref_total, 1)})",
                        ha="center", va="bottom", fontsize=7, fontweight="bold",
                        color=rs.COLOR_COMBUSTIBLE)

    ax.set_ylim(0, ymax)
    rs.add_year_xticks(ax, years, sub_positions)
    rs.add_group_labels(ax, group_centers, rs.scenario_ticklabels(scenarios))
    rs.apply_report_style(ax, "Costo unitario del sistema [USD/MWh]", european_y=True)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.12), ncol=3,
              frameon=False, fontsize=8.5)
    fig.tight_layout()
    return fig


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--years", nargs="+", type=int, default=rs.MULTI_YEARS)
    ap.add_argument("--scenarios", nargs="+", default=rs.CORE_SCENARIOS)
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
    os.makedirs(FIGURES_DIR, exist_ok=True)
    base = args.out or os.path.join(FIGURES_DIR, "fig_costo_unitario")
    png = rs.save(fig, base)
    print(f"OK -> {png}")


if __name__ == "__main__":
    main()
