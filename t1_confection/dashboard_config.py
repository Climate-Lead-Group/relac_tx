"""
dashboard_config.py — Configuración compartida para el dashboard RELAC_TX:
paths, años de referencia, escenarios, paletas de color, clasificadores de
tecnología y helpers de carga del CSV combinado.
"""

import os

import pandas as pd

# ================================================================
# Paths
# ================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "RELAC_TX_Combined_Inputs_Outputs.csv")
FIGURES_DIR = os.path.join(BASE_DIR, "Figures")

# Sufijo opcional para los nombres de archivo generados (vacío = sin sufijo).
OUTPUT_SUFFIX = ""

# ================================================================
# Reference years & scenarios
# ================================================================
REFERENCE_YEARS = [2025, 2030, 2035, 2040, 2045, 2050]
# Todos los años del horizonte del CSV (candidatos del selector dinámico).
ALL_YEARS = list(range(2023, 2051))
SCENARIOS = ["BAU", "INV", "OPT"]
# Alias de DISPLAY de los escenarios (los datos siguen usando BAU/INV/OPT).
SCENARIO_ALIAS = {"BAU": "OPTIMO", "OPT": "PLANIFICADO", "INV": "VEGETATIVO"}

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
# Color palettes
# ================================================================
COLORS_TECH_GROUP = {
    "Renovable": "#4E9A4D",
    "No Renovable": "#2D2D2D",
}
COLOR_GW_LINE = "#ED7D31"

# Color por escenario (gráficos 8 y 11). Definidos por el usuario.
COLORS_SCENARIO = {
    "BAU": "#bab0ac",
    "INV": "#e15759",
    "OPT": "#f28e2b",
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


# ================================================================
# Data loading helpers
# ================================================================
# Caché en memoria: el CSV (308 MB) se lee como mucho una vez por conjunto de
# columnas durante la ejecución (útil al renderizar varios gráficos seguidos).
_LOAD_CACHE: dict[tuple[str, ...], pd.DataFrame] = {}


def load_column(columns: list[str], extra_dims: list[str] | None = None) -> pd.DataFrame:
    """Lee columnas de valor del CSV combinado.

    Siempre devuelve las dimensiones Scenario/YEAR/TECHNOLOGY. Usa
    ``extra_dims`` (p.ej. ["FUEL", "TIMESLICE", "MODE_OF_OPERATION"]) cuando un
    gráfico necesite columnas índice adicionales. YEAR se castea a int. El
    resultado se cachea por conjunto de columnas durante la ejecución.
    """
    always = ["Scenario", "YEAR", "TECHNOLOGY"] + (extra_dims or [])
    usecols = list(dict.fromkeys(always + columns))
    cache_key = tuple(usecols)
    if cache_key in _LOAD_CACHE:
        return _LOAD_CACHE[cache_key].copy()

    df = pd.read_csv(CSV_PATH, usecols=usecols, low_memory=False)
    df = df.dropna(subset=["YEAR"])
    df["YEAR"] = df["YEAR"].astype(int)
    _LOAD_CACHE[cache_key] = df
    return df.copy()
