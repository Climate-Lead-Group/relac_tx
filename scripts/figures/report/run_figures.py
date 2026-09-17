"""
run_figures.py — maestro de las figuras de REPORTE (scripts/figures/report/).

Corre, en el mismo proceso, los fig_*.py encendidos en run_figures.yaml (orden =
orden del YAML) tras construir/reutilizar el subconjunto Parquet BAC+ISR.
Salidas: outputs/Figures/Report/ (dashboard_config.FIGURES_DIR).

Uso:
    python scripts/figures/report/run_figures.py
    python scripts/figures/report/run_figures.py --list
    python scripts/figures/report/run_figures.py --only fig_almacenamiento_2050 fig_costo_unitario
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # -> scripts/
from figures.common import fig_runner  # noqa: E402

PACKAGE = "report"
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
