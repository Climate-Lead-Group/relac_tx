"""Careful reserve-margin repair with per-country-region firm capacity caps.

Library behind patch_reserve_margin_repair_careful_xlsx.py and patch_activity_upper_limit.py
(the blunt patch_reserve_margin_repair.py it derived from is no longer part of the
pipeline). It does not edit the input datafile in place. Also usable as its own CLI, with
fallbacks supplied via CSV/CLI assignments instead of an xlsx workbook, though that CLI is
not wired into the B2 chain (see patch_reserve_margin_repair_careful_xlsx.py for that).

Main differences from the blunt patcher it replaced:
- Reserve tags can still be added for PWRBCK and PWRCCS.
- TotalAnnualMaxCapacity (stock) and TotalAnnualMaxCapacityInvestment (flow)
  are patched independently.
- Firm fossil cap values come from per-country-region fallbacks.
- Only sentinel values are replaced by default: 0 and 9999.
- Suspicious stock/flow combinations are reported as warnings.

Inputs:
    <input_file> (positional arg, own CLI only): OSeMOSYS .txt datafile to read.
    --fallback-csv (own CLI only): CSV of CR plus stock/flow fallback columns.
Outputs:
    -o/--output (own CLI only): patched .txt datafile.
Usage:
    Library: imported by patch_reserve_margin_repair_careful_xlsx.py (tag/capacity patching
        functions) and by patch_activity_upper_limit.py (`find_param_block`, `fmt_number`).
    Own CLI: python scripts/pipeline/patch_reserve_margin_repair_careful.py <input> -o
        <output> [--fallback-csv <path>] [--stock-fallback CR=VALUE ...] [flags]
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path


STOCK_PARAM = "TotalAnnualMaxCapacity"
FLOW_PARAM = "TotalAnnualMaxCapacityInvestment"


@dataclass(frozen=True)
class CapFallback:
    """One firm-capacity fallback rule: a value for `parameter` scoped by prefix/CR/year.

    `prefix`, `cr` and `year` may be the literal wildcard "*", matched by `resolve_fallback`
    from most to least specific.
    """

    parameter: str
    prefix: str
    cr: str
    year: str
    value: float


def fmt_number(value: float) -> str:
    """Format `value` as an integer string when it is whole, else 12 significant digits."""
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.12g}"


def parse_float(value: str, label: str) -> float:
    """Parse `value` as a float, raising ValueError tagged with `label` on failure."""
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"Invalid numeric value for {label}: {value!r}") from exc


def find_param_block(lines: list[str], name: str) -> tuple[int, int]:
    """Return the (start, end) line indices of a `param ... <name> := ... ;` block.

    Args:
        lines: full text of the .txt datafile, split into lines.
        name: OSeMOSYS parameter name to locate (matched as a substring of the header).

    Returns:
        (start, end): header line index and the index of the terminating `;` line.

    Raises:
        ValueError: if the header or its terminating `;` is not found.
    """
    start = None
    pattern = re.compile(rf"^\s*param\b.*\b{name}\b.*:=\s*$")
    for idx, line in enumerate(lines):
        if pattern.match(line):
            start = idx
            break
    if start is None:
        raise ValueError(f"Could not find parameter block: {name}")

    for idx in range(start + 1, len(lines)):
        if lines[idx].strip() == ";":
            return start, idx
    raise ValueError(f"Could not find closing semicolon for parameter block: {name}")


def extract_simple_set(lines: list[str], name: str) -> list[str]:
    """Return the members of a `set <name> := ...;` block, in file order.

    Args:
        lines: full text of the .txt datafile, split into lines.
        name: GMPL set name to locate.

    Returns:
        List of whitespace-separated tokens found between `:=` and the terminating `;`;
        empty if the set is not found.
    """
    items: list[str] = []
    in_set = False
    pattern = re.compile(rf"^\s*set\s+{re.escape(name)}\s*:=")

    for line in lines:
        work = line.strip()
        if not in_set:
            if not pattern.match(work):
                continue
            work = work.split(":=", 1)[1].strip()
            in_set = True

        if in_set:
            done = ";" in work
            if done:
                work = work.split(";", 1)[0]
            items.extend(token for token in work.split() if token)
            if done:
                break

    return items


def select_years(lines: list[str]) -> list[str]:
    """Return the YEAR set members, falling back to regex-scanning 4-digit years (20xx)."""
    years = extract_simple_set(lines, "YEAR")
    if not years:
        years = sorted(set(re.findall(r"\b(20\d{2})\b", "\n".join(lines))), key=int)
    return years


def infer_items(lines: list[str], prefixes: list[str]) -> list[str]:
    """Return distinct tokens starting with any of `prefixes`, in first-seen order.

    Fallback used when the TECHNOLOGY set cannot be extracted directly (e.g. a stripped
    or partially patched datafile).
    """
    pattern = re.compile(r"\b(" + "|".join(re.escape(p) for p in prefixes) + r"\S*)\b")
    seen = set()
    items: list[str] = []
    for line in lines:
        for match in pattern.findall(line):
            if match not in seen:
                seen.add(match)
                items.append(match)
    return items


def select_techs(lines: list[str], prefixes: list[str]) -> list[str]:
    """Return TECHNOLOGY set members (or inferred tokens) matching any of `prefixes`."""
    technologies = extract_simple_set(lines, "TECHNOLOGY")
    if not technologies:
        technologies = infer_items(lines, prefixes)
    return [tech for tech in technologies if any(tech.startswith(prefix) for prefix in prefixes)]


def split_prefix_and_cr(technology: str, prefixes: list[str]) -> tuple[str, str] | None:
    """Split a tech code into (matched_prefix, country_region_suffix), or None if no match.

    Tries `prefixes` longest-first so a more specific prefix wins over a shorter one.
    """
    for prefix in sorted(prefixes, key=len, reverse=True):
        if technology.startswith(prefix) and len(technology) > len(prefix):
            return prefix, technology[len(prefix) :]
    return None


def parse_assignment_list(values: list[str], parameter: str) -> list[CapFallback]:
    """Parse `["CR=VALUE", ...]` CLI-style items into wildcard-prefix/year `CapFallback`s.

    Args:
        values: strings of the form "CR=VALUE".
        parameter: `CapFallback.parameter` to assign to every entry (STOCK_PARAM or
            FLOW_PARAM).

    Returns:
        One `CapFallback` per item, with prefix="*" and year="*".

    Raises:
        ValueError: if an item lacks "=" or has an empty CR.
    """
    fallbacks: list[CapFallback] = []
    for item in values:
        if "=" not in item:
            raise ValueError(f"Expected CR=VALUE for {parameter}, got {item!r}")
        cr, raw = item.split("=", 1)
        cr = cr.strip()
        if not cr:
            raise ValueError(f"Empty country-region in fallback item {item!r}")
        fallbacks.append(
            CapFallback(
                parameter=parameter,
                prefix="*",
                cr=cr,
                year="*",
                value=parse_float(raw.strip(), f"{parameter}:{cr}"),
            )
        )
    return fallbacks


def pick_column(row: dict[str, str], *candidates: str) -> str | None:
    """Return the first non-empty value among `candidates` column names (case-insensitive)."""
    lower_map = {key.lower(): key for key in row.keys()}
    for candidate in candidates:
        key = lower_map.get(candidate.lower())
        if key is not None:
            value = row.get(key)
            if value is not None and str(value).strip() != "":
                return str(value).strip()
    return None


def load_fallback_csv(path: Path) -> list[CapFallback]:
    """Read per-country-region firm-capacity fallbacks from a CSV.

    Args:
        path: CSV with a CR column (or COUNTRY_REGION/REGION_CODE/REGION) and optional
            TECH_PREFIX/YEAR columns, plus STOCK_PARAM/FLOW_PARAM-like value columns.

    Returns:
        List of `CapFallback` entries: a STOCK_PARAM entry when the row has a stock-like
        column, a FLOW_PARAM entry when it has a flow-like column; a row may yield both.

    Raises:
        ValueError: if a row is missing its CR value.
    """
    fallbacks: list[CapFallback] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row_number, row in enumerate(reader, start=2):
            cr = pick_column(row, "CR", "COUNTRY_REGION", "REGION_CODE", "REGION")
            if not cr:
                raise ValueError(f"{path}:{row_number}: missing CR column/value")
            prefix = pick_column(row, "TECH_PREFIX", "TECHNOLOGY_PREFIX", "PREFIX") or "*"
            year = pick_column(row, "YEAR") or "*"

            stock = pick_column(row, STOCK_PARAM, "STOCK", "MAX_CAPACITY", "TOTAL_CAPACITY")
            flow = pick_column(
                row,
                FLOW_PARAM,
                "FLOW",
                "MAX_INVESTMENT",
                "MAX_NEW_CAPACITY",
                "ANNUAL_INVESTMENT",
            )

            if stock is not None:
                fallbacks.append(
                    CapFallback(
                        parameter=STOCK_PARAM,
                        prefix=prefix,
                        cr=cr,
                        year=year,
                        value=parse_float(stock, f"{path}:{row_number}:{STOCK_PARAM}"),
                    )
                )
            if flow is not None:
                fallbacks.append(
                    CapFallback(
                        parameter=FLOW_PARAM,
                        prefix=prefix,
                        cr=cr,
                        year=year,
                        value=parse_float(flow, f"{path}:{row_number}:{FLOW_PARAM}"),
                    )
                )
    return fallbacks


def make_fallback_lookup(fallbacks: list[CapFallback]) -> dict[tuple[str, str, str, str], float]:
    """Index `fallbacks` by (parameter, prefix, cr, year) for `resolve_fallback`.

    Later entries with the same key overwrite earlier ones.
    """
    lookup: dict[tuple[str, str, str, str], float] = {}
    for fallback in fallbacks:
        key = (fallback.parameter, fallback.prefix, fallback.cr, fallback.year)
        lookup[key] = fallback.value
    return lookup


def resolve_fallback(
    lookup: dict[tuple[str, str, str, str], float],
    parameter: str,
    prefix: str,
    cr: str,
    year: str,
) -> float | None:
    """Resolve a fallback value for (parameter, prefix, cr, year), most specific first.

    Tries 8 candidate keys in order, from exact (parameter, prefix, cr, year) down to the
    fully wildcarded (parameter, "*", "*", "*"), wildcarding year before prefix before cr.

    Returns:
        The matched value, or None if no candidate key is in `lookup`.
    """
    candidates = [
        (parameter, prefix, cr, year),
        (parameter, prefix, cr, "*"),
        (parameter, "*", cr, year),
        (parameter, "*", cr, "*"),
        (parameter, prefix, "*", year),
        (parameter, prefix, "*", "*"),
        (parameter, "*", "*", year),
        (parameter, "*", "*", "*"),
    ]
    for key in candidates:
        if key in lookup:
            return lookup[key]
    return None


def is_sentinel(value: float, sentinels: list[float], tolerance: float = 1e-9) -> bool:
    """Return True if `value` matches any of `sentinels` within `tolerance`."""
    return any(abs(value - sentinel) <= tolerance for sentinel in sentinels)


def patch_reserve_tags(
    lines: list[str],
    targets: dict[tuple[str, str], float],
) -> tuple[list[str], int, int]:
    """Set ReserveMarginTagTechnology values for the given (tech, year) targets.

    Args:
        lines: full text of the .txt datafile, split into lines.
        targets: {(tech, year): tag_value} to write; typically built by `build_tag_targets`.

    Returns:
        (patched_lines, n_updated, n_inserted): existing rows are updated in place;
        targets with no existing row and a non-zero value get a new row appended to the
        block.

    Raises:
        ValueError: if `targets` is non-empty and the ReserveMarginTagTechnology block is
            not found (propagated from `find_param_block`).
    """
    if not targets:
        return lines, 0, 0

    start, end = find_param_block(lines, "ReserveMarginTagTechnology")
    row_pattern = re.compile(r"^(\s*GLOBAL\s+)(\S+)(\s+)(\d{4})(\s+)([-+0-9.eE]+)(\s*)$")
    seen: set[tuple[str, str]] = set()
    updated = 0
    patched = lines[:]

    for idx in range(start + 1, end):
        match = row_pattern.match(patched[idx])
        if not match:
            continue
        tech = match.group(2)
        year = match.group(4)
        key = (tech, year)
        if key not in targets:
            continue
        seen.add(key)
        new_value = fmt_number(targets[key])
        if match.group(6) != new_value:
            patched[idx] = (
                f"{match.group(1)}{tech}{match.group(3)}{year}"
                f"{match.group(5)}{new_value}{match.group(7)}"
            )
            updated += 1

    missing_lines = []
    for tech, year in sorted(targets, key=lambda item: (item[0], int(item[1]))):
        if (tech, year) in seen:
            continue
        value = targets[(tech, year)]
        if abs(value) < 1e-12:
            continue
        missing_lines.append(f"GLOBAL {tech} {year} {fmt_number(value)}\n")

    if missing_lines:
        patched = patched[:end] + missing_lines + patched[end:]

    return patched, updated, len(missing_lines)


def build_tag_targets(
    lines: list[str],
    years: list[str],
    backstop_credit: float | None,
    ccs_credit: float | None,
    backstop_prefixes: list[str],
    ccs_prefixes: list[str],
) -> tuple[dict[tuple[str, str], float], dict[str, int]]:
    """Build ReserveMarginTagTechnology targets for backstop/CCS techs across all years.

    Args:
        lines: full text of the .txt datafile, split into lines.
        years: years to set a tag value for, for every matched tech.
        backstop_credit: tag value for techs matching `backstop_prefixes`; None to skip.
        ccs_credit: tag value for techs matching `ccs_prefixes`; None to skip.
        backstop_prefixes: tech-name prefixes selecting the backstop (e.g. PWRBCK) family.
        ccs_prefixes: tech-name prefixes selecting the CCS (e.g. PWRCCS) family.

    Returns:
        (targets, counts): `targets` is {(tech, year): credit}; `counts` reports
        "backstop_techs"/"ccs_techs" tech counts (only for the credits that were set).
    """
    targets: dict[tuple[str, str], float] = {}
    counts: dict[str, int] = {}

    if backstop_credit is not None:
        techs = select_techs(lines, backstop_prefixes)
        counts["backstop_techs"] = len(techs)
        for tech in techs:
            for year in years:
                targets[(tech, year)] = backstop_credit

    if ccs_credit is not None:
        techs = select_techs(lines, ccs_prefixes)
        counts["ccs_techs"] = len(techs)
        for tech in techs:
            for year in years:
                targets[(tech, year)] = ccs_credit

    return targets, counts


def read_param_values(
    lines: list[str],
    parameter: str,
    target_prefixes: list[str],
) -> dict[tuple[str, str], float]:
    """Read {(tech, year): value} for `parameter` rows whose tech matches `target_prefixes`.

    Args:
        lines: full text of the .txt datafile, split into lines.
        parameter: OSeMOSYS parameter name to read (a `GLOBAL <tech> <year> <value>` block).
        target_prefixes: tech-name prefixes to keep (via `split_prefix_and_cr`).

    Returns:
        {(tech, year): value} for matching rows.
    """
    values: dict[tuple[str, str], float] = {}
    start, end = find_param_block(lines, parameter)
    row_pattern = re.compile(r"^\s*GLOBAL\s+(\S+)\s+(\d{4})\s+([-+0-9.eE]+)\s*$")
    for line in lines[start + 1 : end]:
        match = row_pattern.match(line)
        if not match:
            continue
        tech = match.group(1)
        if split_prefix_and_cr(tech, target_prefixes) is None:
            continue
        values[(tech, match.group(2))] = float(match.group(3))
    return values


def capacity_floors(
    lines: list[str],
    target_prefixes: list[str],
) -> tuple[dict[tuple[str, str], float], dict[tuple[str, str], float]]:
    """Compute minimum-allowed stock/flow caps per (tech, year), from existing minima.

    Args:
        lines: full text of the .txt datafile, split into lines.
        target_prefixes: tech-name prefixes to consider.

    Returns:
        (stock_floors, flow_floors): stock_floors[(tech, year)] =
        max(TotalAnnualMinCapacity, ResidualCapacity + TotalAnnualMinCapacityInvestment);
        flow_floors[(tech, year)] = TotalAnnualMinCapacityInvestment. Used by
        `patch_capacity_param` to never write a fallback below an existing minimum.
    """
    residual = read_param_values(lines, "ResidualCapacity", target_prefixes)
    min_stock = read_param_values(lines, "TotalAnnualMinCapacity", target_prefixes)
    min_flow = read_param_values(lines, "TotalAnnualMinCapacityInvestment", target_prefixes)

    stock_floors: dict[tuple[str, str], float] = {}
    flow_floors: dict[tuple[str, str], float] = {}
    keys = set(residual) | set(min_stock) | set(min_flow)
    for key in keys:
        residual_value = residual.get(key, 0.0)
        min_stock_value = min_stock.get(key, 0.0)
        min_flow_value = min_flow.get(key, 0.0)
        stock_floors[key] = max(min_stock_value, residual_value + min_flow_value)
        flow_floors[key] = min_flow_value
    return stock_floors, flow_floors


def techs_with_any_min_investment(
    lines: list[str],
    target_prefixes: list[str],
) -> set[str]:
    """Return techs (matching `target_prefixes`) with a nonzero min-investment in any year.

    Used by `patch_capacity_param` to skip replacing FLOW_PARAM sentinels for techs that
    have a forced minimum investment somewhere in the horizon.
    """
    min_flow = read_param_values(lines, "TotalAnnualMinCapacityInvestment", target_prefixes)
    return {
        tech
        for (tech, _year), value in min_flow.items()
        if value > 1e-12
    }


def patch_capacity_param(
    lines: list[str],
    parameter: str,
    target_prefixes: list[str],
    sentinels: list[float],
    lookup: dict[tuple[str, str, str, str], float],
    floors: dict[tuple[str, str], float] | None = None,
    skip_techs: set[str] | None = None,
    modify_from_year: int | None = None,
) -> tuple[list[str], int, int, list[str]]:
    """Replace sentinel values of a capacity parameter with resolved fallbacks.

    For each `GLOBAL <tech> <year> <value>` row of `parameter` whose tech matches
    `target_prefixes`: skips years before `modify_from_year` (left untouched, e.g.
    historical years); skips non-sentinel values; skips (with a warning) techs in
    `skip_techs`; otherwise resolves a fallback via `resolve_fallback`, raises it to
    `floors[(tech, year)]` if lower (with a warning), and writes it in place.

    Args:
        lines: full text of the .txt datafile, split into lines.
        parameter: capacity parameter to patch (STOCK_PARAM or FLOW_PARAM).
        target_prefixes: tech-name prefixes to consider.
        sentinels: values eligible for replacement (e.g. [0.0, 9999.0]).
        lookup: fallback table from `make_fallback_lookup`.
        floors: {(tech, year): minimum allowed value}, from `capacity_floors`; default 0.0.
        skip_techs: techs to leave untouched regardless of sentinel status (with a warning).
        modify_from_year: if set, years before this are never modified.

    Returns:
        (patched_lines, n_changed, n_skipped, warnings).

    Raises:
        ValueError: if the `parameter` block is not found (propagated from
            `find_param_block`).
    """
    patched = lines[:]
    floors = floors or {}
    skip_techs = skip_techs or set()
    start, end = find_param_block(patched, parameter)
    row_pattern = re.compile(r"^(\s*GLOBAL\s+)(\S+)(\s+)(\d{4})(\s+)([-+0-9.eE]+)(\s*)$")
    changed = 0
    skipped = 0
    warnings: list[str] = []

    for idx in range(start + 1, end):
        match = row_pattern.match(patched[idx])
        if not match:
            continue

        tech = match.group(2)
        split = split_prefix_and_cr(tech, target_prefixes)
        if split is None:
            continue
        prefix, cr = split
        year = match.group(4)
        # Year cutoff: leave historical/observed years untouched. Cells before
        # modify_from_year keep exactly what the upstream produced, so the
        # reserve-margin fallback does not introduce a 2023-2025 divergence
        # across scenarios. Mirrors A3's MODIFY_FROM_YEAR=2026 convention.
        if modify_from_year is not None and int(year) < modify_from_year:
            continue
        current = float(match.group(6))
        if not is_sentinel(current, sentinels):
            continue

        if tech in skip_techs:
            skipped += 1
            warnings.append(
                f"{parameter}: skipped {tech} {year}; tech has nonzero "
                "TotalAnnualMinCapacityInvestment in at least one model year."
            )
            continue

        replacement = resolve_fallback(lookup, parameter, prefix, cr, year)
        if replacement is None:
            skipped += 1
            warnings.append(
                f"{parameter}: skipped {tech} {year}; current={fmt_number(current)} "
                f"is sentinel but no fallback was provided for CR={cr}, prefix={prefix}."
            )
            continue

        floor = floors.get((tech, year), 0.0)
        if replacement < floor:
            warnings.append(
                f"{parameter}: raised fallback for {tech} {year} from "
                f"{fmt_number(replacement)} to {fmt_number(floor)} to respect existing minima."
            )
            replacement = floor

        replacement_text = fmt_number(replacement)
        if replacement_text != match.group(6):
            patched[idx] = (
                f"{match.group(1)}{tech}{match.group(3)}{year}"
                f"{match.group(5)}{replacement_text}{match.group(7)}"
            )
            changed += 1

    return patched, changed, skipped, warnings


def stock_flow_warnings(
    lines: list[str],
    target_prefixes: list[str],
) -> list[str]:
    """Report suspicious stock/flow combinations for `target_prefixes` techs, as warnings.

    Flags, per (tech, year): stock=0 with flow>0 ("Inconsistent cap"), stock>0 with flow=0
    ("Investment blocked"), and stock>0 with flow>stock ("Stock likely binds flow").
    """
    stock = read_param_values(lines, STOCK_PARAM, target_prefixes)
    flow = read_param_values(lines, FLOW_PARAM, target_prefixes)
    warnings: list[str] = []

    for key in sorted(set(stock) | set(flow), key=lambda item: (item[0], int(item[1]))):
        tech, year = key
        stock_value = stock.get(key)
        flow_value = flow.get(key)
        if stock_value is None or flow_value is None:
            continue
        if abs(stock_value) <= 1e-12 and flow_value > 1e-12:
            warnings.append(
                f"Inconsistent cap: {tech} {year} has {STOCK_PARAM}=0 "
                f"but {FLOW_PARAM}={fmt_number(flow_value)}."
            )
        elif stock_value > 1e-12 and abs(flow_value) <= 1e-12:
            warnings.append(
                f"Investment blocked: {tech} {year} has {STOCK_PARAM}={fmt_number(stock_value)} "
                f"but {FLOW_PARAM}=0."
            )
        elif stock_value > 1e-12 and flow_value > stock_value:
            warnings.append(
                f"Stock likely binds flow: {tech} {year} has {STOCK_PARAM}={fmt_number(stock_value)} "
                f"below {FLOW_PARAM}={fmt_number(flow_value)}."
            )
    return warnings


def parse_args() -> argparse.Namespace:
    """Parse and return this module's own CLI arguments (see module docstring for `Usage`)."""
    parser = argparse.ArgumentParser(
        description=(
            "Patch reserve tags and carefully replace sentinel firm-capacity caps "
            "using per-country-region fallbacks."
        )
    )
    parser.add_argument("input_file", help="Input OSeMOSYS datafile.")
    parser.add_argument("-o", "--output", required=True, help="Patched output datafile.")

    parser.add_argument("--backstop-credit", type=float, default=1.0)
    parser.add_argument("--ccs-credit", type=float, default=0.9)
    parser.add_argument("--skip-backstop-credit", action="store_true")
    parser.add_argument("--skip-ccs-credit", action="store_true")
    parser.add_argument("--backstop-prefixes", nargs="+", default=["PWRBCK"])
    parser.add_argument("--ccs-prefixes", nargs="+", default=["PWRCCS"])

    parser.add_argument("--target-prefixes", nargs="+", default=["PWRPET", "PWROIL", "PWRNGS"])
    parser.add_argument(
        "--sentinel-values",
        nargs="+",
        type=float,
        default=[0.0, 9999.0],
        help="Only these existing cap values are replaced.",
    )
    parser.add_argument(
        "--fallback-csv",
        help=(
            "CSV with CR plus stock/flow fallback columns. Optional columns: "
            "TECH_PREFIX and YEAR."
        ),
    )
    parser.add_argument(
        "--stock-fallback",
        nargs="*",
        default=[],
        metavar="CR=VALUE",
        help=f"Per-CR fallback for {STOCK_PARAM}.",
    )
    parser.add_argument(
        "--flow-fallback",
        nargs="*",
        default=[],
        metavar="CR=VALUE",
        help=f"Per-CR fallback for {FLOW_PARAM}.",
    )
    parser.add_argument("--default-stock-fallback", type=float)
    parser.add_argument("--default-flow-fallback", type=float)
    parser.add_argument(
        "--modify-from-year",
        type=int,
        default=None,
        help="If set, only sentinel cap cells in years >= this value are "
             "replaced; earlier (historical) years are left untouched.",
    )
    parser.add_argument(
        "--warnings-file",
        help="Optional file to write warnings to. Warnings are always printed to stderr.",
    )
    return parser.parse_args()


