# -*- coding: utf-8 -*-
"""
veg_tx_constraints.py
=====================
Implementacion de referencia (reproducible) de las reglas de transmision del
modelo RELAC / OSeMOSYS, workstream FIG 3. Escribe SOBRE COPIAS del datafile
MathProg de cada escenario; nunca toca los originales.

Tres reglas:

  A. LINEAS NUEVAS NO PLANIFICADAS (familias TRNNLI, RNWNLI)
     Tope de inversion = trayectoria absoluta de inversion regional, repartida
     por pais con shares s(c), convertida a GW via CapitalCost. Anos 2030+.
     Solo en los vegetativos (INV, VGB). Es aditiva: convive con las lineas
     planificadas (que define Andrey en <=2029) y con la repotenciacion.

  B. REPOTENCIACION (familias TRNRPO, RNWRPO)
     Tope fisico derivado del stock EXISTENTE (no del residual de la propia
     tech de repotenciacion, que en RELAC es 0; el stock vive en PWRTRN/RNWTRN).
     Solo flujo anual (TotalAnnualMaxCapacityInvestment): rampa 2% (2028) a 3%
     (2040), congelado en 3% despues. SIN techo acumulado. Los 4 escenarios.

  C. ESCALADA DE COSTO
     +0.3% real/ano al CapitalCost de las 6 familias Tx (el costo hoy es
     constante en el modelo, verificado). Los 4 escenarios.

DERIVACION (trazable; referencias completas al final del archivo)
-----------------------------------------------------------------
  Nivel NLI 3000 MUSD @2022: IEA Latin America Energy Outlook 2023, via SEGIB
    (transmision LAC se multiplica x6.5 hasta >20000 MUSD en 2050 -> 20000/6.5
    = ~3077 ~ 3000 en 2022). Crece a 1.9%/ano (tendencia historica), muy por
    debajo del x6.5 (~7%/ano) de la necesidad APS.
  Repotenciacion flujo rampa 2%->3%: la actividad de reemplazo de red en
    economias emergentes sube de forma sostenida hasta 2040 en el APS (IEA
    "Building the Future Transmission Grid", feb 2025). El 2% de arranque es la
    tasa de reemplazo de lineas en EMDE (~2%/ano, misma IEA); el 3% de llegada es
    la tasa de reemplazo de transformadores en EMDE (~3%/ano, misma IEA). Rampa
    lineal 2028->2040, congelada en 3% despues (se mantiene el ritmo alcanzado).
  Sin techo acumulado: el flujo anual es el unico control (decision del proyecto,
    2026-07-09). Se elimina el techo de 40% que existia antes.
  Inicio repotenciacion 2028: los proyectos tardan 18m-3a (GridLab); una decision
    de 2026 no entrega antes de ~2028. El modelo ya bloquea repotenciacion <2028.
  Costo +0.3%/ano: metales (cobre+aluminio) son ~25-30% del CAPEX (Thunder Said/
    PJM) con crecimiento real neto ~+0.3%/ano (Goldman 2025); el resto sin
    tendencia documentada (Gorman, Mills, Wiser, LBNL 2019). El choque 2019-24
    (IEA 2025) es de NIVEL, no de pendiente.
"""
import shutil
from pathlib import Path

# ============================ USER CONFIGURATION ============================
HERE = Path(__file__).resolve().parent
EXE = HERE.parent / "t1_confection" / "Executables"

# Escenario -> (datafile origen, aplica regla NLI?). Repotenciacion y costo
# aplican a los 4 (regla fisica). NLI solo a los vegetativos.
SCENARIOS = {
    "BAU": (EXE / "BAU_0" / "Pre_processed_BAU_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt", False),
    "OPT": (EXE / "OPT_0" / "Pre_processed_OPT_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt", False),
    "INV": (EXE / "INV_0" / "Pre_processed_INV_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt", True),
    "VGB": (EXE / "VGB_0" / "Pre_processed_VGB_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt", True),
}
OUT_DIR = HERE

