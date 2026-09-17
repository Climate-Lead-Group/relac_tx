"""
dashboard_config.py — Configuración compartida para el dashboard RELAC_TX:
paths, años de referencia, escenarios, paletas de color, clasificadores de
tecnología y helpers de carga del CSV combinado.
"""

import os
import sys
from pathlib import Path

import pandas as pd

# Rutas canónicas del repo (inputs/, outputs/) vía scripts/common/relac_paths.
# Este módulo vive en scripts/figures/common/ -> parents[2] es scripts/, el
# ÚNICO directorio que entra en sys.path; todo se importa como paquete
# (common.relac_paths, figures.common.dashboard_config, ...). Spec 2026-09-16 §3.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common import relac_paths as P  # noqa: E402

# ================================================================
# Paths
# ================================================================
# CSV combinado que produce B2 (outputs/RELAC_TX_Combined_Inputs_Outputs.csv).
CSV_PATH = str(P.OUTPUTS / "RELAC_TX_Combined_Inputs_Outputs.csv")
# Capacidad/distancia de líneas por país (chart_10, fig_km_lineas*).
CAPACITY_DISTANCES_PATH = str(P.DATA / "CapacityAndDistances.xlsx")
# Centroides por región para los mapas de transmisión (pestañas 16/17).
CENTERPOINTS_PATH = str(P.MISCELLANEOUS / "centerpoints.csv")
# Año base BAU con datos reales de Primary/Secondary/Demand Techs (pestaña 18, RES).
RES_BASE_YEAR_XLSX = str(P.A1_OUTPUTS / "A1_Outputs_BAU" / "A-O_AR_Model_Base_Year.xlsx")
# Códigos/nombres de país (Z_AUX_generate_RES_diagram).
COUNTRY_CODES_YAML = str(P.CONFIG_COUNTRY_CODES)
# Salidas (spec 2026-09-16 §5.1): todo bajo outputs/Figures/ vía relac_paths.
# Los nombres se conservan porque los usan los 40 fig_*.py y build_dashboard.py.
FIGURES_DIR = str(P.FIGURES_REPORT)                     # fig_*.py de scripts/figures/report/
FIGURES_PRESENTATION_DIR = str(P.FIGURES_PRESENTATION)  # fig_*_presentation.py (letra grande,
                                                        # grupos juntos, leyenda en una fila)
DASHBOARD_DIR = str(P.FIGURES_DASHBOARD)                # dashboard.html + chart*.png (--png)
# Caché de escenarios autodetectados del CSV (antes vivía en Figures/).
SCENARIOS_CACHE = os.path.join(str(P.FIGURES), ".scenarios_cache.json")
# Balance energético anual OLADE/sieLAC (cuotas de importación, gráfico 12).
OLADE_BALANCE_PATH = str(
    P.MATRIZ_BALANCE / "OLADE - Matriz de balance energético - Anual.xlsx"
)

# Sufijo opcional para los nombres de archivo generados (vacío = sin sufijo).
OUTPUT_SUFFIX = ""

# ================================================================
# Reference years & scenarios
# ================================================================
REFERENCE_YEARS = [2025, 2030, 2035, 2040, 2045, 2050]
# Todos los años del horizonte del CSV (candidatos del selector dinámico).
ALL_YEARS = list(range(2023, 2051))
# Los escenarios se AUTODETECTAN de la columna Scenario del CSV combinado, para
# que CUALQUIER escenario nuevo aparezca solo en los menús sin tocar el código.
# Orden: los preferidos primero (2026-09-16: el orden de la tabla de los 14
# escenarios de la corrida — familia OPT (B**), familia ETT (I**), PLAN, ETT-GP;
# después los códigos legados por si reaparecen), el resto alfabético. Se cachea
# por mtime del CSV (.scenarios_cache.json) para no releer ~1 GB en cada import;
# si el CSV falta o falla, cae a los 14 de la corrida.
_SCEN_14 = [
    "BAC", "BFA", "BFB", "BRA", "BRB", "BSR",
    "ISR", "IFA", "IFB", "INV", "IRA", "IRB",
    "OPC", "VSR",
]
_SCEN_PREFERRED = _SCEN_14 + [
    # legados (corridas anteriores a 2026-09-16)
    "BAU", "VGB", "OPT", "BCR", "OCR", "BCL", "OCL",
    "ICL", "ICR", "VCL", "VCR",
]


def _detect_scenarios() -> list:
    try:
        import json
        cache = SCENARIOS_CACHE
        mt = os.path.getmtime(CSV_PATH)
        if os.path.exists(cache):
            c = json.load(open(cache, encoding="utf-8"))
            if c.get("mtime") == mt and c.get("scen"):
                return c["scen"]
        found = (
            pd.read_csv(CSV_PATH, usecols=["Scenario"])["Scenario"]
            .dropna().astype(str).unique().tolist()
        )
        ordered = [s for s in _SCEN_PREFERRED if s in found]
        ordered += sorted(s for s in found if s not in _SCEN_PREFERRED)
        ordered = ordered or list(_SCEN_14)
        try:
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            json.dump({"mtime": mt, "scen": ordered}, open(cache, "w", encoding="utf-8"))
        except Exception:
            pass
        return ordered
    except Exception:
        return list(_SCEN_14)


