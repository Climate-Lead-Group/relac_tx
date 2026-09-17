"""
fig_km_lineas_existentes_tmp.py — TEMPORAL. Igual que fig_km_lineas_acumulados.py
(km de líneas acumulados desde `y0` hasta 2030/2040/2050 por escenario) pero:

  1. Añade la serie "Líneas Existentes":
       km_exist(año) = Σ (ResidualCapacity(año) / Capacity) × Distancia,
       sobre PWRTRN* + RNWTRN* (mismos techs que "Líneas Planificadas").
     ResidualCapacity es un STOCK que decae con el tiempo, así que se toma su
     valor EN el año de la barra (no se acumula en la ventana [y0, año]).
     Distancia RNW para RNW*, NRNW para PWR/TRN; Capacity/Distancia de
     CapacityAndDistances.xlsx (por Scenario+país).
  2. Etiqueta el valor de CADA componente dentro de su tramo de barra (además
     del total encima) para comparar componentes entre escenarios/años.
  3. Imprime una tabla larga (año, escenario, componente, km) en consola y la
     exporta a CSV junto a la figura.

Las otras 3 series conservan la fórmula del script original:
  Planificadas         Σ (NewCapacity/Capacity)·Dist, PWRTRN* + RNWTRN*
  Nuevas No Plan.      Σ (NewCapacity/Capacity)·Dist, RNWNLI* + TRNNLI*
  Repotenciadas No Pl. Σ (NewCapacity/Capacity)·Dist·1,25, RNWRPO* + TRNRPO*
(acumuladas en [y0, año], NewCapacity por tech-año = max sobre timeslices).

Uso:
    PYTHONUTF8=1 python fig_km_lineas_existentes_tmp.py
    PYTHONUTF8=1 python fig_km_lineas_existentes_tmp.py --y0 2026 --years 2030 2040 2050 --scenarios BAC ISR
"""

from __future__ import annotations

import argparse
import os
import sys

# Solo scripts/ entra en sys.path; todo se importa como paquete (spec 2026-09-16 §3).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd

from figures.common.dashboard_config import (
    FIGURES_DIR,
    COUNTRY_ISO3_BY_NAME,
    SCENARIO_ALIAS,
    classify_line_group_raw,
    classify_tech_type,
    load_capacity_and_distances,
)
from figures.common import report_style as rs

EXISTENTES = "Líneas Existentes"

# Orden de apilado (de abajo hacia arriba) y color de cada grupo de línea.
CATEGORIES = [
    (EXISTENTES, rs.COLOR_LINEAS_EXISTENTES),
    ("Líneas Planificadas", rs.COLOR_LINEAS_PLANIFICADAS),
    ("Líneas Nuevas No Planificadas", rs.COLOR_LINEAS_NUEVAS_NOPLAN),
    ("Líneas Repotenciadas No Planificadas", rs.COLOR_LINEAS_REPO_NOPLAN),
]

# ISO3 -> nombre de país (el xlsx de capacidades/distancias usa el nombre).
_COUNTRY_NAMES = {iso3: name for name, iso3 in COUNTRY_ISO3_BY_NAME.items()}


