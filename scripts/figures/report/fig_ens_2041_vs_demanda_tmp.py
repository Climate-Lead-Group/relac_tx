"""
fig_ens_2041_vs_demanda_tmp.py — SCRIPT TEMPORAL. Razón entre la Energía no
Suministrada (ENS) del año BASE 2041 (valor FIJO por escenario) y la demanda
de cada año, como serie de tiempo 2041–2050 [%]. Una línea por escenario.

Cómputo:
  - Numerador (fijo): ENS del año base = producción del backstop (techs con
    "BCK") vía ProductionByTechnology en PJ, sumada en el año base por
    escenario (mismo cómputo que fig_ens_tmp.py). NO cambia a lo largo de la
    serie. OJO: BAC/OPC no tienen BCK en 2041 (su primer BCK aparece en 2045),
    así que sus líneas salen planas en 0.
  - Denominador (varía por año): demanda final exógena de electricidad =
    SpecifiedAnnualDemand (insumo del modelo, fuels ELC por país) sumada por
    escenario-año en PJ. Idéntica en los 4 escenarios core del snapshot actual.
  - Razón [%] = ENS_base / demanda_año × 100. Ambos en PJ (la conversión a TWh
    se cancela; el print de consola sí reporta la ENS base en TWh).

Uso:
    python scripts/figures/report/fig_ens_2041_vs_demanda_tmp.py
    python scripts/figures/report/fig_ens_2041_vs_demanda_tmp.py --base-year 2041 --years 2041 2042 ... 2050
    python scripts/figures/report/fig_ens_2041_vs_demanda_tmp.py --scenarios BAC ISR
"""

from __future__ import annotations

import argparse
import os
import sys

# Solo scripts/ entra en sys.path; todo se importa como paquete (spec 2026-09-16 §3).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from figures.common.dashboard_config import FIGURES_DIR, SCENARIO_ALIAS
from figures.common import report_style as rs

PJ_PER_TWH = 0.277778  # PJ -> TWh (misma constante que chart_11)

DEFAULT_BASE_YEAR = 2041
DEFAULT_YEARS = list(range(2041, 2051))


def compute(base_year: int, years: list[int], scenarios: list[str]) -> tuple[dict[str, dict[int, float]], dict[str, float]]:
    """({scenario: {año: razón_%}}, {scenario: ENS_base_PJ}).

    Razón = ENS del año base (producción BCK, fija por escenario) / demanda
    exógena (SpecifiedAnnualDemand) de cada año, en %. Escenarios sin BCK en
    el año base entran con ENS 0 (línea plana en 0)."""
    prod = rs.load(["ProductionByTechnology"], scenarios=scenarios)
    prod = prod[(prod["Scenario"].isin(scenarios)) & (prod["YEAR"] == base_year)]
    present = set(prod["Scenario"].unique())
    ens_base = prod[prod["TECHNOLOGY"].astype(str).str.contains("BCK", na=False)] \
        .groupby("Scenario")["ProductionByTechnology"].sum()

    dem = rs.load(["SpecifiedAnnualDemand"], scenarios=scenarios)
    dem = dem[(dem["Scenario"].isin(scenarios)) & (dem["YEAR"].isin(years))]
    dem = dem.dropna(subset=["SpecifiedAnnualDemand"])
    dem_sy = dem.groupby(["Scenario", "YEAR"])["SpecifiedAnnualDemand"].sum()

    out: dict[str, dict[int, float]] = {}
    base_pj: dict[str, float] = {}
    for sc in scenarios:
        if sc not in present:
            continue
        ens_pj = float(ens_base.get(sc, 0.0))
        base_pj[sc] = ens_pj
        for year in years:
            d = float(dem_sy.get((sc, year), 0.0))
            if d <= 0:
                continue
            out.setdefault(sc, {})[year] = ens_pj / d * 100
    return out, base_pj


def build_figure(data: dict, scenarios: list[str], years: list[int], base_year: int):
    scenarios = [s for s in scenarios if s in data]

    fig, ax = rs.new_ax()
    for sc in scenarios:
        ys = [y for y in years if y in data[sc]]
        vals = [data[sc][y] for y in ys]
        label = SCENARIO_ALIAS.get(sc, sc)
        sub = rs.SCENARIO_SUBLABEL.get(sc)
        if sub:
            label = f"{label} · {sub}"
        ax.plot(ys, vals, color=rs.scenario_color(sc), label=label,
                linewidth=2, marker="o", markersize=3.5, zorder=3)

    all_vals = [v for sc in scenarios for v in data[sc].values()]
    ymax = max(all_vals) * 1.15 if all_vals and max(all_vals) > 0 else 1.0
    ax.set_ylim(0, ymax)
    from matplotlib.ticker import FuncFormatter
    ax.yaxis.set_major_formatter(
        FuncFormatter(lambda v, _pos: f"{v:.2f}".replace(".", ",") + "%"))
    ax.set_xticks(years)
    ax.set_xticklabels([str(y) for y in years], fontsize=8, rotation=45, ha="right")

    rs.apply_report_style(ax, f"ENS {base_year} / demanda del año [%]")
    ax.legend(loc="upper right", ncol=2, frameon=False, fontsize=8.5)
    fig.tight_layout()
    return fig


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-year", type=int, default=DEFAULT_BASE_YEAR,
                     help="Año cuya ENS se usa como numerador FIJO (default 2041).")
    ap.add_argument("--years", nargs="+", type=int, default=DEFAULT_YEARS)
    ap.add_argument("--scenarios", nargs="+", default=rs.CORE_SCENARIOS)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    data, base_pj = compute(args.base_year, args.years, args.scenarios)
    if not data:
        raise SystemExit(f"Sin datos para base {args.base_year} / {args.years} / {args.scenarios}")

    print(f"ENS {args.base_year} (fija, producción BCK) / demanda exógena de cada año [%]:")
    for sc in args.scenarios:
        if sc in data:
            ens = base_pj.get(sc, 0.0)
            print(f"  {SCENARIO_ALIAS.get(sc, sc):8s} ({sc}): ENS {args.base_year} = "
                  f"{rs.eu(ens * PJ_PER_TWH, 2)} TWh ({rs.eu(ens, 2)} PJ)")
            traj = "  ".join(f"{y}={rs.eu(data[sc][y], 2)}%" for y in args.years if y in data[sc])
            print(f"           {traj}")

    fig = build_figure(data, args.scenarios, args.years, args.base_year)
    os.makedirs(FIGURES_DIR, exist_ok=True)
    base = args.out or os.path.join(
        FIGURES_DIR, f"fig_ens_{args.base_year}_vs_demanda_{args.years[0]}_{args.years[-1]}_tmp")
    png = rs.save(fig, base)
    print(f"OK -> {png}")


if __name__ == "__main__":
    main()
