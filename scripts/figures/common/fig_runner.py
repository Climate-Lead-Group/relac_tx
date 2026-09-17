"""
fig_runner.py — lógica compartida de los maestros de carpeta
(scripts/figures/report/run_figures.py y scripts/figures/presentation/run_figures.py).

Lee un YAML de encendido/apagado (clave = módulo fig_* sin .py; valor = true|false
o {enabled: bool, args: [str, ...]}; el orden del YAML es el orden de ejecución),
construye/reutiliza el subconjunto Parquet BAC+ISR (paso 0) y ejecuta cada figura
encendida EN EL MISMO PROCESO (comparte la caché en memoria de
dashboard_config.load_column: el Parquet no se relee entre figuras con las mismas
columnas). Un fallo NO detiene al resto. Spec 2026-09-16 §8.1.
"""
from __future__ import annotations

import importlib
import io
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from figures.common import dashboard_config as cfg
from figures.common import report_style as rs

STATUS_OK, STATUS_WARN, STATUS_ERROR, STATUS_SKIP = "OK", "AVISO", "ERROR", "OMITIDO"


@dataclass
class Entry:
    name: str
    enabled: bool
    args: list[str] = field(default_factory=list)


@dataclass
class Result:
    name: str
    status: str
    seconds: float = 0.0
    output: str = ""


def read_yaml(yaml_path: Path) -> list[Entry]:
    """Mapa YAML -> lista ordenada de Entry. Acepta `nombre: true|false` o
    `nombre: {enabled: bool, args: [..]}` (enabled por defecto true en la forma larga)."""
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{yaml_path}: se esperaba un mapa nombre -> true|false|{{enabled, args}}")
    entries: list[Entry] = []
    for name, val in raw.items():
        if isinstance(val, bool):
            entries.append(Entry(str(name), val))
        elif isinstance(val, dict):
            args = [str(a) for a in (val.get("args") or [])]
            entries.append(Entry(str(name), bool(val.get("enabled", True)), args))
        else:
            raise ValueError(f"{yaml_path}: valor inválido para {name!r}: {val!r} "
                             "(use true/false o {enabled: bool, args: [...]})")
    return entries


def scripts_on_disk(folder: Path) -> list[str]:
    return sorted(p.stem for p in folder.glob("fig_*.py"))


def validate(entries: list[Entry], folder: Path) -> list[str]:
    """Avisos: claves del YAML sin .py, fig_*.py en disco sin clave (no se ejecutarán), claves repetidas."""
    disk = set(scripts_on_disk(folder))
    names = [e.name for e in entries]
    out = []
    for n in names:
        if n not in disk:
            out.append(f"[aviso] {n}: está en el YAML pero no existe {folder / (n + '.py')}")
    for n in sorted(disk - set(names)):
        out.append(f"[aviso] {n}.py existe en disco pero no está en el YAML (no se ejecutará)")
    for n in sorted({n for n in names if names.count(n) > 1}):
        out.append(f"[aviso] {n}: clave repetida en el YAML")
    return out


class _Tee(io.TextIOBase):
    """Reenvía a la consola y guarda copia para extraer las líneas 'OK -> <ruta>'."""

    def __init__(self, real):
        self.real, self.buf = real, io.StringIO()

    def write(self, s):
        self.real.write(s)
        self.buf.write(s)
        return len(s)

    def flush(self):
        self.real.flush()