def _km_table(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    """Filtra techs de Transmisión, cruza con Capacity/Distancia y calcula km.

    Devuelve filas (Scenario, YEAR, TECHNOLOGY, Country, LG, km); el valor por
    tech-año es el max sobre timeslices (gotcha del dashboard).
    """
    df = df[df["TECHNOLOGY"].apply(classify_tech_type) == "Transmisión"].copy()
    df["Country"] = df["TECHNOLOGY"].str[6:9].map(_COUNTRY_NAMES)
    per = (
        df.groupby(["Scenario", "YEAR", "TECHNOLOGY", "Country"])[value_col]
        .max()
        .reset_index()
        .dropna(subset=[value_col, "Country"])
    )
    per = per.merge(load_capacity_and_distances(), on=["Scenario", "Country"], how="inner")

    is_rnw = per["TECHNOLOGY"].str.startswith("RNW")
    dist = per["Distance RNW"].where(is_rnw, per["Distance NRNW"])
    factor = per["TECHNOLOGY"].str.contains("RPO", regex=False).map({True: 1.25, False: 1.0})
    per["km"] = (per[value_col] / per["Capacity"]) * dist * factor
    per["LG"] = per["TECHNOLOGY"].apply(classify_line_group_raw)
    return per[per["LG"].notna()]


def compute(y0: int, years: list[int], scenarios: list[str]) -> dict[int, dict[str, dict]]:
    """{year: {scenario: {grupo: km, ..., 'total': km}}}.

    Grupos NewCapacity: acumulado en [y0, year]. Existentes: ResidualCapacity en `year`.
    """
    y1 = max(years)
    df = rs.load(["NewCapacity", "ResidualCapacity"], scenarios=scenarios)
    df = df[(df["YEAR"] >= y0) & (df["YEAR"] <= y1) & (df["Scenario"].isin(scenarios))]

    new = _km_table(df.dropna(subset=["NewCapacity"]), "NewCapacity")
    res = _km_table(df.dropna(subset=["ResidualCapacity"]), "ResidualCapacity")
    res = res[res["LG"] == "Líneas Planificadas"]  # PWRTRN* + RNWTRN*

    out: dict[int, dict[str, dict]] = {}
    for year in years:
        g_new = (new[new["YEAR"] <= year].groupby(["Scenario", "LG"])["km"].sum()
                 .unstack(fill_value=0.0))
        g_res = res[res["YEAR"] == year].groupby("Scenario")["km"].sum()
        for sc in scenarios:
            if sc not in g_new.index and sc not in g_res.index:
                continue
            row = {}
            for name, _ in CATEGORIES:
                if name == EXISTENTES:
                    row[name] = float(g_res.get(sc, 0.0))
                else:
                    row[name] = float(g_new.at[sc, name]) if (sc in g_new.index and name in g_new.columns) else 0.0
            row["total"] = sum(row[name] for name, _ in CATEGORIES)
            out.setdefault(year, {})[sc] = row
    return out


def build_figure(data: dict, scenarios: list[str], y0: int, years: list[int]):
    scenarios = [s for s in scenarios if any(s in data.get(y, {}) for y in years)]
    group_centers, sub_positions = rs.grouped_bar_layout(len(scenarios), len(years))

    cats = [(n, c) for n, c in CATEGORIES
            if any(data[y][s][n] > 1e-9 for y in years for s in scenarios if s in data.get(y, {}))]
    all_totals = [data[y][s]["total"] for y in years for s in scenarios if s in data.get(y, {})]
    ymax = max(all_totals) * 1.16 if all_totals else 1.0
    min_label_h = ymax * 0.035  # tramos más finos que esto no llevan etiqueta interna

    fig, ax = rs.new_ax(figsize=(11.0, 5.6))
    for yi, year in enumerate(years):
        x = sub_positions[yi]
        bottoms = [0.0] * len(scenarios)
        for name, color in cats:
            vals = [data.get(year, {}).get(s, {}).get(name, 0.0) for s in scenarios]
            ax.bar(x, vals, 0.22, bottom=bottoms, color=color, zorder=3,
                   label=name if yi == 0 else None)
            for xi, b, v in zip(x, bottoms, vals):
                if v >= min_label_h:
                    ax.text(xi, b + v / 2, rs.eu(v), ha="center", va="center",
                            fontsize=6.5, color=rs.COLOR_LABEL_ON_BAR, zorder=4)
            bottoms = [b + v for b, v in zip(bottoms, vals)]

        totals = [data.get(year, {}).get(s, {}).get("total", 0.0) for s in scenarios]
        for xi, tot in zip(x, totals):
            ax.text(xi, tot + ymax * 0.015, rs.eu(tot), ha="center", va="bottom",
                    fontsize=8, fontweight="bold", color=rs.COLOR_TOTAL)

    ax.set_ylim(0, ymax)
    rs.add_year_xticks(ax, years, sub_positions)
    rs.add_group_labels(ax, group_centers, rs.scenario_ticklabels(scenarios))
    rs.apply_report_style(
        ax, f"Kilómetros de líneas: existentes (en el año) + acumulados desde {y0} [km]",
        european_y=True)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.16), ncol=2,
              frameon=False, fontsize=8.5)
    fig.tight_layout()
    return fig


def to_long_table(data: dict, scenarios: list[str], years: list[int]) -> pd.DataFrame:
    rows = []
    for year in years:
        for sc in scenarios:
            if sc not in data.get(year, {}):
                continue
            d = data[year][sc]
            for name, _ in CATEGORIES:
                rows.append({"year": year, "scenario": sc, "alias": SCENARIO_ALIAS.get(sc, sc),
                             "componente": name, "km": d[name],
                             "share_total": d[name] / d["total"] if d["total"] else 0.0})
            rows.append({"year": year, "scenario": sc, "alias": SCENARIO_ALIAS.get(sc, sc),
                         "componente": "TOTAL", "km": d["total"], "share_total": 1.0})
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--y0", type=int, default=2026)
    ap.add_argument("--years", nargs="+", type=int, default=rs.MULTI_YEARS)
    ap.add_argument("--scenarios", nargs="+", default=rs.CORE_SCENARIOS)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    data = compute(args.y0, args.years, args.scenarios)
    if not data:
        raise SystemExit(f"Sin datos para {args.y0}-{args.years} / {args.scenarios}")

    # Tabla por componente: filas = componente, columnas = escenario (una por año).
    print(f"Kilómetros de líneas [km] — existentes en el año + acumulados desde {args.y0}:")
    for year in args.years:
        scs = [s for s in args.scenarios if s in data.get(year, {})]
        print(f"\n hasta {year}:")
        hdr = f"  {'componente':40s}" + "".join(f"{SCENARIO_ALIAS.get(s, s) + ' (' + s + ')':>18s}" for s in scs)
        print(hdr)
        for name, _ in CATEGORIES + [("total", None)]:
            print(f"  {name:40s}" + "".join(f"{rs.eu(data[year][s][name]):>18s}" for s in scs))

    fig = build_figure(data, args.scenarios, args.y0, args.years)
    os.makedirs(FIGURES_DIR, exist_ok=True)
    base = args.out or os.path.join(
        FIGURES_DIR, f"fig_km_lineas_existentes_tmp_{args.y0}_{max(args.years)}")
    png = rs.save(fig, base)
    csv_path = base + ".csv"
    to_long_table(data, args.scenarios, args.years).to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\nOK -> {png}\nOK -> {csv_path}")


if __name__ == "__main__":
    main()
