# -*- coding: utf-8 -*-
"""Plot floors & ceilings from the ORIGINAL vs VEGCON .txt datafiles.
   Investment (GW/yr) and capacity (GW cumulative). Read-only, F5-executable."""
import re
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
EXE  = HERE.parent / "t1_confection" / "Executables"

ORIG = {
    "BAU": EXE / "BAU_0" / "Pre_processed_BAU_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt",
    "OPT": EXE / "OPT_0" / "Pre_processed_OPT_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt",
    "INV": EXE / "INV_0" / "Pre_processed_INV_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt",
    "VGB": EXE / "VGB_0" / "Pre_processed_VGB_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt",
}
VEGCON = {s: HERE / f"Pre_processed_{s}_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_VEGCON.txt" for s in ORIG}

PARAMS = ("TotalAnnualMinCapacityInvestment", "TotalAnnualMaxCapacityInvestment",
          "TotalAnnualMaxCapacity", "ResidualCapacity", "CapitalCost")

FAM6   = ("PWRTRN", "RNWTRN", "TRNNLI", "RNWNLI", "TRNRPO", "RNWRPO")
PLAN   = ("PWRTRN", "RNWTRN")
NLI    = ("TRNNLI", "RNWNLI")
RPO    = ("TRNRPO", "RNWRPO")
YEARS  = list(range(2023, 2051))
C2A    = 31.536  # GW-yr -> PJ


def read_params(path, params):
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    out, cur = {p: {} for p in params}, None
    for ln in lines:
        s = ln.strip()
        if s.startswith("param") and ":=" in s:
            cur = None
            for p in params:
                if f": {p} :=" in s or f":{p}:=" in s.replace(" ", ""):
                    cur = p
                    break
        elif s == ";":
            cur = None
        elif cur:
            t = ln.split()
            if len(t) == 4:
                try:
                    out[cur][(t[1], int(t[2]))] = float(t[3])
                except ValueError:
                    pass
    return out


def fam_of(tech):
    for f in FAM6:
        if tech.startswith(f):
            return f
    return None


def group_of(tech):
    f = fam_of(tech)
    if f in PLAN:   return "PLAN"
    if f in NLI:    return "NLI"
    if f in RPO:    return "RPO"
    return None


def agg_by_year(param_dict, families, years):
    """Sum values across techs matching families, per year."""
    out = {}
    for y in years:
        out[y] = sum(v for (t, yy), v in param_dict.items()
                     if yy == y and t.startswith(families))
    return out


def agg_by_group_year(param_dict, years):
    """Sum per (group, year)."""
    out = {"PLAN": {}, "NLI": {}, "RPO": {}}
    for y in years:
        for grp, fams in [("PLAN", PLAN), ("NLI", NLI), ("RPO", RPO)]:
            out[grp][y] = sum(v for (t, yy), v in param_dict.items()
                              if yy == y and t.startswith(fams))
    return out


def cumul(annual, years):
    """Cumulative sum."""
    c, out = 0.0, {}
    for y in years:
        c += annual.get(y, 0.0)
        out[y] = c
    return out


def musd_by_year(gw_dict, cc, families, years):
    """Sum GW*CapitalCost across techs matching families, per year -> MUSD/yr."""
    out = {}
    for y in years:
        out[y] = sum(gw * cc.get((t, y), 0.0) for (t, yy), gw in gw_dict.items()
                     if yy == y and t.startswith(families))
    return out


def musd_by_group_year(gw_dict, cc, years):
    """Sum GW*CapitalCost per (group, year) -> MUSD/yr."""
    out = {"PLAN": {}, "NLI": {}, "RPO": {}}
    for y in years:
        for grp, fams in [("PLAN", PLAN), ("NLI", NLI), ("RPO", RPO)]:
            out[grp][y] = sum(gw * cc.get((t, y), 0.0) for (t, yy), gw in gw_dict.items()
                              if yy == y and t.startswith(fams))
    return out


def i_region(y, anchor=3000.0, anchor_year=2022, growth=0.019):
    """Envelope regional objetivo (MUSD/ano): 3000 @2022 x 1.9%/ano."""
    return anchor * (1 + growth) ** (y - anchor_year)


# ─── Load everything ────────────────────────────────────────────────────────
data = {}  # data[label][scen] = {param: {(tech,year): val}}
for scen in ORIG:
    data.setdefault("ORIGINAL", {})[scen] = read_params(ORIG[scen], PARAMS)
    vc = VEGCON[scen]
    if vc.exists():
        data.setdefault("VEGCON", {})[scen] = read_params(vc, PARAMS)

print("Loaded OK. Building plot...")

# ─── Palette ────────────────────────────────────────────────────────────────
plt.rcParams["font.family"] = "DejaVu Sans"
CM     = "#00414D"   # dark teal
REFc   = "#5A7682"   # grey-blue (REF/BAU)
OPTc   = "#C9622E"   # burnt orange (OPT)
INVc   = "#2E86AB"   # blue (INV)
VGBc   = "#7A9AA6"   # light grey-blue (VGB)
TXT    = "#0F2E36"
PLANc  = "#00414D"
NLIc   = "#C9622E"
RPOc   = "#5A7682"
SCEN_COLS = {"BAU": REFc, "OPT": OPTc, "INV": INVc, "VGB": VGBc}
SCEN_LBL  = {"BAU": "REF", "OPT": "OPT", "INV": "INV", "VGB": "VGB"}