# --- Regla A: lineas nuevas no planificadas -------------------------------
ANCHOR_YEAR, ANCHOR_MUSD = 2022, 3000.0     # SEGIB/IEA
GROWTH = 0.019                              # tendencia historica
NLI_FIRST_YEAR = 2030                       # no planificadas: no antes de 2030
REN_SHARE_2050 = 0.70                       # glide desde mezcla existente a esto
# (REN_SHARE en 2030 se calcula de la mezcla del stock existente en el archivo)

# --- Regla B: repotenciacion (flujo rampa, SIN techo acumulado) -----------
RPO_FIRST_YEAR = 2028
RPO_PCT_START = 0.02        # 2028: tasa de reemplazo de lineas EMDE (IEA 2025)
RPO_PCT_END = 0.03          # 2040+: tasa de reemplazo de transformadores EMDE (IEA 2025)
RPO_RAMP_END = 2040         # rampa lineal 2028->2040, luego congelado
RPO_SOURCE = {"TRNRPO": "PWRTRN", "RNWRPO": "RNWTRN"}  # repo -> stock existente

# --- Regla C: escalada de costo -------------------------------------------
COST_ESC_FROM, COST_ESC_RATE = 2025, 0.003  # +0.3% real/ano

LAST_YEAR = 2050
FAM6 = ("PWRTRN", "RNWTRN", "TRNNLI", "RNWNLI", "TRNRPO", "RNWRPO")

# --- Shares por pais: max entre fuentes (BLEND balanceado, sin sub-contar) --
# Deep research (MUSD/ano, regulador nacional).  BNAM = capex acumulado del
# pipeline (se anualiza /3 [EST]).  FALLBACK = literatura, extremo bajo [EST].
DEEP = {"BRA": 3500, "MEX": 700, "CHL": 700, "COL": 400, "PER": 425, "PRY": 175,
        "ECU": 120, "URY": 100, "PAN": 100, "BOL": 90, "DOM": 70, "CRI": 70,
        "ARG": 65, "GTM": 60, "NIC": 65, "HND": 50, "SLV": 40, "HTI": 15, "BRB": 7}
FALLBACK = {"BRA": 1000, "MEX": 500, "CHL": 300, "PER": 200, "ARG": 100,
            "COL": 100, "ECU": 100, "URY": 100, "DOM": 100, "BOL": 50, "PRY": 50,
            "PAN": 30, "GTM": 30, "CRI": 30, "HND": 10, "SLV": 10, "NIC": 5,
            "HTI": 2, "BRB": 2}
BNAM_CUM = {"BRA": 10643, "CHL": 2131, "COL": 1339, "PER": 608, "URY": 200,
            "DOM": 199, "HND": 164, "BOL": 145, "PRY": 100, "ARG": 91,
            "ECU": 21, "PAN": 18, "SLV": 3}   # acumulado; /3 para anualizar [EST]
BNAM_YEARS = 3   # [EST] duracion del pipeline para anualizar BNamericas
# ===========================================================================

TARGET_PARAMS = ("CapitalCost", "TotalAnnualMaxCapacityInvestment",
                 "TotalAnnualMaxCapacity", "ResidualCapacity")


def i_region(y):
    return ANCHOR_MUSD * (1 + GROWTH) ** (y - ANCHOR_YEAR)


def rpo_pct(y):
    """Flujo de repotenciacion: rampa lineal 2%->3% (2028-2040), congelado 3%."""
    if y < RPO_FIRST_YEAR:
        return 0.0
    if y >= RPO_RAMP_END:
        return RPO_PCT_END
    return RPO_PCT_START + (RPO_PCT_END - RPO_PCT_START) * \
        (y - RPO_FIRST_YEAR) / (RPO_RAMP_END - RPO_FIRST_YEAR)


def final_shares():
    """max(DR, fallback, BNam anualizado) por pais, normalizado a 1."""
    bn = {c: v / BNAM_YEARS for c, v in BNAM_CUM.items()}
    raw = {c: max(DEEP[c], FALLBACK.get(c, 0), bn.get(c, 0)) for c in DEEP}
    tot = sum(raw.values())
    return {c: v / tot for c, v in raw.items()}


def ren_share(year, ren_2030):
    """glide lineal de la mezcla existente (2030) a REN_SHARE_2050 (2050)."""
    if year <= NLI_FIRST_YEAR:
        return ren_2030
    f = (year - NLI_FIRST_YEAR) / (LAST_YEAR - NLI_FIRST_YEAR)
    return ren_2030 + (REN_SHARE_2050 - ren_2030) * f


