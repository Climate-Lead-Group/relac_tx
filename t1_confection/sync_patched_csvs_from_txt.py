"""sync_patched_csvs_from_txt.py

Extract parameter blocks from a patched OSeMOSYS GMPL datafile (.txt) and write
them back into otoole-format CSVs in a sibling mirror folder. The original A2
otoole input CSV folder is never modified -- this script writes to
--out-csv-folder, which is a copy of --source-csv-folder with the requested
parameter CSVs overwritten by the patched values found in the .txt.

Intended to be called from B2 between the patcher chain and
generate_combined_input_file() so the Combined_Inputs_Outputs.csv reflects
the patched inputs the solver actually consumed.
"""

from __future__ import annotations

import argparse
import re
import shutil
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


def mirror_csv_folder(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for entry in source.iterdir():
        if entry.is_file() and entry.suffix.lower() == '.csv':
            shutil.copy2(entry, destination / entry.name)


def sync_csv_from_txt(
    txt_lines: list[str],
    csv_source: Path,
    csv_destination: Path,
    param_name: str,
) -> bool:
    if not csv_source.exists():
        print(f"[skip] no source CSV for {param_name}: {csv_source}")
        return False

    rows = parse_param_rows(txt_lines, param_name)
    if rows is None:
        print(f"[skip] param block {param_name!r} not found in .txt")
        return False

    header_line = csv_source.read_text(encoding='utf-8').splitlines()[0]
    n_cols = len(header_line.split(','))

    for i, row in enumerate(rows):
        if len(row) != n_cols:
            raise RuntimeError(
                f"Row width mismatch for {param_name} (row {i}: {row!r}); "
                f"expected {n_cols} cols matching header {header_line!r}"
            )

    out_lines = [header_line] + [",".join(row) for row in rows] + [""]
    csv_destination.write_text("\n".join(out_lines), encoding='utf-8')
    print(f"[ok] {param_name}: wrote {len(rows)} rows -> {csv_destination}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--txt", required=True, help="Patched .txt datafile.")
    parser.add_argument(
        "--source-csv-folder",
        required=True,
        help="Original A2 otoole CSV folder (read-only).",
    )
    parser.add_argument(
        "--out-csv-folder",
        required=True,
        help="Destination mirror folder for the patched CSVs.",
    )
    parser.add_argument(
        "--params",
        nargs="+",
        required=True,
        help="Parameter names to sync from the .txt into the mirror folder.",
    )
    args = parser.parse_args()

    txt_path = Path(args.txt)
    csv_src = Path(args.source_csv_folder)
    csv_dst = Path(args.out_csv_folder)

    if not txt_path.exists():
        print(f"[error] txt not found: {txt_path}", file=sys.stderr)
        return 1
    if not csv_src.is_dir():
        print(f"[error] source CSV folder not found: {csv_src}", file=sys.stderr)
        return 1

    mirror_csv_folder(csv_src, csv_dst)
    txt_lines = txt_path.read_text(encoding='utf-8').splitlines()

    synced = 0
    for param in args.params:
        csv_source = csv_src / f"{param}.csv"
        csv_destination = csv_dst / f"{param}.csv"
        if sync_csv_from_txt(txt_lines, csv_source, csv_destination, param):
            synced += 1

    print(f"Synced {synced}/{len(args.params)} params from {txt_path.name} into {csv_dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
