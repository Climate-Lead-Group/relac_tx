# scripts/common/relac_paths.py
"""Layout del repositorio relac_tx. TODO script obtiene sus rutas de aquí.

Convención: inputs/ = mantenido a mano (el pipeline lo lee); outputs/ = regenerado al correr;
scripts/ = código. Ver docs/superpowers/specs/2026-09-07-restructure-inputs-scripts-outputs-design.md
"""
from pathlib import Path


def _find_repo_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / "dvc.yaml").is_file():
            return p
    raise RuntimeError(f"No se encontró dvc.yaml subiendo desde {start}")


REPO_ROOT = _find_repo_root(Path(__file__).resolve().parent)
INPUTS = REPO_ROOT / "inputs"
SCRIPTS = REPO_ROOT / "scripts"
OUTPUTS = REPO_ROOT / "outputs"

# ---- inputs ----
CONFIG = INPUTS / "config"
CONFIG_A = CONFIG / "Config_MOMF_T1_A.yaml"
CONFIG_AB = CONFIG / "Config_MOMF_T1_AB.yaml"
CONFIG_COUNTRY_CODES = CONFIG / "Config_country_codes.yaml"
CONFIG_REGION_CONSOLIDATION = CONFIG / "Config_region_consolidation.yaml"
CONFIG_TECH_EQUIVALENCES = CONFIG / "Config_tech_equivalences.yaml"
A3_CONFIG = CONFIG / "A3_process"                    # lid_rule.yaml, TECH_TYPES.csv
MODEL = INPUTS / "model"
OSEMOSYS_MODEL = MODEL / "osemosys_fast_preprocessed.txt"
OG_CSVS_INPUTS = INPUTS / "OG_csvs_inputs"
A1_OUTPUTS = INPUTS / "A1_Outputs"
A2_EXTRA_INPUTS = INPUTS / "A2_Extra_Inputs"
MISCELLANEOUS = INPUTS / "Miscellaneous"
DATA = INPUTS / "data"
REFERENCE = INPUTS / "reference"
OLD_INPUTS = REFERENCE / "Old_Inputs"
BASE_SCENARIO_REF = REFERENCE / "NO BORRAR A1_Outputs - Escenario Base"
MATRIZ_BALANCE = REFERENCE / "Matriz Balance energético"
TX_CHAIN_IN = INPUTS / "tx_chain"
CANDIDATE_FLOORS = TX_CHAIN_IN / "fix_dispatch" / "candidate_floors.csv"
VEG_TX_NEEDS_CSV = TX_CHAIN_IN / "outputs_BSR" / "NewCapacity.csv"

# ---- outputs ----
A2_OUTPUT_PARAMS = OUTPUTS / "A2_Output_Params"
A2_STRUCTURE_LISTS = OUTPUTS / "A2_Structure_Lists.xlsx"
A2_OTOOLE = OUTPUTS / "A2_Outputs_Params_otoole"
EXECUTABLES = OUTPUTS / "Executables"
OUTPUT_MODEL = OUTPUTS / "model"
FIGURES = OUTPUTS / "Figures"
LOGS = OUTPUTS / "logs"
FIX_DISPATCH_OUT = OUTPUTS / "fix_dispatch"
TX_CHAIN_OUT = OUTPUTS / "tx_chain"
EXPERIMENTAL_OUT = OUTPUTS / "experimental"
TEMPLATES_OUT = OUTPUTS / "templates"

# ---- scripts ----
PIPELINE = SCRIPTS / "pipeline"
FIX_DISPATCH = SCRIPTS / "fix_dispatch"
TX_CHAIN = SCRIPTS / "tx_chain"
TOOLS = SCRIPTS / "tools"


def scenario_dir(scenario: str) -> Path:
    """inputs/A1_Outputs/A1_Outputs_<scenario>"""
    return A1_OUTPUTS / f"A1_Outputs_{scenario}"


def executables_dir(scenario: str) -> Path:
    """outputs/Executables/<scenario>_0"""
    return EXECUTABLES / f"{scenario}_0"


def ensure_output_dirs() -> None:
    for d in (OUTPUTS, A2_OUTPUT_PARAMS, A2_OTOOLE, EXECUTABLES, OUTPUT_MODEL, FIGURES, LOGS,
              FIX_DISPATCH_OUT, TX_CHAIN_OUT, EXPERIMENTAL_OUT, TEMPLATES_OUT):
        d.mkdir(parents=True, exist_ok=True)