def main() -> int:
    """Parse CLI args, apply the reserve-tag/capacity patch, and write the output.

    Side effects:
        Writes `--output` (patched datafile) and, if warnings occurred and
        `--warnings-file` is given, a text file of those warnings; prints a run summary to
        stdout and warnings to stderr.
    """
    args = parse_args()
    input_path = Path(args.input_file)
    output_path = Path(args.output)

    lines = input_path.read_text(encoding="utf-8").splitlines(keepends=True)
    years = select_years(lines)

    backstop_credit = None if args.skip_backstop_credit else args.backstop_credit
    ccs_credit = None if args.skip_ccs_credit else args.ccs_credit
    tag_targets, tag_counts = build_tag_targets(
        lines,
        years,
        backstop_credit,
        ccs_credit,
        args.backstop_prefixes,
        args.ccs_prefixes,
    )

    fallbacks: list[CapFallback] = []
    if args.fallback_csv:
        fallbacks.extend(load_fallback_csv(Path(args.fallback_csv)))
    fallbacks.extend(parse_assignment_list(args.stock_fallback, STOCK_PARAM))
    fallbacks.extend(parse_assignment_list(args.flow_fallback, FLOW_PARAM))
    if args.default_stock_fallback is not None:
        fallbacks.append(
            CapFallback(STOCK_PARAM, "*", "*", "*", args.default_stock_fallback)
        )
    if args.default_flow_fallback is not None:
        fallbacks.append(
            CapFallback(FLOW_PARAM, "*", "*", "*", args.default_flow_fallback)
        )

    fallback_lookup = make_fallback_lookup(fallbacks)

    patched, tag_updates, tag_inserts = patch_reserve_tags(lines, tag_targets)
    stock_floors, flow_floors = capacity_floors(patched, args.target_prefixes)
    min_investment_techs = techs_with_any_min_investment(patched, args.target_prefixes)

    patched, stock_changed, stock_skipped, stock_warnings = patch_capacity_param(
        patched,
        STOCK_PARAM,
        args.target_prefixes,
        [0.0],
        fallback_lookup,
        stock_floors,
        modify_from_year=args.modify_from_year,
    )
    patched, flow_changed, flow_skipped, flow_warnings = patch_capacity_param(
        patched,
        FLOW_PARAM,
        args.target_prefixes,
        args.sentinel_values,
        fallback_lookup,
        flow_floors,
        min_investment_techs,
        modify_from_year=args.modify_from_year,
    )
    consistency_warnings = stock_flow_warnings(patched, args.target_prefixes)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(patched), encoding="utf-8")

    warnings = stock_warnings + flow_warnings + consistency_warnings
    if warnings:
        for warning in warnings:
            print(f"[WARN] {warning}", file=sys.stderr)
        if args.warnings_file:
            Path(args.warnings_file).write_text(
                "\n".join(warnings) + "\n",
                encoding="utf-8",
            )

    print(f"Wrote patched datafile: {output_path}")
    print(f"Years patched for reserve tags: {len(years)} ({years[0]}-{years[-1]})")
    if backstop_credit is not None:
        print(
            "Backstop reserve tag: "
            f"{tag_counts.get('backstop_techs', 0)} techs at {fmt_number(backstop_credit)}"
        )
    if ccs_credit is not None:
        print(f"CCS reserve tag: {tag_counts.get('ccs_techs', 0)} techs at {fmt_number(ccs_credit)}")
    print(f"ReserveMarginTagTechnology rows updated: {tag_updates}")
    print(f"ReserveMarginTagTechnology rows inserted: {tag_inserts}")
    print(f"{STOCK_PARAM} sentinel rows changed: {stock_changed}")
    print(f"{STOCK_PARAM} sentinel rows skipped: {stock_skipped}")
    print(f"{FLOW_PARAM} sentinel rows changed: {flow_changed}")
    print(f"{FLOW_PARAM} sentinel rows skipped: {flow_skipped}")
    print(f"Warnings: {len(warnings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
