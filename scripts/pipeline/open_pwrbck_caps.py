# -*- coding: utf-8 -*-
"""Open TotalAnnualMaxCapacity(Investment) caps for PWRBCK* backstop technologies.

Diagnostic, non-destructive patcher for OSTRAM. PWRBCK* are high-cost backstop generators
(VariableCost ~278, vs ~1.4 for real fossil techs) meant to absorb feasibility edge cases, but
the upstream A-O parametrization hardcaps both TotalAnnualMaxCapacity and
TotalAnnualMaxCapacityInvestment at 0 for every PWRBCK*-region-year cell, stripping out that
safety net: when the optimizer needs a backstop in a (region, year, timeslice) the legitimate
generation chain can't satisfy, the LP becomes infeasible. Opening these caps does NOT cause
phantom PWRBCK investment, because the cost penalty (~200x real fossil) keeps them out of
cost-optimal solutions except where the LP is forced to use them. Reads the source file and
writes a sibling output; never mutates the source.

Inputs:
    <input_file> (positional arg): preprocessed OSeMOSYS .txt datafile to read.
Outputs:
    -o/--output: sibling .txt datafile with matching zero-valued cap rows opened.
Usage:
    python scripts/pipeline/open_pwrbck_caps.py <input_file> -o <output_file>
    python scripts/pipeline/open_pwrbck_caps.py <input_file> -o <output_file> --value 9999
    python scripts/pipeline/open_pwrbck_caps.py <input_file> -o <output_file>
        --pattern PWRBCK --value 9999
Notes:
    - Called by B2_Executing_OG_Model.py when `open_pwrbck_active` is set in
      Config_MOMF_T1_AB.yaml (output suffix `OpenBCK`, per `open_pwrbck_suffix`).
"""

import argparse
import os
import sys


# Default config -----------------------------------------------------------
DEFAULT_PATTERN = 'PWRBCK'
DEFAULT_VALUE   = '9999'
DEFAULT_BLOCKS  = ['TotalAnnualMaxCapacity', 'TotalAnnualMaxCapacityInvestment']


def find_block_range(lines, block_name):
    """
    Locate the start (param header) and end (terminating ';') line indices
    of a `param default <X> : <block_name> :=` block in `lines`.
    Returns (start_idx, end_idx) inclusive, or (None, None) if not found.
    """
    header_token = f': {block_name} :='
    start = None
    for i, line in enumerate(lines):
        # The block header must start with 'param default'; the colon-token
        # match avoids accidental hits on parameter names with shared prefixes
        # (e.g. TotalAnnualMaxCapacity vs TotalAnnualMaxCapacityInvestment).
        if line.lstrip().startswith('param default') and header_token in line:
            start = i
            break
    if start is None:
        return None, None
    # Find first line after the header that starts with ';' (block terminator).
    for j in range(start + 1, len(lines)):
        if lines[j].lstrip().startswith(';'):
            return start, j
    return start, None  # malformed block (no terminator)


def patch_block(lines, start, end, pattern, new_value):
    """
    Within lines[start+1 .. end-1], find rows of the form
        REGION TECH YEAR VALUE
    where TECH contains `pattern` and VALUE == 0, and rewrite VALUE to
    `new_value` while preserving the original line ending.
    Returns (n_changed, skipped_nonzero) where skipped_nonzero is a list
    of (tech, year, value) tuples for matched rows that were NOT zero
    (left untouched, defensive: never overwrite a non-zero entry).
    """
    n_changed = 0
    skipped_nonzero = []
    for k in range(start + 1, end):
        line = lines[k]
        # Capture the line ending so we can restore it verbatim
        body = line.rstrip('\r\n')
        eol  = line[len(body):]
        parts = body.split()
        # Expected row format: REGION TECH YEAR VALUE  (4 whitespace-sep tokens)
        if len(parts) != 4:
            continue
        if pattern not in parts[1]:
            continue
        # Numeric value comparison - 0, 0.0, -0.0 all count as zero
        try:
            val = float(parts[3])
        except ValueError:
            continue
        if val == 0.0:
            new_body = ' '.join(parts[:3] + [str(new_value)])
            lines[k] = new_body + eol
            n_changed += 1
        else:
            skipped_nonzero.append((parts[1], parts[2], parts[3]))
    return n_changed, skipped_nonzero


def main():
    """Parse CLI args, open matching zero-valued cap rows, and write the sibling output.

    Side effects:
        Reads `input_file`, creates the output directory if needed, and writes `--output`
        as a new sibling .txt file (source untouched); prints per-block change counts and
        any rows skipped because they were already non-zero.
    """
    parser = argparse.ArgumentParser(
        description='Open PWRBCK* (or other matching) cap rows in '
                    'TotalAnnualMaxCapacity and TotalAnnualMaxCapacityInvestment '
                    'parameter blocks. Diagnostic, non-destructive sibling-output patcher.'
    )
    parser.add_argument('input_file',
                        help='Path to preprocessed datafile to read from.')
    parser.add_argument('-o', '--output', required=True,
                        help='Path to write the patched sibling datafile.')
    parser.add_argument('--pattern', default=DEFAULT_PATTERN,
                        help=f'Substring that must appear in the TECH token '
                             f'for a row to be patched. Default: {DEFAULT_PATTERN}.')
    parser.add_argument('--value', default=DEFAULT_VALUE,
                        help=f'Replacement value for cells currently 0. '
                             f'Default: {DEFAULT_VALUE} (matches TRN* sentinel convention).')
    parser.add_argument('--blocks', nargs='+', default=DEFAULT_BLOCKS,
                        help=f'Parameter block names to patch. Default: {DEFAULT_BLOCKS}.')
    args = parser.parse_args()

    if not os.path.exists(args.input_file):
        print(f'ERROR: input file not found: {args.input_file}', file=sys.stderr)
        sys.exit(1)

    # Read with binary mode and decode so we can preserve original line endings
    # (the OSTRAM datafile is CRLF on Windows; splitlines(keepends=True)
    #  preserves whatever the source uses).
    with open(args.input_file, 'rb') as f:
        raw = f.read()
    text = raw.decode('utf-8')
    lines = text.splitlines(keepends=True)

    print(f'open_pwrbck_caps: reading {args.input_file}')
    print(f'  pattern         = {args.pattern!r}')
    print(f'  replacement     = {args.value}')
    print(f'  blocks targeted = {args.blocks}')

    total_changed = 0
    for block_name in args.blocks:
        start, end = find_block_range(lines, block_name)
        if start is None:
            print(f'  [WARN] block not found: {block_name}')
            continue
        if end is None:
            print(f'  [ERROR] block {block_name} has no terminating semicolon; skipped')
            continue
        n, skipped = patch_block(lines, start, end, args.pattern, args.value)
        total_changed += n
        print(f'  {block_name}: {n} rows opened '
              f'(block lines {start + 1}..{end + 1})')
        if skipped:
            print(f'    note: {len(skipped)} {args.pattern}* rows had non-zero values, '
                  f'left untouched (defensive)')
            for tech, year, val in skipped[:3]:
                print(f'      {tech} {year} {val}')
            if len(skipped) > 3:
                print(f'      ... ({len(skipped) - 3} more)')

    out_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.output, 'wb') as f:
        f.write(''.join(lines).encode('utf-8'))

    print(f'  total rows changed = {total_changed}')
    print(f'  wrote {args.output}')


if __name__ == '__main__':
    main()