def parse_blocks(lines):
    """{param: (lo, hi)} indices de datos (hi = fila del ';')."""
    spans, cur = {}, None
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("param") and ":=" in s:
            for p in TARGET_PARAMS:
                if f": {p} :=" in s or f":{p}:=" in s.replace(" ", ""):
                    cur = (p, i + 1)
                    break
        elif s == ";" and cur:
            spans[cur[0]] = (cur[1], i)
            cur = None
    return spans


def read_map(lines, span):
    """{(tech, year): value} y {tech: value_primer_ano} para un bloque."""
    ty, first = {}, {}
    for ln in lines[span[0]:span[1]]:
        t = ln.split()
        if len(t) == 4:
            ty[(t[1], int(t[2]))] = float(t[3])
            first.setdefault(t[1], float(t[3]))
    return ty, first


def cost_at(base, tech, year):
    """CapitalCost escalado."""
    b = base[tech]
    if year < COST_ESC_FROM:
        return b
    return b * (1 + COST_ESC_RATE) ** (year - COST_ESC_FROM)


def build_mods(lines, apply_nli, shares, ren_2030):
    """Construye los cambios por (param, tech, year). Devuelve dict de dicts."""
    spans = parse_blocks(lines)
    _, cc_base = read_map(lines, spans["CapitalCost"])
    resid_ty, _ = read_map(lines, spans["ResidualCapacity"])
    # stock existente por pais (PWRTRN/RNWTRN, constante -> tomo 2023 si esta)
    def resid(tech):
        for y in range(2023, 2028):
            if (tech, y) in resid_ty:
                return resid_ty[(tech, y)]
        return 0.0

    mod = {"CapitalCost": {}, "TotalAnnualMaxCapacityInvestment": {},
           "TotalAnnualMaxCapacity": {}}
    years = list(range(2023, LAST_YEAR + 1))

    # C. escalada de costo (6 familias, 2025+)
    for tech in cc_base:
        if tech.startswith(FAM6):
            for y in years:
                if y >= COST_ESC_FROM:
                    mod["CapitalCost"][(tech, y)] = cost_at(cc_base, tech, y)

    # techs presentes
    techs = {t for (t, _y) in resid_ty} | set(cc_base)

    # B. repotenciacion (los 4 escenarios): SOLO flujo, rampa 2%->3%, sin techo.
    # El techo acumulado se ELIMINA borrando las filas RPO de TotalAnnualMaxCapacity
    # en write_scenario (default -1 = sin limite). Aqui solo se escribe el flujo.
    for rpo, existing_fam in RPO_SOURCE.items():
        for tech in sorted(t for t in techs if t.startswith(rpo)):
            c = tech[6:9]
            rc = resid(existing_fam + c + "XX")   # stock del pais
            if rc <= 0:
                continue
            for y in range(RPO_FIRST_YEAR, LAST_YEAR + 1):
                mod["TotalAnnualMaxCapacityInvestment"][(tech, y)] = rpo_pct(y) * rc

    # A. lineas nuevas no planificadas (solo vegetativos)
    if apply_nli:
        for fam in ("TRNNLI", "RNWNLI"):
            for tech in sorted(t for t in techs if t.startswith(fam)):
                c = tech[6:9]
                if c not in shares or tech not in cc_base:
                    continue
                cumul_gw = 0.0
                for y in range(NLI_FIRST_YEAR, LAST_YEAR + 1):
                    rs = ren_share(y, ren_2030)
                    w = rs if fam == "RNWNLI" else (1 - rs)
                    musd = shares[c] * i_region(y) * w
                    gw = musd / cost_at(cc_base, tech, y)
                    cumul_gw += gw
                    mod["TotalAnnualMaxCapacityInvestment"][(tech, y)] = gw
                    mod["TotalAnnualMaxCapacity"][(tech, y)] = cumul_gw
    return mod, cc_base, resid


