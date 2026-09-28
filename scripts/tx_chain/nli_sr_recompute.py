# -*- coding: utf-8 -*-
"""nli_sr_recompute.py -- v10 chain step: return the RPO reserve pinning leaves dead to
the NLI budget of the SR scenarios.

Run AFTER cost_sensitivity_v_SR_WF.py and BEFORE the solve. Only the SR scenarios: ISR,
VSR, ISRWF, VSRWF.

WHAT IT FIXES (user 2026-09-01): the SR scenarios inherit their NLI ceilings from
INV/VGB(/WF), computed with the RPO reserve at its CEILING (1% of the frozen stock).
cost_sensitivity_v_SR_WF.py then pins RPO to its floor: the reserve (~750 MUSD/year)
sits dead, unspendable by any channel. This step RE-COMPUTES the NLI ceilings using the
RPO reserve = PINNED FLOOR (the SR scenario's true ceiling), returning that money to the
NLI budget.

HOW (agnostic to the weighting scheme: respects historical or water-fill shares alike):
    new_budget(year) = max(0, i_region(year) - planned_cost - pinned_RPO_cost)
    ratio(year) = max(1, new_budget / old_budget)   [old_budget = sum of NLI ceilings x cost]
    new_NLI_ceiling(tech, year) = old_ceiling x ratio(year)
    TotalAnnualMaxCapacity (NLI) = cumulative sum of the new annual ceilings.
The max(1, .) protects years dominated by the BRB floor (2030: budget 0, only the 3 MUSD
floor; never reduced). The uniform scaling deviates the BRB slice from its exact floor by
<1 MUSD/year (declared; tolerance +-5). IDEMPOTENT: the new budget does not depend on the
existing ceilings, so running it twice yields ratio=1.

DOES NOT TOUCH: the envelope (ANCHOR_MUSD x ENV_GROWTH), the country shares, costs,
floors, RPO, planned techs, ICON, or any non-SR scenario. Only TRNNLI/RNWNLI rows of
TotalAnnualMaxCapacityInvestment and TotalAnnualMaxCapacity, years 2030+ (NLI_FIRST_YEAR).

Inputs:
    Pre_processed_<S>_0_..._FLOORED_VEGCON.txt for S in {ISR, VSR, ISRWF, VSRWF}, already
    processed by cost_sensitivity_v_SR_WF.py: flat in outputs/tx_chain/ by default, or
    under outputs/Executables/<S>_0/ with --executables-dir.
Outputs:
    Same datafiles, modified in place (TRNNLI/RNWNLI rows only).
Usage:
    python scripts/tx_chain/nli_sr_recompute.py --executables-dir <Executables>
    Invoked by B2_Executing_OG_Model.py as the "nli_sr_recompute" entry of
    scenario_transforms in inputs/config/Config_MOMF_T1_AB.yaml, right after
    "cost_sensitivity".
Notes:
    - Must run after cost_sensitivity_v_SR_WF.py: recompute() aborts (sys.exit) if RPO is
      not already pinned (Max != Min on an RPO row).
    - Runs as module-level code (no __main__ guard); importing this module has side
      effects (parses sys.argv, reads/writes datafiles).
    - Exits with sys.exit(1) if any scenario's self-check fails (planned + pinned-RPO +
      NLI cost deviates from max(i_region, planned + RPO) by more than +-5 MUSD).
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> scripts/
from common import relac_paths as P

import argparse
_ap = argparse.ArgumentParser()
_ap.add_argument("--executables-dir", default=None)
_args, _ = _ap.parse_known_args()
EXEDIR = Path(_args.executables_dir).resolve() if _args.executables_dir else None

_NAME = lambda s: f"Pre_processed_{s}_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_VEGCON.txt"
FN = lambda s: (EXEDIR / f"{s}_0" / _NAME(s)) if EXEDIR else (P.TX_CHAIN_OUT / _NAME(s))
if EXEDIR is None:
    P.TX_CHAIN_OUT.mkdir(parents=True, exist_ok=True)  # modo legado: asegura outputs/tx_chain antes de escribir
SR_SCENARIOS = ("ISR", "VSR", "ISRWF", "VSRWF")

ANCHOR_YEAR, ANCHOR_MUSD, ENV_GROWTH = 2022, 3300.0, 0.01   # = v13/v14 (NO tocar)
NLI_FIRST_YEAR, LAST_YEAR = 2030, 2050
NLI = ("TRNNLI", "RNWNLI")
PLN = ("PWRTRN", "RNWTRN")
RPO = ("TRNRPO", "RNWRPO")


def i_region(y):
    return ANCHOR_MUSD * (1 + ENV_GROWTH) ** (y - ANCHOR_YEAR)


def read_block(txt, name):
    m = re.search(r"^param[^\n:]*:\s*" + name + r"\s*:=(.*?)^;", txt, re.S | re.M)
    if not m:
        sys.exit(f"param {name} no encontrado")
    d = {}
    for l in m.group(1).splitlines():
        t = l.split()
        if len(t) >= 4:
            d[(t[1], int(t[2]))] = float(t[3])
    return d


def recompute(path):
    """Rescale TRNNLI/RNWNLI ceilings of one SR datafile using the pinned RPO cost.

    Reads TotalAnnualMaxCapacityInvestment, TotalAnnualMinCapacityInvestment and
    CapitalCost from path, verifies RPO is pinned (Max == Min), computes the new
    per-year NLI budget and ratio described in the module docstring, and — unless the
    file is already recomputed (ratio ~= 1 everywhere) — rewrites the TRNNLI/RNWNLI rows
    of TotalAnnualMaxCapacityInvestment (annual) and TotalAnnualMaxCapacity (cumulative)
    in place.

    Args:
        path: pathlib.Path to the scenario's VEGCON datafile (already processed by
            cost_sensitivity_v_SR_WF.py).

    Returns:
        Tuple (pln_cost, rpo_pin, old_b, new_b, ratio, n_inv, n_cum):
        pln_cost, rpo_pin, old_b, new_b, ratio are dicts keyed by year (2030-2050) with
        the planned-tech cost, pinned-RPO cost, old NLI budget, new NLI budget and
        rescale ratio; n_inv/n_cum are the counts of rewritten annual/cumulative rows
        (both 0 when no rewrite was needed).

    Raises:
        SystemExit: if any RPO row is not pinned (Max != Min beyond 1e-9).

    Side effects:
        Rewrites path in place when rescaling is needed; leaves it untouched otherwise.
    """
    txt = path.read_text(encoding="utf-8", errors="replace")
    mx = read_block(txt, "TotalAnnualMaxCapacityInvestment")
    mn = read_block(txt, "TotalAnnualMinCapacityInvestment")
    cc = read_block(txt, "CapitalCost")

    # guarda SR: la RPO debe venir PINNEADA (Max==Min) -- si no, este no es un SR
    bad = [(t, y) for (t, y), v in mx.items() if t.startswith(RPO)
           and abs(v - mn.get((t, y), 0.0)) > 1e-9]
    if bad:
        sys.exit(f"*** {path.name}: RPO no esta pinneada (Max!=Min en {len(bad)} filas). "
                 "Correr cost_sensitivity primero.")

    years = range(NLI_FIRST_YEAR, LAST_YEAR + 1)
    pln_cost = {y: sum(v * cc.get((t, yy), 0.0) for (t, yy), v in mx.items()
                       if yy == y and t.startswith(PLN)) for y in years}
    rpo_pin = {y: sum(v * cc.get((t, yy), 0.0) for (t, yy), v in mx.items()
                      if yy == y and t.startswith(RPO)) for y in years}
    old_b = {y: sum(v * cc.get((t, yy), 0.0) for (t, yy), v in mx.items()
                    if yy == y and t.startswith(NLI)) for y in years}
    new_b = {y: max(0.0, i_region(y) - pln_cost[y] - rpo_pin[y]) for y in years}
    ratio = {y: (max(1.0, new_b[y] / old_b[y]) if old_b[y] > 1e-9 else 1.0) for y in years}

    # idempotencia: si ya esta recalculado (ratio ~1 en todos los anos), no re-escribir
    # (evita deriva de redondeo .6g en el acumulado al correr dos veces)
    if all(abs(r - 1.0) <= 1e-6 for r in ratio.values()):
        print("  ya recalculado (ratio=1 en todos los anos): sin cambios")
        return pln_cost, rpo_pin, old_b, new_b, ratio, 0, 0

    # topes anuales nuevos + acumulado reconstruido
    new_inv, new_cum, run = {}, {}, {}
    for (t, y), v in sorted(mx.items()):
        if t.startswith(NLI) and y >= NLI_FIRST_YEAR:
            nv = v * ratio[y]
            new_inv[(t, y)] = nv
            run[t] = run.get(t, 0.0) + nv
            new_cum[(t, y)] = run[t]

    # escribir: sobre-escribe filas NLI existentes en los dos bloques
    out, cur = [], None
    n_inv = n_cum = 0
    for ln in txt.splitlines(keepends=True):
        s = ln.strip()
        m = re.match(r"param\b.*:\s*(\w+)\s*:=", s)
        if m:
            cur = m.group(1)
            out.append(ln)
            continue
        if cur and s == ";":
            cur = None
            out.append(ln)
            continue
        if cur in ("TotalAnnualMaxCapacityInvestment", "TotalAnnualMaxCapacity"):
            t = ln.split()
            if len(t) >= 4 and t[1].startswith(NLI):
                k = (t[1], int(t[2]))
                src = new_inv if cur == "TotalAnnualMaxCapacityInvestment" else new_cum
                if k in src:
                    t[3] = f"{src[k]:.6g}"
                    out.append(" ".join(t) + "\n")
                    if cur == "TotalAnnualMaxCapacityInvestment":
                        n_inv += 1
                    else:
                        n_cum += 1
                    continue
        out.append(ln)
    path.write_text("".join(out), encoding="utf-8")
    return pln_cost, rpo_pin, old_b, new_b, ratio, n_inv, n_cum


def selfcheck(path, pln_cost, rpo_pin, new_b):
    txt = path.read_text(encoding="utf-8", errors="replace")
    mx = read_block(txt, "TotalAnnualMaxCapacityInvestment")
    cc = read_block(txt, "CapitalCost")
    ok = True
    print(f"  {'ano':5}{'i_region':>9}{'planif':>8}{'rpo_pin':>8}{'NLI_nuevo':>10}{'identidad':>10}")
    for y in (2030, 2031, 2033, 2035, 2040, 2045, 2050):
        nli = sum(v * cc.get((t, yy), 0.0) for (t, yy), v in mx.items()
                  if yy == y and t.startswith(NLI))
        total = pln_cost[y] + rpo_pin[y] + nli
        target = max(i_region(y), pln_cost[y] + rpo_pin[y])
        dev = total - target
        flag = "OK" if abs(dev) <= 5.0 else "*** FAIL"
        ok &= abs(dev) <= 5.0
        print(f"  {y:5}{i_region(y):9.0f}{pln_cost[y]:8.0f}{rpo_pin[y]:8.0f}{nli:10.1f}"
              f"{dev:+9.1f} {flag}")
    return ok


fail = False
found = [s for s in SR_SCENARIOS if FN(s).is_file()]
if not found:
    sys.exit("*** ningun SR encontrado (ISR/VSR/ISRWF/VSRWF); correr cost_sensitivity primero")
for s in found:
    print("=" * 70 + f"\n{s}: {FN(s).name}")
    pln, rpo, ob, nb, ra, ni, nc = recompute(FN(s))
    tot_old, tot_new = sum(ob.values()), sum(nb.values())
    print(f"  presupuesto NLI 2030-2050: {tot_old:,.0f} -> {tot_new:,.0f} MUSD "
          f"(devuelto: +{tot_new - tot_old:,.0f}); filas: {ni} anuales + {nc} acumuladas")
    print(f"  ratio muestra: 2031={ra[2031]:.3f}  2035={ra[2035]:.3f}  2050={ra[2050]:.3f}  "
          f"2030={ra[2030]:.3f} (floor BRB intacto)")
    ok = selfcheck(FN(s), pln, rpo, nb)
    print(f"  SELF-CHECK identidad (planif + RPO_pin + NLI == max(i_region, planif+RPO) +-5): "
          f"{'OK' if ok else '*** FAIL'}")
    fail |= not ok
print("\nDONE" + ("" if not fail else "  *** SELF-CHECK FAILED ***"))
sys.exit(1 if fail else 0)
