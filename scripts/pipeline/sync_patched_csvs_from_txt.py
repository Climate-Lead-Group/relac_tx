"""sync_patched_csvs_from_txt.py

Extract parameter blocks from a patched OSeMOSYS GMPL datafile (.txt) and
overwrite the matching otoole-format CSVs in the original A2 folder in place.

Intended to be called from B2 between the patcher chain and
generate_combined_input_file() so the Combined_Inputs_Outputs.csv reflects
the patched inputs the solver actually consumed.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def find_param_block(lines: list[str], param_name: str) -> tuple[int, int] | None:
    header_re = re.compile(
        rf"^\s*param(?:\s+default\s+\S+)?\s*:\s*{re.escape(param_name)}\s*:=\s*$"
    )
    start = None
    for i, line in enumerate(lines):
        if header_re.match(line):
            start = i
            break
    if start is None:
        return None
    end = start + 1
    while end < len(lines) and lines[end].strip() != ';':
        end += 1
    if end >= len(lines):
        raise RuntimeError(f"Unterminated param block {param_name!r}")
    return start, end


def parse_param_rows(lines: list[str], param_name: str) -> list[list[str]] | None:
    block = find_param_block(lines, param_name)
    if block is None:
        return None
    start, end = block
    rows: list[list[str]] = []
    for line in lines[start + 1: end]:
        stripped = line.strip()
        if not stripped:
            continue
        rows.append(stripped.split())
    return rows


def sync_csv_from_txt(
    txt_lines: list[str],
    csv_path: Path,
    param_name: str,
) -> bool:
    if not csv_path.exists():
        print(f"[skip] no CSV for {param_name}: {csv_path}")
        return False

    rows = parse_param_rows(txt_lines, param_name)
    if rows is None:
        print(f"[skip] param block {param_name!r} not found in .txt")
        return False

    header_line = csv_path.read_text(encoding='utf-8').splitlines()[0]
    n_cols = len(header_line.split(','))

    for i, row in enumerate(rows):
        if len(row) != n_cols:
            raise RuntimeError(
                f"Row width mismatch for {param_name} (row {i}: {row!r}); "
                f"expected {n_cols} cols matching header {header_line!r}"
            )

    out_lines = [header_line] + [",".join(row) for row in rows] + [""]
    csv_path.write_text("\n".join(out_lines), encoding='utf-8')
    print(f"[ok] {param_name}: wrote {len(rows)} rows -> {csv_path}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--txt", required=True, help="Patched .txt datafile.")
    parser.add_argument(
        "--csv-folder",
        required=True,
        help="A2 otoole CSV folder. The listed param CSVs are overwritten in place.",
    )
    parser.add_argument(
        "--params",
        nargs="+",
        required=True,
        help="Parameter names to sync from the .txt into the CSV folder.",
    )
    args = parser.parse_args()

    txt_path = Path(args.txt)
    csv_folder = Path(args.csv_folder)

    if not txt_path.exists():
        print(f"[error] txt not found: {txt_path}", file=sys.stderr)
        return 1
    if not csv_folder.is_dir():
        print(f"[error] CSV folder not found: {csv_folder}", file=sys.stderr)
        return 1

    txt_lines = txt_path.read_text(encoding='utf-8').splitlines()

    synced = 0
    for param in args.params:
        csv_path = csv_folder / f"{param}.csv"
        if sync_csv_from_txt(txt_lines, csv_path, param):
            synced += 1

    print(f"Synced {synced}/{len(args.params)} params from {txt_path.name} into {csv_folder}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
