#!/usr/bin/env python
"""compare_manifests.py manifest <repo_root> <old|new> <out.json>
   compare_manifests.py diff <a.json> <b.json>"""
import hashlib, json, sys
from pathlib import Path

# (carpeta relativa a la raíz, prefijo canónico)
LAYOUT = {
    "old": [
        ("t1_confection/A2_Output_Params", "A2_Output_Params"),
        ("t1_confection/A2_Outputs_Params_otoole", "A2_Outputs_Params_otoole"),
        ("t1_confection/Executables", "Executables"),
        ("t1_confection/osemosys_fast_preprocessed_storage_delay.txt", "model/osemosys_fast_preprocessed_storage_delay.txt"),
        ("RELAC_TX_data_storage_delay.txt", "RELAC_TX_data_storage_delay.txt"),
        ("fix_dispatch/upstream_floor_rows.csv", "fix_dispatch/upstream_floor_rows.csv"),
    ],
    "new": [
        ("outputs/A2_Output_Params", "A2_Output_Params"),
        ("outputs/A2_Outputs_Params_otoole", "A2_Outputs_Params_otoole"),
        ("outputs/Executables", "Executables"),
        ("outputs/model/osemosys_fast_preprocessed_storage_delay.txt", "model/osemosys_fast_preprocessed_storage_delay.txt"),
        ("outputs/RELAC_TX_data_storage_delay.txt", "RELAC_TX_data_storage_delay.txt"),
        ("outputs/fix_dispatch/upstream_floor_rows.csv", "fix_dispatch/upstream_floor_rows.csv"),
    ],
}
SKIP_SUFFIXES = (".pyc", ".png", ".lp", ".sol", ".glp")
SKIP_PARTS = ("__pycache__", "Outputs")   # Outputs/ = resultados de solver previos, no se comparan

def md5(p: Path) -> str:
    h = hashlib.md5()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def manifest(root: Path, layout: str) -> dict:
    out = {}
    for rel, key in LAYOUT[layout]:
        p = root / rel
        if p.is_file():
            out[key] = md5(p)
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if not f.is_file() or f.suffix in SKIP_SUFFIXES:
                    continue
                if any(part in SKIP_PARTS for part in f.relative_to(p).parts):
                    continue
                out[f"{key}/{f.relative_to(p).as_posix()}"] = md5(f)
        else:
            print(f"[warn] no existe: {p}")
    return out

def diff(a: dict, b: dict) -> int:
    only_a = sorted(set(a) - set(b)); only_b = sorted(set(b) - set(a))
    changed = sorted(k for k in set(a) & set(b) if a[k] != b[k])
    for title, items in (("SOLO EN BASELINE", only_a), ("SOLO EN NUEVO", only_b), ("DISTINTOS", changed)):
        print(f"== {title}: {len(items)}")
        for k in items[:200]:
            print("   ", k)
    print(f"\nTotal comparados: {len(set(a) & set(b))}  iguales: {len(set(a) & set(b)) - len(changed)}")
    return 0 if not (only_a or only_b or changed) else 1

if __name__ == "__main__":
    if sys.argv[1] == "manifest":
        m = manifest(Path(sys.argv[2]).resolve(), sys.argv[3])
        Path(sys.argv[4]).write_text(json.dumps(m, indent=1, sort_keys=True))
        print(f"{len(m)} archivos -> {sys.argv[4]}")
    elif sys.argv[1] == "diff":
        sys.exit(diff(json.loads(Path(sys.argv[2]).read_text()), json.loads(Path(sys.argv[3]).read_text())))