SCENARIOS = _detect_scenarios()
# Alias de DISPLAY de los escenarios (lo que VE el usuario; la clave es el
# CÓDIGO de la columna Scenario del CSV). Cualquier código sin alias se muestra
# tal cual (fallback SCENARIO_ALIAS.get(sc, sc)).
#
# 2026-09-16: tabla de los 14 escenarios de la corrida. Familias:
#   B** = OPT  (BAC base; BSR = sin repotenciación; BF*/BR* = sensibilidades)
#   I** = ETT  (ISR base; INV = con repotenciación; IF*/IR* = sensibilidades)
#   OPC = PLAN ; VSR = ETT-GP.
#   *FA/*FB = mayor/menor costo de combustible (fósil); *RA/*RB = mayor/menor
#   costo de renovables.
SCENARIO_ALIAS = {
    # --- familia OPT ---
    "BAC": "OPT",
    "BFA": "OPT mayor costo combustible",
    "BFB": "OPT menor costo combustible",
    "BRA": "OPT mayor costo renovables",
    "BRB": "OPT menor costo renovables",
    "BSR": "OPT sin repotenciación",
    # --- familia ETT ---
    "ISR": "ETT",
    "IFA": "ETT mayor costo combustible",
    "IFB": "ETT menor costo combustible",
    "INV": "ETT con repotenciación",
    "IRA": "ETT mayor costo renovables",
    "IRB": "ETT menor costo renovables",
    # --- otros ---
    "OPC": "PLAN",
    "VSR": "ETT-GP",
    # --- LEGADO (códigos que ya no vienen en la corrida 2026-09-16; se conservan
    # por si se abre un CSV viejo). Ninguno choca con los 14 alias de arriba. ---
    "VGB": "ETT-GP-OLD",       # Tx restringida, generación planificada / PEGs (= OPT)
    "OPT": "OPT-output",       # OPT crudo (sin tope) — distinto del alias de BAC ("OPT")
    "BCR": "OPT menor costo renovables (legado)",             # BAU: renovables ×0.6, combustible ×1.7
    "OCR": "PLAN menor costo renovables",
    "BCL": "OPT menor costo combustibles fósiles",   # BAU: combustible fósil más barato
    "OCL": "PLAN menor costo combustibles fósiles",
    "ICR": "ETT-MC menor costo renovables",
    "ICL": "ETT-MC menor costo combustibles fósiles",
    "VCR": "ETT-GP menor costo renovables",
    "VCL": "ETT-GP menor costo combustibles fósiles",
}
# HISTORIA:
# - 2026-08-18: BAU (sin tope) dejó de llevar alias de reporte — BAC (con tope)
#   pasó a ser la referencia de reporte. BAU queda con su código crudo en
#   cualquier figura donde aparezca (p.ej. fig_costo_no_inversion_tope.py).
#   OPT (sin tope) lleva alias propio ("OPT-output") desde 2026-08-19 para no
#   chocar con el alias "OPT" de BAC.
# - 2026-08-19: ICL/ICR/VCL/VCR = variantes de menor-costo de INV (ETT-MC) y
#   VGB (ETT-GP), análogas a BCL/BCR (BAC) y OCL/OCR (OPC). "combustible(s)" en
#   todos estos alias significa siempre combustibles FÓSILES.
# - 2026-08-27: variantes "SR" (BSR/ISR/VSR) como escenarios de origen de
#   Figures_Presentation; entonces se mostraban con el MISMO nombre que
#   BAC/INV/VGB (BSR="OPT", ISR="ETT-MC", VSR="ETT-GP").
# - 2026-09-16: renombre para la corrida de 14 escenarios: ISR pasa a ser el
#   ETT base ("ETT"), INV = "ETT con repotenciación" (antes "ETT-MC-OLD"),
#   BSR = "OPT sin repotenciación" (antes "OPT", que chocaba con BAC). "BCR"
#   legado lleva sufijo "(legado)" para no chocar con BRB.

# ================================================================
# Technology Generation Group classification
# ================================================================
RENEWABLE_CODES = [
    "PWRBIO", "PWRCSP", "PWRGEO", "PWRHYD",
    "PWRSPV", "PWRWAS", "PWRWOF", "PWRWON",
]
NON_RENEWABLE_CODES = [
    "PWRCSS", "PWRCOA", "PWRCOG", "PWRNGS",
    "PWROIL", "PWROTH", "PWRPET", "PWRURN",
]


def classify_tech_generation(tech: str) -> str | None:
    t = str(tech)
    for code in RENEWABLE_CODES:
        if code in t:
            return "Renovable"
    for code in NON_RENEWABLE_CODES:
        if code in t:
            return "No Renovable"
    if "BCK" in t:
        return "Backstop"
    return None


# ================================================================
# Origen del combustible (gráfico 15 — Seguridad Energética)
# ----------------------------------------------------------------
# Indicador de seguridad energética: energía primaria importada vs autóctona.
#   Importado : MIN*INT*  (extracción "minera" de fuente internacional)
#   Autóctono : MIN sin INT (extracción local) o RNW que NO sea línea de
#               transmisión (excluye NLI/RPO/TRN).
# ================================================================
COLORS_ENERGY_ORIGIN = {
    "Autóctono": "#7EBA7B",   # verde más claro que el de generación renovable
    "Importado": "#BAB0AC",   # mismo gris que "Líneas Nuevas Planificadas" (gráfico 4)
}