def write_scenario(name, src, apply_nli, shares, ren_2030):
    lines = src.read_text(encoding="utf-8").splitlines(keepends=True)
    mod, cc_base, resid = build_mods(lines, apply_nli, shares, ren_2030)

    # aplicar: sobre-escribir filas existentes, insertar las faltantes
    out, cur, seen = [], None, set()
    for ln in lines:
        s = ln.strip()
        if s.startswith("param") and ":=" in s:
            for p in ("CapitalCost", "TotalAnnualMaxCapacityInvestment",
                      "TotalAnnualMaxCapacity"):
                if f": {p} :=" in s:
                    cur, seen = p, set()
                    break
            else:
                cur = None
            out.append(ln)
            continue
        if cur and s == ";":
            for (tech, y), v in mod[cur].items():
                if (tech, y) not in seen:
                    out.append(f"GLOBAL {tech} {y} {v:.6g}\n")
            cur = None
            out.append(ln)
            continue
        if cur == "TotalAnnualMaxCapacity":
            t = ln.split()
            if len(t) == 4 and t[1].startswith(("TRNRPO", "RNWRPO")):
                continue  # ELIMINAR techo acumulado de repotenciacion (solo flujo controla)
        if cur:
            t = ln.split()
            if len(t) == 4 and (t[1], int(t[2])) in mod[cur]:
                key = (t[1], int(t[2]))
                seen.add(key)
                out.append(f"GLOBAL {t[1]} {key[1]} {mod[cur][key]:.6g}\n")
                continue
        out.append(ln)

    dst = src.parent / f"Pre_processed_{name}_0_FLOORED__VEGCON.txt"
    shutil.copy2(src, dst)
    dst.write_text("".join(out), encoding="utf-8")
    n = {p: len(mod[p]) for p in mod}
    return dst, n, cc_base, resid