# ─── Figure: 3 rows × 2 cols ───────────────────────────────────────────────
#  Row 0: Investment FLOOR (MinCapInv, GW/yr)   — ORIGINAL vs VEGCON, all 4
#  Row 1: Investment CEILING (MaxCapInv, GW/yr)  — by family group, all 4
#  Row 2: Capacity stock (cumul forced + residual) vs ceiling
fig, axes = plt.subplots(3, 2, figsize=(15, 13.5))
fig.suptitle("PISOS y TECHOS de Tx en los .txt  (ORIGINAL vs VEGCON)",
             color=TXT, fontsize=14, fontweight="bold", y=0.995)

# ═══════════════ ROW 0: Investment FLOOR (MUSD/yr) ═══════════════════════════
for col, label in enumerate(["ORIGINAL", "VEGCON"]):
    ax = axes[0, col]
    dd = data.get(label, {})
    for scen in ("BAU", "OPT", "INV", "VGB"):
        if scen not in dd:
            continue
        mini = dd[scen]["TotalAnnualMinCapacityInvestment"]
        cc = dd[scen]["CapitalCost"]
        vals = musd_by_year(mini, cc, FAM6, YEARS)
        ys = [vals.get(y, 0) for y in YEARS]
        lw = 2.4 if scen in ("BAU", "OPT") else 1.4
        ls = "-" if scen in ("BAU", "OPT") else "--"
        ax.plot(YEARS, ys, color=SCEN_COLS[scen], lw=lw, ls=ls,
                label=f"{SCEN_LBL[scen]}")
    ax.set_title(f"A{col+1}. Piso de inversion comprometida (MinCapInv) — {label}",
                 color=TXT, fontsize=11)
    ax.set_ylabel("MUSD / ano")
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(alpha=.25)
    ax.set_ylim(bottom=0)
    ax.set_xlim(2023, 2050)
    ax.tick_params(colors=TXT)

# ═══════════════ ROW 1: Investment CEILING (MUSD/yr) ═════════════════════════
TOP_B = 9000  # MUSD, tope visual comun
for col, label in enumerate(["ORIGINAL", "VEGCON"]):
    ax = axes[1, col]
    dd = data.get(label, {})
    # linea de referencia: envelope regional 3000 x1.9% (el "3300 -> 5000+")
    ax.plot(YEARS, [i_region(y) for y in YEARS], color=TXT, lw=1.4, ls=(0, (4, 3)),
            label="Envelope objetivo 3000 x1.9% (3.3k→5.1k)", zorder=5)
    if label == "ORIGINAL":
        # los originales NO tienen techo de Tx: el modelo invierte sin limite
        ax.fill_between(YEARS, 0, TOP_B, facecolor="none", hatch="////",
                        edgecolor="#AA3333", alpha=.30, linewidth=0.0,
                        label="SIN tope (los 4 escenarios, libre ↑)")
        ax.text(0.5, 0.5, "SIN TECHO DE Tx\n(0 filas MaxCapInv en los 4 datafiles\n"
                "→ inversion libre en las 6 familias)",
                transform=ax.transAxes, ha="center", va="center",
                fontsize=12, color="#AA3333", fontweight="bold")
    else:
        # VEGCON — honesto sobre lo que ESTA capado:
        #  · veg (INV/VGB): envelope ACOTADO = planif + RPO + NLI dentro del budget
        #  · OPT/REF: solo planif + RPO capadas; la NLI NO tiene tope (libre)
        # OPT/REF: linea solida = planif+RPO; arriba, region rayada = NLI sin tope
        for scen in ("BAU", "OPT"):
            if scen not in dd:
                continue
            cc = dd[scen]["CapitalCost"]
            grp = musd_by_group_year(dd[scen]["TotalAnnualMaxCapacityInvestment"], cc, YEARS)
            pr = [grp["PLAN"].get(y, 0) + grp["RPO"].get(y, 0) for y in YEARS]
            ax.plot(YEARS, pr, color=SCEN_COLS[scen], lw=2.2,
                    label=f"{SCEN_LBL[scen]}: planif+RPO (NLI SIN tope)")
        cc_opt = dd["OPT"]["CapitalCost"]
        go = musd_by_group_year(dd["OPT"]["TotalAnnualMaxCapacityInvestment"], cc_opt, YEARS)
        pr_opt = [go["PLAN"].get(y, 0) + go["RPO"].get(y, 0) for y in YEARS]
        nli_open = [y for y in YEARS if y >= 2030]
        ax.fill_between(nli_open, [pr_opt[YEARS.index(y)] for y in nli_open], TOP_B,
                        facecolor="none", hatch="////", edgecolor="#AA3333",
                        alpha=.30, linewidth=0.0, label="NLI OPT/REF: SIN tope (libre ↑)")
        # veg (INV/VGB): envelope acotado (solido); fill de familia para INV
        for scen in ("INV", "VGB"):
            if scen not in dd:
                continue
            cc = dd[scen]["CapitalCost"]
            grp = musd_by_group_year(dd[scen]["TotalAnnualMaxCapacityInvestment"], cc, YEARS)
            total = [grp["PLAN"].get(y, 0) + grp["NLI"].get(y, 0) + grp["RPO"].get(y, 0)
                     for y in YEARS]
            ax.plot(YEARS, total, color=SCEN_COLS[scen], lw=2.0,
                    ls="--" if scen == "VGB" else "-",
                    label=f"{SCEN_LBL[scen]}: envelope ACOTADO (planif+RPO+NLI)")
        gi = musd_by_group_year(dd["INV"]["TotalAnnualMaxCapacityInvestment"],
                                dd["INV"]["CapitalCost"], YEARS)
        p = [gi["PLAN"].get(y, 0) for y in YEARS]
        r = [gi["RPO"].get(y, 0)  for y in YEARS]
        n = [gi["NLI"].get(y, 0)  for y in YEARS]
        ax.fill_between(YEARS, 0, p, color=PLANc, alpha=.14, label="INV planif. (=plan OPT)")
        ax.fill_between(YEARS, p, [a+b for a, b in zip(p, r)], color=RPOc, alpha=.14,
                        label="INV RPO")
        ax.fill_between(YEARS, [a+b for a, b in zip(p, r)],
                        [a+b+c for a, b, c in zip(p, r, n)], color=NLIc, alpha=.20,
                        label="INV NLI (remanente del envelope)")
    ax.set_title(f"B{col+1}. Techo de inversion (MaxCapInv) — {label}",
                 color=TXT, fontsize=11)
    ax.set_ylabel("MUSD / ano")
    ax.legend(fontsize=6.5, loc="upper right", ncol=1)
    ax.grid(alpha=.25)
    ax.set_ylim(0, TOP_B)
    ax.set_xlim(2023, 2050)
    ax.tick_params(colors=TXT)

