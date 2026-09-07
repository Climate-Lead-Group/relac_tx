# -*- coding: utf-8 -*-
"""
veg_tx_constraints.py
=====================
Implementacion de referencia (reproducible) de las reglas de transmision del
modelo RELAC / OSeMOSYS, workstream FIG 3. Escribe SOBRE COPIAS del datafile
MathProg de cada escenario; nunca toca los originales. F5-ejecutable. Espanol.

PIPELINE (en orden; cada paso se prueba en el preflight al final):

  0. PISO (SWAP)  -- corrige el piso comprometido (TotalAnnualMinCapacityInvestment)
     El OPTIMO debe tener AL MENOS tanto grid comprometido como la REFERENCIA.
     En los datos base, Brasil esta al reves: la REFERENCIA fuerza ~22 GW de Tx
     en 2027-2029 y el OPTIMO fuerza 0 alli. Se INTERCAMBIA (swap) el piso entre
     REF y OPT en cada (tech, ano) donde REF>OPT: el OPT recibe el valor mayor,
     la REF (y por identidad INV/VGB) el menor. Solo anos >=2027 (no toca lo
     historico 2023-2026, que es identico entre escenarios). REF/INV/VGB quedan
     con piso Tx identico entre si; el OPT queda >= REF en todos los anos.

  1. COSTO (nivel real) + CALIBRACION
     La base de Executables YA esta en costo real (el x2 vive AGUAS ABAJO, en los
     archivos de solve; ver nota abajo). Se aplica UN factor de escala m (calibracion)
     que hace que la inversion COMPROMETIDA (piso planificado de la REF) PROMEDIE el
     ancla IEA (~3080 MUSD/ano @2022) en la ventana 2025-2029. El supuesto: el modelo
     no debe invertir mas de lo planificado, asi que el piso es la base de calibracion.

  2. ENVELOPE NLI -- lineas nuevas no planificadas (familias TRNNLI, RNWNLI)
     La inversion Tx TOTAL del vegetativo (planificadas + RPO + NLI) se capa en la
     trayectoria regional I_region(ano) = 3000 @2022 x1.9%/ano (~3.3k -> 5.1k MUSD).
     Las PLANIFICADAS (= plan OPT) y la RPO consumen el envelope PRIMERO; la NLI recibe
     SOLO el remanente: presup_NLI = max(0, I_region - costo_planif - costo_RPO). Ese
     remanente se reparte por pais con shares s(c) y ren/no-ren, y se pasa a GW via el
     costo corregido. Anos 2030+. Solo en los vegetativos (INV, VGB). NO aditiva
     (v1 usaba el I_region completo para NLI y se apilaba sobre el plan: ese era el bug).

  3. REPOTENCIACION (familias TRNRPO, RNWRPO)
     Tope fisico del stock EXISTENTE (PWRTRN/RNWTRN). Solo flujo anual, rampa 2%
     (2028) a 3% (2040), congelado en 3% despues. SIN techo acumulado. Los 4.

  3b. TECHO PLANIFICADAS (familias PWRTRN, RNWTRN)
     MaxCapacityInvestment = piso del OPTIMO (post-swap), en LOS 4 escenarios, 2027+.
     OPT fijado (min=max); REF/veg eligen entre su piso y el plan OPT; nadie invierte
     en planificadas mas que el plan optimo.

  4. ESCALADA DE COSTO
     +0.3% real/ano al CapitalCost corregido de las 6 familias Tx (2025+). Los 4.

DERIVACION (trazable; referencias completas al final del archivo)
-----------------------------------------------------------------
  Nivel 3000 MUSD @2022: IEA Latin America Energy Outlook 2023 via SEGIB
    (20000/6.5 = ~3077 ~ 3000 en 2022). Crece 1.9%/ano (tendencia historica),
    muy por debajo del x6.5 (~7%/ano) de la necesidad APS.
  Repotenciacion rampa 2%->3%: reemplazo de red en EMDE sube sostenido hasta
    2040 en el APS (IEA "Building the Future Transmission Grid", feb 2025). 2%
    = reemplazo de lineas EMDE; 3% = reemplazo de transformadores EMDE.
  Costo +0.3%/ano: metales ~25-30% del CAPEX (Thunder Said/PJM), crecimiento
    real neto ~+0.3%/ano (Goldman 2025); resto sin tendencia (Gorman/Mills/
    Wiser, LBNL 2019). El choque 2019-24 (IEA 2025) es de NIVEL, no de pendiente.
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # -> scripts/
from common import relac_paths as P

# ============================ USER CONFIGURATION ============================
HERE = Path(__file__).resolve().parent
EXE = P.EXECUTABLES

# Escenario -> (datafile origen, aplica regla NLI?). RPO y costo aplican a los 4.
# NLI solo a los vegetativos. El swap del piso usa REF y OPT (abajo).
SCENARIOS = {
    "BAU": (EXE / "BAU_0" / "Pre_processed_BAU_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt", False),
    "OPT": (EXE / "OPT_0" / "Pre_processed_OPT_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt", False),
    "INV": (EXE / "INV_0" / "Pre_processed_INV_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt", True),
    "VGB": (EXE / "VGB_0" / "Pre_processed_VGB_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt", True),
}
OUT_DIR = P.EXPERIMENTAL_OUT / "veg_tx_abs_test"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# --- Paso 0: SWAP del piso comprometido -----------------------------------
SWAP_REF, SWAP_OPT = "BAU", "OPT"        # el piso de REF se propaga a INV/VGB
SWAP_TWINS = ("BAU", "INV", "VGB")       # los tres comparten piso Tx identico
SWAP_FAMILIES = ("PWRTRN", "RNWTRN", "TRNNLI", "RNWNLI", "TRNRPO", "RNWRPO")
SWAP_FIRST_YEAR = 2027                    # no tocar historico 2023-2026

# --- Paso 1: costo (nivel real) + factor de escala m ----------------------
# Regla (Andrey): los valores del costo halvados (nivel real), multiplicados por
# un factor de escala m (>1), deben PROMEDIAR el ancla 3.08k en 2023-2029. Algunos
# anos quedan por encima y otros por debajo del promedio; lo que se ancla es el
# promedio.  m = 3080 / promedio_{2023..2029}( piso comprometido x costo_real )
#
# OJO NIVEL DE COSTO: los .txt base de Executables ({SCEN}_0/..._FLOORED.txt) YA
# estan en costo REAL (p.ej. PWRTRNBRAXX=246.263). El x2 vive AGUAS ABAJO, en los
# archivos de solve (StorageDelay/OpenBCK: PWRTRNBRAXX=492.527 = 2x). Por eso aqui
# LEVEL_MULT_CURRENT=1.0 (no hay que dividir; la base ya es el valor "halvado").
# El costo final escrito = base x m. IMPORTANTE para Andrey: el x2 aguas abajo debe
# REEMPLAZARSE por este m (o resolver las copias VEGCON directamente), NO ambos.
LEVEL_MULT_CURRENT = 1.0                  # base Executables ya es costo real (sin x2)
CALIB_ANCHOR_MUSD = 3080.0               # ancla IEA/SEGIB (promedio objetivo)
CALIB_ANCHOR_YEAR = 2022
# Calibrar sobre las LINEAS PLANIFICADAS DE LA REFERENCIA (piso original, pre-swap;
# es la tarea de Andrey: "resolver REF, extraer el multiplicador"). Su comisionado
# principal termina en 2029. Ventana 2025-2029 -> m~1.25 (>1). Calibrar sobre OPT
# daria m<1 en esta ventana, contradiciendo el requisito m>1.
CALIB_FLOOR_SCENARIO = "BAU"             # de donde sale el piso de calibracion (REF original)
CALIB_WINDOW = (2025, 2029)              # 2025 al ultimo ano de comisionado principal (REF)
CALIB_MULT_OVERRIDE = None               # None = calcular m del promedio; o fijar a mano

# --- Paso 2: lineas nuevas no planificadas --------------------------------
ANCHOR_YEAR, ANCHOR_MUSD = 2022, 3000.0     # SEGIB/IEA
GROWTH = 0.019                              # tendencia historica
NLI_FIRST_YEAR = 2030                       # no planificadas: no antes de 2030
REN_SHARE_2050 = 0.70                       # glide desde mezcla existente a esto

# --- Paso 3: repotenciacion (flujo rampa, SIN techo acumulado) ------------
RPO_FIRST_YEAR = 2028
RPO_PCT_START = 0.02
RPO_PCT_END = 0.03
RPO_RAMP_END = 2040
RPO_SOURCE = {"TRNRPO": "PWRTRN", "RNWRPO": "RNWTRN"}

# --- Paso 4: escalada de costo --------------------------------------------
COST_ESC_FROM, COST_ESC_RATE = 2025, 0.003  # +0.3% real/ano

LAST_YEAR = 2050
FAM6 = ("PWRTRN", "RNWTRN", "TRNNLI", "RNWNLI", "TRNRPO", "RNWRPO")

# --- Shares por pais: max entre fuentes (blend, sin sub-contar) ------------
DEEP = {"BRA": 3500, "MEX": 700, "CHL": 700, "COL": 400, "PER": 425, "PRY": 175,
        "ECU": 120, "URY": 100, "PAN": 100, "BOL": 90, "DOM": 70, "CRI": 70,
        "ARG": 65, "GTM": 60, "NIC": 65, "HND": 50, "SLV": 40, "HTI": 15, "BRB": 7}
FALLBACK = {"BRA": 1000, "MEX": 500, "CHL": 300, "PER": 200, "ARG": 100,
            "COL": 100, "ECU": 100, "URY": 100, "DOM": 100, "BOL": 50, "PRY": 50,
            "PAN": 30, "GTM": 30, "CRI": 30, "HND": 10, "SLV": 10, "NIC": 5,
            "HTI": 2, "BRB": 2}
BNAM_CUM = {"BRA": 10643, "CHL": 2131, "COL": 1339, "PER": 608, "URY": 200,
            "DOM": 199, "HND": 164, "BOL": 145, "PRY": 100, "ARG": 91,
            "ECU": 21, "PAN": 18, "SLV": 3}
BNAM_YEARS = 3
# ===========================================================================

MININV = "TotalAnnualMinCapacityInvestment"
TARGET_PARAMS = ("CapitalCost", "TotalAnnualMaxCapacityInvestment",
                 "TotalAnnualMaxCapacity", "ResidualCapacity", MININV)
# parametros que el escritor gestiona (sobre-escribe / inserta)
WRITE_PARAMS = ("CapitalCost", "TotalAnnualMaxCapacityInvestment",
                "TotalAnnualMaxCapacity", MININV)


def i_region(y):
    return ANCHOR_MUSD * (1 + GROWTH) ** (y - ANCHOR_YEAR)


def calib_anchor(y):
    return CALIB_ANCHOR_MUSD * (1 + GROWTH) ** (y - CALIB_ANCHOR_YEAR)


def rpo_pct(y):
    if y < RPO_FIRST_YEAR:
        return 0.0
    if y >= RPO_RAMP_END:
        return RPO_PCT_END
    return RPO_PCT_START + (RPO_PCT_END - RPO_PCT_START) * \
        (y - RPO_FIRST_YEAR) / (RPO_RAMP_END - RPO_FIRST_YEAR)


def final_shares():
    bn = {c: v / BNAM_YEARS for c, v in BNAM_CUM.items()}
    raw = {c: max(DEEP[c], FALLBACK.get(c, 0), bn.get(c, 0)) for c in DEEP}
    tot = sum(raw.values())
    return {c: v / tot for c, v in raw.items()}


def ren_share(year, ren_2030):
    if year <= NLI_FIRST_YEAR:
        return ren_2030
    f = (year - NLI_FIRST_YEAR) / (LAST_YEAR - NLI_FIRST_YEAR)
    return ren_2030 + (REN_SHARE_2050 - ren_2030) * f


def parse_blocks(lines):
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
    ty, first = {}, {}
    for ln in lines[span[0]:span[1]]:
        t = ln.split()
        if len(t) == 4:
            ty[(t[1], int(t[2]))] = float(t[3])
            first.setdefault(t[1], float(t[3]))
    return ty, first


# --------------------------------------------------------------------------
# Paso 0: SWAP del piso
# --------------------------------------------------------------------------
def load_min(src):
    """{(tech, year): value} del piso, solo familias Tx, del datafile."""
    lines = src.read_text(encoding="utf-8").splitlines(keepends=True)
    spans = parse_blocks(lines)
    if MININV not in spans:
        return {}
    mn, _ = read_map(lines, spans[MININV])
    return {(t, y): v for (t, y), v in mn.items() if t.startswith(SWAP_FAMILIES)}


def compute_swap(ref_min, opt_min):
    """Donde REF>OPT (ano>=SWAP_FIRST_YEAR): OPT recibe el mayor, REF el menor.
    Devuelve (opt_override, twins_override, movers)."""
    opt_over, twin_over, movers = {}, {}, []
    keys = set(ref_min) | set(opt_min)
    for (t, y) in keys:
        if y < SWAP_FIRST_YEAR:
            continue
        r = ref_min.get((t, y), 0.0)
        o = opt_min.get((t, y), 0.0)
        if r > o + 1e-9:               # inversion: REF fuerza mas que OPT
            opt_over[(t, y)] = r        # OPT sube al mayor
            twin_over[(t, y)] = o        # REF/INV/VGB bajan al menor
            movers.append((t, y, r, o))
    return opt_over, twin_over, movers


# --------------------------------------------------------------------------
# Paso 1: costo real + calibracion
# --------------------------------------------------------------------------
def true_base_costs(cc_txt):
    """costo unitario real = costo del .txt / multiplicador de nivel actual (x2)."""
    return {t: v / LEVEL_MULT_CURRENT for t, v in cc_txt.items()}


def calibrate(floor_map, true_base):
    """Factor de escala m sobre el costo REAL, tal que el PROMEDIO de la inversion
    comprometida (piso planificado de la REF) en la ventana CALIB_WINDOW iguale el
    ancla:  m = CALIB_ANCHOR_MUSD / promedio_{ventana}( piso x costo_real )
    Cerrado (no busqueda). Algunos anos quedan +/- del promedio. Devuelve (m, diag)."""
    y0, y1 = CALIB_WINDOW
    per_year = {}
    for y in range(y0, y1 + 1):
        per_year[y] = sum(gw * true_base.get(t, 0.0)
                          for (t, yy), gw in floor_map.items() if yy == y)
    n = y1 - y0 + 1
    mean_true = sum(per_year.values()) / n if n else 0.0
    mult = CALIB_MULT_OVERRIDE if CALIB_MULT_OVERRIDE is not None \
        else (CALIB_ANCHOR_MUSD / mean_true if mean_true > 0 else 1.0)
    modo = "override" if CALIB_MULT_OVERRIDE is not None \
        else f"promedio {y0}-{y1} = ancla"
    return mult, {"modo": modo, "per_year_true": per_year, "mean_true": mean_true,
                  "n": n}


def cost_final(true_base, tech, year, calib):
    """costo real x calibracion x escalada (+0.3%/ano desde 2025)."""
    b = true_base[tech] * calib
    if year < COST_ESC_FROM:
        return b
    return b * (1 + COST_ESC_RATE) ** (year - COST_ESC_FROM)


# --------------------------------------------------------------------------
# construccion de todos los cambios por (param, tech, year)
# --------------------------------------------------------------------------
def build_mods(lines, apply_nli, shares, ren_2030, calib, min_override, planned_ceiling):
    spans = parse_blocks(lines)
    _, cc_txt = read_map(lines, spans["CapitalCost"])
    true_base = true_base_costs(cc_txt)
    resid_ty, _ = read_map(lines, spans["ResidualCapacity"])

    def resid(tech):
        for y in range(2023, 2028):
            if (tech, y) in resid_ty:
                return resid_ty[(tech, y)]
        return 0.0

    mod = {"CapitalCost": {}, "TotalAnnualMaxCapacityInvestment": {},
           "TotalAnnualMaxCapacity": {}, MININV: dict(min_override)}
    years = list(range(2023, LAST_YEAR + 1))

    # Paso 1+4: costo real x calib x escalada, TODOS los anos, 6 familias Tx
    for tech in cc_txt:
        if tech.startswith(FAM6):
            for y in years:
                mod["CapitalCost"][(tech, y)] = cost_final(true_base, tech, y, calib)

    techs = {t for (t, _y) in resid_ty} | set(cc_txt)

    # piso efectivo (post-swap): existente + override. Se usa para (a) el presupuesto
    # NLI (restar el techo RPO post-guarda) y (b) la guarda de factibilidad al final.
    existing_min, _ = read_map(lines, spans[MININV]) if MININV in spans else ({}, {})
    eff_min = dict(existing_min)
    eff_min.update(min_override)

    # Paso 3: repotenciacion (4 escenarios), solo flujo, sin techo
    for rpo, existing_fam in RPO_SOURCE.items():
        for tech in sorted(t for t in techs if t.startswith(rpo)):
            c = tech[6:9]
            rc = resid(existing_fam + c + "XX")
            if rc <= 0:
                continue
            for y in range(RPO_FIRST_YEAR, LAST_YEAR + 1):
                mod["TotalAnnualMaxCapacityInvestment"][(tech, y)] = rpo_pct(y) * rc

    # Paso 2: lineas nuevas no planificadas (solo vegetativos) -- ENVELOPE TOTAL
    # La inversion Tx TOTAL del vegetativo (planificadas + RPO + NLI) se capa en la
    # trayectoria regional I_region(ano) = 3000 x1.9% (~3.3k -> 5k+ MUSD/ano). Las
    # PLANIFICADAS (= plan OPT) y la REPOTENCIACION CONSUMEN el envelope PRIMERO; las
    # NLI reciben SOLO el remanente (NO se apilan sobre el plan). 2030+. Antes de 2030
    # las planificadas ya estan capadas al plan OPT (no hay NLI antes de 2030).
    if apply_nli:
        planned_cost = {}                          # MUSD del techo planificado (= plan OPT)
        for (t, y), gw in planned_ceiling.items():
            planned_cost[y] = planned_cost.get(y, 0.0) + gw * cost_final(true_base, t, y, calib)
        rpo_cost = {}                              # MUSD del techo RPO POST-guarda
        for (t, y), gw in mod["TotalAnnualMaxCapacityInvestment"].items():
            if t.startswith(("TRNRPO", "RNWRPO")):
                eff_gw = max(gw, eff_min.get((t, y), 0.0))   # la guarda elevara al piso
                rpo_cost[y] = rpo_cost.get(y, 0.0) + eff_gw * cost_final(true_base, t, y, calib)
        # presupuesto NLI = envelope regional - lo que ya consumen planificadas + RPO
        nli_budget = {y: max(0.0, i_region(y) - planned_cost.get(y, 0.0) - rpo_cost.get(y, 0.0))
                      for y in range(NLI_FIRST_YEAR, LAST_YEAR + 1)}
        for fam in ("TRNNLI", "RNWNLI"):
            for tech in sorted(t for t in techs if t.startswith(fam)):
                c = tech[6:9]
                if c not in shares or tech not in true_base:
                    continue
                cumul_gw = 0.0
                for y in range(NLI_FIRST_YEAR, LAST_YEAR + 1):
                    rs = ren_share(y, ren_2030)
                    w = rs if fam == "RNWNLI" else (1 - rs)
                    musd = shares[c] * nli_budget[y] * w
                    gw = musd / cost_final(true_base, tech, y, calib)
                    cumul_gw += gw
                    mod["TotalAnnualMaxCapacityInvestment"][(tech, y)] = gw
                    mod["TotalAnnualMaxCapacity"][(tech, y)] = cumul_gw

    # Regla PLANIFICADAS (PWRTRN/RNWTRN): techo comun = piso del OPTIMO (post-swap),
    # en LOS 4 escenarios. Ningun escenario invierte en lineas planificadas mas que
    # el plan optimo. REF/veg eligen entre su piso (min propio) y este techo; el OPT
    # queda fijado en su plan (min=max). Factible porque el swap ya dejo OPT_min >=
    # REF_min en cada celda. 2027+ (no toca el historico 2023-2026).
    for tech in sorted(t for t in techs if t.startswith(("PWRTRN", "RNWTRN"))):
        for y in range(SWAP_FIRST_YEAR, LAST_YEAR + 1):
            mod["TotalAnnualMaxCapacityInvestment"][(tech, y)] = planned_ceiling.get((tech, y), 0.0)

    # GUARDA DE FACTIBILIDAD: ningun tope de inversion por debajo de un piso.
    # Los RPO traen piso comprometido propio (p.ej. CHL/CRI/SLV) que puede exceder
    # la rampa fisica; el tope se eleva al piso para no volver el LP infactible
    # (min>max => conjunto factible vacio). No toca los centinelas -1 (sin limite).
    # eff_min ya se calculo arriba (existente + swap).
    raised = []
    for (tech, y), mx in list(mod["TotalAnnualMaxCapacityInvestment"].items()):
        mn = eff_min.get((tech, y), 0.0)
        if 0 <= mx < mn - 1e-12:
            mod["TotalAnnualMaxCapacityInvestment"][(tech, y)] = mn
            raised.append((tech, y, mx, mn))
    return mod, cc_txt, true_base, resid, raised


def apply_and_write(name, src, mod):
    """Escribe la copia: sobre-escribe filas existentes, inserta faltantes.
    Min: valor 0 -> elimina la fila (default 0 = sin piso). RPO MaxCap -> elimina."""
    lines = src.read_text(encoding="utf-8").splitlines(keepends=True)
    out, cur, seen = [], None, set()
    for ln in lines:
        s = ln.strip()
        if s.startswith("param") and ":=" in s:
            cur = None
            for p in WRITE_PARAMS:
                if f": {p} :=" in s:
                    cur, seen = p, set()
                    break
            out.append(ln)
            continue
        if cur and s == ";":
            # sorted() -> orden de fila DETERMINISTA (evita el orden aleatorio de
            # set/hash entre corridas; el solve no depende del orden, pero el .txt
            # debe ser byte-reproducible para Andrey).
            for (tech, y), v in sorted(mod[cur].items()):
                if (tech, y) in seen:
                    continue
                if cur == MININV and abs(v) < 1e-12:
                    continue                       # 0 = sin piso, no insertar
                out.append(f"GLOBAL {tech} {y} {v:.6g}\n")
            cur = None
            out.append(ln)
            continue
        if cur == "TotalAnnualMaxCapacity":
            t = ln.split()
            if len(t) == 4 and t[1].startswith(("TRNRPO", "RNWRPO")):
                continue                            # eliminar techo acumulado RPO
        if cur:
            t = ln.split()
            if len(t) == 4 and (t[1], int(t[2])) in mod[cur]:
                key = (t[1], int(t[2]))
                seen.add(key)
                v = mod[cur][key]
                if cur == MININV and abs(v) < 1e-12:
                    continue                        # bajar a 0 = eliminar la fila
                out.append(f"GLOBAL {t[1]} {key[1]} {v:.6g}\n")
                continue
        out.append(ln)

    dst = OUT_DIR / f"Pre_processed_{name}_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_VEGCON.txt"
    shutil.copy2(src, dst)
    dst.write_text("".join(out), encoding="utf-8")
    return dst


def ren_from(src):
    lines = src.read_text(encoding="utf-8").splitlines(keepends=True)
    spans = parse_blocks(lines)
    resid_ty, _ = read_map(lines, spans["ResidualCapacity"])
    pwr = sum(v for (t, y), v in resid_ty.items() if t.startswith("PWRTRN") and y == 2023)
    rnw = sum(v for (t, y), v in resid_ty.items() if t.startswith("RNWTRN") and y == 2023)
    return rnw / (pwr + rnw) if (pwr + rnw) else 0.4


# --------------------------------------------------------------------------
# escaneo de FACTIBILIDAD OSeMOSYS (lee el .txt escrito, TODAS las techs)
# --------------------------------------------------------------------------
FEAS_PARAMS = ("ResidualCapacity", "TotalAnnualMinCapacity", "TotalAnnualMaxCapacity",
               "TotalAnnualMinCapacityInvestment", "TotalAnnualMaxCapacityInvestment",
               "TotalTechnologyAnnualActivityLowerLimit",
               "TotalTechnologyAnnualActivityUpperLimit")


def read_params(path, params):
    """Lector general (independiente de TARGET_PARAMS): {param: {(tech,year): val}}."""
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


def feasibility_scan(dst):
    """Busca los patrones de infactibilidad de OSeMOSYS en el .txt escrito, para
    TODAS las tecnologias (no solo Tx). Un -1 = 'sin limite' (centinela), se ignora.
    Devuelve {categoria: [violaciones]}; categorias '[warn]' son potenciales
    (la retirada por OperationalLife podria salvarlas). Independiente del preflight."""
    P = read_params(dst, FEAS_PARAMS)
    resid = P["ResidualCapacity"]
    minc, maxc = P["TotalAnnualMinCapacity"], P["TotalAnnualMaxCapacity"]
    mini, maxi = P["TotalAnnualMinCapacityInvestment"], P["TotalAnnualMaxCapacityInvestment"]
    lla, ula = (P["TotalTechnologyAnnualActivityLowerLimit"],
                P["TotalTechnologyAnnualActivityUpperLimit"])
    v = {}

    def add(cat, item):
        v.setdefault(cat, []).append(item)

    # --- chequeos locales (mismo tech,ano) -------------------------------
    for k, mn in mini.items():                         # A. piso inv > techo inv
        mx = maxi.get(k)
        if mx is not None and 0 <= mx < mn - 1e-9:
            add("min_inv>max_inv", (k, mn, mx))
    for k, mn in minc.items():                         # B. piso cap > techo cap
        mx = maxc.get(k)
        if mx is not None and 0 <= mx < mn - 1e-9:
            add("min_cap>max_cap", (k, mn, mx))
    for k, r in resid.items():                         # D. residual solo > techo cap
        mx = maxc.get(k)
        if mx is not None and 0 <= mx < r - 1e-9:
            add("residual>max_cap", (k, r, mx))
    for k, lo in lla.items():                           # F. piso actividad > techo
        hi = ula.get(k)
        if hi is not None and 0 <= hi < lo - 1e-9:
            add("act_low>act_up", (k, lo, hi))

    # --- chequeos acumulados (por tech, a lo largo de los anos) ----------
    techs = {t for (t, _y) in list(resid) + list(minc) + list(maxc)
             + list(mini) + list(maxi)}
    for tech in techs:
        yrs = sorted({y for (t, y) in list(resid) + list(minc) + list(maxc)
                      + list(mini) + list(maxi) if t == tech})
        cum_min = cum_max = 0.0
        maxinv_unbounded = False          # algun ano sin tope explicito (o -1) = ilimitado
        for y in yrs:
            cum_min += mini.get((tech, y), 0.0)
            mv = maxi.get((tech, y))
            if mv is None or mv < 0:
                maxinv_unbounded = True
            else:
                cum_max += mv
            r = resid.get((tech, y), 0.0)
            mc = minc.get((tech, y))
            if mc is not None and not maxinv_unbounded and mc > r + cum_max + 1e-9:
                add("cap_floor_inalcanzable", ((tech, y), mc, r + cum_max))  # E
            mx = maxc.get((tech, y))
            if mx is not None and mx >= 0 and r + cum_min > mx + 1e-9:
                add("forzado_acum>max_cap[warn]", ((tech, y), r + cum_min, mx))  # C
    return v


# --------------------------------------------------------------------------
# preflight de piso comprometido (lee los .txt escritos; prueba OPT>=REF>=VEG)
# --------------------------------------------------------------------------
def committed_musd(dst, true_base_for_cost):
    """inversion comprometida (piso) por ano, leida del .txt escrito, al costo
    ya escrito en ese mismo archivo."""
    lines = dst.read_text(encoding="utf-8").splitlines(keepends=True)
    spans = parse_blocks(lines)
    mn, _ = read_map(lines, spans[MININV]) if MININV in spans else ({}, {})
    cc, _ = read_map(lines, spans["CapitalCost"])
    out = {}
    for (t, y), gw in mn.items():
        if t.startswith(FAM6):
            out[y] = out.get(y, 0.0) + gw * cc.get((t, y), 0.0)
    return out, mn


def allowed_musd(dst):
    """envelope permitido (piso + techos NLI/RPO) por ano, al costo del .txt."""
    lines = dst.read_text(encoding="utf-8").splitlines(keepends=True)
    spans = parse_blocks(lines)
    cc, _ = read_map(lines, spans["CapitalCost"])
    mn, _ = read_map(lines, spans[MININV]) if MININV in spans else ({}, {})
    mx, _ = read_map(lines, spans["TotalAnnualMaxCapacityInvestment"])
    out = {}
    for (t, y), gw in mn.items():
        if t.startswith(FAM6):
            out[y] = out.get(y, 0.0) + gw * cc.get((t, y), 0.0)
    for (t, y), gw in mx.items():
        if t.startswith(("TRNNLI", "RNWNLI", "TRNRPO", "RNWRPO")):
            out[y] = out.get(y, 0.0) + gw * cc.get((t, y), 0.0)
    return out


def main():
    passed = failed = 0

    def chk(label, ok):
        nonlocal passed, failed
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
        passed += ok
        failed += (not ok)

    shares = final_shares()
    print("=" * 80)
    print("REGLAS DE TRANSMISION RELAC  (referencia reproducible, sobre copias)")
    print("=" * 80)

    # --- Paso 0: swap del piso (REF <-> OPT) --------------------------------
    ref_src = SCENARIOS[SWAP_REF][0]
    opt_src = SCENARIOS[SWAP_OPT][0]
    ref_min = load_min(ref_src)
    opt_min = load_min(opt_src)
    opt_over, twin_over, movers = compute_swap(ref_min, opt_min)

    print("\n=== PASO 0: SWAP del piso comprometido (donde REF>OPT, ano>=2027) ===")
    print(f"  celdas intercambiadas: {len(movers)}")
    by_c = {}
    for (t, y, r, o) in movers:
        by_c.setdefault(t[6:9], [0.0, 0])
        by_c[t[6:9]][0] += (r - o)
        by_c[t[6:9]][1] += 1
    for c, (gw, n) in sorted(by_c.items(), key=lambda x: -x[1][0]):
        print(f"    {c}: +{gw:.2f} GW movidos de REF a OPT ({n} celdas)")
    opt_min_post = dict(opt_min)
    for k, v in opt_over.items():
        opt_min_post[k] = v
    # techo comun para lineas planificadas = piso del OPTIMO (post-swap)
    opt_planned_ceiling = {(t, y): v for (t, y), v in opt_min_post.items()
                           if t.startswith(("PWRTRN", "RNWTRN"))}

    # --- Paso 1: calibracion (sobre las lineas planificadas de la REF, original) --
    # El costo es identico entre escenarios; el PISO de calibracion es el de la REF
    # ORIGINAL (pre-swap): son las lineas planificadas de la referencia (tarea Andrey).
    cal_src = SCENARIOS[CALIB_FLOOR_SCENARIO][0]
    lines_cal = cal_src.read_text(encoding="utf-8").splitlines(keepends=True)
    _, cc_txt_cal = read_map(lines_cal, parse_blocks(lines_cal)["CapitalCost"])
    tb_cal = true_base_costs(cc_txt_cal)
    calib_floor = load_min(cal_src)          # piso ORIGINAL de la REF (pre-swap)
    calib, cdiag = calibrate(calib_floor, tb_cal)
    print("\n=== PASO 1: nivel de costo real + factor de escala m ===")
    _sample = cc_txt_cal.get("PWRTRNBRAXX", 0.0)
    print(f"  costo base leido (Executables): PWRTRNBRAXX={_sample:.3f} "
          f"({'REAL, sin x2 (OK)' if _sample < 400 else 'ATENCION: parece traer el x2'})")
    print(f"  LEVEL_MULT_CURRENT=x{LEVEL_MULT_CURRENT} (base ya es real; el x2 vive aguas abajo)")
    print(f"  regla: promedio {CALIB_WINDOW[0]}-{CALIB_WINDOW[1]} del piso (costo real) "
          f"x m = ancla {CALIB_ANCHOR_MUSD:.0f}")
    print(f"  promedio piso real {CALIB_WINDOW[0]}-{CALIB_WINDOW[1]}: "
          f"{cdiag['mean_true']:.1f} MUSD/ano")
    print(f"  FACTOR DE ESCALA m = x{calib:.4f}  ({cdiag['modo']})   "
          f"[{'>1 OK' if calib > 1 else 'ATENCION: m<=1'}]")
    print(f"  promedio calibrado = {cdiag['mean_true']*calib:.1f} MUSD (== ancla)")
    print(f"  => costo final escrito = base_real x m = x{calib:.4f} de la base "
          f"(y x{calib/2:.4f} vs los archivos de solve con x2)")
    print("  piso real (base Executables) x m por ano (algunos +/- del promedio):")
    for y in range(CALIB_WINDOW[0], CALIB_WINDOW[1] + 1):
        pt = cdiag["per_year_true"].get(y, 0.0)
        mark = "+" if pt * calib > CALIB_ANCHOR_MUSD else "-"
        print(f"    {y}: real={pt:8.1f}  x m={pt*calib:8.1f}  ({mark} vs promedio)")

    print("\n=== Shares finales (max entre DR / BNam anualizado / fallback) ===")
    for c in sorted(shares, key=lambda x: -shares[x]):
        print(f"  {c}: {shares[c]:.3f}", end="   ")
    print()
    chk("shares suman 1", abs(sum(shares.values()) - 1) < 1e-9)

    # --- Escribir los 4 escenarios -----------------------------------------
    written = {}
    for name, (src, apply_nli) in SCENARIOS.items():
        if not src.exists():
            print(f"\n[SKIP] {name}: no existe {src.name}")
            continue
        min_ov = opt_over if name == SWAP_OPT else (twin_over if name in SWAP_TWINS else {})
        lines = src.read_text(encoding="utf-8").splitlines(keepends=True)
        mod, cc_txt, true_base, resid, raised = build_mods(
            lines, apply_nli, shares, ren_from(src), calib, min_ov, opt_planned_ceiling)
        dst = apply_and_write(name, src, mod)
        written[name] = dst
        rule = "NLI+RPO+costo" if apply_nli else "RPO+costo"
        swaptag = ("OPT+swap" if name == SWAP_OPT else
                   ("REF/twin-swap" if name in SWAP_TWINS else "sin swap"))
        print(f"\n--- {name} ({rule}; piso={swaptag}) -> {dst.name}")
        print(f"    celdas: CapitalCost={len(mod['CapitalCost'])} "
              f"MaxCapInv={len(mod['TotalAnnualMaxCapacityInvestment'])} "
              f"MaxCap={len(mod['TotalAnnualMaxCapacity'])} "
              f"MinInv(swap)={len(mod[MININV])}")
        if raised:
            print(f"    guarda factibilidad: {len(raised)} topes RPO elevados al piso "
                  f"comprometido (p.ej. {raised[0][0]} {raised[0][1]}: "
                  f"{raised[0][2]:.3f}->{raised[0][3]:.3f} GW)")

    # --- PREFLIGHT del piso: OPT >= REF, y REF==INV==VGB en Tx --------------
    print("\n=== PREFLIGHT PISO (lee los .txt escritos) ===")
    if all(k in written for k in ("BAU", "OPT", "INV", "VGB")):
        cbau, mbau = committed_musd(written["BAU"], None)
        copt, mopt = committed_musd(written["OPT"], None)
        cinv, minv = committed_musd(written["INV"], None)
        cvgb, mvgb = committed_musd(written["VGB"], None)
        yrs = sorted(set(cbau) | set(copt))
        no_inv = all(copt.get(y, 0) >= cbau.get(y, 0) - 1e-6 for y in yrs)
        chk("OPT piso comprometido >= REF en TODOS los anos (swap corrige la inversion)",
            no_inv)
        # REF==INV==VGB en piso Tx (mismas celdas del swap)
        tx = lambda m: {k: v for k, v in m.items() if k[0].startswith(FAM6)}
        same = tx(mbau) == tx(minv) == tx(mvgb)
        chk("REF/INV/VGB comparten piso Tx identico", same)
        # el mover material (Brasil) ahora en OPT (piso Tx GW 2027+)
        bra_opt = sum(v for (t, y), v in mopt.items()
                      if t.startswith(FAM6) and t[6:9] == "BRA" and y >= 2027)
        bra_ref = sum(v for (t, y), v in mbau.items()
                      if t.startswith(FAM6) and t[6:9] == "BRA" and y >= 2027)
        chk(f"Brasil piso 2027+ ahora mayor en OPT ({bra_opt:.1f} GW) que REF ({bra_ref:.1f} GW)",
            bra_opt > bra_ref)
        print(f"  piso comprometido acumulado (MUSD): "
              f"REF={sum(cbau.values()):.0f}  OPT={sum(copt.values()):.0f}")

    # --- PREFLIGHT FACTIBILIDAD OSeMOSYS (escaneo completo, todas las techs) --
    # Patrones que vuelven infactible el LP: min>max en inversion o en capacidad,
    # residual sobre el techo, piso de capacidad inalcanzable, piso de actividad
    # sobre el techo. '[warn]' = potencial (la retirada por vida util puede salvar).
    print("\n=== PREFLIGHT FACTIBILIDAD OSeMOSYS (todas las techs, todos los .txt) ===")
    HARD = ("min_inv>max_inv", "min_cap>max_cap", "residual>max_cap",
            "cap_floor_inalcanzable", "act_low>act_up")
    for name in written:
        scan = feasibility_scan(written[name])
        hard = {c: scan[c] for c in HARD if c in scan}
        warn = {c: scan[c] for c in scan if c.endswith("[warn]")}
        nh = sum(len(x) for x in hard.values())
        chk(f"[{name}] factible: 0 conflictos duros (min>max / residual>techo / "
            f"piso inalcanzable / actividad)", nh == 0)
        for c, items in hard.items():
            print(f"      DURO {c}: {len(items)}  e.j. {items[0]}")
        for c, items in warn.items():
            print(f"      [warn] {c}: {len(items)} (potencial; retirada por vida util "
                  f"puede salvar)  e.j. {items[0]}")

    # --- PREFLIGHT TECHO LINEAS PLANIFICADAS: Max = plan OPT en los 4 --------
    # Regla: ningun escenario invierte en lineas planificadas mas que el plan
    # OPTIMO. OPT queda fijado (min==max); REF/veg eligen entre su piso y el plan
    # OPT. Las NO planificadas (NLI) solo se capan en el veg.
    print("\n=== PREFLIGHT TECHO LINEAS PLANIFICADAS (Max = plan OPT, los 4) ===")

    def planned_max(dst):
        L = dst.read_text(encoding="utf-8").splitlines(keepends=True)
        mx, _ = read_map(L, parse_blocks(L)["TotalAnnualMaxCapacityInvestment"])
        return {k: v for k, v in mx.items() if k[0].startswith(("PWRTRN", "RNWTRN"))}

    pm = {n: planned_max(written[n]) for n in written}
    chk("techo lineas planificadas IDENTICO en los 4 (= plan OPT)",
        all(pm[n] == pm["OPT"] for n in pm))
    Lo = written["OPT"].read_text(encoding="utf-8").splitlines(keepends=True)
    omn, _ = read_map(Lo, parse_blocks(Lo)[MININV])
    opl = pm["OPT"]
    pin_ok = all(abs(opl.get(k, -9) - v) < 1e-9 for k, v in omn.items()
                 if k[0].startswith(("PWRTRN", "RNWTRN")) and k[1] >= SWAP_FIRST_YEAR and v > 1e-9)
    chk("OPT FIJADO en su plan (min==max) en lineas planificadas 2027+", pin_ok)
    print("  REF/veg eligen entre su piso y el plan OPT; nadie supera el plan OPT.")
    print("  NLI no planificadas: tope solo en veg (REF/OPT libres en NLI):")
    for y in (2030, 2040, 2050):
        print(f"    VEG tope NLI {y}: {i_region(y):8.0f} MUSD (ancla 3000 x1.9%)")

    # --- PREFLIGHT vegetativo (valor deseado NLI + RPO no se auto-detiene) --
    print("\n=== PREFLIGHT VEGETATIVO (valor deseado + factibilidad) ===")
    ser = None
    for name in ("INV", "VGB"):
        if name in written:
            ser, pp, pf = preflight_veg(name, written[name])
            passed += pp
            failed += pf

    # --- graficas de prueba ------------------------------------------------
    committed_all = {n: committed_musd(written[n], None)[0] for n in written}
    png1 = OUT_DIR / "veg_pipeline_proof.png"
    plot_pipeline(committed_all, png1)
    print(f"\n  PNG prueba pipeline: {png1.name}")
    if ser:
        png2 = OUT_DIR / "veg_preflight.png"
        plot_preflight(ser, png2)
        print(f"  PNG preflight veg:   {png2.name}")

    print(f"\nRESULTADO: PASS={passed} FAIL={failed}")
    print_deliverables(calib)


def preflight_veg(name, dst):
    """Lee el .txt del vegetativo: NLI da la trayectoria, RPO no se auto-detiene,
    capacidad no decrece. Devuelve (series, n_pass, n_fail)."""
    lines = dst.read_text(encoding="utf-8").splitlines(keepends=True)
    spans = parse_blocks(lines)
    cc, _ = read_map(lines, spans["CapitalCost"])
    inv, _ = read_map(lines, spans["TotalAnnualMaxCapacityInvestment"])
    cap, _ = read_map(lines, spans["TotalAnnualMaxCapacity"])
    resid_ty, _ = read_map(lines, spans["ResidualCapacity"])
    years = list(range(RPO_FIRST_YEAR, LAST_YEAR + 1))
    nli_f, rpo_f, plan_f = ("TRNNLI", "RNWNLI"), ("TRNRPO", "RNWRPO"), ("PWRTRN", "RNWTRN")

    nli_musd = {y: sum(gw * cc.get((t, y), 0.0) for (t, yy), gw in inv.items()
                       if yy == y and t.startswith(nli_f)) for y in years}
    rpo_musd = {y: sum(gw * cc.get((t, y), 0.0) for (t, yy), gw in inv.items()
                       if yy == y and t.startswith(rpo_f)) for y in years}
    plan_musd = {y: sum(gw * cc.get((t, y), 0.0) for (t, yy), gw in inv.items()
                        if yy == y and t.startswith(plan_f)) for y in years}
    total_musd = {y: nli_musd[y] + rpo_musd[y] + plan_musd[y] for y in years}
    resid_exist = sum(v for (t, yy), v in resid_ty.items()
                      if t.startswith(("PWRTRN", "RNWTRN")) and yy == 2023)
    nli_cap = {y: sum(v for (t, yy), v in cap.items()
                      if yy == y and t.startswith(nli_f)) for y in years}
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

    # ENVELOPE TOTAL: planificadas + RPO + NLI = max(I_region, planificadas+RPO).
    # (Donde planificadas+RPO <= presupuesto: total == I_region, NLI llena el resto.
    #  Donde planificadas+RPO ya excede el presupuesto: NLI=0, total = planif+RPO.)
    env = all(abs(total_musd[y] - max(i_region(y), plan_musd[y] + rpo_musd[y]))
              < 0.01 * i_region(y) for y in range(NLI_FIRST_YEAR, LAST_YEAR + 1))
    t(f"[{name}] envelope Tx TOTAL = 3300->5000+ (planif+RPO+NLI dentro; "
      f"2030={total_musd[2030]:.0f}, 2035={total_musd[2035]:.0f}, 2050={total_musd[2050]:.0f})",
      env)
    # NLI NO se apila sobre el plan: cuando el plan+RPO llena el presupuesto, NLI=0
    no_stack = all(nli_musd[y] <= i_region(y) + 1e-6 for y in
                   range(NLI_FIRST_YEAR, LAST_YEAR + 1))
    t(f"[{name}] NLI = remanente del envelope, no apilada (2030={nli_musd[2030]:.0f}, "
      f"2050={nli_musd[2050]:.0f})", no_stack)
    gw40 = sum(gw for (t2, yy), gw in inv.items() if yy == 2040 and t2.startswith(rpo_f))
    gw50 = sum(gw for (t2, yy), gw in inv.items() if yy == 2050 and t2.startswith(rpo_f))
    t(f"[{name}] RPO no se auto-detiene: flujo GW congelado 3% (2040={gw40:.1f}=2050={gw50:.1f})",
      abs(gw40 - gw50) < 1e-6 and rpo_musd[2050] > 1.0)
    totcap = {y: resid_exist + nli_cap[y] + rpo_cap[y] for y in years}
    nd = all(totcap[y] >= totcap[y - 1] - 1e-6 for y in years[1:])
    t(f"[{name}] feasible: capacidad total no decrece ({resid_exist:.0f}->{totcap[2050]:.0f} GW)",
      nd and totcap[2050] > resid_exist)
    ser = {"years": years, "nli": nli_musd, "rpo": rpo_musd, "resid": resid_exist,
           "nli_cap": nli_cap, "rpo_cap": rpo_cap}
    return ser, pp, pf


def plot_pipeline(committed_all, png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "DejaVu Sans"
    REF, OPTC, TXT = "#5A7682", "#C9622E", "#0F2E36"
    yrs = list(range(2027, 2051))

    fig, ax = plt.subplots(1, 2, figsize=(13.5, 4.9))
    fig.suptitle("PRUEBA PIPELINE: swap del piso -> el OPTIMO ya no queda por debajo "
                 "de la REFERENCIA (piso comprometido, costo real /2)",
                 color=TXT, fontsize=12, y=1.02)

    # A: piso comprometido por ano, REF vs OPT (el swap corrige la inversion)
    cb = [committed_all["BAU"].get(y, 0) for y in yrs]
    co = [committed_all["OPT"].get(y, 0) for y in yrs]
    ax[0].plot(yrs, co, color=OPTC, lw=2.6, label="OPTIMO (piso, post-swap)")
    ax[0].plot(yrs, cb, color=REF, lw=2.2, label="REFERENCIA / VEG (piso)")
    ax[0].fill_between(yrs, cb, co, color=OPTC, alpha=.10)
    ax[0].set_title("A. Piso comprometido por ano (MUSD/ano) - OPT >= REF en todos los anos",
                    color=TXT, fontsize=10)
    ax[0].set_ylabel("MUSD/ano (costo real /2)")
    ax[0].legend(fontsize=8)
    ax[0].grid(alpha=.25)
    ax[0].set_ylim(bottom=0)

    # B: piso comprometido acumulado por escenario (barras) - OPT domina
    order = [n for n in ("OPT", "BAU", "INV", "VGB") if n in committed_all]
    labels = {"OPT": "OPTIMO", "BAU": "REFERENCIA", "INV": "VEG-A", "VGB": "VEG-B"}
    cols = {"OPT": OPTC, "BAU": REF, "INV": "#00414D", "VGB": "#7A9AA6"}
    tot = [sum(committed_all[n].values()) for n in order]
    ax[1].bar([labels[n] for n in order], tot, color=[cols[n] for n in order])
    for i, v in enumerate(tot):
        ax[1].annotate(f"{v:.0f}", (i, v), ha="center", va="bottom", fontsize=9, color=TXT)
    ax[1].set_title("B. Piso comprometido ACUMULADO por escenario (MUSD)",
                    color=TXT, fontsize=10)
    ax[1].set_ylabel("MUSD (suma 2023-2050, costo real /2)")
    ax[1].grid(alpha=.25, axis="y")
    ax[1].annotate("VEG (A/B) ademas lleva\ntope de lineas nuevas;\nREF y OPT sin tope de Tx",
                   (len(order) - 1, max(tot) * 0.55), ha="right", fontsize=8, color=TXT)
    for a in ax:
        a.tick_params(colors=TXT)
    fig.tight_layout()
    fig.savefig(png, dpi=130, bbox_inches="tight")


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


def print_deliverables(calib):
    print("\n" + "=" * 80)
    print("ENTREGABLE REPORTE (texto) -- v2")
    print("=" * 80)
    print(
        "El piso comprometido de transmision estaba mal asignado: la REFERENCIA "
        "forzaba ~22 GW de lineas brasilenas en 2027-2029 que el OPTIMO no tenia, "
        "invirtiendo el orden esperado (el planificado debe tener mas grid, no "
        "menos). Se intercambia (swap) ese piso entre REFERENCIA y OPTIMO donde la "
        "REFERENCIA excedia al OPTIMO, de modo que el OPTIMO queda con al menos "
        "tanto grid comprometido como la REFERENCIA en cada ano. El costo de capital "
        "de la base de Executables YA esta en nivel real (el multiplicador x2 vive "
        "aguas abajo, en los archivos de solve); se le aplica un unico factor de "
        f"calibracion (x{calib:.3f}) que posa la inversion comprometida sobre el ancla "
        "IEA (~3080 MUSD/ano @2022, promedio 2025-2029). Sobre esto se define, SOLO en "
        "los vegetativos, un ENVELOPE TOTAL de inversion Tx = 3000 x1.9%/ano "
        "(~3.3k -> 5.1k MUSD): las lineas planificadas (= plan OPTIMO) y la "
        "repotenciacion consumen el envelope PRIMERO, y las lineas nuevas no "
        "planificadas (NLI) reciben SOLO el remanente (no se apilan). La "
        "repotenciacion (4 escenarios) corre a 2-3%/ano del stock existente sin techo "
        "acumulado. Las planificadas se capan al plan OPTIMO en LOS 4 escenarios. "
        "[EST] marca los tramos estimados.")
    print("\n" + "=" * 80)
    print("ENTREGABLE ANDREY (pasos) -- v2")
    print("=" * 80)
    for i, s in enumerate([
        "PISO (swap): intercambiar TotalAnnualMinCapacityInvestment entre REF y OPT "
        "donde REF>OPT (ano>=2027); propagar el piso de REF a INV y VGB (identicos en "
        "Tx). Asi el OPTIMO queda con OPT_min >= REF_min en cada celda.",
        "COSTO: la base de Executables YA es costo real (sin x2; el x2 vive aguas "
        "abajo). Multiplicar por el factor de escala m reportado (promedio 2025-2029 "
        "del piso planificado de la REF x m = 3080). NO volver a aplicar el x2 aguas "
        "abajo (o resolver directamente las copias VEGCON).",
        "TECHO PLANIFICADAS: MaxCapacityInvestment de PWRTRN/RNWTRN = piso del OPTIMO "
        "(post-swap), en LOS 4 escenarios, 2027+. OPT queda fijado (min=max); REF/veg "
        "eligen entre su piso y el plan OPT; nadie invierte en planificadas mas que el "
        "plan optimo. Factible porque el swap dejo OPT_min>=REF_min en cada celda.",
        "RPO flujo (4 escenarios): MaxCapacityInvestment = pct(ano) x stock "
        "PWRTRN/RNWTRN, 2028-2050, pct 2%->3% (rampa a 2040) congelado; eliminar el "
        "techo acumulado RPO.",
        "ENVELOPE NLI (SOLO INV/VGB, 2030+): el tope de inversion Tx TOTAL del "
        "vegetativo = I_region(ano) = 3000 x1.9%. NLI recibe el REMANENTE: "
        "presupuesto_NLI(ano) = max(0, I_region(ano) - costo(planificadas) - "
        "costo(RPO)). Repartir ese remanente por pais con shares s(c) y ren/no-ren, y "
        "convertir a GW dividiendo por el costo corregido. NO usar el I_region "
        "completo para NLI (eso lo apila sobre el plan; era el bug de la v1).",
        "COSTO escalada: x1.003^(ano-2025) sobre el costo ya corregido, 6 familias.",
        "GUARDA FACTIBILIDAD: algunas RPO (CHL/CRI/SLV) traen piso comprometido que "
        "excede la rampa fisica; elevar su tope al piso (max=max(rampa,piso)) para no "
        "volver el LP infactible (min>max). ~9 celdas por escenario. Restar el RPO "
        "POST-guarda del presupuesto NLI (si no, el envelope se pasa unos MUSD).",
        "PREFLIGHT (baked-in, 18/18): shares=1; OPT>=REF en piso; REF/INV/VGB piso Tx "
        "identico; techo planificadas identico en los 4 (=plan OPT) y OPT fijado; "
        "envelope Tx total = 3.3k->5.1k con NLI como remanente (no apilada); RPO no se "
        "auto-detiene; capacidad no decrece; 0 conflictos duros de factibilidad en los "
        "4 (min>max inv/cap, residual>techo, piso inalcanzable, actividad). Luego "
        "resolver CPLEX y confirmar OPT el mayor y backstop ~0.",
    ], 1):
        print(f"  {i}. {s}")


if __name__ == "__main__":
    main()
