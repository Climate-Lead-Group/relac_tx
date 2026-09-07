# -*- coding: utf-8 -*-
"""Explica COMO se reparte el envelope MUSD en topes por-tech (GW). Lee el INV
   escrito y descompone: planificadas + RPO + NLI, y la NLI por pais. Read-only."""
import sys
from pathlib import Path
import importlib.util

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # -> scripts/
from common import relac_paths as RP

HERE = Path(__file__).resolve().parent
INV = RP.REFERENCE / "veg_tx_abs_test" / "Pre_processed_INV_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_VEGCON.txt"

# importar las funciones del script canonico (no corre main())
spec = importlib.util.spec_from_file_location("vtc", HERE / "veg_tx_constraints.py")
vtc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vtc)

PLAN = ("PWRTRN", "RNWTRN")
NLI  = ("TRNNLI", "RNWNLI")
RPO  = ("TRNRPO", "RNWRPO")


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


P = read_params(INV, ("TotalAnnualMaxCapacityInvestment", "CapitalCost"))
maxi, cc = P["TotalAnnualMaxCapacityInvestment"], P["CapitalCost"]


def musd(fams, y):
    return sum(gw * cc.get((t, y), 0.0) for (t, yy), gw in maxi.items()
              if yy == y and t.startswith(fams))


def musd_by_country(fams, y):
    d = {}
    for (t, yy), gw in maxi.items():
        if yy == y and t.startswith(fams):
            d[t[6:9]] = d.get(t[6:9], 0.0) + gw * cc.get((t, y), 0.0)
    return d


print("=" * 74)
print("1) CLAVE DE REPARTO POR PAIS  shares[c]  (solo afecta a la NLI)")
print("=" * 74)
shares = vtc.final_shares()
for c in sorted(shares, key=lambda x: -shares[x]):
    print(f"   {c}: {shares[c]*100:5.2f}%", end="   ")
    if list(sorted(shares, key=lambda x: -shares[x])).index(c) % 4 == 3:
        print()
print("\n   (= max(deep-research, pipeline BNamericas anualizado, fallback), normalizado a 1)")

print("\n" + "=" * 74)
print("2) DESCOMPOSICION DEL ENVELOPE POR ANO (MUSD/ano, leido del INV escrito)")
print("=" * 74)
print(f"   {'yr':>4} {'envelope':>9} | {'planif':>8} {'RPO':>8} {'NLI(resto)':>10} | {'suma':>8} {'check':>6}")
for y in (2030, 2032, 2035, 2040, 2050):
    env = vtc.i_region(y)
    pl, rp, nl = musd(PLAN, y), musd(RPO, y), musd(NLI, y)
    tot = pl + rp + nl
    chk = "==env" if abs(tot - max(env, pl + rp)) < 1 else "committed>env"
    print(f"   {y:>4} {env:>9.0f} | {pl:>8.0f} {rp:>8.0f} {nl:>10.0f} | {tot:>8.0f} {chk:>6}")

print("\n" + "=" * 74)
print("3) COMO SE PARTE EL 'RESTO' NLI ENTRE PAISES (ejemplo 2035)")
print("=" * 74)
y = 2035
nli_c = musd_by_country(NLI, y)
nli_tot = sum(nli_c.values())
print(f"   presupuesto NLI 2035 = {nli_tot:.0f} MUSD, repartido por shares[c]:")
for c in sorted(nli_c, key=lambda x: -nli_c[x])[:6]:
    print(f"     {c}: {nli_c[c]:7.0f} MUSD  ({nli_c[c]/nli_tot*100:4.1f}%  vs share {shares.get(c,0)*100:4.1f}%)")
print("   ...y dentro de cada pais, RNWNLI vs TRNNLI por ren_share(ano) (glide a 70% ren en 2050).")

print("\n" + "=" * 74)
print("RESUMEN: planif (plan OPT) y RPO (rampa fisica) se calculan PRIMERO;")
print("la NLI recibe el REMANENTE del envelope, repartido por shares[c] y ren/no-ren.")
print("Cada tope es por-tech en GW = MUSD_asignado / costo_corregido(tech,ano).")
print("La SUMA de topes = envelope; el solver puede invertir MENOS, nunca MAS.")
