"""
fig_capacidad_transmision_2050_tmp.py — TEMPORAL: versión de
fig_capacidad_transmision_2050.py CON la corrección del error del modelo en
las líneas RP. El script original muestra el dato crudo; este aplica el
máximo acumulado (ver abajo) y escribe outputs con sufijo _tmp (no pisa la
figura oficial).

Corrección de un error del modelo: TotalCapacityAnnual de las líneas RP
(grupo RPO) cae en los últimos años de la corrida (desde 2044 en ISR/VSR;
solo en 2050 en BAC/OPC), cuando una línea repotenciada no puede
"des-repotenciarse". Por eso la serie anual agregada de TCA_rpo de cada
escenario se reemplaza por su máximo acumulado (cummax) sobre TODOS los años
del modelo (no solo los mostrados: el pico de BAC ocurre en 2049, que no se
grafica). Esto corrige a la vez Repotenciadas No Planificadas (dejan de
caer) y Existentes (dejan de inflarse, porque restan TCA_rpo). El cummax es
por escenario, sin mezclar escenarios, y no toca PLAN ni NLI.

NOTA (2026-09-02): la caída se observó en el snapshot del CSV de agosto; en
el CSV regenerado el 2026-09-02 ya NO aparece a nivel agregado, así que hoy
este script da lo mismo que el original y el cummax queda como salvaguarda
por si el error reaparece en futuras corridas.

Resto del cómputo idéntico al original (ver su docstring): ecuaciones a
valor nominal con FACTOR_REPOTENCIADAS/FACTOR_EXISTENTES, valores por
tech-año vía max sobre timeslices, cierre exacto del total.

Uso:
    python scripts/figures/report/fig_capacidad_transmision_2050_tmp.py
    python scripts/figures/report/fig_capacidad_transmision_2050_tmp.py --years 2030 2040 2050 --scenarios BAC ISR
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
    classify_line_group,
)
from figures.common import report_style as rs

# Factores fijos de ajuste (ver docstring del script original).
FACTOR_REPOTENCIADAS = 2.25
FACTOR_EXISTENTES = 1.25

# Orden de apilado (de abajo hacia arriba) y color de cada categoría.
CATEGORIES = [
    ("Líneas Existentes", rs.COLOR_LINEAS_EXISTENTES),
    ("Líneas Nuevas Planificadas", rs.COLOR_LINEAS_NUEVAS_PLAN),
    ("Líneas Repotenciadas Planificadas", rs.COLOR_LINEAS_REPO_PLAN),
    ("Líneas Nuevas No Planificadas", rs.COLOR_LINEAS_NUEVAS_NOPLAN),
    ("Líneas Repotenciadas No Planificadas", rs.COLOR_LINEAS_REPO_NOPLAN),
]

_COLS = [
    "AccumulatedNewCapacity",
    "TotalCapacityAnnual",
    "AccumulatedTotalAnnualMinCapacityInvestment",
]


def compute(years: list[int], scenarios: list[str]) -> dict[int, dict[str, dict]]:
    """{year: {scenario: {categoria: GW, ..., 'total': GW}}}."""
    df = rs.load(_COLS, scenarios=scenarios)
    df["LineGroup"] = df["TECHNOLOGY"].apply(classify_line_group)
    df = df[df["LineGroup"].notna()]
    # Se cargan TODOS los años (no solo los mostrados): el cummax de RPO de
    # abajo necesita la serie anual completa para capturar picos en años que
    # no se grafican (p. ej. 2049 en BAC).
    df = df[df["Scenario"].isin(scenarios)]

    per_tech = (
        df.groupby(["Scenario", "YEAR", "TECHNOLOGY", "LineGroup"])[_COLS].max().reset_index()
    )
    g = per_tech.groupby(["Scenario", "YEAR", "LineGroup"], as_index=False)[_COLS].sum()

    # Error del modelo: TCA de las líneas RP cae en los últimos años (ver
    # docstring). Se sostiene el máximo ya alcanzado, por escenario.
    rpo = g["LineGroup"] == "RPO"
    g.loc[rpo, "TotalCapacityAnnual"] = (
        g[rpo].sort_values("YEAR").groupby("Scenario")["TotalCapacityAnnual"].cummax()
    )

    g = g.set_index(["Scenario", "YEAR", "LineGroup"])
    present = set(zip(df["Scenario"], df["YEAR"]))

    out: dict[int, dict[str, dict]] = {}
    for year in years:
        for sc in scenarios:
            if (sc, year) not in present:
                continue

            def val(group: str, col: str) -> float:
                k = (sc, year, group)
                return float(g.at[k, col]) if k in g.index else 0.0

            acc_new_plan = val("PLAN", "AccumulatedNewCapacity")
            tca_plan = val("PLAN", "TotalCapacityAnnual")
            tca_nli = val("NLI", "TotalCapacityAnnual")
            tca_rpo = val("RPO", "TotalCapacityAnnual")
            acc_min_rpo = val("RPO", "AccumulatedTotalAnnualMinCapacityInvestment")

            # Repotenciadas: cálculo original de cada categoría × FACTOR_REPOTENCIADAS.
            repot_plan = acc_min_rpo * FACTOR_REPOTENCIADAS
            repot_noplan = (tca_rpo - acc_min_rpo) * FACTOR_REPOTENCIADAS

            # Existentes: cálculo original menos las repotenciadas originales
            # (Planificadas + No Planificadas = tca_rpo, sin factor) × FACTOR_EXISTENTES.
            existentes = (tca_plan - acc_new_plan) - tca_rpo * FACTOR_EXISTENTES

            cats = {
                "Líneas Existentes": existentes,
                "Líneas Nuevas Planificadas": acc_new_plan,
                "Líneas Repotenciadas Planificadas": repot_plan,
                "Líneas Nuevas No Planificadas": tca_nli,
                "Líneas Repotenciadas No Planificadas": repot_noplan,
            }
            cats["total"] = sum(cats.values())
            out.setdefault(year, {})[sc] = cats
    return out


def build_figure(data: dict, scenarios: list[str], years: list[int]):
    scenarios = [s for s in scenarios if any(s in data.get(y, {}) for y in years)]
    group_centers, sub_positions = rs.grouped_bar_layout(len(scenarios), len(years))

    # Categorías con datos en algún año/escenario mostrado.
    cats = [(n, c) for n, c in CATEGORIES
            if any(abs(data[y][s][n]) > 1e-9 for y in years for s in scenarios if s in data.get(y, {}))]

    all_totals = [data[y][s]["total"] for y in years for s in scenarios if s in data.get(y, {})]
    ymax = max(all_totals) * 1.18 if all_totals else 1.0

    fig, ax = rs.new_ax(figsize=(9.6, 5.2))
    for yi, year in enumerate(years):
        x = sub_positions[yi]
        bottoms = [0.0] * len(scenarios)
        for name, color in cats:
            vals = [data.get(year, {}).get(s, {}).get(name, 0.0) for s in scenarios]
            ax.bar(x, vals, 0.22, bottom=bottoms, color=color, zorder=3,
                   label=name if yi == 0 else None)
            bottoms = [b + v for b, v in zip(bottoms, vals)]

        totals = [data.get(year, {}).get(s, {}).get("total", 0.0) for s in scenarios]
        for xi, tot in zip(x, totals):
            ax.text(xi, tot + ymax * 0.015, rs.eu(tot), ha="center", va="bottom",
                    fontsize=8, fontweight="bold", color=rs.COLOR_TOTAL)

    ax.set_ylim(0, ymax)
    rs.add_year_xticks(ax, years, sub_positions)
    rs.add_group_labels(ax, group_centers, rs.scenario_ticklabels(scenarios))
    rs.apply_report_style(ax, "Capacidad instalada de transmisión [GW]", european_y=True)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.2), ncol=2,
              frameon=False, fontsize=8.5)
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

    print(f"Capacidad instalada de transmisión {rs.years_label(args.years)} [GW] (RP con cummax):")
    for year in args.years:
        print(f" {year}:")
        for sc in args.scenarios:
            if sc in data.get(year, {}):
                d = data[year][sc]
                detail = "  ".join(f"{n}={rs.eu(d[n])}" for n, _ in CATEGORIES
                                   if abs(d[n]) > 1e-9)
                print(f"  {SCENARIO_ALIAS.get(sc, sc):8s} ({sc}): total={rs.eu(d['total'])}  |  {detail}")

    fig = build_figure(data, args.scenarios, args.years)
    os.makedirs(FIGURES_DIR, exist_ok=True)
    base = args.out or os.path.join(FIGURES_DIR, "fig_capacidad_transmision_2050_tmp")
    png = rs.save(fig, base)
    print(f"OK -> {png}")


if __name__ == "__main__":
    main()
