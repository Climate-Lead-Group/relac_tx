"""Overwrite otoole-format CSVs in an A2 output folder from a patched OSeMOSYS .txt.

Extracts named parameter blocks from a patched OSeMOSYS GMPL datafile (.txt) and rewrites
the matching CSVs in the original A2 folder in place, so the combined input/output CSVs
reflect the patched inputs the solver actually consumed.

Inputs:
    --txt (patched .txt datafile)
    --csv-folder (A2 otoole CSV folder, e.g. outputs/A2_Outputs_Params_otoole/<scenario>/)
Outputs:
    <csv-folder>/<param>.csv for each name in --params, overwritten in place.
Usage:
    python scripts/pipeline/sync_patched_csvs_from_txt.py --txt <path> --csv-folder <dir>
        --params <name1> <name2> ...
Notes:
    - Called by B2_Executing_OG_Model.py between the patcher chain and
      generate_combined_input_file(), i.e. BEFORE the solve, when `sync_patched_csvs_active`.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def find_param_block(lines: list[str], param_name: str) -> tuple[int, int] | None:
    """Return the (start, end) line indices of a `param ... : <param_name> := ... ;` block.

    Args:
        lines: full text of the .txt datafile, split into lines.
        param_name: OSeMOSYS parameter name to locate.

    Returns:
        (start, end) indices into `lines` (header line, terminating `;` line), or None if
        the parameter header is not found.

    Raises:
        RuntimeError: if the block is opened but never terminated by a `;` line.
    """
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
    """Return the whitespace-split data rows of a parameter block, or None if not found.

    Args:
        lines: full text of the .txt datafile, split into lines.
        param_name: OSeMOSYS parameter name to locate.

    Returns:
        List of rows (each a list of whitespace-split tokens), or None if the block is
        missing.
    """
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
    """Overwrite `csv_path` with the rows of `param_name` parsed from `txt_lines`.

    Args:
        txt_lines: full text of the patched .txt datafile, split into lines.
        csv_path: otoole CSV file to overwrite; skipped (not created) if it does not exist.
        param_name: OSeMOSYS parameter name; must match `csv_path`'s header column count.

    Returns:
        True if the CSV was rewritten, False if it was skipped (missing CSV or missing
        parameter block in the .txt).

    Raises:
        RuntimeError: if a parsed row's width does not match the CSV header's column count.

    Side effects:
        Overwrites `csv_path` in place when the sync succeeds.
    """
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
    """Parse CLI args, sync each requested parameter's CSV, and print a summary.

    Returns:
        0 on completion (including partial syncs where individual params were skipped),
        1 if `--txt` or `--csv-folder` does not exist.
    """
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
