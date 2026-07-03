"""
relac_io.py  --  shared read-only IO / parsing for the dispatch-floor fix.

Authoritative sources (per the revised division of labor):
  - Activity limits (LowerLimit / UpperLimit) + forced builds (MinCapacityInvestment)
      -> parsed directly from the per-scenario preprocessed GLPK/MathProg txt
         t1_confection/Executables/<SCEN>_0/
             Pre_processed_<SCEN>_0_StorageDelayN5_OpenBCK_RMCarefulXLSX*.txt
  - Other inputs (ResidualCapacity, CapacityToActivityUnit, CapitalCost, FixedCost,
      VariableCost, OperationalLife, Input/Output/EmissionActivityRatio, demand)
      -> A2 otoole per-scenario CSVs  t1_confection/A2_Outputs_Params_otoole/<SCEN>/*.csv
  - Model outputs (TotalCapacityAnnual, TotalTechnologyAnnualActivity, production, CF...)
      -> the combined inputs+outputs CSV in the repo root.

NOTHING here writes to any live input. The only writes are parquet caches under
fix_dispatch/cache/.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
REPO = Path(__file__).resolve().parents[1]
T1 = REPO / "t1_confection"
EXECUTABLES = T1 / "Executables"
OTOOLE = T1 / "A2_Outputs_Params_otoole"
CACHE = Path(__file__).resolve().parent / "cache"
CACHE.mkdir(exist_ok=True)

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

COUNTRIES = ["ARG", "BOL", "BRA", "BRB", "CHL", "COL", "CRI", "DOM", "ECU",
             "GTM", "HND", "HTI", "MEX", "NIC", "PAN", "PER", "PRY", "SLV", "URY"]

# The forced-fossil-unfloored working set (from the session brief).
WORKING_SET = [
    "PWRNGSMEXXX", "PWRPETECUXX", "PWRNGSPERXX", "PWRNGSPANXX", "PWRNGSSLVXX",
    "PWROILCRIXX", "PWRNGSGTMXX", "PWRNGSDOMXX", "PWROILHNDXX", "PWROILSLVXX",
    "PWRPETBRBXX",
]


# --------------------------------------------------------------------------- #
# Technology name parsing (see CLAUDE.md "Technology naming")
# --------------------------------------------------------------------------- #
def parse_tech(tech: str) -> dict:
    """Return {kind, fuel, country, is_fossil, is_renewable, is_nuclear, is_storage}.

    kind in {plant, tx, interconnector, other}.
    For plants  PWR+fuel(3)+country(3)+suffix : fuel=t[3:6], country=t[6:9].
    For interconnectors TRN+C1(3)+XX+C2(3)+XX : country=C1=t[3:6], to=t[8:11].
    Domestic Tx prefixes carry a country at t[6:9] but no combustion fuel.
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
    return parse_tech(tech)["country"]


def tech_fuel(tech: str) -> str | None:
    return parse_tech(tech)["fuel"]


# --------------------------------------------------------------------------- #
# MathProg (.txt) parameter parsing  -- AUTHORITATIVE for limits + forced builds
# --------------------------------------------------------------------------- #
_PARAM_DECL = re.compile(r"^\s*param\s+default\s+(\S+)\s*:\s*(\w+)\s*:=\s*$")


def executable_txt(scenario: str) -> Path:
    """The ORIGINAL preprocessed txt for the canonical
    StorageDelayN5_OpenBCK_RMCarefulXLSX build. Excludes the *.warnings.txt log
    and *_FLOORED.txt copies so that once write_floors.py drops a floored copy
    next to the original, every reader (feasibility, validators, write_floors
    itself on a re-run) still resolves to the true original and never
    floors-on-top-of-floors."""
    folder = EXECUTABLES / f"{scenario}_0"
    matches = sorted(
        p for p in folder.glob(
            f"Pre_processed_{scenario}_0_StorageDelayN5_OpenBCK_RMCarefulXLSX*.txt")
        if not p.name.endswith(".warnings.txt")
        and not p.name.endswith("_FLOORED.txt")
    )
    if not matches:
        raise FileNotFoundError(f"No preprocessed txt for scenario {scenario} in {folder}")
    return matches[0]


def floored_txt(scenario: str) -> Path:
    """Path where write_floors.py writes the floored COPY (may not exist yet).

    Derived from the resolved original so the copy sits right next to it and
    carries the same build tag, e.g.
    Pre_processed_<SCEN>_0_StorageDelayN5_OpenBCK_RMCarefulXLSX_FLOORED.txt.
    The '_FLOORED.txt' exclusion in executable_txt() keeps this copy from ever
    being mistaken for an original (no floors-on-floors on a re-run)."""
    orig = executable_txt(scenario)
    return orig.with_name(orig.stem + "_FLOORED.txt")


def parse_mathprog(scenario: str, wanted: list[str]) -> dict[str, pd.DataFrame]:
    """Parse the requested 'param default X : NAME :=  ... ;' list-blocks.

    Every target block here is 4-token per row: REGION TECHNOLOGY YEAR VALUE.
    Returns {param: DataFrame[REGION, TECHNOLOGY, YEAR, VALUE]}; missing params
    yield an empty DataFrame. The block default is attached as df.attrs['default'].
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
    """Read t1_confection/A2_Outputs_Params_otoole/<SCEN>/<param>.csv verbatim."""
    path = OTOOLE / scenario / f"{param}.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if "YEAR" in df.columns:
        df["YEAR"] = pd.to_numeric(df["YEAR"], errors="coerce").astype("Int64")
    return df


# --------------------------------------------------------------------------- #
# Combined inputs+outputs CSV  -- outputs + input cross-check
# --------------------------------------------------------------------------- #
def find_combined_csv() -> Path:
    cands = sorted(REPO.glob("RELAC_TX*Combined_Inputs_Outputs*.csv"))
    if not cands:
        raise FileNotFoundError("No combined inputs+outputs CSV in repo root")
    # prefer the largest (the full inputs+outputs file, not a _fecha slice)
    return max(cands, key=lambda p: p.stat().st_size)


_COMBINED_IDX = ["Future", "Scenario", "REGION", "YEAR", "TECHNOLOGY",
                 "FUEL", "EMISSION", "MODE_OF_OPERATION"]


def extract_combined(params: list[str], csv_path: Path | None = None,
                     cache_tag: str | None = None,
                     rebuild: bool = False,
                     chunksize: int = 400_000) -> dict[str, pd.DataFrame]:
    """One streaming pass over the (large) combined CSV; one tidy parquet per param.

    Returns {param: DataFrame} with only the index columns that are ever populated
    for that param (plus VALUE). Cached under fix_dispatch/cache/<tag>__<param>.parquet.
    Only Future==0 rows are kept (deterministic model).
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
    """DataFrame -> {tuple(keys): value}. Last write wins on duplicates."""
    if df is None or len(df) == 0:
        return {}
    out = {}
    for row in df[keys + [value]].itertuples(index=False, name=None):
        out[tuple(row[:-1])] = row[-1]
    return out


if __name__ == "__main__":
    # quick self-check
    print("REPO:", REPO)
    print("Combined CSV:", find_combined_csv().name)
    for s in SCENARIOS:
        print(f"  {s} txt:", executable_txt(s).name)
    d = parse_mathprog("BAU", ["TotalTechnologyAnnualActivityLowerLimit",
                               "TotalAnnualMinCapacityInvestment"])
    for k, v in d.items():
        print(f"  BAU {k}: {len(v)} rows, default={v.attrs.get('default')}")
    sys.exit(0)
