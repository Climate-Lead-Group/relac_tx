# -*- coding: utf-8 -*-
"""FB cost-sensitivity transform: cheap fossil fuel ONLY (hostile case for the Tx thesis).
Consolidates v7 (BAC->BFB) and v9 (INV->IFB) into a single script restricted to the
B* and I* scenarios. Reads a base VEGCON .txt, scales VariableCost of fossil MIN* supply
by x0.52 and writes a new datafile. NO changes to VRE/wind/storage CapitalCost (unlike
the former CR transform). Only VALUES change; structure/bounds untouched -> feasibility
preserved. Backstop left AS-IS in the solve.

Source: EIA AEO2025 Low Oil Price case, Brent 47 vs 91 USD/b in 2050 -> ratio 0.517 ~ 0.52
[derived]. Flat scalar 2023-2050 (declared simplification; see
sensitivity_multipliers_calibration.md). Pairs: BAC->BFB, INV->IFB.

Datafile location (same convention as cost_sensitivity_v_SR_WF.py):
  default            -> flat in outputs/tx_chain/
  --executables-dir  -> <dir>/<S>_0/<datafile>  (B2 Executables layout; BFB_0/, IFB_0/ created)"""
import re, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> scripts/
from common import relac_paths as P

import argparse
_ap = argparse.ArgumentParser()
_ap.add_argument("--executables-dir", default=None,
                 help="Carpeta Executables de B2; resuelve cada datafile en <dir>/<S>_0/ "
                      "(default: plano en outputs/tx_chain/)")
_args, _ = _ap.parse_known_args()
EXEDIR = Path(_args.executables_dir).resolve() if _args.executables_dir else None

FN = lambda s: f"Pre_processed_{s}_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_VEGCON.txt"

def LOCAL(s):
    if EXEDIR is None:
        return P.TX_CHAIN_OUT / FN(s)     # modo legado (plano)
    d = EXEDIR / f"{s}_0"                # modo Executables: BFB_0/, IFB_0/ se crean aqui
    d.mkdir(parents=True, exist_ok=True)
    return d / FN(s)

# base scenario -> new scenario code (only B* and I*)
PAIRS={"BAC":"BFB", "INV":"IFB"}

# ----- tunable knobs -----
FUEL_MULT  = 0.52                      # fossil fuel supply VariableCost x0.52 (EIA AEO2025 Low Oil Price)
FUEL_MIN   = {"MINCOA","MINGAS","MINOIL","MINPET","MINOTH","MINCOG"}  # fossil supply (excl. URN)

def transform(src, dst):
    lines=open(src,encoding="utf-8",errors="replace").read().splitlines(keepends=True)
    out=[]; cur=None; n_vc=0
    for ln in lines:
        s=ln.strip()
        m=re.match(r"param\b.*:\s*(\w+)\s*:=", s)
        if m: cur=m.group(1); out.append(ln); continue
        if cur and s==";": cur=None; out.append(ln); continue
        if cur=="VariableCost" and s.startswith("GLOBAL"):
            t=ln.split()
            if len(t)>=4 and t[1][:6] in FUEL_MIN:
                try: v=float(t[-1])
                except: out.append(ln); continue
                t[-1]=f"{v*FUEL_MULT:.6g}"
                out.append(" ".join(t)+"\n"); n_vc+=1
                continue
        out.append(ln)
    open(dst,"w",encoding="utf-8",newline="").write("".join(out))
    return n_vc

for base,new in PAIRS.items():
    src=LOCAL(base); dst=LOCAL(new)
    if not src.exists(): sys.exit(f"missing base datafile: {src}")
    nv=transform(src,dst)
    print(f"[{base}->{new}] scaled {nv} VariableCost rows (fossil fuel); CapitalCost untouched")
    print(f"   wrote {dst.name}  ({os.path.getsize(dst):,} bytes)")

# ---- SELF-CHECK (preflight): fuel scaled x0.52, everything else intact ----
def val(path,param,tech,year):
    txt=open(path,encoding="utf-8",errors="replace").read()
    blk=re.search(r"param[^\n:]*:\s*"+param+r"\s*:=(.*?);",txt,re.S).group(1)
    for l in blk.splitlines():
        t=l.split()
        if len(t)>=4 and t[1]==tech and t[-2]==str(year): return float(t[-1])
    return None

fail=False
for base,new in PAIRS.items():
    b=LOCAL(base); n=LOCAL(new)
    print("\n"+"="*66+f"\nSELF-CHECK: {new} vs {base} sample values (2030)\n"+"="*66)
    # fuel VariableCost: expect ratio 0.52
    for tech in ["MINGASPER","MINOILPER","MINCOAPER"]:
        o=val(b,"VariableCost",tech,2030); nn=val(n,"VariableCost",tech,2030)
        r=(nn/o) if (o and nn) else None
        if r is not None and abs(r-FUEL_MULT)>1e-3: fail=True
        print(f"  VariableCost {tech:12s}: {base}={o}  {new}={nn}  ratio={r:.3f}  (x0.52)" if r else f"  VariableCost {tech}: {base}={o} {new}={nn}")
    # CapitalCost must be UNCHANGED (this is what distinguishes FB from CR)
    for tech in ["PWRSPVPERXX","PWRWONPERXX","PWRSDSPERXX","PWRLDSPERXX","PWRNGSPERXX","PWRTRNPERXX","PWRBCKPERXX"]:
        o=val(b,"CapitalCost",tech,2030); nn=val(n,"CapitalCost",tech,2030)
        ok="OK" if o==nn else "*** CHANGED ***"
        if o!=nn: fail=True
        print(f"  CapitalCost  {tech:12s}: {base}={o}  {new}={nn}  (UNCHANGED expected) {ok}")
    # backstop VariableCost intact
    o=val(b,"VariableCost","PWRBCKPERXX",2030); nn=val(n,"VariableCost","PWRBCKPERXX",2030)
    if o!=nn: fail=True
    print(f"  VariableCost PWRBCKPERXX: {base}={o}  {new}={nn}  (backstop UNCHANGED in solve) {'OK' if o==nn else '*** CHANGED ***'}")
    # line-count parity (structure intact)
    lo=sum(1 for _ in open(b,encoding='utf-8',errors='replace')); ln=sum(1 for _ in open(n,encoding='utf-8',errors='replace'))
    if lo!=ln: fail=True
    print(f"  line counts: {base}={lo}  {new}={ln}  ({'IDENTICAL structure' if lo==ln else '*** DIFFERS ***'})")
print("\nDONE" + ("" if not fail else "  *** SELF-CHECK FAILED ***"))
sys.exit(1 if fail else 0)
