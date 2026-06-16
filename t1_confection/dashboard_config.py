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
# Balance energético anual OLADE/sieLAC (cuotas de importación, gráfico 12).
OLADE_BALANCE_PATH = os.path.join(
    BASE_DIR, "Matriz Balance energético",
    "OLADE - Matriz de balance energético - Anual.xlsx",
)

# Sufijo opcional para los nombres de archivo generados (vacío = sin sufijo).
OUTPUT_SUFFIX = ""

# ================================================================
# Reference years & scenarios
# ================================================================
REFERENCE_YEARS = [2025, 2030, 2035, 2040, 2045, 2050]
# Todos los años del horizonte del CSV (candidatos del selector dinámico).
ALL_YEARS = list(range(2023, 2051))
# VGB va justo después de INV para que VEGETATIVO A (INV) y VEGETATIVO B (VGB)
# queden adyacentes en filas/columnas/líneas de todos los gráficos.
SCENARIOS = ["BAU", "INV", "VGB", "OPT"]
# Alias de DISPLAY de los escenarios (los datos siguen usando BAU/INV/VGB/OPT).
SCENARIO_ALIAS = {
    "BAU": "REFERENCIA",
    "OPT": "OPTIMO",
    "INV": "VEGETATIVO A",
    "VGB": "VEGETATIVO B",
}

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
# VGB (VEGETATIVO B) deriva de INV; se le da un violeta distinto para que las
# líneas/barras por escenario sean legibles junto al rojo de INV.
COLORS_SCENARIO = {
    "BAU": "#bab0ac",
    "INV": "#e15759",
    "VGB": "#b07aa1",
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