def main():
    passed = failed = 0

    def chk(label, ok):
        nonlocal passed, failed
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
        passed += ok
        failed += (not ok)

    shares = final_shares()
    print("=" * 78)
    print("REGLAS DE TRANSMISION RELAC  (referencia reproducible, sobre copias)")
    print("=" * 78)
    print(f"Nivel NLI: {ANCHOR_MUSD:.0f} @{ANCHOR_YEAR} x {GROWTH*100:.1f}%/ano "
          f"(SEGIB/IEA) | NLI desde {NLI_FIRST_YEAR} | RPO desde {RPO_FIRST_YEAR} "
          f"(rampa {RPO_PCT_START*100:.0f}%->{RPO_PCT_END*100:.0f}% a {RPO_RAMP_END}, sin techo) | "
          f"costo +{COST_ESC_RATE*100:.1f}%/ano desde {COST_ESC_FROM}")

    print("\n=== Shares finales (max entre DR / BNam anualizado / fallback) ===")
    for c in sorted(shares, key=lambda x: -shares[x]):
        print(f"  {c}: {shares[c]:.3f}", end="   ")
    print()
    chk("shares suman 1", abs(sum(shares.values()) - 1) < 1e-9)

    for name, (src, apply_nli) in SCENARIOS.items():
        if not src.exists():
            print(f"\n[SKIP] {name}: no existe {src.name}")
            continue
        dst, n, cc_base, resid = write_scenario(name, src, apply_nli, shares, ren_from(src))
        rule = "NLI + RPO + costo" if apply_nli else "RPO + costo (fisica)"
        print(f"\n--- {name} ({rule}) -> {dst.name}")
        print(f"    celdas: CapitalCost={n['CapitalCost']} "
              f"MaxCapInv={n['TotalAnnualMaxCapacityInvestment']} "
              f"MaxCap={n['TotalAnnualMaxCapacity']}")

    # verificacion de valores (sobre INV)
    print("\n=== VERIFICACION (INV) ===")
    inv_src = SCENARIOS["INV"][0]
    lines = inv_src.read_text(encoding="utf-8").splitlines(keepends=True)
    mod, cc_base, resid = build_mods(lines, True, shares, ren_from(inv_src))
    # B: repotenciacion Brasil, rampa 2%->3% del stock PWRTRN(78), sin techo
    rc_pwr = resid("PWRTRNBRAXX")
    f28 = mod["TotalAnnualMaxCapacityInvestment"].get(("TRNRPOBRAXX", 2028))
    f40 = mod["TotalAnnualMaxCapacityInvestment"].get(("TRNRPOBRAXX", 2040))
    f50 = mod["TotalAnnualMaxCapacityInvestment"].get(("TRNRPOBRAXX", 2050))
    chk(f"RPO flujo BRA 2028 = 2% de PWRTRN({rc_pwr:.0f}) = {0.02*rc_pwr:.3f}",
        abs(f28 - 0.02 * rc_pwr) < 1e-6)
    chk(f"RPO flujo BRA 2040 y 2050 = 3% = {0.03*rc_pwr:.3f} (rampa y congelado)",
        abs(f40 - 0.03 * rc_pwr) < 1e-6 and abs(f50 - 0.03 * rc_pwr) < 1e-6)
    chk("RPO SIN techo acumulado (nada en TotalAnnualMaxCapacity para RPO)",
        not any(t.startswith(("TRNRPO", "RNWRPO")) for (t, _y) in mod["TotalAnnualMaxCapacity"]))
    # A: NLI no antes de 2030
    chk("NLI sin celdas antes de 2030",
        not any(y < NLI_FIRST_YEAR for (_t, y) in mod["TotalAnnualMaxCapacityInvestment"]
                if _t.startswith(("TRNNLI", "RNWNLI"))))
    # C: costo 2050 = base x 1.003^25
    cc50 = mod["CapitalCost"].get(("TRNNLIBRAXX", 2050))
    chk(f"costo TRNNLIBRA 2050 = base x 1.003^25 ({cc_base['TRNNLIBRAXX']*1.003**25:.2f})",
        abs(cc50 - cc_base["TRNNLIBRAXX"] * 1.003 ** 25) < 1e-3)
    # ren glide
    r30 = ren_from(inv_src)
    print(f"  reparto NLI renovable: {r30*100:.0f}% (2030) -> {REN_SHARE_2050*100:.0f}% (2050)")

    # PREFLIGHT: relee los .txt del vegetativo y verifica valor deseado + factibilidad
    print("\n=== PREFLIGHT (lee los .txt del VEGETATIVO, independiente del BAU) ===")
    for name in ("INV", "VGB"):
        dst = SCENARIOS[name][0].parent / f"Pre_processed_{name}_0_FLOORED__VEGCON.txt"
        if not dst.exists():
            continue
        ser, pp, pf = preflight(name, dst)
        passed += pp
        failed += pf
        if name == "INV":
            png = OUT_DIR / "veg_preflight.png"
            plot_preflight(ser, png)
            print(f"  PNG: {png.name}")

    print(f"\nRESULTADO: PASS={passed} FAIL={failed}")
    print_deliverables()


def ren_from(src):
    """mezcla renovable del stock existente (RNWTRN / (PWRTRN+RNWTRN))."""
    lines = src.read_text(encoding="utf-8").splitlines(keepends=True)
    spans = parse_blocks(lines)
    resid_ty, _ = read_map(lines, spans["ResidualCapacity"])
    pwr = sum(v for (t, y), v in resid_ty.items() if t.startswith("PWRTRN") and y == 2023)
    rnw = sum(v for (t, y), v in resid_ty.items() if t.startswith("RNWTRN") and y == 2023)
    return rnw / (pwr + rnw) if (pwr + rnw) else 0.4


