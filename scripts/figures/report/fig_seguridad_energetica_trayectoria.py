"""
fig_seguridad_energetica_trayectoria.py — Energía autóctona / seguridad
energética [%] por escenario, trayectoria 2025–2050 (figura de reporte,
Entregable 2).

Gráfico de LÍNEAS (una por escenario, paleta del reporte rs.SCENARIO_COLORS)
con la participación autóctona agregada regional año a año (2025–2050).
Misma métrica que fig_seguridad_energetica_2050.py (versión barra, agrupada
por escenario y año 2030/2040/2050), réplica de la lógica regional del
chart_12 del dashboard:
  - Fósil/nuclear: combustible consumido (UseByTechnology) por país y fuel,
    repartido importado/autóctono con las cuotas de importación de OLADE
    (load_fossil_import_shares; fallback 1,0 = importado).
  - Renovable: electricidad generada (ProductionByTechnology) por país = autóctona.
  - Share autóctono = (fósil local + renovable) / (idem + fósil importado),
    agregado regional por escenario-año.

Requiere el balance OLADE (dashboard_config.OLADE_BALANCE_PATH).

Uso:
    python scripts/figures/report/fig_seguridad_energetica_trayectoria.py
    python scripts/figures/report/fig_seguridad_energetica_trayectoria.py --years 2025 2030 2035 2040 2045 2050
"""

from __future__ import annotations

import argparse
import os
import sys

# Solo scripts/ entra en sys.path; todo se importa como paquete (spec 2026-09-16 §3).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from figures.common.dashboard_config import (
    FIGURES_DIR,
    ALL_YEARS,
    NON_RENEWABLE_CODES,
    RENEWABLE_CODES,
    SCENARIO_ALIAS,
    load_fossil_import_shares,
)
from figures.common import report_style as rs

# Todos los años del horizonte desde 2025 (2023-2024 se excluyen: calibración).
DEFAULT_YEARS = [y for y in ALL_YEARS if y >= 2025]


def compute(years: list[int], scenarios: list[str]) -> dict[str, dict[int, float]]:
    """{scenario: {año: % autóctono}} agregado regional."""
    df = rs.load(["UseByTechnology", "ProductionByTechnology"], extra_dims=["FUEL"], scenarios=scenarios)
    df = df[(df["YEAR"].isin(years)) & (df["Scenario"].isin(scenarios))].copy()
    df["pref"] = df["TECHNOLOGY"].str[:6]
    df["pais"] = df["TECHNOLOGY"].str[6:9]

    # Fósil: UseByTechnology por país y fuel, repartido con cuotas OLADE.
    fos = df[df["pref"].isin(NON_RENEWABLE_CODES)].dropna(subset=["UseByTechnology"])
    fos = fos[fos["UseByTechnology"] != 0].copy()
    fos["fuel"] = fos["FUEL"].astype(str).str[:3]
    fos_g = (
        fos.groupby(["Scenario", "YEAR", "pais", "fuel"])["UseByTechnology"]
        .sum()
        .reset_index()
    )
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

    out: dict[str, dict[int, float]] = {}
    for sc in scenarios:
        for year in years:
            key = (sc, year)
            imported = float(fos_agg.at[key, "imported"]) if key in fos_agg.index else 0.0
            local = float(fos_agg.at[key, "local"]) if key in fos_agg.index else 0.0
            renv = float(ren_agg.get(key, 0.0))
            auto = local + renv
            total = auto + imported
            if total <= 0:
                continue
            out.setdefault(sc, {})[year] = auto / total * 100
    return out


def build_figure(data: dict, scenarios: list[str], years: list[int]):
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

    # Eje Y fino (cada 2 pp) y eje X con TODOS los años, rotados.
    all_vals = [v for sc in scenarios for v in data[sc].values()]
    lo = (int(min(all_vals)) // 2) * 2 - 2
    hi = -(-int(max(all_vals)) // 2) * 2 + 2
    ax.set_ylim(lo, hi)
    from matplotlib.ticker import FuncFormatter, MultipleLocator
    ax.yaxis.set_major_locator(MultipleLocator(2))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _pos: f"{v:.0f}%"))
    ax.set_xticks(years)
    ax.set_xticklabels([str(y) for y in years], fontsize=8, rotation=45, ha="right")

    rs.apply_report_style(ax, "Energía autóctona / seguridad energética [%]")
    ax.legend(loc="upper left", ncol=2, frameon=False, fontsize=8.5)
    fig.tight_layout()
    return fig


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--years", nargs="+", type=int, default=DEFAULT_YEARS)
    ap.add_argument("--scenarios", nargs="+", default=rs.CORE_SCENARIOS)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    data = compute(args.years, args.scenarios)
    if not data:
        raise SystemExit(f"Sin datos para {args.years} / {args.scenarios}")

    print("Energía autóctona / seguridad energética [%]:")
    for sc in args.scenarios:
        if sc in data:
            traj = "  ".join(f"{y}={data[sc][y]:.1f}%" for y in args.years if y in data[sc])
            print(f"  {SCENARIO_ALIAS.get(sc, sc):8s} ({sc}): {traj}")

    fig = build_figure(data, args.scenarios, args.years)
    os.makedirs(FIGURES_DIR, exist_ok=True)
    base = args.out or os.path.join(FIGURES_DIR, "fig_seguridad_energetica_trayectoria")
    png = rs.save(fig, base)
    print(f"OK -> {png}")


if __name__ == "__main__":
    main()
