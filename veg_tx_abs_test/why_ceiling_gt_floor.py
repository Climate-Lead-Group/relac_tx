# -*- coding: utf-8 -*-
"""Why is OPT ceiling (B2) > OPT floor (A2)? Decompose MinCapInv vs MaxCapInv
   for OPT by family group, at key years. Read-only."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
OPT = HERE / "Pre_processed_OPT_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_VEGCON.txt"

PLAN = ("PWRTRN", "RNWTRN")
NLI  = ("TRNNLI", "RNWNLI")
RPO  = ("TRNRPO", "RNWRPO")
FAM6 = PLAN + NLI + RPO


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


def grp_sum(d, fams, year):
    return sum(v for (t, y), v in d.items() if y == year and t.startswith(fams))


P = read_params(OPT, ("TotalAnnualMinCapacityInvestment",
                      "TotalAnnualMaxCapacityInvestment"))
mn = P["TotalAnnualMinCapacityInvestment"]
mx = P["TotalAnnualMaxCapacityInvestment"]

print("OPT (VEGCON) — GW/ano, por familia")
print("=" * 78)
hdr = f"{'yr':>4} | {'PLAN min':>9} {'PLAN max':>9} | {'RPO min':>8} {'RPO max':>8} | {'NLI min':>8} {'NLI max':>8} | {'TOT min':>8} {'TOT max':>8}"
print(hdr)
print("-" * len(hdr))
for y in (2027, 2028, 2029, 2030, 2032, 2035, 2040, 2050):
    pmn, pmx = grp_sum(mn, PLAN, y), grp_sum(mx, PLAN, y)
    rmn, rmx = grp_sum(mn, RPO, y),  grp_sum(mx, RPO, y)
    nmn, nmx = grp_sum(mn, NLI, y),  grp_sum(mx, NLI, y)
    tmn = grp_sum(mn, FAM6, y)
    tmx = grp_sum(mx, FAM6, y)
    print(f"{y:>4} | {pmn:>9.2f} {pmx:>9.2f} | {rmn:>8.2f} {rmx:>8.2f} | "
          f"{nmn:>8.2f} {nmx:>8.2f} | {tmn:>8.2f} {tmx:>8.2f}")

print("\nLECTURA:")
print("  PLAN: min == max (OPT fijado en su plan)  -> no aporta a la brecha")
print("  RPO : min ~ 0, max = rampa 2-3% del stock -> ESTA es la brecha techo>piso")
print("  NLI : 0 en OPT (apply_nli=False)")
