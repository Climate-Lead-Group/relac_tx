# -*- coding: utf-8 -*-
"""v11 transform: SOLO REPOTENCIACION PLANIFICADA (RPO pinneada al piso).
v11 (2026-09-01): agrega la familia water-fill: ISRWF <- INVWF, VSRWF <- VGBWF
(archivos generados por veg_tx_constraints con WATERFILL_ENABLE=True).
Despues de este paso, correr nli_sr_recompute.py (devuelve la reserva RPO
muerta al presupuesto NLI de los 4 SR). Logica intacta desde v10.
Reads a base datafile and, for every repowering technology (families TRNRPO*/RNWRPO*,
19 countries each), sets TotalAnnualMaxCapacityInvestment = TotalAnnualMinCapacityInvestment
(the planned floor) in every model year, i.e. 0 wherever nothing is planned. The model can
then build EXACTLY the planned RPO and nothing else. TotalAnnualMinCapacityInvestment is left
UNTOUCHED. Everything else (CapitalCost, VariableCost, NLI, planned PWRTRN/RNWTRN) untouched.

Coverage guarantee (user 2026-08-27): the ceiling must exist for ALL RPO techs x ALL years.
RPO techs are derived from `set TECHNOLOGY`, years from `set YEAR`; the full cartesian product
is written -- existing rows are overwritten, missing rows are INSERTED. Never relies on the
default (-1 = unbounded) of TotalAnnualMaxCapacityInvestment.

Sources (user 2026-08-28): BSR <- BAU, ISR <- INV, VSR <- VGB, all from the local
*_VEGCON.txt files in outputs/tx_chain/ (legacy mode) or --executables-dir
(same convention as v5-v9)."""
import re, os, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> scripts/
from common import relac_paths as P

import argparse
_ap = argparse.ArgumentParser()
_ap.add_argument("--executables-dir", default=None,
                 help="Carpeta Executables de B2; resuelve cada datafile en <dir>/<S>_0/ "
                      "(default: plano en outputs/tx_chain/, comportamiento actual)")
_args, _ = _ap.parse_known_args()
EXEDIR = Path(_args.executables_dir).resolve() if _args.executables_dir else None

FN = lambda s: f"Pre_processed_{s}_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_VEGCON.txt"

def LOCAL(s):
    if EXEDIR is None:
        return P.TX_CHAIN_OUT / FN(s)     # modo legado (plano)
    d = EXEDIR / f"{s}_0"                # modo Executables: BSR_0/, ISR_0/, ... se crean aqui
    d.mkdir(parents=True, exist_ok=True)
    return d / FN(s)

# new scenario -> (base scenario code, source datafile)
SOURCES = {
    "BSR": ("BAU", LOCAL("BAU")),
    "ISR": ("INV", LOCAL("INV")),
    "VSR": ("VGB", LOCAL("VGB")),
    "ISRWF": ("INVWF", LOCAL("INVWF")),   # v11: familia water-fill (v14)
    "VSRWF": ("VGBWF", LOCAL("VGBWF")),
}

RPO_FAMILIES=("TRNRPO","RNWRPO")
MAXP="TotalAnnualMaxCapacityInvestment"
MINP="TotalAnnualMinCapacityInvestment"
REGION="GLOBAL"

def is_rpo(t): return t.startswith(RPO_FAMILIES)

def read_set(txt, name):
    m=re.search(r"^set\s+"+name+r"\s*:=(.*?);", txt, re.S|re.M)
    if not m: sys.exit(f"set {name} not found")
    return m.group(1).split()

def read_param_block(txt, name):
    """-> dict (tech, year)->value for a 'param default X : NAME :=' block."""
    m=re.search(r"^param[^\n:]*:\s*"+name+r"\s*:=(.*?)^;", txt, re.S|re.M)
    if not m: sys.exit(f"param {name} not found")
    d={}
    for l in m.group(1).splitlines():
        t=l.split()
        if len(t)>=4: d[(t[1],t[2])]=float(t[3])
    return d

