"""Shared read-only IO/parsing library for the dispatch-floor fix (fix_dispatch chain).

Library module imported by six scripts in this folder: feasibility.py,
make_candidates.py, write_floors.py, validate_constraints.py, floor_effect.py,
fig_floor_effect.py. Authoritative sources, per the revised division of labor:
  - Activity limits (LowerLimit / UpperLimit) + forced builds (MinCapacityInvestment)
      -> parsed directly from the per-scenario preprocessed GLPK/MathProg txt
         outputs/Executables/<SCEN>_0/
             Pre_processed_<SCEN>_0_StorageDelayN5_OpenBCK_RMCarefulXLSX*.txt
  - Other inputs (ResidualCapacity, CapacityToActivityUnit, CapitalCost, FixedCost,
      VariableCost, OperationalLife, Input/Output/EmissionActivityRatio, demand)
      -> A2 otoole per-scenario CSVs  outputs/A2_Outputs_Params_otoole/<SCEN>/*.csv
  - Model outputs (TotalCapacityAnnual, TotalTechnologyAnnualActivity, production, CF...)
      -> the combined inputs+outputs CSV in outputs/.

Inputs:
    outputs/Executables/<SCEN>_0/Pre_processed_<SCEN>_0_..._*.txt (preprocessed MathProg)
    outputs/A2_Outputs_Params_otoole/<SCEN>/*.csv (A2 otoole per-scenario CSVs)
    outputs/RELAC_TX*Combined_Inputs_Outputs*.csv (combined inputs+outputs CSV)
Outputs:
    outputs/fix_dispatch/cache/*.parquet (parquet cache of extract_combined() only)
Usage:
    import relac_io as io   # from any script in this folder
Notes:
    - Nothing here writes to any live input; the only writes are the parquet caches.
    - CapacityToActivityUnit default (C2A_DEFAULT) is 31.536 (GW-yr -> PJ).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> scripts/
from common import relac_paths as P

import pandas as pd

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
EXECUTABLES = P.EXECUTABLES
OTOOLE = P.A2_OTOOLE
CACHE = P.FIX_DISPATCH_OUT / "cache"
CACHE.mkdir(parents=True, exist_ok=True)

SCENARIOS = ["BAU", "INV", "OPT", "VGB"]

# Model horizon / conventions
FIRST_YEAR = 2023
LAST_YEAR = 2050
SYMMETRY_YEARS = [2023, 2024, 2025, 2026]  # scenarios must be identical here
C2A_DEFAULT = 31.536                       # CapacityToActivityUnit, GW-yr -> PJ

# Technology fuel-code classification
FOSSIL_CODES = {"COA", "GAS", "NGS", "OIL", "PET", "COG"}
NUCLEAR_CODES = {"URN"}
RENEWABLE_CODES = {"SPV", "WON", "WOF", "HYD", "BIO", "GEO", "CSP", "WAV"}
STORAGE_CODES = {"LDS", "SDS"}

# Fuels that receive a dispatch floor: fossil combustion techs only. Nuclear
# (URN) is deliberately excluded -- it is dispatched freely on economics
# (PI decision, 2026-07-03). GAS/COG are listed for completeness; the current
# model has zero techs on those two fuel codes.
FLOOR_FUELS = {"COA", "NGS", "OIL", "PET", "GAS", "COG"}

COUNTRIES = ["ARG", "BOL", "BRA", "BRB", "CHL", "COL", "CRI", "DOM", "ECU",
             "GTM", "HND", "HTI", "MEX", "NIC", "PAN", "PER", "PRY", "SLV", "URY"]

# DEPRECATED (2026-07-03): superseded by nonren_floor_techs(scenario), which
# floors the full fossil fleet instead of this 11-tech hand-picked subset.
# WORKING_SET undercounted the fleet: techs with a legacy 2023-2026 floor
# (e.g. BRA/MEX/ARG gas) were excluded from this list precisely because they
# already had a floor -- but that floor stops at 2026, so the entire residual
# fleet behind those legacy floors went unfloored from 2027 on. Kept here only
# so any script that still imports it does not break; do not add new uses.
WORKING_SET = [
    "PWRNGSMEXXX", "PWRPETECUXX", "PWRNGSPERXX", "PWRNGSPANXX", "PWRNGSSLVXX",
    "PWROILCRIXX", "PWRNGSGTMXX", "PWRNGSDOMXX", "PWROILHNDXX", "PWROILSLVXX",
    "PWRPETBRBXX",
]


# --------------------------------------------------------------------------- #
# Technology name parsing (see CLAUDE.md "Technology naming")
# --------------------------------------------------------------------------- #
def parse_tech(tech: str) -> dict:
    """Classify a technology code by its OSeMOSYS naming convention.

    kind is one of {plant, tx, interconnector, other}. For plants (PWR+fuel(3)+
    country(3)+suffix): fuel=t[3:6], country=t[6:9]. For interconnectors
    (TRN+C1(3)+XX+C2(3)+XX): country=C1=t[3:6], country2=C2=t[8:11]. Domestic Tx
    prefixes (PWRTRN/RNWTRN/TRNNLI/RNWNLI/TRNRPO/RNWRPO) carry a country at
    t[6:9] but no combustion fuel.

    Args:
        tech: technology code, e.g. "PWRNGSMEXXX".

    Returns:
        dict with keys kind, fuel, country, country2, is_fossil, is_renewable,
        is_nuclear, is_storage.
    """
    t = str(tech)
    out = {"kind": "other", "fuel": None, "country": None, "country2": None,
           "is_fossil": False, "is_renewable": False, "is_nuclear": False,
           "is_storage": False}
    tx_prefixes = ("PWRTRN", "RNWTRN", "TRNNLI", "RNWNLI", "TRNRPO", "RNWRPO")
    if t.startswith("PWR") and len(t) >= 9 and not t.startswith(tx_prefixes):
        fuel = t[3:6]
        out.update(kind="plant", fuel=fuel, country=t[6:9])
        out["is_fossil"] = fuel in FOSSIL_CODES
        out["is_renewable"] = fuel in RENEWABLE_CODES
        out["is_nuclear"] = fuel in NUCLEAR_CODES
        out["is_storage"] = fuel in STORAGE_CODES
    elif t.startswith(tx_prefixes) and len(t) >= 9:
        out.update(kind="tx", country=t[6:9])
    elif t.startswith("TRN") and len(t) >= 11:
        out.update(kind="interconnector", country=t[3:6], country2=t[8:11])
    return out


def tech_country(tech: str) -> str | None:
    """Return the 3-letter country code parsed from tech, or None (see parse_tech)."""
    return parse_tech(tech)["country"]


def tech_fuel(tech: str) -> str | None:
    """Return the 3-letter fuel code parsed from tech, or None (see parse_tech)."""
    return parse_tech(tech)["fuel"]


# --------------------------------------------------------------------------- #
# MathProg (.txt) parameter parsing  -- AUTHORITATIVE for limits + forced builds
# --------------------------------------------------------------------------- #
_PARAM_DECL = re.compile(r"^\s*param\s+default\s+(\S+)\s*:\s*(\w+)\s*:=\s*$")


def executable_txt(scenario: str) -> Path:
    """Locate the ORIGINAL preprocessed txt for the canonical
    StorageDelayN5_OpenBCK_RMCarefulXLSX build. Excludes the *.warnings.txt log
    and *_FLOORED.txt copies so that once write_floors.py drops a floored copy
    next to the original, every reader (feasibility, validators, write_floors
    itself on a re-run) still resolves to the true original and never
    floors-on-top-of-floors.

    Args:
        scenario: one of io.SCENARIOS (e.g. "BAU").

    Returns:
        Path to the matching Pre_processed_<SCEN>_0_...txt file.

    Raises:
        FileNotFoundError: if no matching txt exists for the scenario.
    """
    folder = EXECUTABLES / f"{scenario}_0"
    matches = sorted(
        p for p in folder.glob(
            f"Pre_processed_{scenario}_0_StorageDelayN5_OpenBCK_RMCarefulXLSX*.txt")
        if not p.name.endswith(".warnings.txt")
        and "_FLOORED" not in p.name
    )
    if not matches:
        raise FileNotFoundError(f"No preprocessed txt for scenario {scenario} in {folder}")
    return matches[0]


def floored_txt(scenario: str) -> Path:
    """Return the path where write_floors.py writes the floored COPY (may not exist yet).

    Derived from the resolved original so the copy sits right next to it and
    carries the same build tag, e.g.
    Pre_processed_<SCEN>_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt.
    The '_FLOORED.txt' exclusion in executable_txt() keeps this copy from ever
    being mistaken for an original (no floors-on-floors on a re-run).

    Args:
        scenario: one of io.SCENARIOS.

    Returns:
        Path to the (possibly not-yet-existing) floored txt copy.
    """
    orig = executable_txt(scenario)
    return orig.with_name(orig.stem + "_FLOORED.txt")


def solver_txt(scenario: str) -> Path:
    """Locate the txt the solver ACTUALLY consumed: the most-patched variant present.

    Patch chain: original -> _FLOORED (write_floors.py) -> _FLOORED_VEGCON
    (veg_tx_constraints.py). Each step writes a copy next to its source and the
    repo may carry only the final variant (intermediates get cleaned up), so
    this resolves by explicit preference instead of deriving the name from
    executable_txt() like floored_txt() does.

    Args:
        scenario: one of io.SCENARIOS.

    Returns:
        Path to the highest-priority existing variant (_FLOORED_VEGCON.txt,
        then _FLOORED.txt).

    Raises:
        FileNotFoundError: if neither patched variant exists for the scenario.
    """
    folder = EXECUTABLES / f"{scenario}_0"
    base = f"Pre_processed_{scenario}_0_StorageDelayN5_OpenBCK_RMCarefulXLSX"
    for suffix in ("_FLOORED_VEGCON.txt", "_FLOORED.txt"):
        cand = folder / (base + suffix)
        if cand.exists():
            return cand
    raise FileNotFoundError(
        f"[{scenario}] ni {base}_FLOORED_VEGCON.txt ni {base}_FLOORED.txt "
        f"en {folder}; corre write_floors.py (y veg_tx_constraints.py) primero")


def parse_mathprog(scenario: str, wanted: list[str]) -> dict[str, pd.DataFrame]:
    """Parse the requested 'param default X : NAME :=  ... ;' list-blocks from the
    scenario's preprocessed MathProg txt (executable_txt()).

    Every target block here is 4-token per row: REGION TECHNOLOGY YEAR VALUE.

    Args:
        scenario: one of io.SCENARIOS.
        wanted: list of MathProg parameter names to extract (e.g.
            "TotalTechnologyAnnualActivityLowerLimit").

    Returns:
        {param: DataFrame[REGION, TECHNOLOGY, YEAR, VALUE]}; missing params yield
        an empty DataFrame. The block default value is attached as
        df.attrs['default'].
    """
    path = executable_txt(scenario)
    wanted_set = set(wanted)
    rows: dict[str, list] = {p: [] for p in wanted}
    defaults: dict[str, str] = {}
    current = None
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            decl = _PARAM_DECL.match(line)
            if decl:
                default_val, name = decl.group(1), decl.group(2)
                current = name if name in wanted_set else None
                if current:
                    defaults[current] = default_val
                continue
            if current is None:
                continue
            s = line.strip()
            if s == ";" or s == "":
                if s == ";":
                    current = None
                continue
            toks = s.split()
            if len(toks) < 4:
                continue  # unexpected arity; skip defensively
            region, tech, year, value = toks[0], toks[1], toks[2], toks[-1]
            try:
                rows[current].append((region, tech, int(float(year)), float(value)))
            except ValueError:
                continue

    result = {}
    for p in wanted:
        df = pd.DataFrame(rows[p], columns=["REGION", "TECHNOLOGY", "YEAR", "VALUE"])
        df.attrs["default"] = defaults.get(p)
        result[p] = df
    return result


# --------------------------------------------------------------------------- #
# otoole A2 per-scenario CSVs  -- other inputs
# --------------------------------------------------------------------------- #
def load_otoole(scenario: str, param: str) -> pd.DataFrame:
    """Read outputs/A2_Outputs_Params_otoole/<SCEN>/<param>.csv verbatim.

    Args:
        scenario: one of io.SCENARIOS.
        param: otoole parameter name (CSV file stem), e.g. "ResidualCapacity".

    Returns:
        The CSV as a DataFrame (YEAR coerced to nullable Int64 if present), or an
        empty DataFrame if the file does not exist.
    """
    path = OTOOLE / scenario / f"{param}.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if "YEAR" in df.columns:
        df["YEAR"] = pd.to_numeric(df["YEAR"], errors="coerce").astype("Int64")
    return df


# --------------------------------------------------------------------------- #
# Fossil-fleet enumeration -- floor universe
# --------------------------------------------------------------------------- #
def nonren_floor_techs(scenario: str) -> list[str]:
    """List all fossil techs (fuel in FLOOR_FUELS) that carry any residual
    capacity, any forced build (TotalAnnualMinCapacityInvestment), or any
    existing dispatch floor (TotalTechnologyAnnualActivityLowerLimit) in this
    scenario. This is the full flooring universe, replacing WORKING_SET.

    Args:
        scenario: one of io.SCENARIOS.

    Returns:
        Sorted list of technology codes.
    """
    techs: set[str] = set()

    resid = load_otoole(scenario, "ResidualCapacity")
    if len(resid):
        for t, v in zip(resid["TECHNOLOGY"], resid["VALUE"]):
            if float(v) > 0 and parse_tech(t)["fuel"] in FLOOR_FUELS:
                techs.add(t)

    mp = parse_mathprog(scenario, ["TotalAnnualMinCapacityInvestment",
                                    "TotalTechnologyAnnualActivityLowerLimit"])
    for df in mp.values():
        if len(df):
            for t, v in zip(df["TECHNOLOGY"], df["VALUE"]):
                if float(v) > 0 and parse_tech(t)["fuel"] in FLOOR_FUELS:
                    techs.add(t)

    return sorted(techs)


# --------------------------------------------------------------------------- #
# Combined inputs+outputs CSV  -- outputs + input cross-check
# --------------------------------------------------------------------------- #
def find_combined_csv() -> Path:
    """Locate the combined inputs+outputs CSV under outputs/.

    Returns:
        The largest file matching outputs/RELAC_TX*Combined_Inputs_Outputs*.csv
        (the full inputs+outputs file, not a dated slice).

    Raises:
        FileNotFoundError: if no matching CSV exists.
    """
    cands = sorted(P.OUTPUTS.glob("RELAC_TX*Combined_Inputs_Outputs*.csv"))
    if not cands:
        raise FileNotFoundError("No combined inputs+outputs CSV in outputs/")
    # prefer the largest (the full inputs+outputs file, not a _fecha slice)
    return max(cands, key=lambda p: p.stat().st_size)


_COMBINED_IDX = ["Future", "Scenario", "REGION", "YEAR", "TECHNOLOGY",
                 "FUEL", "EMISSION", "MODE_OF_OPERATION"]


def extract_combined(params: list[str], csv_path: Path | None = None,
                     cache_tag: str | None = None,
                     rebuild: bool = False,
                     chunksize: int = 400_000) -> dict[str, pd.DataFrame]:
    """Make one streaming pass over the (large) combined CSV; one tidy parquet per param.

    Args:
        params: combined-CSV value columns to extract (e.g.
            "TotalTechnologyAnnualActivity").
        csv_path: combined CSV to read; defaults to find_combined_csv().
        cache_tag: cache-file tag; defaults to csv_path.stem (sanitized).
        rebuild: if True, re-read csv_path and overwrite the cache even if present.
        chunksize: pandas.read_csv chunk size (rows).

    Returns:
        {param: DataFrame} with only the index columns that are ever populated
        for that param (plus VALUE). Cached under
        fix_dispatch/cache/<tag>__<param>.parquet. Only Future==0 rows are kept
        (deterministic model).

    Side effects:
        Writes one parquet file per param to CACHE; reads from cache instead of
        csv_path when the cache is already complete and rebuild is False.
    """
    csv_path = Path(csv_path) if csv_path else find_combined_csv()
    tag = cache_tag or csv_path.stem
    tag = re.sub(r"[^A-Za-z0-9_.-]", "_", tag)

    out_paths = {p: CACHE / f"{tag}__{p}.parquet" for p in params}
    if not rebuild and all(pp.exists() for pp in out_paths.values()):
        return {p: pd.read_parquet(pp) for p, pp in out_paths.items()}

    usecols = _COMBINED_IDX + list(params)
    buffers: dict[str, list[pd.DataFrame]] = {p: [] for p in params}
    reader = pd.read_csv(csv_path, usecols=lambda c: c in usecols,
                         chunksize=chunksize, low_memory=False)
    for ch in reader:
        ch = ch[ch["Future"] == 0]
        for p in params:
            sub = ch[ch[p].notna()]
            if len(sub) == 0:
                continue
            keep = [c for c in _COMBINED_IDX if c != "Future"]
            piece = sub[keep + [p]].rename(columns={p: "VALUE"})
            buffers[p].append(piece)

    result = {}
    for p in params:
        if buffers[p]:
            df = pd.concat(buffers[p], ignore_index=True)
            # drop index columns that are entirely null for this parameter
            for c in ["FUEL", "EMISSION", "MODE_OF_OPERATION"]:
                if c in df.columns and df[c].isna().all():
                    df = df.drop(columns=c)
            if "YEAR" in df.columns:
                df["YEAR"] = pd.to_numeric(df["YEAR"], errors="coerce").astype("Int64")
        else:
            df = pd.DataFrame(columns=["Scenario", "REGION", "YEAR", "TECHNOLOGY", "VALUE"])
        df.to_parquet(out_paths[p], index=False)
        result[p] = df
    return result


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def to_lookup(df: pd.DataFrame, keys: list[str], value: str = "VALUE") -> dict:
    """Convert a DataFrame to a {tuple(keys): value} lookup dict.

    Args:
        df: source DataFrame; None or empty returns {}.
        keys: column names forming the lookup key tuple, in order.
        value: column name to use as the value.

    Returns:
        dict keyed by tuple(keys). Last write wins on duplicate keys.
    """
    if df is None or len(df) == 0:
        return {}
    out = {}
    for row in df[keys + [value]].itertuples(index=False, name=None):
        out[tuple(row[:-1])] = row[-1]
    return out


if __name__ == "__main__":
    # quick self-check
    print("REPO:", P.REPO_ROOT)
    print("Combined CSV:", find_combined_csv().name)
    for s in SCENARIOS:
        print(f"  {s} txt:", executable_txt(s).name)
    d = parse_mathprog("BAU", ["TotalTechnologyAnnualActivityLowerLimit",
                               "TotalAnnualMinCapacityInvestment"])
    for k, v in d.items():
        print(f"  BAU {k}: {len(v)} rows, default={v.attrs.get('default')}")
    sys.exit(0)
