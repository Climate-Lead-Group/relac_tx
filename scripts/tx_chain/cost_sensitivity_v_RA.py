# -*- coding: utf-8 -*-
"""RA (Renovables Altos) cost-sensitivity transform: renewable CapitalCost ONLY.
PENDIENTE (2026-09-16): CALIBRAR los multiplicadores de Renovables Altos. Hoy son los de RB
(renovables baratas), es decir, el escenario aun NO representa renovables caras.
Copia estructural de cost_sensitivity_v_RB.py (2026-09-16): misma logica, mismas familias,
mismo self-check. Los MULTIPLICADORES se ajustan manualmente en la seccion "tunable knobs";
el self-check se deriva de esos knobs, asi que no hay que tocar nada mas al cambiarlos.
Restricted to the B* and I* scenarios. Reads a base VEGCON .txt, scales CapitalCost of
solar, wind and battery storage, writes a new datafile. Only VALUES change; structure/bounds
untouched -> feasibility preserved. Backstop is left AS-IS in the solve.

Multipliers (PLACEHOLDER = RB; PENDIENTE CALIBRAR Renovables Altos):
  - PWRSPV/PWRCSP x0.60 (NREL ATB 2024 PV Moderate; EIA AEO2025 Low Zero-Carbon Tech Cost)
  - PWRWON/PWRWOF x0.75 (NREL ATB 2024 land-based wind Moderate [EST]; shallower than PV)
  - PWRSDS x0.50 (NREL ATB 2024 utility battery Moderate)
  - PWRLDS EXCLUDED (no literature basis; base trajectory already declines 56%)
  - fossil MIN* VariableCost UNCHANGED (that is the FA/FB scripts)
Pairs: BAC->BRA, INV->IRA.

Datafile location (same convention as cost_sensitivity_v_SR_WF.py):
  default            -> flat in outputs/tx_chain/
  --executables-dir  -> <dir>/<S>_0/<datafile>  (B2 Executables layout; BRA_0/, IRA_0/ created)"""
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
    d = EXEDIR / f"{s}_0"                # modo Executables: BRA_0/, IRA_0/ se crean aqui
    d.mkdir(parents=True, exist_ok=True)
    return d / FN(s)

# base scenario -> new scenario code (only B* and I*)
PAIRS={"BAC":"BRA", "INV":"IRA"}

# ----- tunable knobs ----- PENDIENTE: calibrar Renovables Altos (valores actuales = RB)
VRE_MULT   = 0.6                       # solar CapitalCost x0.6
WIND_MULT  = 0.75                      # wind CapitalCost x0.75 (shallower decline than PV)
STO_MULT   = 0.5                       # battery storage CapitalCost x0.5
VRE_FAMS   = {"PWRSPV","PWRCSP"}       # the genuinely-declining solar
WIND_FAMS  = {"PWRWON","PWRWOF"}
STO_FAMS   = {"PWRSDS"}                # batteries only; PWRLDS excluded (no literature basis)

def transform(src, dst):
    lines=open(src,encoding="utf-8",errors="replace").read().splitlines(keepends=True)
    out=[]; cur=None; n_cap=0
    for ln in lines:
        s=ln.strip()
        m=re.match(r"param\b.*:\s*(\w+)\s*:=", s)
        if m: cur=m.group(1); out.append(ln); continue
        if cur and s==";": cur=None; out.append(ln); continue
        if cur=="CapitalCost" and s.startswith("GLOBAL"):
            t=ln.split()
            if len(t)>=4:
                fam=t[1][:6]; val=t[-1]
                try: v=float(val)
                except: out.append(ln); continue
                mult=None
                if fam in VRE_FAMS: mult=VRE_MULT
                elif fam in WIND_FAMS: mult=WIND_MULT
                elif fam in STO_FAMS: mult=STO_MULT
                if mult is not None:
                    nv=v*mult
                    t[-1]=f"{nv:.6g}"
                    out.append(" ".join(t)+"\n")
                    n_cap+=1
                    continue
        out.append(ln)
    open(dst,"w",encoding="utf-8",newline="").write("".join(out))
    return n_cap