def classify_fuel_origin(tech: str) -> str | None:
    t = str(tech)
    if t.startswith("MIN"):
        return "Importado" if "INT" in t else "Autóctono"
    if t.startswith("RNW") and not any(x in t for x in ("NLI", "RPO", "TRN")):
        return "Autóctono"
    return None


# ================================================================
# Combustibles fósiles de entrada (gráficos 8A y 8B)
# ----------------------------------------------------------------
# El consumo fósil se mide por la actividad (TotalTechnologyAnnualActivity, ya en
# PJ) de las tecnologías de extracción/importación MIN*. El código de combustible
# son los chars [3:6] del nombre (MIN<FUEL><PAIS>); se incluyen las importadas
# (MIN*INT). Se EXCLUYE URN (uranio/nuclear: no es fósil, no emite CO2 de
# combustión) para que el total sea comparable 1:1 con las emisiones (gráfico 8).
# ================================================================
FOSSIL_MIN_FUELS = ["COA", "COG", "GAS", "OIL", "PET", "OTH"]

# Agrupación de las 6 familias en 3 tipos para el desglose del gráfico 8B.
# Nota: en el lado MIN el gas natural es "GAS"; aguas abajo (generación) es "NGS".
FOSSIL_FUEL_GROUP = {
    "COA": "Carbón", "COG": "Carbón",
    "GAS": "Gas natural",
    "OIL": "Petróleo/derivados", "PET": "Petróleo/derivados", "OTH": "Petróleo/derivados",
}
COLORS_FOSSIL_FUEL = {
    "Carbón": "#595959",             # gris oscuro / negro carbón
    "Gas natural": "#6699cc",        # azul gas
    "Petróleo/derivados": "#b07d3c",  # ámbar/marrón petróleo
}


def classify_min_fossil(tech: str) -> str | None:
    """Código de combustible fósil (COA/COG/GAS/OIL/PET/OTH) si la tecnología es
    una MIN* fósil; None en otro caso (incluye MINURN y todo lo no-MIN)."""
    t = str(tech)
    if not t.startswith("MIN"):
        return None
    fuel = t[3:6]
    return fuel if fuel in FOSSIL_MIN_FUELS else None


def classify_min_fossil_group(tech: str) -> str | None:
    """Familia agrupada (Carbón / Gas natural / Petróleo/derivados) o None."""
    fuel = classify_min_fossil(tech)
    return FOSSIL_FUEL_GROUP[fuel] if fuel else None


# ================================================================
# Color palettes
# ================================================================
COLORS_TECH_GROUP = {
    "Renovable": "#4E9A4D",
    "No Renovable": "#2D2D2D",
}
COLOR_GW_LINE = "#ED7D31"

# Color por escenario (gráficos 8, 11 y 13). Definidos por el usuario.
# Color por escenario. Los conocidos llevan color fijo; cualquier escenario
# nuevo (autodetectado) recibe uno de la paleta de reserva por índice, así
# ningún gráfico de líneas revienta por KeyError al crecer la lista.
#
# 2026-09-16 — 14 escenarios de la corrida, SIN duplicados entre ellos:
#   familia OPT (B**) en tonos FRÍOS (gris/azules/teal/verde) alrededor del gris
#   de BAC; familia ETT (I**) en tonos CÁLIDOS (rojos/rosas/marrón/ocre)
#   alrededor del rojo de INV/ISR; OPC naranja y VSR violeta (como el VGB del
#   que deriva). BAC/OPC/INV conservan su color histórico.
_KNOWN_SCEN_COLORS = {
    # --- familia OPT (fríos) ---
    "BAC": "#bab0ac",   # gris (color histórico de reporte)
    "BFA": "#1f77b4",   # azul
    "BFB": "#a0cbe8",   # azul claro
    "BRA": "#0f8b8d",   # teal oscuro
    "BRB": "#86bcb6",   # teal claro
    "BSR": "#2ca02c",   # verde
    # --- familia ETT (cálidos) ---
    "ISR": "#8b1a1a",   # granate (ETT base)
    "INV": "#e15759",   # rojo (color histórico)
    "IFA": "#ff9da7",   # rosa claro
    "IFB": "#d37295",   # rosa oscuro / magenta
    "IRA": "#9c755f",   # marrón
    "IRB": "#b6992d",   # ocre
    # --- otros ---
    "OPC": "#f28e2b",   # naranja (color histórico)
    "VSR": "#9467bd",   # violeta
    # --- LEGADO (corridas anteriores; pueden repetir color con los 14 de
    # arriba, solo importa si coexisten en el mismo CSV). BAC/OPC tomaron en
    # 2026-08-18 los colores que antes tenían BAU/OPT y viceversa. ---
    "BAU": "#4e79a7", "VGB": "#b07aa1", "OPT": "#59a14f",
    "BCR": "#76b7b2", "OCR": "#edc948", "BCL": "#ff9da7", "OCL": "#9c755f",
}
_SCEN_FALLBACK_PALETTE = [
    "#4e79a7", "#59a14f", "#76b7b2", "#edc948", "#ff9da7",
    "#9c755f", "#b6992d", "#86bcb6", "#d37295", "#a0cbe8",
]
COLORS_SCENARIO = {
    sc: _KNOWN_SCEN_COLORS.get(sc, _SCEN_FALLBACK_PALETTE[i % len(_SCEN_FALLBACK_PALETTE)])
    for i, sc in enumerate(SCENARIOS)
}

