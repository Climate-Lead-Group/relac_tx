"""Patch the DaysInDayType block of a preprocessed OSeMOSYS .txt datafile in place.

The B1 -> otoole -> preprocess chain never generates DaysInDayType, so the .txt ships with
an empty block and OSeMOSYS falls back to default=7. With 4 seasons x 1 daytype this makes
storage equations see 4 * 7 = 28 days/year, while energy-balance equations correctly see
365 days (via YearSplit), an unbounded-LP mismatch that surfaces downstream as
infeasibility on storage intraday balance rows. Using the OSeMOSYS identity
YearSplit[ts, y] = DaysInDayType[ls, ld, y] * DaySplit[lh, y] / 365, this script sums
YearSplit per (season, year), computes DaysInDayType[season, 1, year] = round(weight * 365)
and replaces the (probably empty) block. Idempotent; safe to re-run on an already-patched
file.

Inputs:
    <path/to/Pre_processed_X_0.txt> (positional arg): target OSeMOSYS .txt, read for its
        YearSplit and DAYTYPE blocks.
Outputs:
    Same .txt file, DaysInDayType block replaced in place.
Usage:
    python scripts/pipeline/inject_DaysInDayType.py <path/to/Pre_processed_X_0.txt>
Notes:
    - Assumes a single DAYTYPE (DAYTYPE = {1}); warns at runtime if more are found (the
      patcher hard-codes daytype=1 regardless).
    - Timeslice tags follow S{season}D{dailytimebracket}; the 'D' suffix encodes the daily
      time bracket, not the daytype.
    - Called by B2_Executing_OG_Model.py always, right after preprocess_data.py.
"""
import sys
import re
from pathlib import Path
from collections import defaultdict


def inject(path: Path) -> None:
    """Compute and write the DaysInDayType block for `path`, in place.

    Args:
        path: path to the OSeMOSYS .txt datafile to patch.

    Raises:
        SystemExit: if the YearSplit or DaysInDayType block is missing from the file, or
            if no timeslices could be parsed from the YearSplit block.

    Side effects:
        Overwrites `path` with the DaysInDayType block replaced; prints a summary,
        including a sanity check that per-season days sum to 365 for the first year found.
    """
    text = path.read_text(encoding='utf-8')

    # 1. Locate YearSplit block
    ys_match = re.search(
        r'param default \S+ : YearSplit :=\s*(.*?);',
        text,
        re.DOTALL,
    )
    if not ys_match:
        raise SystemExit(f"YearSplit block not found in {path}")

    # 2. Locate DAYTYPE set and warn if assumption breaks
    dt_match = re.search(r'set DAYTYPE :=\s*(.*?);', text, re.DOTALL)
    daytypes = [t for t in dt_match.group(1).split() if t] if dt_match else []
    if len(daytypes) != 1:
        print(f"  WARNING: expected 1 daytype, found {len(daytypes)}: {daytypes}")
        print(f"  This patcher hard-codes daytype=1; revisit if multi-daytype.")

    # 3. Sum YearSplit per (season, year)
    season_year_total = defaultdict(float)
    for line in ys_match.group(1).splitlines():
        parts = line.strip().split()
        if len(parts) != 3:
            continue
        ts, year_s, val_s = parts
        m = re.match(r'S(\d+)D\d+', ts)
        if not m:
            continue
        season = int(m.group(1))
        season_year_total[(season, int(year_s))] += float(val_s)

    if not season_year_total:
        raise SystemExit("No timeslices parsed from YearSplit. Aborting.")

    # 4. Build DaysInDayType rows: <season> <daytype=1> <year> <days>
    new_rows = []
    for (season, year), total in sorted(season_year_total.items()):
        days = round(total * 365)
        new_rows.append(f"{season} 1 {year} {days}")

    # 5. Replace DaysInDayType block (idempotent: matches whether populated or empty)
    new_block = (
        "param default 7 : DaysInDayType :=\n"
        + "\n".join(new_rows)
        + "\n;"
    )
    new_text, n = re.subn(
        r'param default \S+ : DaysInDayType :=.*?;',
        new_block,
        text,
        count=1,
        flags=re.DOTALL,
    )
    if n == 0:
        raise SystemExit("DaysInDayType block not found in file. Aborting.")

    path.write_text(new_text, encoding='utf-8')

    # 6. Summary print
    print(f"Injected {len(new_rows)} DaysInDayType rows into {path.name}")
    years = sorted({y for (_, y) in season_year_total})
    if years:
        y = years[0]
        seasons = sorted({s for (s, yy) in season_year_total if yy == y})
        print(f"  Per-season days for year {y} (sanity check):")
        total = 0
        for s in seasons:
            ys_total = season_year_total[(s, y)]
            d = round(ys_total * 365)
            total += d
            print(f"    Season {s}: YearSplit total = {ys_total:.6f}  ->  {d} days")
        flag = "OK" if total == 365 else "!!! does not sum to 365 !!!"
        print(f"    TOTAL   : {total} days  [{flag}]")


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python inject_DaysInDayType.py <preprocessed_file.txt>")
        sys.exit(1)
    target = Path(sys.argv[1])
    if not target.exists():
        raise SystemExit(f"File not found: {target}")
    inject(target)


if __name__ == '__main__':
    main()
