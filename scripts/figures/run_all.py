"""
run_all.py — maestro total de figuras: report -> presentation -> dashboard según run_all.yaml.

Paso 0: construir/reutilizar el subconjunto Parquet BAC+ISR. Después, en este orden
fijo y en el mismo proceso, cada rama encendida:
  report        -> scripts/figures/report/run_figures.py       (outputs/Figures/Report/)
  presentation  -> scripts/figures/presentation/run_figures.py (outputs/Figures/Presentation/)
  dashboard     -> figures.dashboard.build_dashboard.main([..]) (outputs/Figures/Dashboard/dashboard.html)
Una rama que falle no detiene a las demás; al final imprime un resumen por rama y
devuelve 1 si alguna falló.

Uso:
    python scripts/figures/run_all.py
    python scripts/figures/run_all.py --list
    python scripts/figures/run_all.py --only report presentation
"""
import argparse
import sys
import time
import traceback
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> scripts/
from figures.common import fig_runner  # noqa: E402

HERE = Path(__file__).resolve().parent
ORDER = ["report", "presentation", "dashboard"]


def run_report() -> int:
    return fig_runner.run_folder("report", HERE / "report" / "run_figures.yaml")


def run_presentation() -> int:
    return fig_runner.run_folder("presentation", HERE / "presentation" / "run_figures.yaml")


def run_dashboard() -> int:
    from figures.dashboard import build_dashboard
    # Sin argumentos: TODOS los charts + pestañas 16-18. Pasarle un número dejaría el
    # HTML combinado con un solo chart (§8.4 de la spec).
    build_dashboard.main(["build_dashboard.py"])
    return 0


RUNNERS = {"report": run_report, "presentation": run_presentation, "dashboard": run_dashboard}


def read_config(path: Path) -> dict[str, bool]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    unknown = sorted(set(raw) - set(ORDER))
    if unknown:
        raise ValueError(f"{path}: claves desconocidas {unknown}; válidas: {ORDER}")
    return {k: bool(raw.get(k, False)) for k in ORDER}


def main(argv: list[str] | None = None) -> int:
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
