"""
fig_costo_no_inversion_ens_tmp.py — SCRIPT TEMPORAL. Variante de
fig_costo_no_inversion.py que SÍ incluye la Energía no Suministrada (ENS)
en el costo total, sumada DENTRO del componente "Combustible" (sin leyenda
nueva: la figura sigue mostrando CAPEX / O&M / Combustible).

Diferencias de cómputo respecto a fig_costo_no_inversion.py:
  - Nuevo sumando ENS = producción del backstop (techs con "BCK") en PJ
    valorada al VOLL 1.750 USD/MWh (= 1.750/3,6 MUSD/PJ). OJO: NO es el VOLL
    1.500 USD/MWh de chart_14/15 del dashboard; el valor 1.750 fue fijado a
    mano para esta corrida temporal (2026-09-01).
  - La ENS se AGREGA al componente "Combustible" (mismo color/leyenda); el
    total del escenario y el diferencial vs. la referencia la incluyen.
  - El OperatingCost del BCK (penalty big-M artificial) se sigue EXCLUYENDO:
    la ENS se valora solo al VOLL, no al big-M.

Todo lo demás (CAPEX/O&M, ajuste ÷1,2 de PWRTRN/RNWTRN, acumulación por
tramo, unidades en billones de USD) es idéntico a fig_costo_no_inversion.py;
ver ese script para la documentación completa.

Uso:
    python scripts/figures/report/fig_costo_no_inversion_ens_tmp.py
    python scripts/figures/report/fig_costo_no_inversion_ens_tmp.py --periods 2026 2030 2031 2040 2041 2050
    python scripts/figures/report/fig_costo_no_inversion_ens_tmp.py --scenarios BAC ISR --ref BAC
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

# (nombre, color, mostrar_en_leyenda). La ENS va sumada dentro de
# "Combustible": no hay cuarta leyenda.
COMPONENTS = [
    ("CAPEX", rs.COLOR_CAPEX, True),
    ("O&M", rs.COLOR_OM, True),
    ("Combustible", rs.COLOR_COMBUSTIBLE, True),
]

MUSD_PER_BILLON = 1_000_000.0  # 1 billón (10^12 USD) = 1.000.000 MUSD (10^6 USD c/u)

# VOLL fijado a mano para esta variante temporal (NO el 1.500 del dashboard).
VOLL_USD_PER_MWH = 1750.0
VOLL_MUSD_PER_PJ = VOLL_USD_PER_MWH / 3.6  # ≈ 486,1 MUSD/PJ


def compute(periods: list[tuple[int, int]], scenarios: list[str]) -> dict[tuple[int, int], dict[str, dict]]:
    """{periodo: {scenario: {'CAPEX','O&M','Combustible','ENS','total'}}}
    (MUSD) acumulado dentro de cada periodo. Igual que fig_costo_no_inversion.py
    más la ENS (BCK × VOLL), que se suma dentro de 'Combustible'; la clave 'ENS'
    se conserva solo para el print de consola (ya está incluida en Combustible,
    NO volver a sumarla)."""
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

    # ENS: producción del backstop en PJ (suma de timeslices/fuels, como
    # chart_15) valorada al VOLL.
    prod = rs.load(["ProductionByTechnology"], scenarios=scenarios)
    prod = prod[prod["Scenario"].isin(scenarios)]
    bck = prod[prod["TECHNOLOGY"].astype(str).str.contains("BCK", na=False)]

    out: dict[tuple[int, int], dict[str, dict]] = {}
    for p in periods:
        y0, y1 = p
        pper = per[(per["YEAR"] >= y0) & (per["YEAR"] <= y1)]
        infra = pper.groupby("Scenario")[["CAPEX", "O&M", "Combustible"]].sum()
        ens = bck[(bck["YEAR"] >= y0) & (bck["YEAR"] <= y1)] \
            .groupby("Scenario")["ProductionByTechnology"].sum() * VOLL_MUSD_PER_PJ

        for sc in scenarios:
            if sc not in infra.index:
                continue
            row = {c: float(infra.at[sc, c]) for c in ("CAPEX", "O&M", "Combustible")}
            row["ENS"] = float(ens.get(sc, 0.0))
            row["Combustible"] += row["ENS"]
            row["total"] = sum(row[c] for c, _, _ in COMPONENTS)
            out.setdefault(p, {})[sc] = row
    return out


def build_figure(data: dict, scenarios: list[str], periods: list[tuple[int, int]], ref: str = "BAC"):
    scenarios = [s for s in scenarios if any(s in data.get(p, {}) for p in periods)]
    group_centers, sub_positions = rs.grouped_bar_layout(len(scenarios), len(periods))

    per_period = []
    all_totals = []
    for p in periods:
        totals = [data.get(p, {}).get(s, {}).get("total", 0.0) / MUSD_PER_BILLON for s in scenarios]
        ref_total = data.get(p, {}).get(ref, {}).get("total")
        ref_total = ref_total / MUSD_PER_BILLON if ref_total is not None else None
        per_period.append((totals, ref_total))
        all_totals += totals
    ymax = max(all_totals) * 1.2 if all_totals else 1.0

    fig, ax = rs.new_ax(figsize=(9.6, 5.2))
    for pi, p in enumerate(periods):
        x = sub_positions[pi]
        bottoms = [0.0] * len(scenarios)
        for comp, color, show_legend in COMPONENTS:
            vals = [data.get(p, {}).get(s, {}).get(comp, 0.0) / MUSD_PER_BILLON for s in scenarios]
            label = comp if (show_legend and pi == 0) else "_nolegend_"
            ax.bar(x, vals, 0.22, bottom=bottoms, color=color, label=label, zorder=3)
            bottoms = [b + v for b, v in zip(bottoms, vals)]

        totals, ref_total = per_period[pi]
        for xi, s, tot in zip(x, scenarios, totals):
            ax.text(xi, tot + ymax * 0.015, rs.eu(tot, 2), ha="center", va="bottom",
                    fontsize=7.5, fontweight="bold", color=rs.COLOR_TOTAL)
            if ref_total is not None and s != ref:
                delta = tot - ref_total
                ax.text(xi, tot + ymax * 0.08, f"({rs.signed_eu(delta, 2)})", ha="center",
                        va="bottom", fontsize=7, fontweight="bold", color=rs.COLOR_COMBUSTIBLE)

    ax.set_ylim(0, ymax)
    rs.add_group_xticks(ax, [rs.period_label(p) for p in periods], sub_positions,
                         fontsize=7.5, rotation=45)
    rs.add_group_labels(ax, group_centers, rs.scenario_ticklabels(scenarios), y=-0.22)
    rs.apply_report_style(ax, "Costo total del sistema incl. ENS, acumulado por tramo [BUSD]",
                          european_y=True)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.14), ncol=3,
              frameon=False, fontsize=8.5)
    fig.tight_layout()
    return fig


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--periods", nargs="+", type=int, default=None,
                     help="Años y0 y1 y0 y1 ... (pares); por defecto 2026 2030 2031 2040 2041 2050")
    ap.add_argument("--scenarios", nargs="+", default=rs.CORE_SCENARIOS)
    ap.add_argument("--ref", default="BAC", help="Escenario de referencia para el diferencial.")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    periods = rs.periods_from_flat_years(args.periods)

    data = compute(periods, args.scenarios)
    if not data:
        raise SystemExit(f"Sin datos para {periods} / {args.scenarios}")

    print(f"Costo total del sistema acumulado por tramo [BUSD] — ENS (VOLL {rs.eu(VOLL_USD_PER_MWH, 0)} USD/MWh) incluida en Combustible:")
    for p in periods:
        print(f" {rs.period_label(p)}:")
        ref_total = data.get(p, {}).get(args.ref, {}).get("total")
        for sc in args.scenarios:
            if sc in data.get(p, {}):
                d = data[p][sc]
                tot = d["total"]
                delta = f"  Δ vs {SCENARIO_ALIAS.get(args.ref, args.ref)}={rs.signed_eu((tot - ref_total) / MUSD_PER_BILLON, 2)}" \
                    if (ref_total is not None and sc != args.ref) else ""
                print(f"  {SCENARIO_ALIAS.get(sc, sc):8s} ({sc}): total={rs.eu(tot / MUSD_PER_BILLON, 2)}"
                      f"  [ENS dentro de Combustible={rs.eu(d['ENS'] / MUSD_PER_BILLON, 3)}]{delta}")

    fig = build_figure(data, args.scenarios, periods, ref=args.ref)
    os.makedirs(FIGURES_DIR, exist_ok=True)
    base = args.out or os.path.join(FIGURES_DIR, f"fig_costo_no_inversion_ens_{periods[0][0]}_{periods[-1][1]}_tmp")
    png = rs.save(fig, base)
    print(f"OK -> {png}")


if __name__ == "__main__":
    main()
