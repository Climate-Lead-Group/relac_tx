"""Master runner for the presentation figures (scripts/figures/presentation/).

Runs, in the same process, the fig_*_presentation*.py scripts enabled in run_figures.yaml
(in file order), after building or reusing the BAC+ISR Parquet subset.

Inputs:
    run_figures.yaml (per-script on/off switches)
Outputs:
    outputs/Figures/Presentation/ (dashboard_config.FIGURES_PRESENTATION_DIR; delegated to
    each fig script)
Usage:
    python scripts/figures/presentation/run_figures.py
    python scripts/figures/presentation/run_figures.py --list
    python scripts/figures/presentation/run_figures.py --only fig_almacenamiento_2050_presentation
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # -> scripts/
from figures.common import fig_runner  # noqa: E402

PACKAGE = "presentation"
YAML = Path(__file__).with_name("run_figures.yaml")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="+", default=None, metavar="fig_x",
                    help="correr solo estos módulos (ignora el true/false del YAML)")
    ap.add_argument("--list", action="store_true", help="mostrar el YAML resuelto sin correr nada")
    args = ap.parse_args(argv)
    return fig_runner.run_folder(PACKAGE, YAML, only=args.only, list_only=args.list)


if __name__ == "__main__":
    sys.exit(main())
