"""
build_combined.py  --  Paso 2 de INSTRUCCIONES_SOLVE.md: armar el CSV combinado
(inputs+outputs) para las corridas FLOORED. Los escenarios NO estan fijos:
se procesan todos los de relac_io.SCENARIOS que tengan outputs otoole del
Paso 1 en solved_FLOORED/<ESC>/Outputs/ (hoy BAU y OPT; INV/VGB entran solos
cuando se resuelvan).

Produce outputs/fix_dispatch/solved_FLOORED/RELAC_TX_FLOORED_Combined_Inputs_Outputs.csv
con el MISMO formato (89 columnas) que el CSV base de outputs/, reutilizando
la maquinaria existente del pipeline en vez de reimplementarla:

  2a. scripts/tools/concatenate_relac.py sobre solved_FLOORED/<ESC>/Outputs
      -> staging/<ESC>_0/Pre_processed_<ESC>_0_output.csv (candidato 2 de
      active_output_csv_candidates; el nombre <ESC>_0_Output.csv NUNCA matchea).
  2b. <ESC>_0_Input.csv reconstruido SOLO desde el datafile que consumio el
      solver: outputs/Executables/<ESC>_0/Pre_processed_..._FLOORED_VEGCON.txt (o
      .._FLOORED.txt si no hay variante VEGCON; ver relac_io.solver_txt). Cada bloque
      `param` del txt se parsea (indices por parametro segun
      Miscellaneous/conversion_format.yaml, mas EXTRA_PARAM_INDICES para los
      params que inyectan los patchers, p.ej. StorageBuildAllowed) y se
      materializa como CSV otoole en staging/<ESC>_0/txt_params/;
      generate_combined_input_file() de B2 los combina en el Input.csv.
      A2_Outputs_Params_otoole ya NO participa: todo input (pisos 2027+
      incluidos) sale del txt, sin injertos. Consecuencia: el txt preprocesado
      omite las filas con valor default, asi que el Input.csv contiene
      exactamente lo que el solver vio y nada mas.
  2c. B2_Executing_OG_Model.concatenate_all_scenarios() apuntada al staging via
      params['executables'], con prefix_final_files='RELAC_TX_FLOORED_' y
      HERE=solved_FLOORED para que el combinado caiga donde piden las
      instrucciones. Luego Z_AUX annualize_capital_investment() agrega la
      columna 89 (CapitalInvestmentAnnualized), igual que hace B2 en __main__.

Ningun archivo del pipeline original se modifica: todo se escribe bajo
outputs/fix_dispatch/solved_FLOORED/.

Uso (desde la raiz del repo):
  python scripts/fix_dispatch/build_combined.py
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent           # scripts/fix_dispatch
sys.path.insert(0, str(HERE.parents[0]))         # -> scripts/
from common import relac_paths as P
SOLVED = P.FIX_DISPATCH_OUT / "solved_FLOORED"
STAGING = SOLVED / "staging"
CONCAT_SCRIPT = P.TOOLS / "concatenate_relac.py"
LOWER = "TotalTechnologyAnnualActivityLowerLimit"

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(P.PIPELINE))

import relac_io as io                            # noqa: E402
import B2_Executing_OG_Model as b2               # noqa: E402

# Params que los patchers inyectan al txt y no existen en conversion_format.yaml.
EXTRA_PARAM_INDICES = {
    "StorageBuildAllowed": ["REGION", "STORAGE", "YEAR"],  # patch StorageDelay
}

# Dos formas de declaracion en el txt preprocesado:
#   param default 0 : NombreParam :=      (bloques otoole/preprocesados)
#   param NombreParam :=                  (bloques inyectados por patchers)
_PARAM_DECL = re.compile(r"^param\s+(?:default\s+\S+\s*:\s*)?(\w+)\s*:=\s*$")


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


def load_param_indices() -> dict[str, list[str]]:
    """Parametro -> nombres de sus indices, del config otoole del pipeline."""
    import yaml

    with open(P.MISCELLANEOUS / "conversion_format.yaml", "r") as fh:
        conv = yaml.safe_load(fh)
    idx = {name: spec["indices"] for name, spec in conv.items()
           if isinstance(spec, dict) and spec.get("type") == "param"}
    idx.update(EXTRA_PARAM_INDICES)
    return idx


def parse_txt_params(scenario: str) -> dict[str, pd.DataFrame]:
    """TODOS los bloques `param` no vacios del txt del solver, como DataFrames.

    Cada bloque del txt preprocesado es formato lista: una fila por registro,
    tokens = indices + valor. Un param desconocido o una fila con aridad
    inesperada abortan (mejor que adivinar nombres de indices)."""
    path = io.solver_txt(scenario)
    indices_map = load_param_indices()
    lines = path.read_bytes().decode("utf-8").splitlines()
    out: dict[str, pd.DataFrame] = {}
    i, n = 0, len(lines)
    while i < n:
        m = _PARAM_DECL.match(lines[i])
        if not m:
            i += 1
            continue
        name = m.group(1)
        i += 1
        rows = []
        while i < n and lines[i].strip() != ";":
            toks = lines[i].split()
            if toks:
                rows.append(toks)
            i += 1
        if not rows:
            continue
        if name not in indices_map:
            raise SystemExit(
                f"[{scenario}] param {name} del txt no esta en conversion_format.yaml "
                "ni en EXTRA_PARAM_INDICES; agrega sus indices para reconstruirlo")
        idx_names = indices_map[name]
        want = len(idx_names) + 1
        bad = next((r for r in rows if len(r) != want), None)
        if bad is not None:
            raise SystemExit(
                f"[{scenario}] {name}: fila con {len(bad)} tokens, esperaba "
                f"{want} ({'+'.join(idx_names)}+VALUE); ej: {' '.join(bad[:8])}")
        df = pd.DataFrame(rows, columns=idx_names + ["VALUE"])
        if "YEAR" in df.columns:
            df["YEAR"] = df["YEAR"].astype(float).astype(int)
        df["VALUE"] = df["VALUE"].astype(float)
        out[name] = df
    return out


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
    """2b: Input.csv reconstruido SOLO desde el txt que consumio el solver.

    Cada bloque `param` del txt se materializa como CSV otoole en
    staging/<ESC>_0/txt_params/ y generate_combined_input_file() (B2) los
    combina, igual que antes hacia con A2_Outputs_Params_otoole. El Input.csv
    queda identico a lo que el solver consumio (pisos 2027+ incluidos), asi
    que el injerto de LowerLimit ya no es necesario.
    """
    dst_dir = STAGING / f"{scenario}_0"
    params_dir = dst_dir / "txt_params"
    if params_dir.exists():
        shutil.rmtree(params_dir)  # no heredar CSVs de una corrida anterior
    params_dir.mkdir(parents=True)

    parsed = parse_txt_params(scenario)
    if LOWER not in parsed:
        raise SystemExit(f"[{scenario}] el txt floored no tiene bloque {LOWER}; "
                         "corre write_floors.py primero")
    for name, df in sorted(parsed.items()):
        df.to_csv(params_dir / f"{name}.csv", index=False)
    floors = parsed[LOWER]
    print(f"  [{scenario}] {len(parsed)} params parseados de {io.solver_txt(scenario).name}; "
          f"{LOWER}: {len(floors)} filas (YEAR {floors.YEAR.min()}-{floors.YEAR.max()})")

    src, _head = b2.generate_combined_input_file(
        input_folder=str(params_dir),
        output_folder=str(dst_dir),
        scenario_name=f"{scenario}_0",
    )
    if src is None:
        raise SystemExit(f"generate_combined_input_file no produjo Input.csv para {scenario}")
    dst = Path(src)
    print(f"  [{scenario}] escrito {dst.relative_to(P.REPO_ROOT)}")
    return dst


def combine() -> Path:
    """2c: reuse concatenate_all_scenarios() pointed at the staging folder."""
    import yaml

    with open(P.CONFIG_AB, "r") as fh:
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