def preflight(name, dst):
    """Lee el .txt escrito del VEGETATIVO y reconstruye inversion y capacidad
    implicitas (pre-solve). Es un test independiente: no confia en el calculo,
    relee el archivo. Devuelve (series, n_pass, n_fail)."""
    lines = dst.read_text(encoding="utf-8").splitlines(keepends=True)
    spans = parse_blocks(lines)
    cc, _ = read_map(lines, spans["CapitalCost"])
    inv, _ = read_map(lines, spans["TotalAnnualMaxCapacityInvestment"])
    cap, _ = read_map(lines, spans["TotalAnnualMaxCapacity"])
    resid_ty, _ = read_map(lines, spans["ResidualCapacity"])
    years = list(range(RPO_FIRST_YEAR, LAST_YEAR + 1))
    nli_f, rpo_f = ("TRNNLI", "RNWNLI"), ("TRNRPO", "RNWRPO")

    # inversion NLI reconstruida = tope_GW x CapitalCost (debe dar la trayectoria)
    nli_musd = {y: sum(gw * cc.get((t, y), 0.0) for (t, yy), gw in inv.items()
                       if yy == y and t.startswith(nli_f)) for y in years}
    # inversion RPO = flujo anual x costo (sin techo: el flujo es el unico control)
    rpo_musd = {y: sum(gw * cc.get((t, y), 0.0) for (t, yy), gw in inv.items()
                       if yy == y and t.startswith(rpo_f)) for y in years}
    resid_exist = sum(v for (t, yy), v in resid_ty.items()
                      if t.startswith(("PWRTRN", "RNWTRN")) and yy == 2023)
    nli_cap = {y: sum(v for (t, yy), v in cap.items()
                      if yy == y and t.startswith(nli_f)) for y in years}
    # capacidad RPO acumulada = suma corrida del flujo (ya no hay techo que leer)
    rpo_cap, _run = {}, 0.0
    for y in years:
        _run += sum(gw for (t, yy), gw in inv.items() if yy == y and t.startswith(rpo_f))
        rpo_cap[y] = _run

    pp = pf = 0

    def t(label, ok):
        nonlocal pp, pf
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
        pp += ok
        pf += (not ok)

    tgt = all(abs(nli_musd[y] - i_region(y)) < 0.01 * i_region(y)
              for y in range(NLI_FIRST_YEAR, LAST_YEAR + 1))
    t(f"[{name}] valor deseado: NLI regional = 3000->5000 "
      f"(2030={nli_musd[2030]:.0f}, 2050={nli_musd[2050]:.0f})", tgt)
    # flujo GW congelado en 3% tras 2040 (la inversion MUSD sube algo por el +0.3% costo)
    gw40 = sum(gw for (t2, yy), gw in inv.items() if yy == 2040 and t2.startswith(rpo_f))
    gw50 = sum(gw for (t2, yy), gw in inv.items() if yy == 2050 and t2.startswith(rpo_f))
    t(f"[{name}] RPO no se auto-detiene: flujo GW congelado 3% (2040={gw40:.1f}=2050={gw50:.1f}), "
      f"inv 2050={rpo_musd[2050]:.0f} MUSD>0", abs(gw40 - gw50) < 1e-6 and rpo_musd[2050] > 1.0)
    totcap = {y: resid_exist + nli_cap[y] + rpo_cap[y] for y in years}
    nd = all(totcap[y] >= totcap[y - 1] - 1e-6 for y in years[1:])
    t(f"[{name}] feasible: capacidad total no decrece y crece sobre el "
      f"residual ({resid_exist:.0f} -> {totcap[2050]:.0f} GW)",
      nd and totcap[2050] > resid_exist)
    ser = {"years": years, "nli": nli_musd, "rpo": rpo_musd, "resid": resid_exist,
           "nli_cap": nli_cap, "rpo_cap": rpo_cap}
    return ser, pp, pf


