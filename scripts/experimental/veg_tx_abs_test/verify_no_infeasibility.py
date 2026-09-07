# -*- coding: utf-8 -*-
"""Chequeo fresco de infactibilidad en los 4 .txt VEGCON, con enfasis en el
   riesgo nuevo del envelope: NLI con presupuesto 0 vs pisos comprometidos.
   Read-only. Reusa feasibility_scan del script canonico."""
import sys
from pathlib import Path
import importlib.util

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # -> scripts/
from common import relac_paths as RP

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("vtc", HERE / "veg_tx_constraints.py")
vtc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vtc)

HARD = ("min_inv>max_inv", "min_cap>max_cap", "residual>max_cap",
        "cap_floor_inalcanzable", "act_low>act_up")
NLI = ("TRNNLI", "RNWNLI")

files = {s: RP.REFERENCE / "veg_tx_abs_test" / f"Pre_processed_{s}_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_VEGCON.txt"
         for s in ("BAU", "OPT", "INV", "VGB")}

print("=" * 72)
print("A) ESCANEO COMPLETO DE FACTIBILIDAD (todas las techs, los 4 .txt)")
print("=" * 72)
grand_hard = 0
for s, path in files.items():
    scan = vtc.feasibility_scan(path)
    hard = {c: scan[c] for c in HARD if c in scan}
    warn = {c: scan[c] for c in scan if c.endswith("[warn]")}
    nh = sum(len(v) for v in hard.values())
    grand_hard += nh
    print(f"\n  [{s}] conflictos DUROS: {nh}")
    for c, items in hard.items():
        print(f"      {c}: {len(items)}  e.j. {items[0]}")
    for c, items in warn.items():
        print(f"      [warn] {c}: {len(items)} (retirada por vida util puede salvar)")
    if nh == 0 and not hard:
        print("      (ninguno)")

print("\n" + "=" * 72)
print("B) RIESGO ESPECIFICO DEL ENVELOPE: NLI con tope 0 vs piso comprometido")
print("=" * 72)
P = ("TotalAnnualMinCapacityInvestment", "TotalAnnualMaxCapacityInvestment")
for s in ("INV", "VGB"):
    Q = vtc.read_params(files[s], P)
    mn, mx = Q[P[0]], Q[P[1]]
    nli_floors = {k: v for k, v in mn.items() if k[0].startswith(NLI) and v > 1e-9}
    n_zero_cap = sum(1 for (t, y), gw in mx.items()
                     if t.startswith(NLI) and abs(gw) < 1e-9)
    conflicts = [(k, mn[k], mx.get(k)) for k in nli_floors
                 if mx.get(k) is not None and mx[k] < nli_floors[k] - 1e-9]
    print(f"  [{s}] NLI: filas con tope=0 = {n_zero_cap}; "
          f"pisos comprometidos NLI = {len(nli_floors)}; "
          f"conflictos min>max en NLI = {len(conflicts)}")
    if conflicts:
        print(f"       {conflicts[:3]}")

print("\n" + "=" * 72)
print(f"VEREDICTO: conflictos duros totales en los 4 archivos = {grand_hard}")
print("  (0 = ninguno de los patrones de infactibilidad de OSeMOSYS que chequeamos:")
print("   min>max inversion/capacidad, residual>techo, piso inalcanzable, actividad)")
print("=" * 72)