def transform(src, dst):
    txt=open(src,encoding="utf-8",errors="replace").read()
    techs=[t for t in read_set(txt,"TECHNOLOGY") if is_rpo(t)]
    years=read_set(txt,"YEAR")
    floor={k:v for k,v in read_param_block(txt,MINP).items() if is_rpo(k[0])}
    target={(t,y):floor.get((t,y),0.0) for t in techs for y in years}

    lines=txt.splitlines(keepends=True)
    out=[]; cur=None; seen=set(); n_over=0; n_ins=0
    for ln in lines:
        s=ln.strip()
        m=re.match(r"param\b.*:\s*(\w+)\s*:=", s)
        if m: cur=m.group(1); out.append(ln); continue
        if cur==MAXP and s==";":
            # insert any (tech,year) not present in the source block
            for k in sorted(target):
                if k not in seen:
                    out.append(f"{REGION} {k[0]} {k[1]} {target[k]:.6g}\n"); n_ins+=1
            cur=None; out.append(ln); continue
        if cur and s==";": cur=None; out.append(ln); continue
        if cur==MAXP and s.startswith(REGION):
            t=ln.split()
            if len(t)>=4 and is_rpo(t[1]):
                k=(t[1],t[2]); seen.add(k)
                t[3]=f"{target[k]:.6g}"
                out.append(" ".join(t)+"\n"); n_over+=1
                continue
        out.append(ln)
    open(dst,"w",encoding="utf-8",newline="").write("".join(out))
    return len(techs), len(years), len(floor), n_over, n_ins

for new,(base,src) in SOURCES.items():
    if not src.is_file(): sys.exit(f"*** source for {new} not found: {src}")
    dst=LOCAL(new)
    print(f"[{base}->{new}] source: {src}")
    nt,ny,nf,no,ni=transform(str(src),str(dst))
    print(f"   RPO techs={nt} years={ny} planned-floor rows={nf} | "
          f"{MAXP}: overwrote {no}, inserted {ni} (target {nt*ny})")
    print(f"   wrote {dst.name}  ({dst.stat().st_size:,} bytes)")

# ---- SELF-CHECK: ceiling == floor for every RPO tech x year; nothing else changed ----
fail=False
for new,(base,src) in SOURCES.items():
    b=str(src); n=str(LOCAL(new))
    tb=open(b,encoding="utf-8",errors="replace").read(); tn=open(n,encoding="utf-8",errors="replace").read()
    techs=[t for t in read_set(tn,"TECHNOLOGY") if is_rpo(t)]; years=read_set(tn,"YEAR")
    countries=sorted({t[6:9] for t in techs})
    mx=read_param_block(tn,MAXP); mn_new=read_param_block(tn,MINP); mn_old=read_param_block(tb,MINP)
    print("\n"+"="*70+f"\nSELF-CHECK {new} (from {base}): {len(techs)} RPO techs, {len(countries)} countries, {len(years)} years\n"+"="*70)
    missing=[(t,y) for t in techs for y in years if (t,y) not in mx]
    bad=[(t,y,mx[(t,y)],mn_new.get((t,y),0.0)) for t in techs for y in years if (t,y) in mx and abs(mx[(t,y)]-mn_new.get((t,y),0.0))>1e-12]
    pinned=sum(1 for t in techs for y in years if mn_new.get((t,y),0.0)>0)
    zeros=len(techs)*len(years)-pinned
    print(f"  Max rows missing for RPO: {len(missing)}  {'OK' if not missing else '*** FAIL ***'}")
    print(f"  Max != Min for RPO:       {len(bad)}  {'OK' if not bad else '*** FAIL ***'}")
    print(f"  pinned to planned floor: {pinned} rows | forced to 0: {zeros} rows")
    print(f"  {MINP} unchanged: {'OK' if mn_new==mn_old else '*** CHANGED ***'}")
    # non-RPO Max rows must be identical
    mx_old=read_param_block(tb,MAXP)
    nonrpo_old={k:v for k,v in mx_old.items() if not is_rpo(k[0])}; nonrpo_new={k:v for k,v in mx.items() if not is_rpo(k[0])}
    print(f"  non-RPO {MAXP} unchanged: {'OK' if nonrpo_old==nonrpo_new else '*** CHANGED ***'}")
    for p in ("CapitalCost","VariableCost","TotalAnnualMaxCapacity"):
        print(f"  {p} unchanged: {'OK' if read_param_block(tb,p)==read_param_block(tn,p) else '*** CHANGED ***'}")
    # samples
    for tech,y in [("TRNRPOCHLXX","2030"),("RNWRPOCOLXX","2025"),("TRNRPOARGXX","2035"),("RNWRPOBRAXX","2045")]:
        print(f"  sample {MAXP} {tech} {y}: {base}={mx_old.get((tech,y),'(none, default -1)')}  {new}={mx.get((tech,y))}  (floor={mn_new.get((tech,y),0.0)})")
    lo=tb.count("\n"); ln=tn.count("\n")
    print(f"  line counts: {base}={lo}  {new}={ln}  ({'IDENTICAL structure' if lo==ln else f'+{ln-lo} inserted rows'})")
    if missing or bad or mn_new!=mn_old or nonrpo_old!=nonrpo_new: fail=True
print("\nDONE" + ("" if not fail else "  *** SELF-CHECK FAILED ***"))
sys.exit(1 if fail else 0)
