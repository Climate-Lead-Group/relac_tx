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
     trayectoria regional I_region(ano) = 3300 @2022 x1.0%/ano (~3.6k @2030 -> 4.4k @2050 MUSD).
     Las PLANIFICADAS (= plan OPT) y la RPO consumen el envelope PRIMERO; la NLI recibe
     SOLO el remanente: presup_NLI = max(0, I_region - costo_planif - costo_RPO). Ese
     remanente se reparte por pais con shares s(c) y ren/no-ren, y se pasa a GW via el
     costo corregido. Anos 2030+. Solo en los vegetativos (INV, VGB). NO aditiva
     (v1 usaba el I_region completo para NLI y se apilaba sobre el plan: ese era el bug).

  3. REPOTENCIACION (familias TRNRPO, RNWRPO)
     Tope fisico del stock EXISTENTE (PWRTRN/RNWTRN). Solo flujo anual, PLANO 1%/ano
     desde 2028 (v13; antes rampa 2%->3%). SIN techo acumulado. Los 4.

  3b. TECHO PLANIFICADAS (familias PWRTRN, RNWTRN)
     MaxCapacityInvestment = piso del OPTIMO (post-swap), en LOS 4 escenarios, 2027+.
     OPT fijado (min=max); REF/veg eligen entre su piso y el plan OPT; nadie invierte
     en planificadas mas que el plan optimo.

  4. ESCALADA DE COSTO
     +0.3% real/ano al CapitalCost corregido de las 6 familias Tx (2025+). Los 4.

DERIVACION (trazable; referencias completas al final del archivo)
-----------------------------------------------------------------
  Nivel 3000 MUSD @2022: IEA Latin America Energy Outlook 2023 via SEGIB
    (20000/6.5 = ~3077 @2022 ~ 3300 en USD 2023). Crece 1.0%/ano (LAEO 2023 fig 1.9: 45->50 GUSD/ano, ~1.06%/ano; redes declinaron => 1% es techo),
    muy por debajo del x6.5 (~7%/ano) de la necesidad APS.
  Repotenciacion 1%/ano plano (v13; la rampa 2%->3% original citaba): reemplazo de red en EMDE sube sostenido hasta
    2040 en el APS (IEA "Building the Future Transmission Grid", feb 2025). 2%
    = reemplazo de lineas EMDE; 3% = reemplazo de transformadores EMDE.
  Costo +0.3%/ano: metales ~25-30% del CAPEX (Thunder Said/PJM), crecimiento
    real neto ~+0.3%/ano (Goldman 2025); resto sin tendencia (Gorman/Mills/
    Wiser, LBNL 2019). El choque 2019-24 (IEA 2025) es de NIVEL, no de pendiente.