# Paleta OFICIAL por tipo de tecnología — consistente en TODO el dashboard.
# Generación va en AZUL (no verde). La usan el gráfico 3 (almacenamiento) y el
# gráfico 5 (inversión); cualquier gráfico que muestre estos tipos debe usarla.
COLORS_TECH_TYPE = {
    "Generación": "#4e79a7",
    "Transmisión": "#e15759",
    "Almacenamiento": "#76b7b2",
}


# ================================================================
# Transmission line groups (gráfico 4 — Capacidad de Transmisión)
# ----------------------------------------------------------------
# Réplica del grupo de Tableau "Technology Lineas (grupos)": clasifica las
# tecnologías TRN/RNW de líneas por prefijo de 6 caracteres en 3 grupos. Los
# interconectores (TRN<paisA>XX<paisB>XX) no entran en el gráfico de capacidad.
#   PLAN -> "Líneas Planificadas"               (PWRTRN*, RNWTRN*)
#   NLI  -> "Líneas Nuevas No Planificadas"     (RNWNLI*, TRNNLI*)
#   RPO  -> "Líneas Repotenciadas No Planif."   (RNWRPO*, TRNRPO*)
# ================================================================
LINE_GROUP_PREFIXES = {
    "PLAN": ("PWRTRN", "RNWTRN"),
    "NLI": ("RNWNLI", "TRNNLI"),
    "RPO": ("RNWRPO", "TRNRPO"),
}


def classify_line_group(tech: str) -> str | None:
    t = str(tech)
    for group, prefixes in LINE_GROUP_PREFIXES.items():
        if t.startswith(prefixes):
            return group
    return None


# Categorías apiladas del gráfico 4, de abajo hacia arriba, con su color.
# Existentes como base (oscuro); planificadas en verdes; no planificadas en
# naranjas (claro = repotenciadas).
TRANSMISSION_CATEGORIES = [
    ("Líneas Existentes", "#57606C"),
    ("Líneas Nuevas Planificadas", "#BAB0AC"),
    ("Líneas Repotenciadas Planificadas", "#C85200"),
    ("Líneas Nuevas No Planificadas", "#1170AA"),
    ("Líneas Repotenciadas No Planificadas", "#FFBC79"),
]


# ================================================================
# Grupos CRUDOS de línea (gráfico 6 — Inversión anual promedio de líneas)
# ----------------------------------------------------------------
# Réplica del grupo Tableau "Technology Lineas (grupos)" SIN el cálculo de
# residuales del gráfico 4: 4 buckets directos por prefijo (el resto = "Other",
# que el gráfico 6 excluye).
#   Líneas Nuevas No Planificadas         -> RNWNLI*, TRNNLI*
#   Líneas Planificadas                   -> PWRTRN*, RNWTRN*
#   Líneas Repotenciadas No Planificadas  -> RNWRPO*, TRNRPO*
#   Interconectores                       -> TRN<paisA>XX<paisB>XX (resto de TRN*)
# ================================================================
def classify_line_group_raw(tech: str) -> str | None:
    t = str(tech)
    if t.startswith(("RNWNLI", "TRNNLI")):
        return "Líneas Nuevas No Planificadas"
    if t.startswith(("PWRTRN", "RNWTRN")):
        return "Líneas Planificadas"
    if t.startswith(("RNWRPO", "TRNRPO")):
        return "Líneas Repotenciadas No Planificadas"
    if t.startswith("TRN"):  # ya descartados TRNNLI/TRNRPO -> interconectores
        return "Interconectores"
    return None


# Categorías apiladas de los gráficos 6 y 10 (color por grupo de línea), de base
# a tope. Reusa los colores del gráfico 4 (TRANSMISSION_CATEGORIES): Interconectores
# toma el de "Existentes" (#57606C) y Planificadas el de "Nuevas Planificadas".
LINE_RAW_CATEGORIES = [
    ("Interconectores", "#57606C"),
    ("Líneas Planificadas", "#BAB0AC"),
    ("Líneas Nuevas No Planificadas", "#1170AA"),
    ("Líneas Repotenciadas No Planificadas", "#FFBC79"),
]


# ================================================================
# Tipo de tecnología (gráfico 5 — Inversión)
# ----------------------------------------------------------------
# Réplica del grupo Tableau "Technology Tipos (grupos)": clasifica por prefijo
#   Almacenamiento -> PWRLDS*, PWRSDS*
#   Transmisión    -> líneas (PWRTRN*, RNWTRN*, RNWNLI*, RNWRPO*, TRNNLI*, TRNRPO*)
#   Generación     -> el resto de PWR* (generación)
# ================================================================
_STORAGE_PREFIXES = ("PWRLDS", "PWRSDS")
_TRANSMISSION_PREFIXES = (
    "PWRTRN", "RNWTRN", "RNWNLI", "RNWRPO", "TRNNLI", "TRNRPO",
)


def classify_tech_type(tech: str) -> str | None:
    t = str(tech)
    if t.startswith(_STORAGE_PREFIXES):
        return "Almacenamiento"
    if t.startswith(_TRANSMISSION_PREFIXES):
        return "Transmisión"
    if t.startswith("PWR"):
        return "Generación"
    return None


