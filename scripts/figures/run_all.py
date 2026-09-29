"""Overall master for all figures: report -> presentation -> dashboard -> tablas per run_all.yaml.

Step 0 builds/reuses the BAC+ISR Parquet subset. Then, in this fixed order, each enabled branch:
  report        -> scripts/figures/report/run_figures.py       (outputs/Figures/Report/)
  presentation  -> scripts/figures/presentation/run_figures.py (outputs/Figures/Presentation/)
  dashboard     -> figures.dashboard.build_dashboard.main([..])
                    (outputs/Figures/Dashboard/dashboard.html)
  tablas        -> scripts/figures/Z_AUX_make_tablas_xlsx.py
                    (outputs/Figures/Tablas_Completas_Resultados.xlsx)
The first three branches run in this same process; `tablas` runs in a subprocess (PYTHONUTF8=1)
because that script does work at import time and reduces the full CSV in chunks, so isolating it
frees that memory once it finishes and it never overlaps in memory with the fig_*.py processes (the
script warns of OOM if run in parallel). A branch that fails does not stop the others; at the end it
prints a per-branch summary table and returns 1 if any branch failed.

Inputs:
    scripts/figures/run_all.yaml               # per-branch on/off switches
    outputs/RELAC_TX_Combined_Inputs_Outputs.csv  # read by fig_runner.step0_subset and the branches
Outputs:
    outputs/Figures/**                         # per branch, see the mapping above
Usage:
    python scripts/figures/run_all.py
    python scripts/figures/run_all.py --list
    python scripts/figures/run_all.py --only report presentation
"""
import argparse
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> scripts/
from figures.common import fig_runner  # noqa: E402

HERE = Path(__file__).resolve().parent
ORDER = ["report", "presentation", "dashboard", "tablas"]


def run_report() -> int:
    """Run the report branch (report/run_figures.py) via fig_runner.run_folder."""
    return fig_runner.run_folder("report", HERE / "report" / "run_figures.yaml")


def run_presentation() -> int:
    """Run the presentation branch (presentation/run_figures.py) via fig_runner.run_folder."""
    return fig_runner.run_folder("presentation", HERE / "presentation" / "run_figures.yaml")


def run_dashboard() -> int:
    """Build the full dashboard (all charts + tabs 16-18) by calling build_dashboard.main([]).

    No chart numbers are passed: passing one would leave the combined HTML with only that
    chart (see spec §8.4).
    """
    from figures.dashboard import build_dashboard
    # Sin argumentos: TODOS los charts + pestañas 16-18. Pasarle un número dejaría el
    # HTML combinado con un solo chart (§8.4 de la spec).
    build_dashboard.main(["build_dashboard.py"])
    return 0


def run_tablas() -> int:
    """Run Z_AUX_make_tablas_xlsx.py in a subprocess (PYTHONUTF8=1) and return its exit code.

    Subprocess isolation: that script is a top-level-code module (no main()) that reads the
    full combined CSV (~1.5 GB) in chunks; isolating it frees that memory once it exits and
    keeps it from overlapping in memory with the fig_*.py processes.
    """
    # Subproceso: el script es un módulo con código de nivel superior (no expone main())
    # y lee el CSV completo (~1,5 GB) por chunks; aislarlo devuelve la RAM al terminar.
    env = {**os.environ, "PYTHONUTF8": "1"}
    proc = subprocess.run([sys.executable, str(HERE / "Z_AUX_make_tablas_xlsx.py")], env=env)
    return proc.returncode


RUNNERS = {"report": run_report, "presentation": run_presentation,
           "dashboard": run_dashboard, "tablas": run_tablas}


def read_config(path: Path) -> dict[str, bool]:
    """Load run_all.yaml and return {branch: enabled} for every branch in ORDER.

    Args:
        path: path to run_all.yaml.

    Returns:
        Dict with one bool per ORDER key (missing keys default to False).

    Raises:
        ValueError: if the YAML has a key outside ORDER.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    unknown = sorted(set(raw) - set(ORDER))
    if unknown:
        raise ValueError(f"{path}: claves desconocidas {unknown}; válidas: {ORDER}")
    return {k: bool(raw.get(k, False)) for k in ORDER}


def main(argv: list[str] | None = None) -> int:
    """Parse CLI args, run the enabled branches in ORDER and print a summary table.

    Runs `fig_runner.step0_subset()` first (shared by report/presentation), then each
    enabled branch's runner from RUNNERS; a branch whose runner raises or returns non-zero
    is marked ERROR but does not stop the remaining branches.

    Args:
        argv: CLI arguments (``--only``, ``--list``); ``None`` uses ``sys.argv``.

    Returns:
        0 if every run branch succeeded (or ``--list``/no branches ran); 1 if any branch
        errored.
    """
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="+", choices=ORDER, default=None,
                    help="correr solo estas ramas (ignora el true/false del YAML)")
    ap.add_argument("--list", action="store_true", help="mostrar el YAML resuelto sin correr nada")
    args = ap.parse_args(argv)

    enabled = read_config(HERE / "run_all.yaml")
    if args.only:
        enabled = {k: (k in args.only) for k in ORDER}
    if args.list:
        for k in ORDER:
            print(f"{'ON ' if enabled[k] else 'off'}  {k}")
        return 0

    t_all = time.perf_counter()
    fig_runner.step0_subset()
    summary: list[tuple[str, str, float]] = []
    for k in ORDER:
        if not enabled[k]:
            summary.append((k, "OMITIDO", 0.0))
            continue
        print(f"\n######## {k} ########")
        t0 = time.perf_counter()
        try:
            status = "OK" if RUNNERS[k]() == 0 else "ERROR"
        except SystemExit as e:           # build_dashboard hace sys.exit(1) con charts desconocidos
            status = "OK" if e.code in (None, 0) else "ERROR"
        except Exception:                 # noqa: BLE001 — seguir con las demás ramas
            traceback.print_exc()
            status = "ERROR"
        summary.append((k, status, time.perf_counter() - t0))

    print(f"\n{'rama':<13}| estado  | segundos")
    print("-------------+---------+---------")
    for k, s, secs in summary:
        print(f"{k:<13}| {s:<7} | {secs:8.1f}")
    print(f"Total {time.perf_counter() - t_all:.1f} s")
    return 1 if any(s == "ERROR" for _, s, _ in summary) else 0


if __name__ == "__main__":
    sys.exit(main())
