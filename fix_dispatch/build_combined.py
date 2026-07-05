"""
build_combined.py  --  Paso 2 de INSTRUCCIONES_SOLVE.md: armar el CSV combinado
(inputs+outputs) para las corridas FLOORED. Los escenarios NO estan fijos:
se procesan todos los de relac_io.SCENARIOS que tengan outputs otoole del
Paso 1 en solved_FLOORED/<ESC>/Outputs/ (hoy BAU y OPT; INV/VGB entran solos
cuando se resuelvan).

Produce fix_dispatch/solved_FLOORED/RELAC_TX_FLOORED_Combined_Inputs_Outputs.csv
con el MISMO formato (89 columnas) que el CSV base de t1_confection, reutilizando
la maquinaria existente del pipeline en vez de reimplementarla:

  2a. concatenate_files/concatenate_relac.py sobre solved_FLOORED/<ESC>/Outputs
      -> staging/<ESC>_0/Pre_processed_<ESC>_0_output.csv (candidato 2 de
      active_output_csv_candidates; el nombre <ESC>_0_Output.csv NUNCA matchea).
  2b. <ESC>_0_Input.csv reconstruido desde A2_Outputs_Params_otoole/<ESC> con
      generate_combined_input_file() de B2 (misma generacion 2026-06-25 que el
      txt que consumio el solver; los Input.csv de Executables son del 06-16 y
      tienen MaxCapInvest desfasado), y con la columna
      TotalTechnologyAnnualActivityLowerLimit reemplazada por el bloque homonimo
      del *_FLOORED.txt (write_floors.py solo toca el datafile txt, nunca los
      CSVs otoole, asi que los pisos 2027+ solo existen en el txt).
  2c. B2_Executing_OG_Model.concatenate_all_scenarios() apuntada al staging via
      params['executables'], con prefix_final_files='RELAC_TX_FLOORED_' y
      HERE=solved_FLOORED para que el combinado caiga donde piden las
      instrucciones. Luego Z_AUX annualize_capital_investment() agrega la
      columna 89 (CapitalInvestmentAnnualized), igual que hace B2 en __main__.

Ningun archivo del pipeline original se modifica: todo se escribe bajo
fix_dispatch/solved_FLOORED/.

Uso (desde la raiz del repo):
  python fix_dispatch/build_combined.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent           # fix_dispatch/
REPO = HERE.parent
T1 = REPO / "t1_confection"
SOLVED = HERE / "solved_FLOORED"
STAGING = SOLVED / "staging"
CONCAT_SCRIPT = REPO / "concatenate_files" / "concatenate_relac.py"
LOWER = "TotalTechnologyAnnualActivityLowerLimit"

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(T1))

import relac_io as io                            # noqa: E402
from write_floors import find_lower_limit_block  # noqa: E402
import B2_Executing_OG_Model as b2               # noqa: E402


def discover_scenarios() -> list[str]:
    """Escenarios con el Paso 1 resuelto: solved_FLOORED/<ESC>/Outputs con CSVs.

    Se recorre relac_io.SCENARIOS (y no los subdirectorios de solved_FLOORED)
    para conservar el orden canonico y no confundir carpetas auxiliares como
    staging/ con un escenario."""
    scens = [s for s in io.SCENARIOS if any((SOLVED / s / "Outputs").glob("*.csv"))]
    if not scens:
        raise SystemExit(f"ningun escenario tiene Outputs/*.csv bajo {SOLVED}; "
                         "corre el Paso 1 primero")
    return scens


def parse_floored_lower_limit(scenario: str) -> pd.DataFrame:
    """Rows of the LowerLimit block exactly as the FLOORED solver run consumed them."""
    path = io.floored_txt(scenario)
    lines = path.read_bytes().decode("utf-8").split("\r\n")
    decl_idx, term_idx, _default = find_lower_limit_block(lines)
    rows = []
    for i in range(decl_idx + 1, term_idx):
        toks = lines[i].split()
        if len(toks) != 4:
            continue
        region, tech, year, value = toks
        rows.append((region, tech, int(float(year)), float(value)))
    df = pd.DataFrame(rows, columns=["REGION", "TECHNOLOGY", "YEAR", "VALUE"])
    print(f"  [{scenario}] {LOWER} en {path.name}: {len(df)} filas")
    return df


def stage_outputs(scenario: str) -> Path:
    """2a: consolidate the 42 otoole CSVs into the wide per-scenario output CSV."""
    outputs_dir = SOLVED / scenario / "Outputs"
    n_csvs = len(list(outputs_dir.glob("*.csv")))
    if n_csvs == 0:
        raise SystemExit(f"{outputs_dir} no tiene CSVs otoole; corre el Paso 1 primero")
    prefix = STAGING / f"{scenario}_0" / f"Pre_processed_{scenario}_0_output"
    prefix.parent.mkdir(parents=True, exist_ok=True)
    print(f"  [{scenario}] concatenate_relac.py sobre {n_csvs} CSVs de {outputs_dir} ...")
    subprocess.run(
        [sys.executable, str(CONCAT_SCRIPT), str(outputs_dir), str(prefix)],
        check=True,
    )
    out_csv = prefix.with_suffix(".csv")
    if not out_csv.exists():
        raise SystemExit(f"concatenate_relac.py no produjo {out_csv}")
    print(f"  [{scenario}] escrito {out_csv.name} ({out_csv.stat().st_size:,} bytes)")
    return out_csv


def stage_input(scenario: str) -> Path:
    """2b: per-scenario Input.csv with the LowerLimit rows the solver actually saw.

    Rebuilt from A2_Outputs_Params_otoole/<ESC> (same 2026-06-25 generation as
    the solver's txt) instead of copying Executables/<ESC>_0/<ESC>_0_Input.csv,
    which is a stale 2026-06-16 build (pre "MaxCapInvest Javier y Luis").
    """
    dst_dir = STAGING / f"{scenario}_0"
    dst_dir.mkdir(parents=True, exist_ok=True)
    src, _head = b2.generate_combined_input_file(
        input_folder=str(T1 / "A2_Outputs_Params_otoole" / scenario),
        output_folder=str(dst_dir),
        scenario_name=f"{scenario}_0",
    )
    if src is None:
        raise SystemExit(f"generate_combined_input_file no produjo Input.csv para {scenario}")
    df = pd.read_csv(src, low_memory=False)
    if LOWER not in df.columns:
        raise SystemExit(f"{src} no tiene columna {LOWER}")
    floors = parse_floored_lower_limit(scenario)
    n_before = int(df[LOWER].notna().sum())
    df = df[df[LOWER].isna()]
    new_rows = pd.DataFrame(
        {
            "REGION": floors["REGION"],
            "TECHNOLOGY": floors["TECHNOLOGY"],
            "YEAR": floors["YEAR"],
            LOWER: floors["VALUE"],
        }
    ).reindex(columns=df.columns)
    df = pd.concat([df, new_rows], ignore_index=True)
    dst = STAGING / f"{scenario}_0" / f"{scenario}_0_Input.csv"
    dst.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(dst, index=False)
    print(f"  [{scenario}] {LOWER}: {n_before} filas pre-floor -> {len(floors)} filas FLOORED; "
          f"escrito {dst.relative_to(REPO)}")
    return dst


def combine() -> Path:
    """2c: reuse concatenate_all_scenarios() pointed at the staging folder."""
    import yaml

    with open(T1 / "Config_MOMF_T1_AB.yaml", "r") as fh:
        params = yaml.safe_load(fh)
    params["executables"] = str(STAGING)
    params["prefix_final_files"] = "RELAC_TX_FLOORED_"

    path_in, path_out, path_comb = b2.concatenate_all_scenarios(str(SOLVED), params)
    if path_comb is None:
        raise SystemExit("concatenate_all_scenarios no produjo el combinado "
                         "(falta input u output en el staging)")
    print(f"  inputs:   {path_in}")
    print(f"  outputs:  {path_out}")
    print(f"  combined: {path_comb} ({Path(path_comb).stat().st_size:,} bytes)")
    return Path(path_comb)


def annualize(path_comb: Path) -> None:
    """Column 89 (CapitalInvestmentAnnualized), same call B2's __main__ makes."""
    try:
        from Z_AUX_capital_annualization_script import annualize_capital_investment
        annualize_capital_investment(input_file_path=str(path_comb), verbose=False)
        print("  CapitalInvestmentAnnualized agregada")
    except Exception as exc:  # column 89 is format parity only; tests never read it
        print(f"  [WARN] anualizacion fallo ({exc}); el combinado queda con 88 columnas")


def main() -> None:
    scenarios = discover_scenarios()
    print(f"escenarios detectados (con Paso 1 resuelto): {scenarios}")
    print("== Paso 2a: consolidar outputs otoole por escenario ==")
    for scen in scenarios:
        stage_outputs(scen)
    print("== Paso 2b: inputs por escenario con pisos FLOORED ==")
    for scen in scenarios:
        stage_input(scen)
    print("== Paso 2c: combinar escenarios ==")
    path_comb = combine()
    print("== Anualizacion de CapitalInvestment ==")
    annualize(path_comb)

    header = pd.read_csv(path_comb, nrows=0).columns
    scen_col = pd.read_csv(path_comb, usecols=["Scenario"])["Scenario"]
    print(f"\nRESUMEN: {path_comb}")
    print(f"  columnas: {len(header)}  |  filas: {len(scen_col):,}  |  "
          f"escenarios: {sorted(scen_col.unique())}")


if __name__ == "__main__":
    main()