# ================================================================
# Familia de "fuente" para el índice de diversidad HHI (gráfico 13)
# ----------------------------------------------------------------
# Indicador de resiliencia agnóstico a la amenaza (Herfindahl-Hirschman):
# si ninguna fuente domina la matriz, cualquier amenaza alcanza sólo una
# porción limitada del suministro. La decisión crítica es qué cuenta como
# fuente "independiente": las fuentes CORRELACIONADAS deben colapsarse en una
# sola para no sobreestimar la resiliencia (p.ej. toda la hidro —presas
# hidrológicamente ligadas— = 1 fuente; tecnologías que comparten combustible
# = 1 fuente). Aquí cada familia = código PWR de 6 letras, agregando todas las
# plantas de esa familia y de todos los países. Sólo generación (se excluyen
# almacenamiento, líneas y backstop). Ver classify_source_family.
# ================================================================
SOURCE_FAMILY_NAMES = {
    "PWRBIO": "Biomasa",
    "PWRCSP": "Solar CSP",
    "PWRGEO": "Geotérmica",
    "PWRHYD": "Hidroeléctrica",
    "PWRSPV": "Solar Fotovoltaica",
    "PWRWAS": "Residuos",
    "PWRWOF": "Eólica Marina",
    "PWRWON": "Eólica Terrestre",
    "PWRCSS": "Carbón con CCS",
    "PWRCOA": "Carbón",
    "PWRCOG": "Cogeneración",
    "PWRNGS": "Gas Natural",
    "PWROIL": "Petróleo/Diésel",
    "PWROTH": "Otros",
    "PWRPET": "Petcoke",
    "PWRURN": "Nuclear",
}


def classify_source_family(tech: str) -> str | None:
    """Familia de fuente (código PWR de 6 letras) para el HHI del gráfico 13.

    Sólo tecnologías de GENERACIÓN (PWR* que no sean almacenamiento ni líneas);
    el backstop (BCK) se excluye por ser una holgura del modelo, no una fuente
    real. Colapsa todas las plantas de la misma familia/combustible y de todos
    los países en UNA sola fuente. Devuelve None si la tecnología no es una
    fuente de generación.
    """
    t = str(tech)
    if "BCK" in t:
        return None
    if classify_tech_type(t) != "Generación":
        return None
    return t[:6]


# Agrupación de años en periodos (eje X del gráfico 5).
YEAR_PERIODS = [
    ("2023-2024", range(2023, 2025)),
    ("2025-2030", range(2025, 2031)),
    ("2031-2035", range(2031, 2036)),
    ("2036-2040", range(2036, 2041)),
    ("2041-2045", range(2041, 2046)),
    ("2046-2050", range(2046, 2051)),
]
# Nombre de periodo -> nº de años (divisor para el promedio anual).
PERIOD_YEARS = {name: len(list(yrs)) for name, yrs in YEAR_PERIODS}
PERIOD_ORDER = [name for name, _ in YEAR_PERIODS]
_YEAR_TO_PERIOD = {y: name for name, yrs in YEAR_PERIODS for y in yrs}


def year_to_period(year: int) -> str | None:
    return _YEAR_TO_PERIOD.get(int(year))


# Categorías apiladas del gráfico 5, de abajo hacia arriba (color de COLORS_TECH_TYPE).
INVESTMENT_CATEGORIES = [
    ("Generación", COLORS_TECH_TYPE["Generación"]),
    ("Transmisión", COLORS_TECH_TYPE["Transmisión"]),
    ("Almacenamiento", COLORS_TECH_TYPE["Almacenamiento"]),
]

# Categorías (orden de apilado) del gráfico 8B — desglose del consumo fósil.
FOSSIL_FUEL_CATEGORIES = [
    ("Carbón", COLORS_FOSSIL_FUEL["Carbón"]),
    ("Gas natural", COLORS_FOSSIL_FUEL["Gas natural"]),
    ("Petróleo/derivados", COLORS_FOSSIL_FUEL["Petróleo/derivados"]),
]


# ================================================================
# Data loading helpers
# ================================================================
# Caché en memoria por (fuente, columnas): el CSV/Parquet se lee como mucho una
# vez por conjunto de columnas durante la ejecución (los maestros corren todas
# las figuras en un proceso).
_LOAD_CACHE: dict[tuple, pd.DataFrame] = {}

# ================================================================
# Subconjunto Parquet de escenarios (figuras estáticas) — spec 2026-09-16 §7
# ----------------------------------------------------------------
# Las figuras de reporte/presentación solo usan BAC+ISR; releer el CSV completo
# (14 escenarios, ~1,4 GB) por cada conjunto de columnas es lento. Se guarda UNA
# vez un Parquet con TODAS las columnas y solo las filas de esos escenarios
# (outputs/Figures/_subset_BAC-ISR.parquet + sidecar .json con la firma del CSV)
# y se reconstruye cuando el CSV cambia (mtime o size), igual que .scenarios_cache.
# El dashboard NO lo usa (necesita todos los escenarios).
# ================================================================
SUBSET_DIR = str(P.FIGURES)
# Subconjunto canónico que usa load_column(scenarios=...). Debe coincidir con
# report_style.CORE_SCENARIOS (lo comprueba scripts/tests/test_scenario_subset.py).
SUBSET_SCENARIOS = ["BAC", "ISR"]
# Columnas de dimensión (texto/categoría) del CSV combinado; el resto son valores
# numéricos con NaN. Parquet exige UN tipo por columna: las dimensiones de tipo
# object se guardan como texto con nulos; las demás se fuerzan a numérico y, si
# no se puede (texto mezclado con números), a texto.
DIM_COLS = ["Future", "Scenario", "REGION", "TECHNOLOGY", "FUEL", "EMISSION",
            "MODE_OF_OPERATION", "TIMESLICE", "STORAGE", "SEASON", "DAYTYPE",
            "DAILYTIMEBRACKET"]
