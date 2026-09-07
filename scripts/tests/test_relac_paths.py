# scripts/tests/test_relac_paths.py
"""Cada constante de relac_paths apunta a algo que existe en el repo (tras el git mv)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> scripts/
from common import relac_paths as P

MUST_EXIST = [
    P.REPO_ROOT / "dvc.yaml", P.INPUTS, P.SCRIPTS, P.OUTPUTS,
    P.CONFIG_A, P.CONFIG_AB, P.CONFIG_COUNTRY_CODES, P.CONFIG_REGION_CONSOLIDATION,
    P.CONFIG_TECH_EQUIVALENCES, P.A3_CONFIG / "lid_rule.yaml", P.A3_CONFIG / "TECH_TYPES.csv",
    P.OSEMOSYS_MODEL, P.OG_CSVS_INPUTS / "EMISSION.csv", P.scenario_dir("BAU") / "A-O_Parametrization.xlsx",
    P.A2_EXTRA_INPUTS / "A-Xtra_Storage.xlsx", P.MISCELLANEOUS / "conversion_format.yaml",
    P.MISCELLANEOUS / "templates", P.DATA / "firm_capacity_fallbacks_by_cr.xlsx",
    P.DATA / "Tech_Country_Matrix.xlsx", P.OLD_INPUTS, P.BASE_SCENARIO_REF / "Base", P.MATRIZ_BALANCE,
    P.CANDIDATE_FLOORS, P.VEG_TX_NEEDS_CSV, P.A2_OUTPUT_PARAMS / "BAU", P.A2_OTOOLE,
    P.OUTPUT_MODEL / "osemosys_fast_preprocessed_storage_delay.txt",
    P.PIPELINE / "B2_Executing_OG_Model.py", P.FIX_DISPATCH / "write_floors.py",
    P.TX_CHAIN / "veg_tx_constraints_v14.py", P.TOOLS / "concatenate_relac.py",
]

def main() -> int:
    missing = [p for p in MUST_EXIST if not p.exists()]
    for p in missing:
        print("FALTA:", p)
    assert P.executables_dir("BAU") == P.OUTPUTS / "Executables" / "BAU_0"
    assert P.REPO_ROOT.name == "relac_tx" or (P.REPO_ROOT / "dvc.yaml").is_file()
    print("OK relac_paths" if not missing else f"{len(missing)} rutas faltan")
    return 1 if missing else 0

if __name__ == "__main__":
    sys.exit(main())