# ═══════════════ ROW 2: CAPACITY — floor vs ceiling, cumulative ═════════════
for col, label in enumerate(["ORIGINAL", "VEGCON"]):
    ax = axes[2, col]
    dd = data.get(label, {})
    for scen in ("BAU", "OPT", "INV", "VGB"):
        if scen not in dd:
            continue
        resid = dd[scen]["ResidualCapacity"]
        mini  = dd[scen]["TotalAnnualMinCapacityInvestment"]
        maxi  = dd[scen]["TotalAnnualMaxCapacityInvestment"]
        maxc  = dd[scen]["TotalAnnualMaxCapacity"]

        # capacity floor = residual + cumul forced builds (MinCapInv)
        resid_yr = agg_by_year(resid, FAM6, YEARS)
        forced_yr = agg_by_year(mini, FAM6, YEARS)
        forced_cum = cumul(forced_yr, YEARS)
        cap_floor = [resid_yr.get(y, 0) + forced_cum.get(y, 0) for y in YEARS]

        # capacity ceiling = residual + cumul max builds (MaxCapInv)
        maxinv_yr = agg_by_year(maxi, FAM6, YEARS)
        has_ceiling = any(v > 0 for v in maxinv_yr.values())
        maxinv_cum = cumul(maxinv_yr, YEARS)
        cap_ceil = [resid_yr.get(y, 0) + maxinv_cum.get(y, 0) for y in YEARS]

        lw = 2.2 if scen in ("BAU", "OPT") else 1.2
        ls = "-" if scen in ("BAU", "OPT") else "--"
        ax.plot(YEARS, cap_floor, color=SCEN_COLS[scen], lw=lw, ls=ls,
                label=f"{SCEN_LBL[scen]} piso (resid+forzado)")
        if has_ceiling:
            ax.plot(YEARS, cap_ceil, color=SCEN_COLS[scen], lw=lw*0.7, ls=":",
                    label=f"{SCEN_LBL[scen]} techo (resid+max inv)")

        # shade the feasible band for BAU and OPT
        if scen in ("BAU", "OPT") and has_ceiling:
            ax.fill_between(YEARS, cap_floor, cap_ceil,
                            color=SCEN_COLS[scen], alpha=0.07)

    if label == "ORIGINAL":
        ax.text(0.5, 0.85, "Sin techo de inversion → techo de capacidad abierto",
                transform=ax.transAxes, ha="center", fontsize=10, color="#AA3333",
                fontstyle="italic")

    ax.set_title(f"C{col+1}. Capacidad Tx acumulada: piso vs techo — {label}",
                 color=TXT, fontsize=11)
    ax.set_ylabel("GW (stock)")
    ax.legend(fontsize=7, loc="upper left", ncol=2)
    ax.grid(alpha=.25)
    ax.set_ylim(bottom=0)
    ax.set_xlim(2023, 2050)
    ax.tick_params(colors=TXT)

fig.tight_layout(rect=[0, 0, 1, 0.97])
png = HERE / "floors_ceilings_comparison.png"
fig.savefig(png, dpi=140, bbox_inches="tight")
print(f"\nPNG: {png}")
print("Done.")
