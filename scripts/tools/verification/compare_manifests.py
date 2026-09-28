#!/usr/bin/env python
"""Compare pipeline outputs between the old and new `inputs/scripts/outputs` layouts.

Computes md5 checksums of every comparable product (A2_Output_Params, A2_Outputs_Params_otoole,
Executables/**.txt, the patched model, the root datafile, fix_dispatch/upstream_floor_rows.csv)
under either layout, mapping both to the same layout-independent keys (see `LAYOUT`), then diffs
two such manifests for exact equality. Part of the restructure verification procedure documented
in `scripts/tools/verification/README.md`.

Inputs:
    <repo_root>/t1_confection/... (layout "old") or <repo_root>/outputs/... (layout "new")
    <a.json>, <b.json>: manifests previously written by the `manifest` subcommand
Outputs:
    <out.json>: JSON manifest (canonical key -> md5), for the `manifest` subcommand
    stdout: diff report (SOLO EN BASELINE / SOLO EN NUEVO / DISTINTOS), for the `diff` subcommand
Usage:
    python scripts/tools/verification/compare_manifests.py manifest <repo_root> <old|new> <out.json>
    python scripts/tools/verification/compare_manifests.py diff <a.json> <b.json>
Notes:
    - `diff` exits 0 when the two manifests match exactly, 1 otherwise.
    - `.pyc`/`.png`/`.lp`/`.sol`/`.glp` files and any `Outputs/`-named sub-path are skipped
      (solver artifacts, not part of the comparison).
"""
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
    """Return the md5 hex digest of file `p`, read in 1 MiB chunks."""
    h = hashlib.md5()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def manifest(root: Path, layout: str) -> dict:
    """Build a canonical-key -> md5 manifest for one layout.

    Args:
        root: repo root (or worktree root) to scan.
        layout: "old" or "new", selects which `LAYOUT` entry maps relative paths to keys.

    Returns:
        Dict mapping layout-independent keys (see `LAYOUT`) to md5 hex digests. Skips
        `SKIP_SUFFIXES` files and any path under a `SKIP_PARTS` folder (solver artifacts).
    """
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
    """Print the only-in-a, only-in-b and differing keys between two manifests.

    Args:
        a: manifest dict (canonical key -> md5), e.g. the baseline.
        b: manifest dict (canonical key -> md5), e.g. the new layout.

    Returns:
        0 if `a` and `b` match exactly, 1 otherwise.
    """
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