_CHUNK_ROWS = 500_000


def subset_paths(scenarios) -> tuple[str, str]:
    """(parquet, sidecar json) para esos escenarios: _subset_<S1>-<S2>-...  (orden alfabético)."""
    key = "-".join(sorted(set(scenarios)))
    base = os.path.join(SUBSET_DIR, f"_subset_{key}")
    return base + ".parquet", base + ".json"


def _csv_signature() -> dict:
    st = os.stat(CSV_PATH)
    return {"csv_mtime": st.st_mtime, "csv_size": st.st_size}


def subset_is_current(scenarios) -> bool:
    """True si existen Parquet+sidecar y la firma (mtime/size) del sidecar es la del CSV actual."""
    import json
    pq, side = subset_paths(scenarios)
    if not (os.path.exists(pq) and os.path.exists(side) and os.path.exists(CSV_PATH)):
        return False
    try:
        meta = json.load(open(side, encoding="utf-8"))
    except Exception:
        return False
    sig = _csv_signature()
    return (meta.get("csv_mtime") == sig["csv_mtime"] and meta.get("csv_size") == sig["csv_size"]
            and meta.get("scenarios") == sorted(set(scenarios)))


def _to_text(s: pd.Series) -> pd.Series:
    return s.map(lambda v: None if pd.isna(v) else str(v)).astype(object)


