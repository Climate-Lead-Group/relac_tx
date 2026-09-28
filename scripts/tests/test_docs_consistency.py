# scripts/tests/test_docs_consistency.py
"""Check that user-facing documentation does not drift from the code.

Checks, over docs/*.md (root only: the published pages) and README.md:
  (a) every `scripts/**/*.py` path cited exists in the repo;
  (b) every `--x` flag cited on the SAME line as a script exists in that script's
      argparse (scripts without argparse are not validated);
  (c) every top-level key of inputs/config/Config_MOMF_T1_AB.yaml appears in some
      user doc.

Inputs:
    docs/*.md (root only), README.md
    inputs/config/Config_MOMF_T1_AB.yaml
    the scripts/**/*.py files cited in those docs (read for their argparse flags)
Usage:
    python scripts/tests/test_docs_consistency.py   (exit 0 = OK)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = sorted((ROOT / "docs").glob("*.md")) + [ROOT / "README.md"]
CONFIG_AB = ROOT / "inputs" / "config" / "Config_MOMF_T1_AB.yaml"

SCRIPT_RE = re.compile(r"scripts/[A-Za-z0-9_/\-]+\.py")
FLAG_RE = re.compile(r"(?<![\w-])--[a-z][a-z0-9-]*")
ARGPARSE_RE = re.compile(r"add_argument\(\s*['\"](--[a-z][a-z0-9-]*)")
KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):", re.M)
IGNORED_FLAGS = {"--help"}


def argparse_flags(script: Path) -> set[str]:
    text = script.read_text(encoding="utf-8", errors="replace")
    return set(ARGPARSE_RE.findall(text))


def check_scripts_and_flags(errors: list[str]) -> None:
    for doc in DOCS:
        for lineno, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            where = f"{doc.relative_to(ROOT)}:{lineno}"
            scripts = sorted(set(SCRIPT_RE.findall(line)))
            for rel in scripts:
                path = ROOT / rel
                if not path.is_file():
                    errors.append(f"{where}: script citado no existe: {rel}")
            if len(scripts) != 1:
                continue  # sin script, o ambiguo (2+ scripts en la linea): no validar flags
            path = ROOT / scripts[0]
            if not path.is_file():
                continue
            known = argparse_flags(path)
            if not known:
                continue
            for flag in sorted(set(FLAG_RE.findall(line)) - IGNORED_FLAGS):
                if flag not in known:
                    errors.append(f"{where}: flag {flag} no existe en {scripts[0]}")


def check_config_keys(errors: list[str]) -> None:
    docs_text = "\n".join(d.read_text(encoding="utf-8") for d in DOCS)
    keys = sorted(set(KEY_RE.findall(CONFIG_AB.read_text(encoding="utf-8"))))
    for key in keys:
        if not re.search(rf"(?<![\w]){re.escape(key)}(?![\w])", docs_text):
            errors.append(f"Config_MOMF_T1_AB.yaml: clave `{key}` no aparece en ningun doc de usuario")


def main() -> int:
    errors: list[str] = []
    check_scripts_and_flags(errors)
    check_config_keys(errors)
    if errors:
        print(f"FAIL: {len(errors)} inconsistencia(s) docs <-> codigo")
        for e in errors:
            print("  -", e)
        return 1
    print(f"OK: {len(DOCS)} docs revisados; scripts, flags y claves de Config_MOMF_T1_AB.yaml consistentes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
