"""
fig_floor_effect.py  --  read-only. Renders the before/after effect of the
dispatch-floor fix as a 3-panel figure.

Data sources:
  - Baseline (pre-floor) combined inputs+outputs CSV: repo root
    RELAC_TX_StorageDelay_Combined_Inputs_Outputs_2026-06-19.csv (~404 MB).
  - Floored (post-floor) combined inputs+outputs CSV: Andrey's solved run at
    fix_dispatch_solved/solved_FLOORED/RELAC_TX_FLOORED_Combined_Inputs_Outputs.csv
    (BAU + OPT only; INV/VGB were not solved in this run).
  - "Before" activity floor (TotalTechnologyAnnualActivityLowerLimit): parsed
    from the original preprocessed MathProg txt via relac_io (authoritative
    source, confirms it ends at 2026 -- that is the bug this fix addresses).
  - "After" activity floor: no *_FLOORED.txt copy exists on disk (Andrey solved
    from a floored otoole CSV, not a floored txt), so the after-floor is read
    from fix_dispatch_solved/solved_FLOORED/RELAC_TX_FLOORED_Inputs.csv, the
    actual floored inputs-only CSV used for the solve. Same parameter, same
    values as what write_floors.py would have put in a _FLOORED.txt; this is
    just the CSV form of the same input.
  - Working-set forced capacity (forced_GW) and contracted_CF: candidate_floors.csv.

No model input is written. Only fig_floor_effect.png and cache/*.parquet.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import relac_io as io

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BASELINE_COMBINED = REPO / "RELAC_TX_StorageDelay_Combined_Inputs_Outputs_2026-06-19.csv"
FLOORED_COMBINED = REPO / "fix_dispatch" / "solved_FLOORED" / "RELAC_TX_FLOORED_Combined_Inputs_Outputs.csv"
FLOORED_INPUTS = REPO / "fix_dispatch" / "solved_FLOORED" / "RELAC_TX_FLOORED_Inputs.csv"
CANDIDATES_CSV = HERE / "candidate_floors.csv"
OUT_PNG = HERE / "fig_floor_effect.png"

C2A = io.C2A_DEFAULT
FIRST_YEAR, LAST_YEAR = 2023, 2050
SCENARIOS = ["BAU", "OPT"]

DARK, TEAL, AMBER, GOLD, SLATE = "#00414D", "#23978E", "#C9622E", "#E0A82E", "#5A7682"

plt.rcParams["font.family"] = "DejaVu Sans"


# --------------------------------------------------------------------------- #
# tech classification
# --------------------------------------------------------------------------- #
def is_dispatchable(tech: str) -> bool:
    p = io.parse_tech(tech)
    return p["is_fossil"] or p["is_nuclear"]


# --------------------------------------------------------------------------- #
# data loaders
# --------------------------------------------------------------------------- #
def load_activity(csv_path: Path, tag: str) -> pd.DataFrame:
    """TotalTechnologyAnnualActivity, all techs, Scenario/TECHNOLOGY/YEAR/VALUE."""
    ext = io.extract_combined(["TotalTechnologyAnnualActivity"], csv_path=csv_path, cache_tag=tag)
    df = ext["TotalTechnologyAnnualActivity"]
    return df[["Scenario", "TECHNOLOGY", "YEAR", "VALUE"]].copy()


def load_original_lowerlimit() -> pd.DataFrame:
    """Original (pre-floor) TotalTechnologyAnnualActivityLowerLimit, BAU+OPT, from the txt."""
    frames = []
    for scen in SCENARIOS:
        mp = io.parse_mathprog(scen, ["TotalTechnologyAnnualActivityLowerLimit"])
        df = mp["TotalTechnologyAnnualActivityLowerLimit"]
        if len(df):
            df = df.copy()
            df["Scenario"] = scen
            frames.append(df[["Scenario", "TECHNOLOGY", "YEAR", "VALUE"]])
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["Scenario", "TECHNOLOGY", "YEAR", "VALUE"])


def load_floored_lowerlimit() -> pd.DataFrame:
    """Post-floor TotalTechnologyAnnualActivityLowerLimit, BAU+OPT, from the floored inputs CSV."""
    ext = io.extract_combined(["TotalTechnologyAnnualActivityLowerLimit"],
                              csv_path=FLOORED_INPUTS, cache_tag="floored_inputs_lowerlimit")
    df = ext["TotalTechnologyAnnualActivityLowerLimit"]
    return df[["Scenario", "TECHNOLOGY", "YEAR", "VALUE"]].copy()


def load_candidates() -> pd.DataFrame:
    cand = pd.read_csv(CANDIDATES_CSV, comment="#")
    return cand[cand.Scenario.isin(SCENARIOS)].copy()


# --------------------------------------------------------------------------- #
# panel data builders
# --------------------------------------------------------------------------- #
def panel_a_series(baseline_act: pd.DataFrame, floored_act: pd.DataFrame) -> dict:
    def yearly_dispatchable_sum(df: pd.DataFrame, scen: str) -> pd.Series:
        sub = df[(df.Scenario == scen) & (df.TECHNOLOGY.map(is_dispatchable))]
        return sub.groupby("YEAR")["VALUE"].sum()

    return dict(
        bau_before=yearly_dispatchable_sum(baseline_act, "BAU"),
        opt_before=yearly_dispatchable_sum(baseline_act, "OPT"),
        bau_after=yearly_dispatchable_sum(floored_act, "BAU"),
        opt_after=yearly_dispatchable_sum(floored_act, "OPT"),
    )


def panel_b_series(orig_ll: pd.DataFrame, floored_ll: pd.DataFrame) -> dict:
    def yearly_dispatchable_sum(df: pd.DataFrame, scen: str) -> pd.Series:
        if len(df) == 0:
            return pd.Series(dtype=float)
        sub = df[(df.Scenario == scen) & (df.TECHNOLOGY.map(is_dispatchable))]
        return sub.groupby("YEAR")["VALUE"].sum()

    bau_bef = yearly_dispatchable_sum(orig_ll, "BAU")
    opt_bef = yearly_dispatchable_sum(orig_ll, "OPT")
    # before the fix BAU and OPT floors are identical (scenario symmetry); combine
    before = bau_bef.combine_first(opt_bef)
    return dict(
        before=before,
        bau_after=yearly_dispatchable_sum(floored_ll, "BAU"),
        opt_after=yearly_dispatchable_sum(floored_ll, "OPT"),
    )


def panel_c_data(baseline_act: pd.DataFrame, floored_act: pd.DataFrame, cand: pd.DataFrame,
                  snapshot_year: int = LAST_YEAR) -> pd.DataFrame:
    # all 11 working-set techs are forced under OPT; use OPT for a single
    # consistent scenario across every plant (BAU only forces 2 of the 11).
    # A single terminal-year (2050) snapshot is used rather than an average
    # over the whole floor window: some plants have an early anomalous high-
    # activity year unrelated to the floor (see the artifact-verification
    # report), which would skew a multi-year average. By 2050 every plant is
    # well past commissioning and at steady state.
    scen = "OPT"
    base_lookup = {(r.TECHNOLOGY, int(r.YEAR)): r.VALUE
                   for r in baseline_act[baseline_act.Scenario == scen].itertuples(index=False)}
    floor_lookup = {(r.TECHNOLOGY, int(r.YEAR)): r.VALUE
                    for r in floored_act[floored_act.Scenario == scen].itertuples(index=False)}

    rows = []
    for tech in io.WORKING_SET:
        crow = cand[(cand.Scenario == scen) & (cand.TECHNOLOGY == tech) & (cand.YEAR == snapshot_year)]
        if len(crow) == 0:
            continue
        crow = crow.iloc[0]
        forced_gw = float(crow["forced_GW"])
        if forced_gw <= 0:
            continue
        contracted_cf = float(crow["contracted_CF"])
        country, fuel = crow["country"], crow["fuel"]

        act_before = base_lookup.get((tech, snapshot_year), 0.0)
        act_after = floor_lookup.get((tech, snapshot_year), 0.0)

        rows.append(dict(
            tech=tech, label=f"{country} {fuel}", contracted_CF=contracted_cf,
            CF_forced_before=act_before / (forced_gw * C2A),
            CF_forced_after=act_after / (forced_gw * C2A),
        ))
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# plotting
# --------------------------------------------------------------------------- #
def plot(panel_a: dict, panel_b: dict, panel_c: pd.DataFrame):
    from matplotlib.gridspec import GridSpecFromSubplotSpec

    fig = plt.figure(figsize=(10, 16), dpi=150)
    outer = fig.add_gridspec(3, 1, height_ratios=[4, 3.6, 4], hspace=0.35,
                             top=0.96, bottom=0.085, left=0.09, right=0.97)
    axA = fig.add_subplot(outer[0])
    inner_b = GridSpecFromSubplotSpec(2, 1, subplot_spec=outer[1], height_ratios=[1, 2.6], hspace=0.08)
    axB_top = fig.add_subplot(inner_b[0])
    axB_bot = fig.add_subplot(inner_b[1], sharex=axB_top)
    axC = fig.add_subplot(outer[2])

    # ---- Panel A ----
    axA.set_title("Generacion no renovable: antes vs despues del piso", fontsize=13, color=DARK)
    axA.plot(panel_a["bau_before"].index, panel_a["bau_before"].values,
             color=SLATE, linestyle="-", lw=2, label="REFERENCIA antes")
    axA.plot(panel_a["bau_after"].index, panel_a["bau_after"].values,
             color=SLATE, linestyle="--", lw=2, label="REFERENCIA despues")
    axA.plot(panel_a["opt_before"].index, panel_a["opt_before"].values,
             color=TEAL, linestyle="-", lw=2, label="OPTIMO antes")
    axA.plot(panel_a["opt_after"].index, panel_a["opt_after"].values,
             color=TEAL, linestyle="--", lw=2, label="OPTIMO despues")
    axA.set_xlabel("Ano")
    axA.set_ylabel("PJ/ano")
    axA.set_xlim(FIRST_YEAR, LAST_YEAR)
    axA.set_ylim(0, axA.get_ylim()[1] * 1.08)
    axA.legend(loc="upper right", fontsize=9, frameon=False)
    axA.spines[["top", "right"]].set_visible(False)

    if LAST_YEAR in panel_a["opt_after"].index and LAST_YEAR in panel_a["opt_before"].index:
        before_2050 = panel_a["opt_before"].loc[LAST_YEAR]
        after_2050 = panel_a["opt_after"].loc[LAST_YEAR]
        delta = after_2050 - before_2050
        pct = 100 * delta / before_2050 if before_2050 else float("nan")
        axA.annotate(
            f"OPTIMO 2050: {before_2050:,.0f} -> {after_2050:,.0f} PJ\n"
            f"delta = {delta:+,.0f} PJ ({pct:+.1f}%)",
            xy=(LAST_YEAR, after_2050), xytext=(2031, 1500), textcoords="data",
            fontsize=9, color=DARK, ha="left",
            arrowprops=dict(arrowstyle="->", color=DARK, lw=1),
        )

    # ---- Panel B (broken y-axis: the pre-2026 legacy floor is ~15x the new
    # post-2026 working-set floor, so a single linear scale hides one or the
    # other; two stacked axes share the x-axis and each get their own range) ----
    axB_top.set_title("Piso de actividad no renovable: antes vs despues", fontsize=13, color=DARK)
    for ax in (axB_top, axB_bot):
        if len(panel_b["before"]):
            ax.plot(panel_b["before"].index, panel_b["before"].values,
                    color=DARK, linestyle=":", lw=2, label="ANTES (ambos escenarios, termina en 2026)")
        ax.plot(panel_b["bau_after"].index, panel_b["bau_after"].values,
                color=SLATE, linestyle="--", lw=2, label="REFERENCIA despues")
        ax.plot(panel_b["opt_after"].index, panel_b["opt_after"].values,
                color=TEAL, linestyle="--", lw=2, label="OPTIMO despues")
        common_years = sorted(set(panel_b["bau_after"].index) & set(panel_b["opt_after"].index))
        if common_years:
            bau_vals = panel_b["bau_after"].reindex(common_years)
            opt_vals = panel_b["opt_after"].reindex(common_years)
            ax.fill_between(common_years, bau_vals.values, opt_vals.values,
                            color=TEAL, alpha=0.2, label="brecha OPTIMO - REFERENCIA")

    # after_max only over years > 2026: the floored series still carries the
    # unchanged pre-2026 legacy rows too (same value as "before"), so the
    # true post-fix floor level must exclude that shared pre-2026 segment.
    bau_after_post = panel_b["bau_after"][panel_b["bau_after"].index > 2026]
    opt_after_post = panel_b["opt_after"][panel_b["opt_after"].index > 2026]
    before_max = panel_b["before"].max() if len(panel_b["before"]) else 0
    after_max = max(bau_after_post.max() if len(bau_after_post) else 0,
                     opt_after_post.max() if len(opt_after_post) else 0)
    axB_top.set_ylim(before_max * 0.93, before_max * 1.06)
    axB_bot.set_ylim(0, after_max * 1.25)

    axB_top.spines["bottom"].set_visible(False)
    axB_bot.spines["top"].set_visible(False)
    axB_top.tick_params(labelbottom=False, bottom=False)
    axB_top.set_xlim(FIRST_YEAR, LAST_YEAR)
    axB_top.spines[["top", "right"]].set_visible(False)
    axB_bot.spines[["top", "right"]].set_visible(False)
    axB_bot.set_xlabel("Ano")
    axB_bot.set_ylabel("PJ/ano")
    axB_bot.yaxis.set_label_coords(-0.09, 1.0)

    d = 0.4
    break_kwargs = dict(marker=[(-1, -d), (1, d)], markersize=8, linestyle="none",
                        color="k", mec="k", mew=1, clip_on=False)
    axB_top.plot([0, 1], [0, 0], transform=axB_top.transAxes, **break_kwargs)
    axB_bot.plot([0, 1], [1, 1], transform=axB_bot.transAxes, **break_kwargs)

    axB_top.legend(loc="lower left", fontsize=8, frameon=False)
    axB_bot.legend(loc="upper left", fontsize=8, frameon=False)

    # ---- Panel C ----
    axC.set_title("Working set: CF sobre capacidad forzada, antes vs despues (2050)", fontsize=13, color=DARK)
    x = list(range(len(panel_c)))
    width = 0.35
    bars_before = axC.bar([i - width / 2 for i in x], panel_c["CF_forced_before"], width,
                          color=AMBER, label="antes (linea base)")
    bars_after = axC.bar([i + width / 2 for i in x], panel_c["CF_forced_after"], width,
                         color=TEAL, label="despues (con piso)")
    for bars in (bars_before, bars_after):
        axC.bar_label(bars, fmt="%.2f", fontsize=7, padding=2, color=DARK)
    axC.set_xticks(x)
    axC.set_xticklabels(panel_c["label"], rotation=45, ha="right", fontsize=9)
    axC.set_ylabel("CF (actividad / capacidad forzada)")
    top = max(0.5, panel_c[["CF_forced_before", "CF_forced_after"]].to_numpy().max() * 1.2)
    axC.set_ylim(0, top)
    axC.legend(loc="upper left", fontsize=9, frameon=False)
    axC.spines[["top", "right"]].set_visible(False)

    fig.suptitle("Efecto del piso de despacho minimo sobre generacion forzada",
                 fontsize=15, color=DARK, y=0.995)
    fig.text(0.5, 0.012,
             "Valores provisionales: NGS CF=0.40, OIL/PET CF=0.10. Piso = despacho minimo "
             "garantizado de la capacidad forzada. Generacion por encima del piso determinada "
             "por el optimizador.",
             ha="center", fontsize=8, color=SLATE, wrap=True)

    fig.savefig(OUT_PNG, dpi=150)
    print(f"wrote {OUT_PNG}")


def main():
    assert BASELINE_COMBINED.exists(), f"missing baseline combined CSV: {BASELINE_COMBINED}"
    assert FLOORED_COMBINED.exists(), f"missing floored combined CSV: {FLOORED_COMBINED}"
    assert FLOORED_INPUTS.exists(), f"missing floored inputs CSV: {FLOORED_INPUTS}"

    print("loading baseline activity (404 MB, chunked, cached after first run)...")
    baseline_act = load_activity(BASELINE_COMBINED, "baseline_combined")
    print(f"  baseline activity rows: {len(baseline_act)}")

    print("loading floored activity (cached from the artifact-verification session)...")
    floored_act = load_activity(FLOORED_COMBINED, "floored_ws_decomp")
    print(f"  floored activity rows: {len(floored_act)}")

    print("parsing original TotalTechnologyAnnualActivityLowerLimit from preprocessed txt...")
    orig_ll = load_original_lowerlimit()
    print(f"  original lower-limit rows: {len(orig_ll)}; "
          f"year range: {orig_ll.YEAR.min() if len(orig_ll) else None}-"
          f"{orig_ll.YEAR.max() if len(orig_ll) else None}")

    print("loading floored TotalTechnologyAnnualActivityLowerLimit from the floored inputs CSV...")
    floored_ll = load_floored_lowerlimit()
    print(f"  floored lower-limit rows: {len(floored_ll)}")

    cand = load_candidates()

    panel_a = panel_a_series(baseline_act, floored_act)
    panel_b = panel_b_series(orig_ll, floored_ll)
    panel_c = panel_c_data(baseline_act, floored_act, cand)

    print("\npanel A (non-renewable generation, PJ/yr) at 2050:")
    for k, v in panel_a.items():
        print(f"  {k}: {v.get(LAST_YEAR, float('nan')):,.1f}" if LAST_YEAR in v.index else f"  {k}: n/a")

    print("\npanel B (activity floor, PJ/yr):")
    print(f"  before: last year present = {panel_b['before'].index.max() if len(panel_b['before']) else None}")
    print(f"  after BAU at 2050: {panel_b['bau_after'].get(LAST_YEAR, float('nan')):,.1f}")
    print(f"  after OPT at 2050: {panel_b['opt_after'].get(LAST_YEAR, float('nan')):,.1f}")

    print("\npanel C (working-set CF_forced, before -> after):")
    with pd.option_context("display.width", 200):
        print(panel_c.to_string(index=False))

    plot(panel_a, panel_b, panel_c)


if __name__ == "__main__":
    main()