def _harmonize_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Un tipo por columna para pyarrow (ver DIM_COLS). YEAR ya viene como int."""
    for col in df.columns:
        if col == "YEAR" or df[col].dtype != object:
            continue
        if col not in DIM_COLS:
            try:
                df[col] = pd.to_numeric(df[col], errors="raise")
                continue
            except (ValueError, TypeError):
                pass
        df[col] = _to_text(df[col])
    return df


def ensure_scenario_subset(scenarios, verbose: bool = True) -> str:
    """Devuelve la ruta del Parquet con TODAS las columnas del CSV y solo las filas de
    `scenarios`; lo construye si falta o si el CSV cambió. Lee el CSV por chunks."""
    import json
    import time
    scen = sorted(set(scenarios))
    pq, side = subset_paths(scen)
    if subset_is_current(scen):
        if verbose:
            print(f"[subset] reutilizado {pq}")
        return pq
    t0 = time.perf_counter()
    sig = _csv_signature()   # ANTES de leer: si el CSV cambia durante la lectura, queda no vigente
    parts = []
    # low_memory=False por chunk: cada chunk (500k filas) cabe en memoria y así el
    # parser no emite un DtypeWarning por chunk (la tipificación final la hace
    # _harmonize_dtypes de todos modos).
    for chunk in pd.read_csv(CSV_PATH, chunksize=_CHUNK_ROWS, low_memory=False):
        part = chunk[chunk["Scenario"].isin(scen)]
        if len(part):
            parts.append(part)
    if not parts:
        raise ValueError(f"El CSV {CSV_PATH} no tiene filas de los escenarios {scen}")
    df = pd.concat(parts, ignore_index=True)
    df = df.dropna(subset=["YEAR"])
    df["YEAR"] = df["YEAR"].astype("int64")
    df = _harmonize_dtypes(df)
    os.makedirs(SUBSET_DIR, exist_ok=True)
    tmp = pq + ".tmp"
    df.to_parquet(tmp, engine="pyarrow", index=False)
    os.replace(tmp, pq)
    meta = {**sig, "scenarios": scen, "rows": int(len(df)),
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with open(side, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
    if verbose:
        print(f"[subset] reconstruido {pq}: {len(df):,} filas en {time.perf_counter() - t0:.1f} s")
    return pq


def load_column(columns: list[str], extra_dims: list[str] | None = None,
                scenarios: list[str] | None = None) -> pd.DataFrame:
    """Lee columnas de valor del CSV combinado (o del subconjunto Parquet).

    Siempre devuelve las dimensiones Scenario/YEAR/TECHNOLOGY (+ ``extra_dims``,
    p.ej. ["FUEL", "TIMESLICE", "MODE_OF_OPERATION"]). YEAR es int sin NaN. El
    resultado se cachea en memoria por (fuente, conjunto de columnas).

    ``scenarios=None`` -> CSV completo (todos los escenarios; lo usa el dashboard).
    ``scenarios=[...]`` -> si todos están en SUBSET_SCENARIOS, lee el Parquet
    canónico _subset_BAC-ISR (construyéndolo si hace falta) y devuelve las filas de
    ESOS escenarios del subconjunto (la figura filtra los suyos, como con el CSV).
    Si alguno queda fuera del subconjunto, avisa y cae al CSV completo.

    NOTA CSV: low_memory=False agota memoria con el CSV de 14 escenarios (~1,4 GB;
    límite del parser C, no del sistema); el default por chunks funciona y solo
    emite un DtypeWarning inofensivo en columnas con NaN mezclado con números.
    """
    always = ["Scenario", "YEAR", "TECHNOLOGY"] + (extra_dims or [])
    usecols = list(dict.fromkeys(always + columns))
    use_subset = False
    if scenarios:
        outside = sorted(set(scenarios) - set(SUBSET_SCENARIOS))
        if outside:
            print(f"[aviso] escenarios fuera del subconjunto Parquet ({outside}); leyendo CSV completo")
        else:
            use_subset = True
    cache_key = (tuple(SUBSET_SCENARIOS) if use_subset else None, tuple(usecols))
    if cache_key in _LOAD_CACHE:
        return _LOAD_CACHE[cache_key].copy()

    if use_subset:
        import pyarrow.parquet as pq_
        path = ensure_scenario_subset(SUBSET_SCENARIOS)
        df = pd.read_parquet(path, columns=usecols)
        # mismo orden de columnas que devolvería pd.read_csv(usecols=...) (orden del archivo)
        order = [c for c in pq_.read_schema(path).names if c in usecols]
        df = df[order]
    else:
        df = pd.read_csv(CSV_PATH, usecols=usecols)
        df = df.dropna(subset=["YEAR"])
        df["YEAR"] = df["YEAR"].astype("int64")
    _LOAD_CACHE[cache_key] = df
    return df.copy()


# ================================================================
# CapacityAndDistances.xlsx — capacidad/distancia por país (chart_10 /
# fig_km_lineas_acumulados.py)
# ----------------------------------------------------------------
# El xlsx nunca se actualizó con los códigos "con tope" BAC/OPC (2026-08-18,
# ver SCENARIO_ALIAS más arriba): solo trae BAU, OPT, INV, VGB y las variantes
# NDC* / BAU_SinInterconexiones (verificado 2026-08-19: NO trae BCR/BCL ni
# ninguna sensibilidad de costo). Como chart_10 y fig_km_lineas_acumulados.py
# cruzan por Scenario+Country con un merge "inner", las filas BAC/OPC no
# encontraban match y se descartaban SIN error ni warning -- la figura salía
# con solo 2 de 4 escenarios (ETT-MC/ETT-GP), faltando OPT/PLAN. BAC es la
# variante con tope de BAU y OPC la de OPT (misma topología de red/país; el
# tope solo limita la rampa de inversión en Tx, no la geografía), así que
# reusar las filas Capacity/Distance de BAU/OPT bajo BAC/OPC es correcto, no
# un dato inventado. Mismo argumento para las sensibilidades de costo
# BCR/BCL (de BAC), OCR/OCL (de OPC), ICR/ICL (de INV) y VCR/VCL (de VGB):
# solo cambian costos (renovables/combustible fósil más baratos), no la
# geografía de la red -> caen al escenario base que SÍ está en el xlsx.
# 2026-09-16: misma lógica para la corrida de 14 escenarios: la familia OPT
# (BAC/BSR/BFA/BFB/BRA/BRB) cae a BAU y la familia ETT (ISR/INV/IFA/IFB/IRA/IRB)
# a INV; OPC -> OPT y VSR -> VGB. Solo se duplica si el código NO está ya en
# el xlsx (ver load_capacity_and_distances).
# ================================================================
CD_SCENARIO_FALLBACK = {
    "BAC": "BAU", "OPC": "OPT",
    "BCR": "BAU", "BCL": "BAU",   # sensibilidades de BAC (base xlsx: BAU) — legado
    "OCR": "OPT", "OCL": "OPT",   # sensibilidades de OPC (base xlsx: OPT) — legado
    "ICR": "INV", "ICL": "INV",   # sensibilidades de INV — legado
    "VCR": "VGB", "VCL": "VGB",   # sensibilidades de VGB — legado
    "BSR": "BAU", "ISR": "INV", "VSR": "VGB",   # set "SR" (2026-08-27): base xlsx de BAC/INV/VGB
    # Corrida 2026-09-16 (sensibilidades de costo FA/FB/RA/RB):
    "BFA": "BAU", "BFB": "BAU", "BRA": "BAU", "BRB": "BAU",   # familia OPT
    "IFA": "INV", "IFB": "INV", "IRA": "INV", "IRB": "INV",   # familia ETT
}


def load_capacity_and_distances() -> pd.DataFrame:
    """Lee CapacityAndDistances.xlsx con fallback de escenario BAC/OPC -> BAU/OPT.

    Devuelve columnas Scenario/Country/Capacity/Distance RNW/Distance NRNW,
    duplicando las filas de BAU/OPT bajo BAC/OPC cuando el xlsx no trae esos
    códigos directamente (ver CD_SCENARIO_FALLBACK).
    """
    cd = pd.read_excel(CAPACITY_DISTANCES_PATH)[
        ["Scenario", "Country", "Capacity", "Distance RNW", "Distance NRNW"]
    ]
    present = set(cd["Scenario"].unique())
    extra = []
    for new_sc, base_sc in CD_SCENARIO_FALLBACK.items():
        if new_sc not in present and base_sc in present:
            dup = cd[cd["Scenario"] == base_sc].copy()
            dup["Scenario"] = new_sc
            extra.append(dup)
    if extra:
        cd = pd.concat([cd] + extra, ignore_index=True)
    return cd


# ================================================================
# Cuotas de importación de combustible fósil (balance OLADE — gráfico 12)
# ----------------------------------------------------------------
# Para cada país y combustible del modelo, la fracción de la OFERTA TOTAL que
# es IMPORTACIÓN según el balance energético anual de OLADE/sieLAC. Es un ratio
# adimensional (no requiere convertir las distintas unidades del balance), que
# se PROMEDIA sobre los años disponibles (2020-2024) y se aplica constante a
# todo el horizonte del modelo. Mapeo combustible-modelo -> columna(s) OLADE:
#   GAS -> GAS NATURAL ; COA -> CARBÓN MINERAL ; URN -> NUCLEAR ;
#   OIL/PET/OTH -> derivados de petróleo (DIÉSEL OIL SIN BIODIÉSEL + FUEL OIL).
# El chart aplica fallback 1.0 (importado) donde no haya dato, coherente con la
# convención del modelo (todo el fósil se enruta por nodos *INT).
# ================================================================
# ISO-3 por nombre de país en español (nombres de las hojas del balance).
COUNTRY_ISO3_BY_NAME = {
    "Argentina": "ARG", "Bolivia": "BOL", "Brasil": "BRA", "Barbados": "BRB",
    "Chile": "CHL", "Colombia": "COL", "Costa Rica": "CRI", "Cuba": "CUB",
    "República Dominicana": "DOM", "Ecuador": "ECU", "Guatemala": "GTM",
    "Honduras": "HND", "Haití": "HTI", "México": "MEX", "Nicaragua": "NIC",
    "Panamá": "PAN", "Perú": "PER", "Paraguay": "PRY", "El Salvador": "SLV",
    "Uruguay": "URY", "Venezuela": "VEN",
}

# Combustible del modelo (FUEL[:3]) -> columnas del balance OLADE a sumar.
_OLADE_FUEL_COLUMNS = {
    "GAS": ["GAS NATURAL"],
    "COA": ["CARBÓN MINERAL"],
    "URN": ["NUCLEAR"],
    # OIL/PET/OTH comparten la cuota de derivados de petróleo.
    "OIL": ["DIÉSEL OIL SIN BIODIÉSEL", "FUEL OIL"],
    "PET": ["DIÉSEL OIL SIN BIODIÉSEL", "FUEL OIL"],
    "OTH": ["DIÉSEL OIL SIN BIODIÉSEL", "FUEL OIL"],
}

_IMPORT_SHARE_CACHE: dict[str, dict[str, float]] = {}


def load_fossil_import_shares() -> dict[str, dict[str, float]]:
    """{iso3: {fuel_modelo: cuota_importación}} desde el balance OLADE.

    ``fuel_modelo`` es uno de GAS/COA/URN/OIL/PET/OTH; el valor es la fracción
    importada (0-1) promediada sobre los años disponibles del balance. Combina
    columnas y promedia por país. Resultado cacheado en memoria.
    """
    if _IMPORT_SHARE_CACHE:
        return _IMPORT_SHARE_CACHE

    sheets = pd.read_excel(OLADE_BALANCE_PATH, sheet_name=None, header=None)
    # acumula shares por (iso3, fuel) a lo largo de los años -> lista de valores
    acc: dict[tuple[str, str], list[float]] = {}

    for name, raw in sheets.items():
        # Nombre de hoja: "AÑO - País".
        parts = name.split(" - ", 1)
        if len(parts) != 2:
            continue
        country = parts[1].strip()
        iso3 = COUNTRY_ISO3_BY_NAME.get(country)
        if iso3 is None:
            continue

        # Localiza filas por etiqueta (col 0) y columnas por encabezado (fila 4).
        labels = {str(raw.iat[i, 0]).strip(): i
                  for i in range(raw.shape[0]) if pd.notna(raw.iat[i, 0])}
        row_imp = labels.get("IMPORTACIÓN")
        row_oferta = labels.get("OFERTA TOTAL")
        if row_imp is None or row_oferta is None:
            continue
        headers = {str(raw.iat[4, c]).strip(): c
                   for c in range(raw.shape[1]) if pd.notna(raw.iat[4, c])}

        def _val(row: int, col: int) -> float:
            v = raw.iat[row, col]
            return float(v) if pd.notna(v) else 0.0

        for fuel, cols in _OLADE_FUEL_COLUMNS.items():
            imp = sum(_val(row_imp, headers[h]) for h in cols if h in headers)
            ofe = sum(_val(row_oferta, headers[h]) for h in cols if h in headers)
            if ofe <= 0:
                continue  # sin oferta -> sin dato; el chart usará fallback 1.0
            share = min(max(imp / ofe, 0.0), 1.0)
            acc.setdefault((iso3, fuel), []).append(share)

    result: dict[str, dict[str, float]] = {}
    for (iso3, fuel), vals in acc.items():
        result.setdefault(iso3, {})[fuel] = sum(vals) / len(vals)

    _IMPORT_SHARE_CACHE.update(result)
    return _IMPORT_SHARE_CACHE
