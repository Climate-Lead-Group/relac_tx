"""
fig_seguridad_energetica_2050.py — Seguridad energética por escenario en
2030/2040/2050: participación autóctona vs importada [%] (figura de reporte,
Entregable 2).

Reproduce la lógica regional del chart_12 del dashboard:
  - Fósil/nuclear: combustible consumido (UseByTechnology) por país y fuel,
    repartido importado/autóctono con las cuotas de importación de OLADE
    (load_fossil_import_shares; fallback 1,0 = importado).
  - Renovable: electricidad generada (ProductionByTechnology) por país = autóctona.
  - Autóctono = fósil local + renovable ; Importado = fósil importado.
    Share autóctono = Autóctono / (Autóctono + Importado), agregado regional
    (suma sobre los 19 países) por escenario.

Barras agrupadas por escenario, con una sub-barra apilada (Autóctono /
Importado, normalizada a 100%) por año dentro de cada grupo
(report_style.grouped_bar_layout).

Requiere el balance OLADE:
  "Matriz Balance energético/OLADE - Matriz de balance energético - Anual.xlsx"
(mismo insumo que el dashboard; ver dashboard_config.OLADE_BALANCE_PATH).

Uso:
    python scripts/figures/report/fig_seguridad_energetica_2050.py
    python scripts/figures/report/fig_seguridad_energetica_2050.py --years 2030 2040 2050 --scenarios BAC ISR
"""

from __future__ import annotations

import argparse
import os
import sys

# Solo scripts/ entra en sys.path; todo se importa como paquete (spec 2026-09-16 §3).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from figures.common.dashboard_config import (
    FIGURES_DIR,
    NON_RENEWABLE_CODES,
    RENEWABLE_CODES,
    SCENARIO_ALIAS,
    load_fossil_import_shares,
)
from figures.common import report_style as rs


def compute(years: list[int], scenarios: list[str]) -> dict[int, dict[str, dict]]:
    """{year: {scenario: {'auto','imp','total','pct_auto'}}} agregado regional."""
    df = rs.load(["UseByTechnology", "ProductionByTechnology"], extra_dims=["FUEL"], scenarios=scenarios)
    df = df[(df["YEAR"].isin(years)) & (df["Scenario"].isin(scenarios))].copy()
    df["pref"] = df["TECHNOLOGY"].str[:6]
    df["pais"] = df["TECHNOLOGY"].str[6:9]

    # Fósil: UseByTechnology por país y fuel.
    fos = df[df["pref"].isin(NON_RENEWABLE_CODES)].dropna(subset=["UseByTechnology"])
    fos = fos[fos["UseByTechnology"] != 0].copy()
    fos["fuel"] = fos["FUEL"].astype(str).str[:3]
    fos_g = fos.groupby(["Scenario", "YEAR", "pais", "fuel"])["UseByTechnology"].sum().reset_index()

    shares = load_fossil_import_shares()
    fos_g["imp_share"] = fos_g.apply(
        lambda r: shares.get(r["pais"], {}).get(r["fuel"], 1.0), axis=1
    )
    fos_g["imported"] = fos_g["UseByTechnology"] * fos_g["imp_share"]
    fos_g["local"] = fos_g["UseByTechnology"] - fos_g["imported"]
    fos_agg = fos_g.groupby(["Scenario", "YEAR"])[["imported", "local"]].sum()

    # Renovable: ProductionByTechnology por país -> autóctona.
    ren = df[df["pref"].isin(RENEWABLE_CODES)].dropna(subset=["ProductionByTechnology"])
    ren = ren[ren["ProductionByTechnology"] != 0]
    ren_agg = ren.groupby(["Scenario", "YEAR"])["ProductionByTechnology"].sum()

    out: dict[int, dict[str, dict]] = {}
    for year in years:
        for sc in scenarios:
            key = (sc, year)
            imported = float(fos_agg.at[key, "imported"]) if key in fos_agg.index else 0.0
            local = float(fos_agg.at[key, "local"]) if key in fos_agg.index else 0.0
            renv = float(ren_agg.get(key, 0.0))
            auto = local + renv
            total = auto + imported
            if total <= 0:
                continue
            out.setdefault(year, {})[sc] = {"auto": auto, "imp": imported, "total": total,
                                             "pct_auto": round(auto / total * 100)}
    return out


def build_figure(data: dict, scenarios: list[str], years: list[int]):
    scenarios = [s for s in scenarios if any(s in data.get(y, {}) for y in years)]
    group_centers, sub_positions = rs.grouped_bar_layout(len(scenarios), len(years))

    fig, ax = rs.new_ax(figsize=(9.6, 5.0))
    for yi, year in enumerate(years):
        x = sub_positions[yi]
        auto_pct = [data.get(year, {}).get(s, {}).get("auto", 0.0)
                    / data.get(year, {}).get(s, {}).get("total", 1.0) * 100 for s in scenarios]
        imp_pct = [100.0 - a for a in auto_pct]
        pct_auto = [data.get(year, {}).get(s, {}).get("pct_auto", 0) for s in scenarios]

        ax.bar(x, auto_pct, 0.22, color=rs.COLOR_AUTOCTONO, zorder=3,
               label="Autóctono" if yi == 0 else None)
        ax.bar(x, imp_pct, 0.22, bottom=auto_pct, color=rs.COLOR_IMPORTADO, zorder=3,
               label="Importado" if yi == 0 else None)
        for xi, a, p in zip(x, auto_pct, pct_auto):
            ax.text(xi, a / 2, f"{p}%", ha="center", va="center",
                    fontsize=8, fontweight="bold", color=rs.COLOR_LABEL_ON_BAR)

    ax.set_ylim(0, 100)
    rs.add_year_xticks(ax, years, sub_positions)
    rs.add_group_labels(ax, group_centers, rs.scenario_ticklabels(scenarios))
    rs.apply_report_style(ax, "Participación autóctona [%]")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.1), ncol=2,
              frameon=False, fontsize=9)
    fig.tight_layout()
    return fig


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--years", nargs="+", type=int, default=rs.MULTI_YEARS)
    ap.add_argument("--scenarios", nargs="+", default=rs.CORE_SCENARIOS)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    data = compute(args.years, args.scenarios)
    if not data:
        raise SystemExit(f"Sin datos para {args.years} / {args.scenarios}")

    print(f"Seguridad energética {rs.years_label(args.years)} (participación autóctona):")
    for year in args.years:
        print(f" {year}:")
        for sc in args.scenarios:
            if sc in data.get(year, {}):
                print(f"  {SCENARIO_ALIAS.get(sc, sc):8s} ({sc}): {data[year][sc]['pct_auto']}% autóctono")

    fig = build_figure(data, args.scenarios, args.years)
    os.makedirs(FIGURES_DIR, exist_ok=True)
    base = args.out or os.path.join(FIGURES_DIR, "fig_seguridad_energetica_2050")
    png = rs.save(fig, base)
    print(f"OK -> {png}")


if __name__ == "__main__":
    main()