"""
import csv as _csvmod
import shutil
import sys
from pathlib import Path

# ============================ USER CONFIGURATION ============================
HERE = Path(__file__).resolve().parent
# Carpeta base con los .txt de entrada, con subcarpetas {SCEN}_0/ y dentro
# Pre_processed_{SCEN}_0_FLOORED.txt. Por defecto los Executables del repo (verificado
# byte-identico a los _FLOORED que resolvio Andrey). Para reproducir OFF de otros
# archivos (p.ej. una copia de los de Andrey), apunta BASE_DIR_OVERRIDE a esa carpeta.
import argparse
_ap = argparse.ArgumentParser()
_ap.add_argument("--base-dir", default=None, help="Carpeta Executables; activa el modo "
                 "per-escenario: lee {S}_0/*_FLOORED.txt y escribe {S}_0/*_VEGCON.txt ahi")
_ap.add_argument("--needs-csv", default=None, help="NewCapacity.csv de la corrida BSR (necesidad revelada)")
_args, _ = _ap.parse_known_args()

PER_SCENARIO_OUT = _args.base_dir is not None      # modo Executables (B2)
BASE_DIR_OVERRIDE = Path(_args.base_dir) if _args.base_dir else \
    Path(r"C:\Users\kt0031\Desktop\relac_tx\t1_confection\Executables")
EXE = BASE_DIR_OVERRIDE

# Escenario -> (datafile origen, aplica regla NLI?). RPO y costo aplican a los 4.
# NLI solo a los vegetativos. El swap del piso usa REF y OPT (abajo).
# v4: 6 escenarios. 2do elemento = MODO NLI: "uncapped" (BAU/OPT como v3, sin tope),
# "envelope" (INV/VGB, presupuesto regional), "ramp" (BAC/OPC = BAU/OPT + tope-rampa que
# capa el pico 2030 y empuja la inversion tardia). BAC usa la base BAU; OPC la base OPT.
SCENARIOS = {
    "BAU": (EXE / "BAU_0" / "Pre_processed_BAU_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt", "uncapped"),
    "OPT": (EXE / "OPT_0" / "Pre_processed_OPT_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt", "uncapped"),
    "INV": (EXE / "INV_0" / "Pre_processed_INV_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt", "envelope"),
    "VGB": (EXE / "VGB_0" / "Pre_processed_VGB_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt", "envelope"),
    "BAC": (EXE / "BAU_0" / "Pre_processed_BAU_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt", "ramp"),
    "OPC": (EXE / "OPT_0" / "Pre_processed_OPT_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt", "ramp"),
    # v14: variantes water-fill (mismo insumo que INV/VGB; solo cambian los pesos NLI).
    # Se generan solo si WATERFILL_ENABLE. Padres de ISRWF/VSRWF (cost_sensitivity v11).
    "INVWF": (EXE / "INV_0" / "Pre_processed_INV_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt", "envelope"),
    "VGBWF": (EXE / "VGB_0" / "Pre_processed_VGB_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt", "envelope"),
}
OUT_DIR = HERE

# --- Paso 0: SWAP del piso comprometido -----------------------------------
SWAP_REF, SWAP_OPT = "BAU", "OPT"        # el piso de REF se propaga a INV/VGB
SWAP_TWINS = ("BAU", "INV", "VGB")       # los tres comparten piso Tx identico
SWAP_FAMILIES = ("PWRTRN", "RNWTRN", "TRNNLI", "RNWNLI", "TRNRPO", "RNWRPO")
SWAP_FIRST_YEAR = 2027                    # no tocar historico 2023-2026
# RAISE (no value-swap): REF/INV/VGB CONSERVAN su piso comprometido propio; OPT = max(REF,OPT).
# El swap original (False) bajaba REF/INV/VGB al min -> los dejaba en ~0 en Brasil (sin la
# inversion comprometida real). El deep research (subastas ANEEL 2023-24) confirma que el piso
# de REF (Brasil ~22.5 GW 2027-29) es REAL; la correccion es SUBIR OPT, no bajar REF.
RAISE_NOT_SWAP = True
# Re-fechado del bipolo Graca Aranha-Silvania (5 GW): ONS COD 2030 (no 2029). Mueve 5 GW de
# RNWTRNBRAXX de 2029 -> 2030 en el piso (aplica a REF/twins/OPT-via-max y a la calibracion).
# Toggle: pon () para desactivar y volver al piso original. Al sacar 5 GW de la ventana
# 2024-2029 sube el multiplicador (~1.49 -> ~1.80) => costos mas altos.
BIPOLE_REDATE = (("RNWTRNBRAXX", 5.0, 2029, 2030),)   # () para desactivar

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
CALIB_WINDOW = (2024, 2029)              # 2024-2029 (usuario 2026-07-10): incluye 2024 bajo -> m=1.489
CALIB_MULT_OVERRIDE = None               # None = calcular m del promedio; o fijar a mano

# --- Paso 2: lineas nuevas no planificadas --------------------------------
ANCHOR_YEAR, ANCHOR_MUSD = 2022, 3300.0     # v13: IEA/SEGIB ~3077 @2022 (20000/6.5), expresado en USD 2023 ~ 3300
GROWTH = 0.019                              # tendencia historica
NLI_FIRST_YEAR = 2030                       # no planificadas: no antes de 2030
REN_SHARE_2050 = 0.70                       # glide desde mezcla existente a esto

# --- Paso 3: repotenciacion (flujo rampa, SIN techo acumulado) ------------
RPO_FIRST_YEAR = 2028
RPO_PCT_START = 0.01          # v13: ritmo anual PLANO 1%/ano (usuario 2026-08-31)
RPO_PCT_END = 0.01            # v13: START==END => rpo_pct(y) = 1% para todo y>=2028 (sin rampa)
RPO_RAMP_END = 2040
RPO_SOURCE = {"TRNRPO": "PWRTRN", "RNWRPO": "RNWTRN"}

# --- Paso 4: escalada de costo --------------------------------------------
COST_ESC_FROM, COST_ESC_RATE = 2025, 0.003  # +0.3% real/ano

# --- Refinamientos 2026-07-10 (tras el solve 20260710) --------------------
# (a) Cerrar la ventana sin tope: los topes de PLANIFICADAS y RPO cubren TODOS los
#     anos (antes empezaban en 2027/2028 y el modelo hacia dumping en el ultimo ano
#     sin tope). RPO pre-2028 => tope 0 (solo el piso comprometido lo salva la guarda).
FIRST_MODEL_YEAR = 2023
# (b) PLANIFICADAS por escenario:
#     - OPTIMO: fijado en el plan OPT (plan optimo).
#     - REFERENCIA: fijado en su piso comprometido (modesto).
#     - VEGETATIVOS: pueden construir ENTRE el nivel REF (piso) y el plan OPT, pero
#       ESCALADO para que el total anual (planif+RPO+NLI) nunca exceda el envelope
#       (i_region ~3.6k->4.4k). En anos pico (Brasil 2027-2030) el techo planificado
#       se escala hacia abajo para caber; en anos sueltos permite hasta el plan OPT.
#       Antes de 2030 (sin NLI) las planificadas son el unico canal -> el escalado deja
#       que el veg use el envelope via planificadas.
VEG_PLANNED_RANGE = False    # (usuario 2026-07-10) False: INV/VGB = REF en planificadas (fijo en piso comprometido). True: veg entre REF y OPT (escalado al envelope)
# (c) REF/OPT: tope SUAVE de NLI (evita el pico de un solo ano; grafica mas limpia).
#     Rampa lineal de REFOPT_NLI_2030 a REFOPT_NLI_2050 (MUSD/ano), repartida por pais.
#     Inicio BAJO (1.5k) para NO apilarse sobre el pico de planificadas del OPT en 2030.
#
# --- Refinamiento post-solve 20260711 (v3.2): QUITAR el tope de NLI de REF/OPT -----
#     Diagnostico (OLD 20260710 vs NEW 20260711): el tope suave por-pais era el UNICO
#     cambio material de insumo entre ambas corridas y HUNDIO la inversion tardia de
#     lineas nuevas (2046-2050): REF 11.3k->5.9k, OPT 9.5k->5.7k MUSD/ano (97% del
#     desplome es NLI). Mecanismo: (1) el reparto por cuota de costo INANICIONA a ARG
#     (cuota 1.4% vs ~14% de demanda revelada) -> ARG cae 35.6->4.4 GW; PER tambien se
#     fija; (2) al morder TEMPRANO (2030-41) reorienta el flujo hacia lineas
#     PLANIFICADAS ya construidas (FC 51%->66%) en vez de construir NLI. El trabajo de
#     transmision se conserva (~14464 PJ 2050 en ambas), asi que el pico es capacidad
#     sustituible; recuperarlo es una decision de planeacion, no de factibilidad.
#     Decision del usuario (2026-07-10): recuperar la magnitud tardia > suavidad.
#     REFOPT_NLI_ENABLE=False => no se escribe NINGUN tope de NLI para REF/OPT
#     (equivale a la corrida OLD, uncapped desde 2030). Solo afecta REF y OPT; los
#     vegetativos (INV/VGB) usan la rama independiente 'apply_nli' (envelope) y NO
#     cambian. Los demas refinamientos de v3.1 (topes 2023-2026, RPO=0 pre-2028,
#     OPT con VEGCON) se conservan. Para re-habilitar el tope: poner True.
REFOPT_NLI_ENABLE = False
REFOPT_NLI_2030 = 1500.0
REFOPT_NLI_2050 = 20000.0

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

# ========================= v14 (2026-09-01) ================================
# Decisiones del usuario 2026-09-01 (diagnostico de los "wedges" ETT):
#  - COMPARADORA (BAC/OPC): la rampa NLI 2000->18000 (v4, SIN fuente) se reemplaza
#    por la trayectoria i_comp: 3300 (USD2023, ancla 2022) -> I_COMP_2050 = 20000
#    (USD2023) EXPONENCIAL (~6.6%/ano). Fuente del endpoint: IEA LAEO 2023,
#    "Investment in transmission networks increases nearly 6.5-fold from 2022
#    levels to reach over USD 20 billion" (lectura conservadora: multiple efectivo
#    6.06x sobre el ancla en USD2023). MISMA identidad contable que el envelope:
#    presup_NLI = max(0, i_comp - planificadas - techo RPO); la RPO queda ABIERTA
#    al 1% en la comparadora. 2030 se auto-capa (el piso comprometido excede i_comp).
#  - FLOOR ARGENTINA (solo comparadora, ADITIVO): el peso historico de ARG (~1.1%)
#    codifica el congelamiento tarifario (Transener), no su necesidad. Rebanada
#    ARG(y) = max(peso x presup(y), share_nec x presup(y)); share_nec =
#    necesidad revelada (BSR) / presupuesto NLI acumulado 2030-2050 (~12-13%) [EST].
#    Necesidad = NewCapacity NLI de ARG en la corrida BSR (NLI sin tope, RPO
#    pinneada), costeada con los costos de ESTE datafile. ADITIVO: los otros 18
#    paises quedan byte-identicos; el total escrito excede i_comp SOLO en el
#    suplemento ARG (desviacion declarada en la nota). NO aplica a INV/VGB ni a
#    los SR: la ETT conserva el congelamiento (es su historia y su hallazgo).
#  - WATER-FILL (WATERFILL_ENABLE, booleano): escenarios INVWF/VGBWF, padres de
#    ISRWF/VSRWF (via cost_sensitivity v11 + nli_sr_recompute). MISMO envelope y
#    MISMO presupuesto que INV/VGB; SOLO cambian los pesos por pais: vector
#    ESTATICO water-fill (cada pais min(necesidad, rebanada); el sobrante se
#    re-vierte a los cortos proporcional al peso original, hasta converger; suma
#    1.0 = conservacion). Necesidad del MISMO archivo pinneado NLI_NEEDS_CSV.
#    PROVENANCE: el vector se imprime en el preflight; recalcular si BSR cambia.
#  - RAMP_NLI_2030/2050 quedan DEPRECADOS (constantes sin uso).
# ========================= v13 (2026-08-31) ================================
# Decisiones del usuario 2026-08-31 (tras diagnostico ISR/VSR: NLI ~= OPT en km):
#  - ENVELOPE: ANCHOR_MUSD 3000 -> 3300 (IEA/SEGIB ~3077 @2022 en USD 2023) y
#    ENV_GROWTH 0.03 -> 0.01 SOURCED (IEA LAEO 2023 fig 1.9: inversion electrica LAC
#    45 -> 50 GUSD/ano en ~10 anos ~ +1.06%/ano; redes DECLINARON en el periodo,
#    1% = lectura alta). Estructura RESIDUAL intacta: presup_NLI = i_region -
#    planificadas - techo RPO.
#  - SHARES RENORMALIZADAS: gshares (share x boost) ahora se dividen por su suma
#    (antes sumaban 1.3464 y los boosts creaban +34.6% de presupuesto NLI sobre el
#    remanente; verificado al MUSD contra los VEGCON previos). Los boosts pasan a
#    ser REDISTRIBUTIVOS (PER/CHL ganan share, BRA/MEX ceden), no aditivos.
#  - RPO: ritmo anual PLANO 1%/ano del stock congelado 2023, desde 2028
#    (antes rampa 2% @2028 -> 3% @2040). RPO_PCT_START = RPO_PCT_END = 0.01.
#  - Etiqueta del preflight ahora derivada de las constantes (la etiqueta fija
#    "1.9%" ocultaba el 3% aplicado desde v4).
#  - Boosts por pais (ALPHA_*, RPO_BOOST, floor BRB) SIN CAMBIO en este v13;
#    recalibrar contra backstop tras el solve (fueron afinados bajo el envelope 3%).
# ========================= v4 (2026-07-11) =================================
# Sobre v3.3. Decisiones del usuario 2026-07-11:
#  - 6 escenarios (arriba): BAU/OPT sin tope (hedge), INV/VGB envelope, BAC/OPC ramp.
#  - ALPHA_GROWTH: sube el presupuesto NLI de los PAISES EN CRECIMIENTO (crecimiento de
#    demanda 2025-2050 > mediana) por pais: presup[c] *= (1 + alpha*(growth[c]-1)). Solo
#    growers; los demas quedan en 1.0. Aplica a los 4 escenarios con tope (INV/VGB/BAC/OPC).
#  - Split ren/no-ren de NLI POR PAIS, leido de la mezcla de generacion resuelta del
#    escenario de referencia (INV<-OPT, VGB<-BAU, BAC<-BAU, OPC<-OPT). Reemplaza la
#    ren_share global (que estrangulaba la tuberia termica de paises como GTM).
#  - Envelope veg subido: ENV_GROWTH 0.019 -> 0.03 (mas espacio para growers).
#  - ICON (interconectores) fijados: MaxCapInv = piso comprometido (sin expansion libre).
#  - m=1.7954 se conserva; sin pisos NLI; BAU/OPT originales intactos.
ALPHA_GROWTH = 0.30           # boost de crecimiento (solo growers > mediana)
ALPHA_PER    = 0.90           # v5: Peru = 3x el alpha base (nodo delivery-bound: mas NLI interna)
ALPHA_CHL    = 0.57           # v12: Chile delivery-bound, 4ta iteracion. Trayectoria backstop
                              #     (solo 2050 desde v9): v8 322 PJ -> v9 29 (alfa .43) -> v10
                              #     7.6 (alfa .52) -> v11 0.50 PJ solo INV (alfa .55; VGB
                              #     cerro). El alfa exacto para 0.50 PJ (0.552) redondea a
                              #     0.55 = el vigente (irrepresentable a 2 decimales), asi que
                              #     se sube con holgura: 0.57 -> factor 1.737, +0.206 GW ren
                              #     = 13x el deficit (cubre la demanda inducida residual).
                              #     Techo 2050 ~17.4 GW (sigue < 26.3 GW revelados en BAU).
RPO_BOOST = {"BRB": 3.5}      # v12: multiplica rpo_pct del pais, islas sin canal de
                              #      expansion pre-2030 (BRB: backstop 0.05 PJ en 2029
                              #      en LOS 4 escenarios; tuberia ren 100% saturada y
                              #      RPO = unico canal legal de cable en 2029)
RPO_BOOST_UNTIL = 2030        # v12: el boost solo cubre la ventana pre-NLI
NLI_BUDGET_FLOOR_MUSD = {"BRB": 3.0}  # v12: piso de la rebanada NLI del pais (MUSD/ano;
                              #      el presupuesto NLI de 2030 es 0 para todos: las
                              #      planificadas+RPO consumen el envelope ese ano)
ENV_GROWTH = 0.01             # v13: 1%/ano SOURCED: IEA LAEO 2023 fig 1.9, inversion electrica
                              #      LAC ~45 GUSD/ano (prom. 2010-2014) -> ~50 GUSD/ano (2020-2022)
                              #      ~ +1.06%/ano; las REDES declinaron en ese periodo, asi que
                              #      1% es lectura ALTA (conservadora hacia arriba) para Tx.
RAMP_NLI_2030 = 2000.0        # v4, DEPRECADO en v14 (la comparadora usa i_comp; sin uso)
RAMP_NLI_2050 = 18000.0       # v4, DEPRECADO en v14 (sin uso)
I_COMP_2050 = 20000.0         # v14: endpoint de la trayectoria comparadora (BAC/OPC)
                              #      @2050 en USD2023. Fuente: IEA LAEO 2023
                              #      ("Investment in transmission networks increases
                              #      nearly 6.5-fold from 2022 levels to reach over
                              #      USD 20 billion"). Lectura conservadora: 20000
                              #      plano en USD2023 => multiple efectivo 6.06x.
NLI_NEEDS_CSV = Path(_args.needs_csv) if _args.needs_csv else HERE / "outputs_BSR" / "NewCapacity.csv"
                              # v14: NECESIDAD REVELADA, pinneada a la corrida BSR del
                              #      2026-09-01 (NLI sin tope + RPO pinneada). Usada por
                              #      (a) el floor ARG de la comparadora y (b) el vector
                              #      water-fill. DEBE venir de una corrida SIN tope NLI;
                              #      recalcular todo si BSR se re-resuelve.
WATERFILL_ENABLE = True       # v14: booleano. True => genera INVWF/VGBWF ademas de la
                              #      familia base. False => solo la familia base
                              #      (byte-identica a v13 salvo la comparadora BAC/OPC).
WF_SCENARIOS = ("INVWF", "VGBWF")
ARG_NEED_GW_DOC = 26.80       # [EST] documentacion: NLI ARG acumulada 2030-2050 en BSR
                              #      (el valor operativo se costea del CSV en runtime)
PIN_ICON = True               # v4: fijar interconectores a MinCapInv (sin expansion)
MEDIAN_GROWTH = 2.9735        # mediana del crecimiento de demanda 2025-2050 (19 paises)
DEMAND_GROWTH = {"ARG": 2.6326, "BOL": 3.5164, "BRA": 2.365, "BRB": 2.0458, "CHL": 2.2927,
  "COL": 3.3325, "CRI": 2.9735, "DOM": 3.9323, "ECU": 2.7377, "GTM": 3.6041, "HND": 3.3577,
  "HTI": 2.937, "MEX": 1.6378, "NIC": 3.0872, "PAN": 3.785, "PER": 3.7851, "PRY": 3.5168,
  "SLV": 2.8466, "URY": 2.2435}
# mezcla renovable de generacion resuelta (bus 00 / (00+01)), promedio 2040-2050:
REN_BAU = {"CRI": 0.7435, "NIC": 0.6493, "CHL": 0.8258, "URY": 0.985, "PRY": 1.0, "ECU": 0.9451,
  "COL": 0.8623, "HTI": 0.9348, "PAN": 0.9903, "GTM": 0.5377, "ARG": 0.5661, "SLV": 0.8152,
  "HND": 0.8579, "DOM": 0.9373, "BOL": 0.9181, "MEX": 0.6589, "BRB": 0.84, "PER": 0.7574, "BRA": 0.9547}
REN_OPT = {"CRI": 0.8119, "NIC": 0.7188, "CHL": 0.8375, "URY": 0.9848, "PRY": 1.0, "ECU": 0.8295,
  "COL": 0.8737, "HTI": 0.8672, "PAN": 0.9251, "GTM": 0.5715, "ARG": 0.563, "SLV": 0.7815,
  "HND": 0.7901, "DOM": 0.7739, "BOL": 0.7759, "MEX": 0.5998, "BRB": 0.3923, "PER": 0.7592, "BRA": 0.9433}
REN_REF = {"BAU": REN_BAU, "OPT": REN_OPT}
# escenario cuya mezcla de generacion define el split ren/no-ren de NLI por pais
REN_REF_SCEN = {"INV": "OPT", "VGB": "BAU", "BAC": "BAU", "OPC": "OPT",
                "INVWF": "OPT", "VGBWF": "BAU"}   # v14: WF hereda el split del padre
# ===========================================================================

MININV = "TotalAnnualMinCapacityInvestment"
TARGET_PARAMS = ("CapitalCost", "TotalAnnualMaxCapacityInvestment",
                 "TotalAnnualMaxCapacity", "ResidualCapacity", MININV)
# parametros que el escritor gestiona (sobre-escribe / inserta)
WRITE_PARAMS = ("CapitalCost", "TotalAnnualMaxCapacityInvestment",
                "TotalAnnualMaxCapacity", MININV)


def i_region(y):
    return ANCHOR_MUSD * (1 + ENV_GROWTH) ** (y - ANCHOR_YEAR)   # v13: 3300 @2022 x 1.0%/ano


def i_comp(y):
    """v14: trayectoria de la COMPARADORA (BAC/OPC). Exponencial del MISMO ancla
    (3300 USD2023 @2022) al endpoint I_COMP_2050=20000 @2050 (~6.64%/ano).
    Misma identidad contable que el envelope; solo cambia la trayectoria."""
    return ANCHOR_MUSD * (I_COMP_2050 / ANCHOR_MUSD) ** ((y - ANCHOR_YEAR) / (2050 - ANCHOR_YEAR))


def refopt_nli_cap(y):
    """Tope suave de NLI para REF/OPT: rampa lineal 2030->2050 (MUSD/ano). Evita el
    pico de un solo ano; deja que el modelo reparta la inversion (grafica mas limpia)."""
    if y < NLI_FIRST_YEAR:
        return 0.0
    f = (y - NLI_FIRST_YEAR) / (LAST_YEAR - NLI_FIRST_YEAR)
    return REFOPT_NLI_2030 + (REFOPT_NLI_2050 - REFOPT_NLI_2030) * f


def calib_anchor(y):
    return CALIB_ANCHOR_MUSD * (1 + GROWTH) ** (y - CALIB_ANCHOR_YEAR)


def rpo_pct(y):
    if y < RPO_FIRST_YEAR:
        return 0.0
    if y >= RPO_RAMP_END:
        return RPO_PCT_END
    return RPO_PCT_START + (RPO_PCT_END - RPO_PCT_START) * \
        (y - RPO_FIRST_YEAR) / (RPO_RAMP_END - RPO_FIRST_YEAR)


def rpo_pct_country(c, y):
    """rpo_pct con boost por pais (RPO_BOOST), solo hasta RPO_BOOST_UNTIL (ventana
    pre-NLI). Paises no listados: identico a rpo_pct(y) en todos los anos."""
    b = RPO_BOOST.get(c, 1.0) if y <= RPO_BOOST_UNTIL else 1.0
    return rpo_pct(y) * b


def final_shares():
    bn = {c: v / BNAM_YEARS for c, v in BNAM_CUM.items()}
    raw = {c: max(DEEP[c], FALLBACK.get(c, 0), bn.get(c, 0)) for c in DEEP}
    tot = sum(raw.values())
    return {c: v / tot for c, v in raw.items()}


def load_needs(csv_path):
    """v14: lee NewCapacity.csv de la corrida de NECESIDAD (BSR: NLI sin tope, RPO
    pinneada): filas NLI 2030+. -> dict (tech, ano) -> GW."""
    rows = {}
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for r in _csvmod.DictReader(fh):
            t = r["TECHNOLOGY"]
            if t.startswith(("TRNNLI", "RNWNLI")) and int(r["YEAR"]) >= NLI_FIRST_YEAR:
                k = (t, int(r["YEAR"]))
                rows[k] = rows.get(k, 0.0) + float(r["VALUE"])
    return rows


def waterfill(w, need_musd, B):
    """v14: water-filling ESTATICO (mismo algoritmo que nli_prerun_check): cada pais
    recibe min(necesidad, rebanada); el sobrante de los que necesitan menos se
    re-vierte a los que siguen cortos, proporcional a su peso ORIGINAL, hasta
    converger. Redistribucion pura: devuelve pesos que suman 1.0 (conservacion)."""
    alloc = dict.fromkeys(w, 0.0)
    rem, active = B, set(w)
    for _ in range(50):
        tot_w = sum(w[c] for c in active)
        if rem < 1e-6 or not active or tot_w < 1e-12:
            break
        newly = set()
        for c in list(active):
            if alloc[c] + rem * w[c] / tot_w >= need_musd.get(c, 0.0) - 1e-9:
                newly.add(c)
        take = 0.0
        for c in (newly or active):
            g = rem * w[c] / tot_w
            if c in newly:
                g = min(g, max(0.0, need_musd.get(c, 0.0) - alloc[c]))
            alloc[c] += g
            take += g
        active -= newly
        rem -= take
        if not newly:
            break
    out = {c: (alloc[c] / B if B > 0 else w[c]) for c in w}
    s = sum(out.values())
    if 0 < s < 1.0 - 1e-9:   # regimen tuneable (sobra dinero sin taker): renormalizar
        out = {c: v / s for c, v in out.items()}
    return out


def ren_share(year, ren_2030):
    if year <= NLI_FIRST_YEAR:
        return ren_2030
    f = (year - NLI_FIRST_YEAR) / (LAST_YEAR - NLI_FIRST_YEAR)
    return ren_2030 + (REN_SHARE_2050 - ren_2030) * f


def growth_factor(c):
    """v4: multiplicador del presupuesto NLI por crecimiento de demanda. Solo growers
    (> mediana); el resto queda en 1.0. factor = 1 + alpha*(growth-1).
    v8: CHL bypasea la guarda de mediana (delivery-bound puro, g<mediana)."""
    g = DEMAND_GROWTH.get(c, 1.0)
    if c == "PER":
        return 1.0 + ALPHA_PER * (g - 1.0)        # grower + delivery-bound
    if c == "CHL":
        return 1.0 + ALPHA_CHL * (g - 1.0)        # v8: delivery-bound puro (bypass mediana)
    return 1.0 + ALPHA_GROWTH * (g - 1.0) if g > MEDIAN_GROWTH else 1.0


def ramp_nli_cap(y):
    """v4: tope-rampa de NLI para BAC/OPC (MUSD/ano). Capa bajo en 2030 (mata el pico)
    y sube linealmente a 2050 -> deja espacio a la inversion tardia."""
    if y < NLI_FIRST_YEAR:
        return 0.0
    f = (y - NLI_FIRST_YEAR) / (LAST_YEAR - NLI_FIRST_YEAR)
    return RAMP_NLI_2030 + (RAMP_NLI_2050 - RAMP_NLI_2030) * f


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


def redate_floor(mp):
    """Aplica BIPOLE_REDATE a un mapa de piso {(tech,year): GW}: mueve GW de 'from' a 'to'."""
    mp = dict(mp)
    for tech, gw, fr, to in BIPOLE_REDATE:
        mp[(tech, fr)] = mp.get((tech, fr), 0.0) - gw
        mp[(tech, to)] = mp.get((tech, to), 0.0) + gw
    return mp


def bipole_cells(base):
    """Solo las celdas re-fechadas (override para los twins, que conservan su base)."""
    ov = {}
    for tech, gw, fr, to in BIPOLE_REDATE:
        ov[(tech, fr)] = base.get((tech, fr), 0.0) - gw
        ov[(tech, to)] = base.get((tech, to), 0.0) + gw
    return ov


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
def build_mods(lines, mode, gshares, ren_c, calib, min_override, planned_ceiling, is_opt,
               need_rows=None, use_waterfill=False):
    # v4: mode in {uncapped, envelope, ramp}; gshares = shares x growth_factor;
    #     ren_c = mezcla renovable por pais (split ren/no-ren de NLI).
    # v14: need_rows = necesidad revelada (load_needs); use_waterfill = reemplazar
    #     gshares por el vector water-fill (solo INVWF/VGBWF). mode "ramp" ahora es
    #     la COMPARADORA (i_comp residual + floor ARG), no la rampa v4.
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

    # Paso 3 (PRIMERO, para conocer el costo RPO al escalar planificadas del veg):
    # repotenciacion (4 escenarios), flujo, sin techo acumulado. Cubre TODOS los anos;
    # rpo_pct=0 antes de 2028 (programa arranca 2028) -> 2023-2027 en 0 y la guarda solo
    # respeta el piso comprometido (sin dumping temprano).
    for rpo, existing_fam in RPO_SOURCE.items():
        for tech in sorted(t for t in techs if t.startswith(rpo)):
            c = tech[6:9]
            rc = resid(existing_fam + c + "XX")
            if rc <= 0:
                continue
            for y in range(FIRST_MODEL_YEAR, LAST_YEAR + 1):
                mod["TotalAnnualMaxCapacityInvestment"][(tech, y)] = rpo_pct_country(c, y) * rc

    def _rpo_cost_musd():                          # MUSD del techo RPO POST-guarda
        d = {}
        for (t, y), gw in mod["TotalAnnualMaxCapacityInvestment"].items():
            if t.startswith(("TRNRPO", "RNWRPO")):
                eff_gw = max(gw, eff_min.get((t, y), 0.0))
                d[y] = d.get(y, 0.0) + eff_gw * cost_final(true_base, t, y, calib)
        return d
    rpo_cost = _rpo_cost_musd()

    # PLANIFICADAS (PWRTRN/RNWTRN) -- techo por escenario, TODOS los anos (2023-2050;
    # esto cierra la ventana sin tope 2023-2026 donde el modelo hacia dumping):
    #   OPTIMO      -> fijado en el plan OPT.
    #   REFERENCIA  -> fijado en su piso comprometido (modesto).
    #   VEGETATIVOS -> ENTRE REF y OPT: plan OPT ESCALADO por scale(y) in [0,1] tal que
    #                  planif+RPO <= envelope(i_region) cada ano. En anos pico (Brasil)
    #                  scale<1 (cabe en el envelope); en anos sueltos scale=1 (hasta OPT).
    plan_techs = sorted(t for t in techs if t.startswith(("PWRTRN", "RNWTRN")))
    yrs_all = list(range(FIRST_MODEL_YEAR, LAST_YEAR + 1))
    scen_planned = {}
    if is_opt:
        for tech in plan_techs:
            for y in yrs_all:
                scen_planned[(tech, y)] = planned_ceiling.get((tech, y), 0.0)
    elif mode != "envelope":                       # BAU/OPT/BAC/OPC: piso comprometido
        for tech in plan_techs:
            for y in yrs_all:
                scen_planned[(tech, y)] = eff_min.get((tech, y), 0.0)
    elif VEG_PLANNED_RANGE:                        # VEGETATIVOS: plan OPT escalado al envelope
        opt_plan_musd = {y: sum(planned_ceiling.get((t, y), 0.0) * cost_final(true_base, t, y, calib)
                                for t in plan_techs) for y in yrs_all}
        for y in yrs_all:
            budget = max(0.0, i_region(y) - rpo_cost.get(y, 0.0))   # sitio para planificadas
            scale = min(1.0, budget / opt_plan_musd[y]) if opt_plan_musd[y] > 1e-9 else 0.0
            for tech in plan_techs:
                scen_planned[(tech, y)] = planned_ceiling.get((tech, y), 0.0) * scale
    else:                                          # VEGETATIVOS (modo fijo): piso comprometido
        for tech in plan_techs:
            for y in yrs_all:
                scen_planned[(tech, y)] = eff_min.get((tech, y), 0.0)

    # escribir el techo de planificadas (por escenario), todos los anos
    for (tech, y), v in scen_planned.items():
        mod["TotalAnnualMaxCapacityInvestment"][(tech, y)] = v

    # Paso 2: lineas nuevas no planificadas (NLI) -----------------------------
    #   VEGETATIVOS (apply_nli): ENVELOPE TOTAL. planif(escalado)+RPO+NLI <= I_region
    #     (3300 x1.0% ~3.6k->4.4k). NLI = remanente. => total del veg <= envelope.
    #   REF/OPT: tope SUAVE de NLI (refopt_nli_cap, rampa 1.5k->20k) -> sin pico de un ano.
    def _write_nli(budget_of_year, share_floor=None):
        share_floor = share_floor or {}
        for fam in ("TRNNLI", "RNWNLI"):
            for tech in sorted(t for t in techs if t.startswith(fam)):
                c = tech[6:9]
                if c not in gshares or tech not in true_base:
                    continue
                cumul_gw = 0.0
                for y in range(NLI_FIRST_YEAR, LAST_YEAR + 1):
                    # v4: split ren/no-ren POR PAIS (mezcla de generacion de referencia)
                    rs = ren_c.get(c, REN_SHARE_2050)
                    w = rs if fam == "RNWNLI" else (1 - rs)
                    # v4: gshares = shares x growth_factor(c) (boost a growers)
                    # v12: piso por pais de la rebanada NLI (islas; el presupuesto
                    #      natural de 2030 es 0 para todos los paises)
                    # v14: share_floor = piso PROPORCIONAL al presupuesto (ARG en la
                    #      comparadora; ADITIVO: no toca las rebanadas de los demas)
                    slice_musd = max(gshares[c] * budget_of_year(y),
                                     share_floor.get(c, 0.0) * budget_of_year(y),
                                     NLI_BUDGET_FLOOR_MUSD.get(c, 0.0))
                    musd = slice_musd * w
                    gw = musd / cost_final(true_base, tech, y, calib)
                    cumul_gw += gw
                    mod["TotalAnnualMaxCapacityInvestment"][(tech, y)] = gw
                    mod["TotalAnnualMaxCapacity"][(tech, y)] = cumul_gw

    def _need_musd_by_country():
        """v14: necesidad revelada por pais (MUSD), costeada con los costos de ESTE
        datafile (cost_final), no con un costo unitario proxy."""
        d = {}
        for (t, y), gw in (need_rows or {}).items():
            if t in true_base:
                d[t[6:9]] = d.get(t[6:9], 0.0) + gw * cost_final(true_base, t, y, calib)
        return d

    if mode == "envelope":                         # INV/VGB (+ WF): envelope residual
        planned_cost = {}
        for (t, y), gw in scen_planned.items():
            planned_cost[y] = planned_cost.get(y, 0.0) + gw * cost_final(true_base, t, y, calib)
        nli_budget = {y: max(0.0, i_region(y) - planned_cost.get(y, 0.0) - rpo_cost.get(y, 0.0))
                      for y in range(NLI_FIRST_YEAR, LAST_YEAR + 1)}
        if use_waterfill:                          # v14: SOLO cambian los pesos; B intacto
            if not need_rows:
                sys.exit("*** WATERFILL: falta el archivo de necesidad NLI_NEEDS_CSV")
            need = _need_musd_by_country()
            B = sum(nli_budget.values())
            gshares = waterfill(gshares, need, B)
            top = sorted(gshares, key=lambda x: -gshares[x])[:8]
            print(f"    [v14 WF] vector water-fill (suma={sum(gshares.values()):.6f}; "
                  f"B={B:,.0f} MUSD): "
                  + "  ".join(f"{c}:{gshares[c]:.3f}" for c in top) + "  ...")
        _write_nli(lambda y: nli_budget[y])
    elif mode == "ramp":                           # v14 COMPARADORA BAC/OPC: i_comp residual
        planned_cost = {}
        for (t, y), gw in scen_planned.items():
            planned_cost[y] = planned_cost.get(y, 0.0) + gw * cost_final(true_base, t, y, calib)
        nli_budget = {y: max(0.0, i_comp(y) - planned_cost.get(y, 0.0) - rpo_cost.get(y, 0.0))
                      for y in range(NLI_FIRST_YEAR, LAST_YEAR + 1)}
        if not need_rows:
            sys.exit("*** COMPARADORA: falta NLI_NEEDS_CSV para el floor de ARG")
        B = sum(nli_budget.values())
        arg_need = _need_musd_by_country().get("ARG", 0.0)
        share_floor = {"ARG": (arg_need / B) if B > 0 else 0.0}
        print(f"    [v14] comparadora: presup NLI 2030-2050 = {B:,.0f} MUSD | "
              f"floor ARG = {arg_need:,.0f} MUSD = {100 * share_floor['ARG']:.1f}% "
              f"del presupuesto (ADITIVO) [EST]")
        _write_nli(lambda y: nli_budget[y], share_floor=share_floor)

    # v4: INTERCONECTORES (ICON = TRN* que NO son NLI/RPO) fijados al piso comprometido
    # (MaxCapInv = MinCapInv). Sin expansion libre; solo lo planificado. anos 2027+.
    if PIN_ICON:
        icon = sorted(t for t in techs if t.startswith("TRN")
                      and not t.startswith(("TRNNLI", "TRNRPO")))
        for tech in icon:
            for y in range(SWAP_FIRST_YEAR, LAST_YEAR + 1):
                mod["TotalAnnualMaxCapacityInvestment"][(tech, y)] = eff_min.get((tech, y), 0.0)

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

    # v4: nombre largo (igual que los archivos de solve) para el paquete de corrida
    fname = f"Pre_processed_{name}_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED_VEGCON.txt"
    if PER_SCENARIO_OUT:
        d = EXE / f"{name}_0"          # BAC_0/, OPC_0/, INVWF_0/, VGBWF_0/ se crean aqui
        d.mkdir(exist_ok=True)
        dst = d / fname
    else:
        dst = OUT_DIR / fname          # modo legado: plano junto al script
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
    ref_base = load_min(ref_src)
    ref_min = redate_floor(ref_base)             # piso REF con el bipolo re-fechado
    opt_min = load_min(opt_src)                  # OPT sin bipolo (lo recibe via max)
    opt_over, twin_over_swap, movers = compute_swap(ref_min, opt_min)
    if RAISE_NOT_SWAP:
        # REF/INV/VGB conservan su piso comprometido propio; solo se re-fecha el bipolo.
        twin_over = bipole_cells(ref_base)
    else:
        twin_over = twin_over_swap                # swap original (baja REF/twins al min)

    print(f"\n=== PASO 0: {'RAISE' if RAISE_NOT_SWAP else 'SWAP'} del piso (donde REF>OPT, ano>=2027) ===")
    print(f"  celdas donde OPT sube al nivel de REF: {len(movers)}"
          + ("   [RAISE: REF/INV/VGB conservan su piso]" if RAISE_NOT_SWAP else ""))
    by_c = {}
    for (t, y, r, o) in movers:
        by_c.setdefault(t[6:9], [0.0, 0])
        by_c[t[6:9]][0] += (r - o)
        by_c[t[6:9]][1] += 1
    for c, (gw, n) in sorted(by_c.items(), key=lambda x: -x[1][0]):
        print(f"    {c}: OPT sube +{gw:.2f} GW hasta el nivel de REF ({n} celdas)")
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
    calib_floor = redate_floor(load_min(cal_src))   # piso de la REF (bipolo re-fechado)
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

    # --- Escribir los 6 escenarios (v4) ------------------------------------
    OPT_LIKE = ("OPT", "OPC")          # heredan el piso OPT (post-raise)
    TWIN_LIKE = ("BAU", "INV", "VGB", "BAC", "INVWF", "VGBWF")   # piso REF (twin)
    # v14: necesidad revelada (una sola lectura, pinneada). Obligatoria para la
    # comparadora (floor ARG) y para los WF; el resto corre sin ella.
    if NLI_NEEDS_CSV.is_file():
        need_rows = load_needs(NLI_NEEDS_CSV)
        print(f"\n[v14] necesidad revelada: {NLI_NEEDS_CSV} "
              f"({len(need_rows)} filas NLI 2030+; ARG={sum(v for (t, _y), v in need_rows.items() if t[6:9] == 'ARG'):.2f} GW)")
    else:
        need_rows = None
        print(f"\n[v14] ATENCION: no existe {NLI_NEEDS_CSV}; la comparadora y los WF abortaran")
    written = {}
    for name, (src, mode) in SCENARIOS.items():
        if name in WF_SCENARIOS and not WATERFILL_ENABLE:
            print(f"\n[SKIP] {name}: WATERFILL_ENABLE=False")
            continue
        if not src.exists():
            print(f"\n[SKIP] {name}: no existe {src.name}")
            continue
        is_opt_like = name in OPT_LIKE
        min_ov = opt_over if is_opt_like else (twin_over if name in TWIN_LIKE else {})
        # v4: shares escaladas por crecimiento (solo escenarios con tope) + split ren por pais
        if mode in ("envelope", "ramp"):
            gshares = {c: shares[c] * growth_factor(c) for c in shares}
            _sg = sum(gshares.values())            # v13: RENORMALIZAR (antes sumaban ~1.346:
            gshares = {c: v / _sg for c, v in gshares.items()}  # los boosts CREABAN presupuesto)
            ren_c = REN_REF.get(REN_REF_SCEN.get(name), {})
        else:                                   # uncapped: no se escribe tope NLI
            gshares = dict(shares)
            ren_c = {}
        lines = src.read_text(encoding="utf-8").splitlines(keepends=True)
        mod, cc_txt, true_base, resid, raised = build_mods(
            lines, mode, gshares, ren_c, calib, min_ov, opt_planned_ceiling, is_opt_like,
            need_rows=need_rows, use_waterfill=(name in WF_SCENARIOS))
        dst = apply_and_write(name, src, mod)
        written[name] = dst
        rule = {"envelope": "NLI-envelope+RPO+costo", "ramp": "NLI-ramp+RPO+costo",
                "uncapped": "RPO+costo (NLI libre)"}[mode]
        swaptag = ("OPT+raise" if is_opt_like else
                   ("REF/twin" if name in TWIN_LIKE else "sin swap"))
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
        chk(f"Brasil piso 2027+ OPT >= REF (raise: OPT {bra_opt:.1f} GW, REF {bra_ref:.1f} GW; "
            f"iguales cuando OPT solo hereda el piso de REF)",
            bra_opt >= bra_ref - 1e-6)
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

    # --- PREFLIGHT TECHO LINEAS PLANIFICADAS: OPT=plan; REF=piso; veg=entre REF y OPT ---
    # Regla v3.1: OPT fijado en el plan OPT; REF fijado en su piso comprometido; los
    # VEGETATIVOS pueden construir ENTRE el piso REF y el plan OPT (escalado al envelope).
    # Los topes cubren TODOS los anos (sin ventana de dumping).
    print("\n=== PREFLIGHT TECHO PLANIFICADAS (OPT=plan; REF=piso; veg=entre REF y OPT) ===")

    def planned_map(dst, param="TotalAnnualMaxCapacityInvestment"):
        L = dst.read_text(encoding="utf-8").splitlines(keepends=True)
        mx, _ = read_map(L, parse_blocks(L)[param])
        return {k: v for k, v in mx.items() if k[0].startswith(("PWRTRN", "RNWTRN"))}

    pmax = {n: planned_map(written[n]) for n in written}
    pmin = {n: planned_map(written[n], MININV) for n in written}
    # OPT: techo planificadas == plan OPT -> fijado
    opt_ceue = all(abs(pmax["OPT"].get(k, 0.0) - v) < 1e-9 for k, v in opt_planned_ceiling.items())
    chk("OPT: techo planificadas == plan OPT (fijado en el plan optimo)", opt_ceue)
    # REF: techo planificadas == su piso comprometido (modesto, fijado)
    ref_pinned = all(abs(pmax["BAU"].get(k, 0.0) - v) < 1e-9 for k, v in pmin["BAU"].items() if v > 1e-9)
    ref_noextra = all(mx <= pmin["BAU"].get(k, 0.0) + 1e-9 for k, mx in pmax["BAU"].items())
    chk("REF: techo planificadas == piso comprometido (modesto)", ref_pinned and ref_noextra)
    # veg: REF(piso) <= techo veg <= plan OPT, en cada celda (entre REF y OPT)
    for n in ("INV", "VGB", "INVWF", "VGBWF"):
        if n not in pmax:
            continue
        keys = set(pmax[n]) | set(pmax["OPT"])
        between = all(pmin[n].get(k, 0.0) - 1e-6 <= pmax[n].get(k, 0.0)
                      <= pmax["OPT"].get(k, 0.0) + 1e-6 for k in keys)
        chk(f"{n}: techo planificadas ENTRE piso REF y plan OPT (celda a celda)", between)
    # OPT construye MAS planificadas que REF (via swap de Brasil)
    opt_plan_gw = sum(pmax["OPT"].values())
    ref_plan_gw = sum(pmax["BAU"].values())
    chk(f"OPT planifica MAS que REF ({opt_plan_gw:.0f} vs {ref_plan_gw:.0f} GW-tope)",
        opt_plan_gw > ref_plan_gw)
    if REFOPT_NLI_ENABLE:
        print("  NLI: veg = envelope tight (3.6k->4.4k); REF/OPT = tope suave (rampa "
              f"{REFOPT_NLI_2030:.0f}->{REFOPT_NLI_2050:.0f} MUSD):")
        for y in (2030, 2040, 2050):
            print(f"    {y}: veg<= {i_region(y):8.0f}   REF/OPT<= {refopt_nli_cap(y):8.0f} MUSD")
    else:
        print("  NLI: veg = envelope tight (3.6k->4.4k); REF/OPT = SIN tope (NLI libre "
              "desde 2030, v3.2 -> recupera el pico de inversion tardia):")
        for y in (2030, 2040, 2050):
            print(f"    {y}: veg<= {i_region(y):8.0f}   REF/OPT<= (sin tope) MUSD")

    # REF/OPT: el tope de NLI sigue la rampa suave (evita picos)
    if REFOPT_NLI_ENABLE:
        for n in ("BAU", "OPT"):
            if n not in written:
                continue
            L = written[n].read_text(encoding="utf-8").splitlines(keepends=True)
            sp = parse_blocks(L)
            mx, _ = read_map(L, sp["TotalAnnualMaxCapacityInvestment"])
            cc, _ = read_map(L, sp["CapitalCost"])
            nli_musd = {y: sum(gw * cc.get((t, y), 0.0) for (t, yy), gw in mx.items()
                               if yy == y and t.startswith(("TRNNLI", "RNWNLI")))
                        for y in range(NLI_FIRST_YEAR, LAST_YEAR + 1)}
            ok = all(abs(nli_musd[y] - refopt_nli_cap(y)) < 0.02 * refopt_nli_cap(y)
                     for y in nli_musd)
            chk(f"{n}: tope NLI suave sigue la rampa (2030={nli_musd[2030]:.0f}, "
                f"2050={nli_musd[2050]:.0f} MUSD; sin pico)", ok)

    # --- PREFLIGHT vegetativo (valor deseado NLI + RPO no se auto-detiene) --
    print("\n=== PREFLIGHT VEGETATIVO (valor deseado + factibilidad) ===")
    ser = None
    for name in ("INV", "VGB", "INVWF", "VGBWF"):
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

    # --- v4: resumen de trayectorias NLI (tope MUSD/ano) por escenario -------
    print("\n=== v4 RESUMEN: tope NLI [MUSD/ano] por escenario (2030/2035/2040/2045/2050) ===")

    def nli_ceiling_musd(dst):
        L = dst.read_text(encoding="utf-8").splitlines(keepends=True)
        sp = parse_blocks(L)
        mx, _ = read_map(L, sp["TotalAnnualMaxCapacityInvestment"])
        cc, _ = read_map(L, sp["CapitalCost"])
        out = {}
        for (tt, yy), gw in mx.items():
            if tt.startswith(("TRNNLI", "RNWNLI")):
                out[yy] = out.get(yy, 0.0) + gw * cc.get((tt, yy), 0.0)
        return out
    for name in ("BAU", "OPT", "INV", "VGB", "BAC", "OPC", "INVWF", "VGBWF"):
        if name not in written:
            continue
        cap = nli_ceiling_musd(written[name])
        tag = "sin tope (NLI libre)" if not cap else ""
        vals = "  ".join(f"{y}={cap.get(y, 0):.0f}" for y in (2030, 2035, 2040, 2045, 2050))
        print(f"  {name}: {vals}   {tag}")
    print(f"  growers (boost x{1+ALPHA_GROWTH:.2f} sobre (g-1)): "
          f"{sorted(c for c in DEMAND_GROWTH if DEMAND_GROWTH[c] > MEDIAN_GROWTH)}")
    # Nodos delivery-bound (PER, CHL): tope NLI por tuberia (ren vs termica) en INV/BAC
    for cc in ("PER", "CHL"):
        for name in ("INV", "BAC"):
            if name not in written:
                continue
            L = written[name].read_text(encoding="utf-8").splitlines(keepends=True)
            sp = parse_blocks(L); mx, _ = read_map(L, sp["TotalAnnualMaxCapacityInvestment"])
            cc_map, _ = read_map(L, sp["CapitalCost"])
            rn = sum(gw * cc_map.get((f"RNWNLI{cc}XX", y), 0.0) for (tt, y), gw in mx.items()
                     if tt == f"RNWNLI{cc}XX" and y == 2050)
            th = sum(gw * cc_map.get((f"TRNNLI{cc}XX", y), 0.0) for (tt, y), gw in mx.items()
                     if tt == f"TRNNLI{cc}XX" and y == 2050)
            print(f"  [{name}] {cc} tope NLI 2050: renovable={rn:.0f}  termica={th:.0f} MUSD "
                  f"(factor growth_factor={growth_factor(cc):.3f})")

    print(f"\nRESULTADO: PASS={passed} FAIL={failed}")
    print_deliverables(calib)
    sys.exit(1 if failed else 0)


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
    # v4: el envelope ya NO es == i_region (se subio a 0.03 y se escalo por crecimiento
    # de los growers), asi que el invariante v3 no aplica. Chequeo: total >= i_region base
    # (el boost solo SUBE) y NLI > 0 y creciente en la ventana tardia.
    # v13: con shares RENORMALIZADAS el invariante vuelve a ser CONSERVACION:
    # total == max(i_region, planificadas+RPO) +- tolerancia (floors BRB ~3 MUSD + redondeo .6g).
    env = all(abs(total_musd[y] - max(i_region(y), total_musd[y] - nli_musd[y])) <= 5.0
              for y in range(NLI_FIRST_YEAR, LAST_YEAR + 1))
    t(f"[{name}] CONSERVACION envelope: total == max(i_region, planif+RPO) +-5 MUSD "
      f"(2030={total_musd[2030]:.0f}, 2035={total_musd[2035]:.0f}, 2050={total_musd[2050]:.0f}; "
      f"i_region 2050={i_region(2050):.0f})", env)
    # v4: NLI crece hacia el final (el growth-boost empuja la magnitud tardia)
    no_stack = nli_musd[2050] >= nli_musd[2035] - 1e-6 and nli_musd[2050] > 0
    t(f"[{name}] NLI tardia > temprana (growth-boost; 2035={nli_musd[2035]:.0f}, "
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
    ax[0].plot(ys, ireg, "--", color=TXT, lw=1.5,
               label=f"Objetivo {ANCHOR_MUSD:.0f}->{i_region(LAST_YEAR):.0f} ({ENV_GROWTH:.1%})")
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
        "los vegetativos, un ENVELOPE TOTAL de inversion Tx = 3300 x1.0%/ano "
        "(~3.6k -> 4.4k MUSD): las lineas planificadas (= plan OPTIMO) y la "
        "repotenciacion consumen el envelope PRIMERO, y las lineas nuevas no "
        "planificadas (NLI) reciben SOLO el remanente (no se apilan). La "
        "repotenciacion corre a 1%/ano PLANO del stock congelado 2023 (v13) sin techo "
        "acumulado. Las planificadas se capan al plan OPTIMO en LOS 4 escenarios. "
        "v14: la COMPARADORA (BAC/OPC) usa la misma identidad con la trayectoria "
        f"i_comp 3300 -> {I_COMP_2050:.0f} MUSD @2050 (IEA LAEO 2023, ~6.6%/ano, RPO "
        "abierta al 1%), mas un floor ADITIVO para Argentina (necesidad revelada BSR, "
        "[EST]) que corrige el artefacto del congelamiento tarifario en su peso "
        "historico. Los escenarios WF reparten el MISMO presupuesto con pesos "
        "water-fill (estaticos, suma 1). [EST] marca los tramos estimados.")
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
        "PWRTRN/RNWTRN, 2028-2050, pct 1% plano desde 2028 (v13); eliminar el "
        "techo acumulado RPO.",
        "ENVELOPE NLI (SOLO INV/VGB, 2030+): el tope de inversion Tx TOTAL del "
        "vegetativo = I_region(ano) = 3300 x1.0%. NLI recibe el REMANENTE: "
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
        "envelope Tx total = 3.6k->4.4k con NLI como remanente (no apilada); RPO no se "
        "auto-detiene; capacidad no decrece; 0 conflictos duros de factibilidad en los "
        "4 (min>max inv/cap, residual>techo, piso inalcanzable, actividad). Luego "
        "resolver CPLEX y confirmar OPT el mayor y backstop ~0.",
    ], 1):
        print(f"  {i}. {s}")


if __name__ == "__main__":
    main()