def plot_preflight(ser, png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "DejaVu Sans"
    GRY, VGA, DK, TXT = "#9BB0B8", "#C9622E", "#00414D", "#0F2E36"
    ys = ser["years"]
    nli = [ser["nli"][y] for y in ys]
    rpo = [ser["rpo"][y] for y in ys]
    ireg = [i_region(y) for y in ys]

    fig, ax = plt.subplots(1, 2, figsize=(12.5, 4.8))
    ax[0].fill_between(ys, 0, nli, color=VGA, alpha=.85, label="Lineas nuevas (NLI)")
    ax[0].fill_between(ys, nli, [a + b for a, b in zip(nli, rpo)], color=DK,
                       alpha=.8, label="Repotenciacion (RPO)")
    ax[0].plot(ys, ireg, "--", color=TXT, lw=1.5, label="Objetivo 3000->5000 (1.9%)")
    ax[0].set_title("PREFLIGHT inversion Tx VEGETATIVO (MUSD/ano)", color=TXT, fontsize=11)
    ax[0].set_ylabel("MUSD/ano")
    ax[0].legend(fontsize=8)
    ax[0].set_ylim(bottom=0)
    ax[0].annotate("RPO: rampa 2%->3% (2028-2040),\nluego constante (sin techo)",
                   (2037, ser["nli"][2037] + ser["rpo"][2037]),
                   xytext=(2038, 1600), fontsize=8, color="white",
                   arrowprops=dict(arrowstyle="->", color=DK))

    resid = ser["resid"]
    nlic = [ser["nli_cap"][y] for y in ys]
    rpoc = [ser["rpo_cap"][y] for y in ys]
    base = [resid] * len(ys)
    mid = [resid + a for a in nlic]
    top = [resid + a + b for a, b in zip(nlic, rpoc)]
    ax[1].fill_between(ys, 0, base, color=GRY, alpha=.8, label=f"Existente ({resid:.0f} GW)")
    ax[1].fill_between(ys, base, mid, color=VGA, alpha=.85, label="Lineas nuevas (acum)")
    ax[1].fill_between(ys, mid, top, color=DK, alpha=.8, label="Repotenciacion (acum)")
    ax[1].set_title("PREFLIGHT capacidad Tx permitida (GW)", color=TXT, fontsize=11)
    ax[1].set_ylabel("GW")
    ax[1].legend(fontsize=8)
    ax[1].set_ylim(bottom=0)
    for a in ax:
        a.grid(alpha=.25)
        a.tick_params(colors=TXT)
    fig.tight_layout()
    fig.savefig(png, dpi=130)


def print_deliverables():
    print("\n" + "=" * 78)
    print("ENTREGABLE REPORTE (texto)")
    print("=" * 78)
    print(
        "El modelo tiende a sobre-invertir en repotenciacion porque es barata "
        "(0.45x una linea nueva) y el fin de horizonte la favorece, produciendo "
        "un comportamiento binario por pais. Para corregirlo se aplica, en TODOS "
        "los escenarios, un tope fisico al flujo anual de repotenciacion: parte en "
        "2% del stock de transmision existente en 2028 (tasa de reemplazo de lineas "
        "en economias emergentes, IEA 2025), sube de forma lineal hasta 3% en 2040 "
        "(tasa de reemplazo de transformadores, misma fuente; la IEA proyecta que la "
        "actividad de reemplazo crece sostenidamente hasta 2040 en el APS) y se "
        "mantiene en 3% despues. No se impone un techo acumulado: el ritmo anual es "
        "el unico control. Sobre esto, en los vegetativos, las lineas nuevas no "
        "planificadas siguen una trayectoria de inversion regional de 3000 MUSD "
        "(2022, IEA via SEGIB) creciendo 1.9%/ano, repartida por pais segun la "
        "inversion historica, muy por debajo de la necesidad de la transicion. "
        "[EST] marca los tramos estimados.")
    print("\n" + "=" * 78)
    print("ENTREGABLE ANDREY (pasos)")
    print("=" * 78)
    for i, s in enumerate([
        "Confirmar codigos TRNRPO/RNWRPO y sus pares existentes PWRTRN/RNWTRN.",
        "Leer ResidualCapacity de PWRTRN/RNWTRN por pais (el stock, constante).",
        "RPO flujo: TotalAnnualMaxCapacityInvestment = pct(ano) x stock, 2028-2050, "
        "con pct = 2% en 2028, rampa lineal a 3% en 2040, y 3% congelado 2041-2050.",
        "RPO techo: ELIMINAR TotalAnnualMaxCapacity de TRNRPO/RNWRPO (borrar filas; "
        "default -1 = sin limite). Solo el flujo controla.",
        "NLI (solo INV/VGB): TotalAnnualMaxCapacityInvestment = s(c) x I_region(ano) "
        "x reparto_ren(ano) / CapitalCost, 2030-2050; dejar <=2029 a lineas planificadas.",
        "Costo: si CapitalCost es constante, x1.003^(ano-2025) en las 6 familias.",
        "Aplicar RPO+costo en los 4 escenarios; NLI solo en los vegetativos, sobre copias.",
        "Correr y verificar: desaparece el comportamiento binario; la repotenciacion "
        "corre a 2-3%/ano sin auto-detenerse; el benchmark regional no se distorsiona.",
    ], 1):
        print(f"  {i}. {s}")


if __name__ == "__main__":
    main()
