# -*- coding: utf-8 -*-
"""nli_sr_recompute.py -- paso NUEVO de la cadena v10 (correr DESPUES de
cost_sensitivity y ANTES de resolver). Solo escenarios SR: ISR, VSR, ISRWF, VSRWF.

QUE CORRIGE (usuario 2026-09-01): los SR heredan los topes NLI de INV/VGB(/WF),
calculados con la reserva RPO al TECHO (1% del stock congelado). Luego v10 pinnea
la RPO al piso: la reserva (~750 MUSD/ano) queda muerta -- ningun canal puede
gastarla. Este paso RE-CALCULA los topes NLI con la reserva RPO = PISO PINNEADO
(el techo verdadero del escenario SR), devolviendo esa plata al presupuesto NLI.

COMO (agnostico a los pesos: respeta historicos o water-fill por igual):
  presup_nuevo(ano) = max(0, i_region(ano) - costo_planificadas - costo_RPO_pinneada)
  ratio(ano) = max(1, presup_nuevo / presup_viejo)    [presup_viejo = suma topes NLI x costo]
  tope_NLI_nuevo(tech, ano) = tope_viejo x ratio(ano)
  TotalAnnualMaxCapacity NLI = suma acumulada de los topes anuales nuevos.
El max(1, .) protege los anos dominados por el floor BRB (2030: presupuesto 0,
solo el floor de 3 MUSD; no se reduce nada, nunca). El escalado uniforme desvia
la rebanada BRB del floor exacto en <1 MUSD/ano (declarado; tolerancia +-5).
IDEMPOTENTE: el presupuesto nuevo no depende de los topes, correrlo 2 veces da ratio=1.

NO TOCA: envelope (3300 x 1.0%), pesos, costos, pisos, RPO, planificadas, ICON,
ni ningun escenario no-SR. Solo filas TRNNLI/RNWNLI de MaxCapacityInvestment y
TotalAnnualMaxCapacity, anos 2030+.
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