for base,new in PAIRS.items():
    src=LOCAL(base); dst=LOCAL(new)
    if not src.exists(): sys.exit(f"missing base datafile: {src}")
    nc=transform(src,dst)
    print(f"[{base}->{new}] scaled {nc} CapitalCost rows (solar/wind/storage); VariableCost untouched")
    print(f"   wrote {dst.name}  ({os.path.getsize(dst):,} bytes)")

# ---- SELF-CHECK (preflight): confirm the scaling landed and structure is intact ----
def val(path,param,tech,year):
    txt=open(path,encoding="utf-8",errors="replace").read()
    blk=re.search(r"param[^\n:]*:\s*"+param+r"\s*:=(.*?);",txt,re.S).group(1)
    for l in blk.splitlines():
        t=l.split()
        if len(t)>=4 and t[1]==tech and t[-2]==str(year): return float(t[-1])
    return None

L_VRE=f"x{VRE_MULT:g}"; L_WIND=f"x{WIND_MULT:g}"; L_STO=f"x{STO_MULT:g}"
EXPECTED={L_VRE:VRE_MULT,L_WIND:WIND_MULT,L_STO:STO_MULT,"UNCHANGED":1.0}
fail=False
for base,new in PAIRS.items():
    b=LOCAL(base); n=LOCAL(new)
    print("\n"+"="*66+f"\nSELF-CHECK: {new} vs {base} sample values (2030)\n"+"="*66)
    for param,tech,exp in [("CapitalCost","PWRSPVPERXX",L_VRE),("CapitalCost","PWRCSPPERXX",L_VRE),
                           ("CapitalCost","PWRWONPERXX",L_WIND),("CapitalCost","PWRWOFPERXX",L_WIND),
                           ("CapitalCost","PWRSDSPERXX",L_STO),("CapitalCost","PWRLDSPERXX","UNCHANGED"),
                           ("CapitalCost","PWRNGSPERXX","UNCHANGED"),("CapitalCost","PWRHYDPERXX","UNCHANGED"),
                           ("CapitalCost","PWRTRNPERXX","UNCHANGED"),("CapitalCost","PWRBCKPERXX","UNCHANGED")]:
        o=val(b,param,tech,2030); nn=val(n,param,tech,2030)
        r=(nn/o) if (o and nn) else None
        if r is not None and abs(r-EXPECTED[exp])>1e-3: fail=True
        print(f"  {param:12s} {tech:12s}: {base}={o}  {new}={nn}  ratio={r:.3f}  ({exp})" if r else f"  {tech}: {base}={o} {new}={nn}")
    # VariableCost fuel must be UNCHANGED (that is the FA script)
    for tech in ["MINCOAPER","MINGASPER","MINOILPER"]:
        o=val(b,"VariableCost",tech,2030); nn=val(n,"VariableCost",tech,2030)
        r=(nn/o) if (o and nn) else None
        if r is not None and abs(r-1.0)>1e-3: fail=True
        print(f"  VariableCost {tech:12s}: {base}={o}  {new}={nn}  ratio={r:.3f}  (UNCHANGED)" if r else f"  {tech}: {base}={o} {new}={nn}")
    o=val(b,"VariableCost","PWRBCKPERXX",2030); nn=val(n,"VariableCost","PWRBCKPERXX",2030)
    if o!=nn: fail=True
    print(f"  VariableCost PWRBCKPERXX: {base}={o}  {new}={nn}  (backstop UNCHANGED in solve) {'OK' if o==nn else '*** CHANGED ***'}")
    # line-count parity (structure intact)
    lo=sum(1 for _ in open(b,encoding='utf-8',errors='replace')); ln=sum(1 for _ in open(n,encoding='utf-8',errors='replace'))
    if lo!=ln: fail=True
    print(f"\n  line counts: {base}={lo}  {new}={ln}  ({'IDENTICAL structure' if lo==ln else '*** DIFFERS ***'})")
print("\nDONE" + ("" if not fail else "  *** SELF-CHECK FAILED ***"))
sys.exit(1 if fail else 0)