def run_one(package: str, entry: Entry) -> Result:
    import matplotlib.pyplot as plt
    t0 = time.perf_counter()
    tee = _Tee(sys.stdout)
    real_stdout, sys.stdout = sys.stdout, tee
    status, output = STATUS_OK, ""
    try:
        mod = importlib.import_module(f"figures.{package}.{entry.name}")
        mod.main(entry.args)
    except SystemExit as e:
        msg = "" if e.code in (None, 0) else str(e.code)
        if msg:
            status, output = (STATUS_WARN if "Sin datos" in msg else STATUS_ERROR), msg
    except Exception as e:  # noqa: BLE001 — un script roto no detiene al resto (§8.1)
        tb = traceback.extract_tb(sys.exc_info()[2])[-1]
        status, output = STATUS_ERROR, f"{type(e).__name__}: {e} @ {Path(tb.filename).name}:{tb.lineno}"
        print("".join(traceback.format_exception(e)[-3:]), file=sys.stderr, end="")
    finally:
        sys.stdout = real_stdout
        plt.close("all")
    if status == STATUS_OK:
        oks = [ln[len("OK -> "):].strip() for ln in tee.buf.getvalue().splitlines() if ln.startswith("OK -> ")]
        output = "; ".join(Path(o).name for o in oks) if oks else "(sin 'OK ->' en la salida)"
    return Result(entry.name, status, time.perf_counter() - t0, output)


def print_table(results: list[Result], total_s: float) -> None:
    w = max([len(r.name) for r in results] + [6])
    print(f"\n{'script':<{w}} | estado  | segundos | salida")
    print("-" * (w + 1) + "+---------+----------+" + "-" * 30)
    for r in results:
        secs = f"{r.seconds:8.1f}" if r.status != STATUS_SKIP else " " * 8
        print(f"{r.name:<{w}} | {r.status:<7} | {secs} | {r.output}")
    n = {s: sum(1 for r in results if r.status == s) for s in (STATUS_OK, STATUS_WARN, STATUS_ERROR, STATUS_SKIP)}
    print(f"\nTotal {total_s:.1f} s — OK {n[STATUS_OK]}, AVISO {n[STATUS_WARN]}, "
          f"ERROR {n[STATUS_ERROR]}, OMITIDO {n[STATUS_SKIP]}")


def step0_subset(scenarios: list[str] | None = None) -> None:
    """Paso 0: construir o reutilizar el Parquet BAC+ISR e informar cuánto tardó."""
    scenarios = list(scenarios or rs.CORE_SCENARIOS)
    t0 = time.perf_counter()
    reused = cfg.subset_is_current(scenarios)
    path = cfg.ensure_scenario_subset(scenarios, verbose=False)
    print(f"[paso 0] subconjunto Parquet {'reutilizado' if reused else 'reconstruido'}: "
          f"{path} ({time.perf_counter() - t0:.1f} s)")


def resolve(entries: list[Entry], only: list[str] | None) -> list[Entry]:
    """Con --only: solo esos nombres, encendidos, conservando los args del YAML si los hay."""
    if not only:
        return entries
    by_name = {e.name: e for e in entries}
    return [Entry(n, True, by_name[n].args if n in by_name else []) for n in only]


def run_folder(package: str, yaml_path: Path, only: list[str] | None = None,
               list_only: bool = False) -> int:
    """Ejecuta las figuras de scripts/figures/<package>/ según yaml_path. Devuelve 1 si hubo ERROR."""
    folder = yaml_path.parent
    entries = read_yaml(yaml_path)
    for w in validate(entries, folder):
        print(w)
    plan = resolve(entries, only)
    out_dir = cfg.FIGURES_DIR if package == "report" else cfg.FIGURES_PRESENTATION_DIR
    if list_only:
        for e in plan:
            print(f"{'ON ' if e.enabled else 'off'}  {e.name}" + (f"  args={e.args}" if e.args else ""))
        print(f"{sum(e.enabled for e in plan)}/{len(plan)} encendidos -> {out_dir}")
        return 0
    t_all = time.perf_counter()
    step0_subset()
    results: list[Result] = []
    for e in plan:
        if not e.enabled:
            results.append(Result(e.name, STATUS_SKIP))
            continue
        print(f"\n=== {package}/{e.name} {' '.join(e.args)} ===")
        results.append(run_one(package, e))
    print_table(results, time.perf_counter() - t_all)
    print(f"Salida: {out_dir}")
    return 1 if any(r.status == STATUS_ERROR for r in results) else 0
