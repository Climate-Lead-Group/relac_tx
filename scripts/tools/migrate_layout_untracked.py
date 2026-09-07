#!/usr/bin/env python
"""Mueve artefactos NO versionados del layout viejo (t1_confection/, fix_dispatch/, ...) al nuevo
(inputs/ scripts/ outputs/). Idempotente: si el origen no existe, lo omite; si el destino ya
existe y no está vacío, NO sobrescribe (informa). Dry-run por defecto; --apply mueve.

Uso:  python scripts/tools/migrate_layout_untracked.py           # dry-run
      python scripts/tools/migrate_layout_untracked.py --apply
"""
import argparse
import shutil
import sys
from pathlib import Path

ROOT = next(p for p in [Path(__file__).resolve(), *Path(__file__).resolve().parents] if (p / "dvc.yaml").is_file())

# (origen relativo a la raíz, destino relativo a la raíz). Carpetas o archivos; globs con '*'.
MOVES = [
    ("t1_confection/Executables",                       "outputs/Executables"),
    ("t1_confection/A2_Structure_Lists.xlsx",           "outputs/A2_Structure_Lists.xlsx"),
    ("t1_confection/RELAC_TX_*.csv",                    "outputs/"),
    ("t1_confection/cplex.log",                         "outputs/logs/cplex.log"),
    ("t1_confection/clone1.log",                        "outputs/logs/clone1.log"),
    ("t1_confection/clone2.log",                        "outputs/logs/clone2.log"),
    ("t1_confection/gurobi.log",                        "outputs/logs/gurobi.log"),
    ("t1_confection/templates",                         "outputs/templates"),
    ("t1_confection/A1_Outputs",                        "inputs/A1_Outputs"),          # restos (backups) si git mv no los llevó
    ("t1_confection/Figures",                           "outputs/Figures"),
    ("fix_dispatch/cache",                              "outputs/fix_dispatch/cache"),
    ("fix_dispatch/outputs_BACKUP",                     "outputs/fix_dispatch/outputs_BACKUP"),
    ("fix_dispatch/solved_FLOORED",                     "outputs/fix_dispatch/solved_FLOORED"),
    ("fix_dispatch/report_lock_planned_capacity_template.html", "outputs/fix_dispatch/report_lock_planned_capacity_template.html"),
    ("RELAC_Tx_v15_run/veg_pipeline_proof.png",         "outputs/tx_chain/veg_pipeline_proof.png"),
    ("RELAC_Tx_v15_run/veg_preflight.png",              "outputs/tx_chain/veg_preflight.png"),
    ("RELAC_Tx_v15_run/templates",                      "outputs/tx_chain/templates"),
]
OLD_DIRS = ["t1_confection", "fix_dispatch", "RELAC_Tx_v15_run", "veg_tx_abs_test", "concatenate_files"]


def _merge_dir(src: Path, dst: Path, apply: bool) -> None:
    """Mueve el contenido de src dentro de dst (dst puede existir por el git mv previo)."""
    for item in sorted(src.iterdir()):
        target = dst / item.name
        if target.exists():
            if item.is_dir() and target.is_dir():
                _merge_dir(item, target, apply)
                continue
            print(f"  [skip] ya existe: {target}")
            continue
        print(f"  {item}  ->  {target}")
        if apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(item), str(target))
    if apply and not any(src.iterdir()):
        src.rmdir()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="mover de verdad (por defecto solo muestra)")
    args = ap.parse_args()
    print(f"Raíz: {ROOT}   modo: {'APPLY' if args.apply else 'DRY-RUN'}\n")
    for src_rel, dst_rel in MOVES:
        srcs = sorted(ROOT.glob(src_rel)) if "*" in src_rel else [ROOT / src_rel]
        for src in srcs:
            if not src.exists():
                continue
            dst = ROOT / dst_rel
            if dst_rel.endswith("/"):
                dst = dst / src.name
            if src.is_dir() and dst.exists():
                print(f"[merge] {src} -> {dst}")
                _merge_dir(src, dst, args.apply)
            elif dst.exists():
                print(f"[skip] ya existe: {dst}")
            else:
                print(f"[move] {src} -> {dst}")
                if args.apply:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(dst))
    print("\n=== Restos en carpetas viejas (revisar y borrar a mano si procede) ===")
    for d in OLD_DIRS:
        p = ROOT / d
        if p.exists():
            rest = [x for x in p.rglob("*") if x.is_file() and "__pycache__" not in x.parts]
            print(f"{d}/: {len(rest)} archivo(s)")
            for x in rest[:20]:
                print("   ", x.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
