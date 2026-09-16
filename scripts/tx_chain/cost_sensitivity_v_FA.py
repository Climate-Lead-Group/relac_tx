# -*- coding: utf-8 -*-
"""FA (Fosiles Altos) cost-sensitivity transform: pricier fossil fuel ONLY.
Split of the former CR (combined) sensitivity, script retired: this script keeps only the
fossil-fuel leg (renewable CapitalCost is left untouched; see cost_sensitivity_v_RB.py
for the other half). Restricted to the B* and I* scenarios. Reads a base VEGCON .txt,
scales VariableCost of the fossil MIN* supply technologies, writes a new datafile.
Only VALUES change; structure/bounds untouched -> feasibility preserved. Backstop is
left AS-IS in the solve (deterrent); its reframe is done in post-processing.

Multiplier per sensitivity_multipliers_calibration.md:
  - fossil MIN* VariableCost x1.70 (EIA AEO2025 High Oil Price, 155/91 [derived])
  - MINURN excluded (not fossil)
  - CapitalCost of PWRSPV/PWRCSP/PWRWON/PWRWOF/PWRSDS UNCHANGED (that is the RB script)
Pairs: BAC->BFA, INV->IFA.

Datafile location (same convention as cost_sensitivity_v_SR_WF.py):
  default            -> flat in outputs/tx_chain/
  --executables-dir  -> <dir>/<S>_0/<datafile>  (B2 Executables layout; BFA_0/, IFA_0/ created)"""
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
    d = EXEDIR / f"{s}_0"                # modo Executables: BFA_0/, IFA_0/ se crean aqui
    d.mkdir(parents=True, exist_ok=True)
    return d / FN(s)

# base scenario -> new scenario code (only B* and I*)
PAIRS={"BAC":"BFA", "INV":"IFA"}

# ----- tunable knobs -----
FUEL_MULT  = 1.7                       # fossil fuel supply VariableCost x1.7
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
            if len(t)>=4:
                fam=t[1][:6]; val=t[-1]
                try: v=float(val)
                except: out.append(ln); continue
                if fam in FUEL_MIN:
                    nv=v*FUEL_MULT
                    t[-1]=f"{nv:.6g}"
                    out.append(" ".join(t)+"\n")
                    n_vc+=1
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

# ---- SELF-CHECK (preflight): confirm the scaling landed and structure is intact ----
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
    # CapitalCost must be UNCHANGED everywhere (renewables included)
    for tech in ["PWRSPVPERXX","PWRWONPERXX","PWRSDSPERXX","PWRLDSPERXX",
                 "PWRNGSPERXX","PWRHYDPERXX","PWRTRNPERXX","PWRBCKPERXX"]:
        o=val(b,"CapitalCost",tech,2030); nn=val(n,"CapitalCost",tech,2030)
        r=(nn/o) if (o and nn) else None
        if r is not None and abs(r-1.0)>1e-3: fail=True
        print(f"  CapitalCost  {tech:12s}: {base}={o}  {new}={nn}  ratio={r:.3f}  (UNCHANGED)" if r else f"  {tech}: {base}={o} {new}={nn}")
    # VariableCost fuel x1.7 (all fossil MIN*), URN unchanged
    for tech,exp in [("MINCOAPER",FUEL_MULT),("MINGASPER",FUEL_MULT),("MINOILPER",FUEL_MULT),
                     ("MINPETPER",FUEL_MULT),("MINOTHPER",FUEL_MULT),("MINCOGPER",FUEL_MULT),
                     ("MINURNPER",1.0)]:
        o=val(b,"VariableCost",tech,2030); nn=val(n,"VariableCost",tech,2030)
        r=(nn/o) if (o and nn) else None
        if r is not None and abs(r-exp)>1e-3: fail=True
        print(f"  VariableCost {tech:12s}: {base}={o}  {new}={nn}  ratio={r:.3f}  (x{exp})" if r else f"  {tech}: {base}={o} {new}={nn}")
    o=val(b,"VariableCost","PWRBCKPERXX",2030); nn=val(n,"VariableCost","PWRBCKPERXX",2030)
    if o!=nn: fail=True
    print(f"  VariableCost PWRBCKPERXX: {base}={o}  {new}={nn}  (backstop UNCHANGED in solve) {'OK' if o==nn else '*** CHANGED ***'}")
    # line-count parity (structure intact)
    lo=sum(1 for _ in open(b,encoding='utf-8',errors='replace')); ln=sum(1 for _ in open(n,encoding='utf-8',errors='replace'))
    if lo!=ln: fail=True
    print(f"\n  line counts: {base}={lo}  {new}={ln}  ({'IDENTICAL structure' if lo==ln else '*** DIFFERS ***'})")
print("\nDONE" + ("" if not fail else "  *** SELF-CHECK FAILED ***"))
sys.exit(1 if fail else 0)
