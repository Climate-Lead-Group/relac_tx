"""
add_max_cap_investment_lid_rule.py
===================================

Independent patch — applies a per-year LID and the V1 UNTIE RULE to
TotalAnnualMaxCapacityInvestment for GENERATION technologies that have
either ResidualCapacity > 0 or TotalAnnualMinCapacityInvestment > 0 in any
year.

This script is INDEPENDENT of add_max_capacity_investment_rule.py. It can run:
  - On a fresh A-O_Parametrization.xlsx (operates on empty MaxInv cells).
  - On the output of the first-patch script (recognizes 9999 placeholders and
    replaces them with the lid).
  - Repeatedly (idempotent — second run produces no changes).

PROBLEM
-------
For ALLOWED generation techs (those with residual or planned capacity), MaxInv
was being left effectively unbounded — either NaN (no constraint at all) or
9999 (a placeholder that's far above any realistic ramp). Without a real upper
bound, the optimizer can over-invest in candidate techs whose annual ramp
should be physically constrained. And without a year-by-year *ramp* tied to
demand, a constant lid either binds in late years (when demand has scaled
3x) or is too generous in early years.

RULE
----
For each tech in the ALLOWED ∩ GENERATION set, the per-year
MaxCapacityInvestment lid is computed in one of two modes, selected by
LID_RULE_MODE.

Common quantities (used by both modes):
    pool(cr, y)         = sum of ResidualCapacity(t, y) for every ALLOWED
                          GENERATION tech t in cr
    mult(cr, y)         = demand(cr, y) / demand(cr, DEMAND_REFERENCE_YEAR)
    scaled_pool(cr, y)  = pool(cr, y) * mult(cr, y)
    country_region(t)   = chars 6..10 of the tech code (e.g. BGDXX, INDNE)

Mode "uniform" (default):
    Every allowed tech in the same cr gets the SAME lid value.

        pct(cr, y) = base_pct(y) * mult(cr, y)
        where base_pct(y) = LID_PERCENTAGE_BY_YEAR.get(y, LID_PERCENTAGE_DEFAULT)
        lid(t, y)  = pct(cr, y) * pool(cr, y)
                   = base_pct(y) * scaled_pool(cr, y)

    The base_pct schedule is a per-decade plateau encoding "tight while we
    have planning data, looser as the horizon gets speculative." Demand
    growth is layered on linearly via mult — fast-growing crs get
    proportionally more headroom.

Mode "proportional":
    Each tech gets a lid sized to its share of the 2024 fleet. Total
    headroom is the year-over-year growth in scaled_pool, distributed
    proportionally and slackened by a security factor.

        tech_share(t)     = ResidualCapacity(t, ref_year) / pool(cr, ref_year)
        pool_delta(cr, y) = max(0, scaled_pool(cr, y) - scaled_pool(cr, y-1))
        lid(t, y)         = LID_SECURITY_FACTOR * tech_share(t) * pool_delta(cr, y)

    The max(0, ...) guard ensures that flat-or-declining demand years
    yield zero new headroom (no negative lids). For the reference year and
    earlier, lid = 0 (no prior year to delta against), so MinCapInv must
    cover any required ref-year build via the untie rule.

Both modes are floored by the V1 untie rule: if MinCapInv(t, y) > 0 and
the proposed lid <= MinCapInv(t, y), we push the lid to
MinCapInv(t, y) * UNTIE_MULTIPLIER. This guarantees the LP-feasibility
invariant MinCapInv < MaxCapInv whenever MinCapInv > 0.

GENERATION FILTER
-----------------
"Generation" is defined by TECH_TYPES.csv (columns: 'Technology (PWR)',
'Technology'). Only techs categorized as 'GENERATION' are eligible. This
correctly excludes storage (e.g. PWRSDSLKAXX), interconnectors, primary
fuels, etc., which need separate lid policies.

DEMAND-ANCHORED RAMP
--------------------
Demand multiplier per (country+region, year) is read from A-O_Demand.xlsx
(sheet 'Demand_Projection', rows where Demand/Share == 'Demand'). Country+
region is parsed from chars 3..7 of the Fuel/Tech code (ELCBGDXX03 -> BGDXX).
Demand rows are summed within each cr and divided by the value at the
reference year (default 2024) to obtain mult(cr, y).

Cell-by-cell, for each MaxInv cell of an ALLOWED tech:
    1. Empty (None) or 9999 placeholder  ->  proposed = lid
    2. Other explicit value (manual cal)  ->  proposed = current value (preserved)
    3. V1 UNTIE RULE (cf. B1b_Pre_solver_validation.py):
         if MinCapacityInvestment(tech, y) >= proposed:
             proposed = MinCapacityInvestment(tech, y) * UNTIE_MULTIPLIER

This guarantees Max_inv > Min_inv per year, eliminating that class of solver
infeasibility.

SCOPE
-----
- ALLOWED set: techs with residual > 0 OR min-cap-investment > 0 in any year.
  Use the pool-based lid (uniform or proportional).
- SPECULATIVE set: gen techs with zero residual AND zero min-inv whose 3-char
  prefix appears in LID_ABSOLUTE_BY_PREFIX. They have no pool to scale against
  (pool=0 -> pool-based lid would be 0), so they get a per-prefix absolute lid
  in GW/year, optionally scaled by demand mult. This is the escape hatch for
  emerging technologies that are completely unconstrained otherwise — e.g.,
  PWRWAV* (wave) which has zero residual fleet anywhere on Earth, or PWRGEO*
  in countries without an existing geothermal fleet. Without an entry in
  LID_ABSOLUTE_BY_PREFIX, a tech with zero pool stays untouched.
- TRN* transmission interconnects (length-13 codes) are SKIPPED entirely —
  they span two country+region pairs and don't fit a single pool. Their
  manually-calibrated MaxInv values are left untouched.

CONFIGURATION
-------------
Edit LID_PERCENTAGE_DEFAULT and LID_PERCENTAGE_BY_YEAR at the top of this
file to change the lid:

    LID_PERCENTAGE_DEFAULT = 0.005       # default 0.5% of pool per year
    LID_PERCENTAGE_BY_YEAR = {            # per-year overrides (optional)
        2030: 0.01,
        2040: 0.02,
    }

OUTPUT
------
1. In-place edit of A-O_Parametrization.xlsx.
2. A JSON change log written inside the scenario dir as
   `lid_rule_changes_<ts>.json`, with per-cell reasons and the
   per-(country_region, year) pool sizes used.

USAGE
-----
    # From the t1_confection directory:
    python add_max_cap_investment_lid_rule.py

    # Override defaults:
    python add_max_cap_investment_lid_rule.py \\
        --input-dir A1_Outputs/A1_Outputs_BAU \\
        --sheets "Secondary Techs"

    # Restore from a legacy _PRE_LID_* backup (if one still exists alongside
    # the scenario dir from before the no-backup default):
    python add_max_cap_investment_lid_rule.py --restore
    python add_max_cap_investment_lid_rule.py \\
        --restore-from A1_Outputs/A1_Outputs_BAU_PRE_LID_20260430_204529
"""

from __future__ import annotations

import argparse
import gc
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

try:
    import yaml as _yaml
    def _load_yaml(path: Path) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            return _yaml.safe_load(f)
except ImportError:
    _yaml = None
    def _load_yaml(path: Path) -> dict:
        raise ImportError("PyYAML is required. Install with: pip install pyyaml")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEFAULT_TARGET_SHEETS = ["Secondary Techs"]
PARAM_FILE_NAME = "A-O_Parametrization.xlsx"

# Optional YAML override. The orchestrator (A3_process.py) detects this
# constant and stages the matching YAML from rules_scripts/configs/<scenario>/
# alongside this script when the scenario provides one. When present, its
# values override the module-level constants below for the lifetime of this
# process. Absent YAML = current module defaults remain in effect (so BAU and
# scenarios without a YAML override behave exactly as before).
YAML_FILE_NAME = "lid_rule.yaml"

RES_PARAM = "ResidualCapacity"
MIN_INV_PARAM = "TotalAnnualMinCapacityInvestment"
MAX_INV_PARAM = "TotalAnnualMaxCapacityInvestment"

PROJ_MODE_COL = "Projection.Mode"
PROJ_MODE_EMPTY = "EMPTY"
PROJ_MODE_USER = "User defined"

# A leftover sentinel from the first-patch script. If we encounter this value,
# treat the cell as a placeholder and replace it with the lid (rather than as
# a manually calibrated value to preserve).
PLACEHOLDER_VALUE = 9999

# When True, treat 0 as a placeholder ALONG WITH 9999 and NaN, BUT ONLY for
# rows that also contain at least one 9999 cell. Rationale (relac_tx):
# Upstream A1 emits 9999 wherever it considers MaxInv data unreliable. If a row
# has any 9999, the whole row is "in the to-be-filled-by-lid bucket" — any 0s
# in that same row are typically missing-data artifacts (e.g., base-year cells
# that got zeroed by the source pipeline), not intentional caps. Rows that have
# 0s but NO 9999 anywhere are treated as intentional bans (e.g., natural-gas
# techs in countries where expansion is policy-prohibited) and are preserved.
# When False (default), 0 is always preserved (OSTRAM-compatible behavior).
ZERO_IS_PLACEHOLDER_IN_LID_ROWS = False

# When True, every positive numeric value (>0) in a MaxCapInv cell of an
# ALLOWED tech is treated as a placeholder too — i.e., the lid overwrites
# values written by prior runs of this script. Zeros and NaNs follow their
# usual rules (zeros are preserved unless ZERO_IS_PLACEHOLDER_IN_LID_ROWS
# matches; NaNs are placeholders). This lets you iterate on the lid schedule
# without restoring the xlsx between runs. WARNING: this also overwrites
# any genuine manual-calibration entries that were written by hand;
# combine with RESTRICT_TO_GENERATION (already on) to limit the blast
# radius to techs in TECH_TYPES.csv GENERATION category.
FORCE_OVERWRITE = False

# Tech naming conventions
PWR_TECH_LENGTH = 11    # e.g. PWRHYDBGDXX (3-letter prefix + 3 fuel + 3 country + 2 region)
TRN_TECH_LENGTH = 13    # transmission interconnects, e.g. TRNINDEAINDNE -- skipped
COUNTRY_REGION_SLICE = slice(6, 11)  # for length-11 PWR* codes: chars 6..10

# ---------------------------------------------------------------------------
# Tech-type filter — only patch GENERATION technologies
# ---------------------------------------------------------------------------
# TECH_TYPES.csv lives next to this script. It lists techs by category
# (GENERATION, INTERCONNECTORS, STORAGE_LONG, STORAGE_SHORT, etc.). Only
# techs in GENERATION_CATEGORY are eligible for the lid + untie rule.
# Set RESTRICT_TO_GENERATION = False to fall back to the prior behavior
# (any allowed tech with a length-11 PWR* shape).
TECH_TYPES_FILE = "TECH_TYPES.csv"
TECH_TYPES_CATEGORY_COL = "Technology (PWR)"
TECH_TYPES_TECH_COL = "Technology"
GENERATION_CATEGORY = "GENERATION"
RESTRICT_TO_GENERATION = True

# ---------------------------------------------------------------------------
# Lid rule configuration
# ---------------------------------------------------------------------------
# LID_RULE_MODE selects which lid formula to use. Both modes share the same
# pool definition and demand multiplier; they differ in *how* the lid is
# distributed among techs. See top-of-file RULE block for full formulas.
#
#   "uniform"      — Per-decade pct schedule, applied uniformly across all
#                    techs in the same cr. Same lid value for every allowed
#                    gen tech in cr per year. Use this for "let the optimizer
#                    pick winners" scenarios and for late-horizon stress tests
#                    where the planning anchor is intentionally relaxed.
#
#   "proportional" — Each tech gets a lid sized to its 2024 fleet share,
#                    times the year-over-year growth in scaled_pool, times
#                    a slack factor. Use this when the BAU narrative is
#                    "fleet evolves proportionally to current composition."
LID_RULE_MODE = "proportional"

# --- Uniform mode parameters --------------------------------------------------
# Per-year base percentage. Encodes "tight near-term, loose late-horizon."
# In uniform mode: pct(cr, y) = LID_PERCENTAGE_BY_YEAR[y] * mult(cr, y)
# Schedule rationale:
#   2023-2030 = 0.5%   - matches current near-term lid; respects national IRPs
#                        which typically have visibility through ~2030.
#   2031-2040 = 10%    - planning data thins past 2030; 20x jump frees the
#                        optimizer enough to substitute for storage if needed.
#   2041-2050 = 50%    - effectively unbounded; "we don't know what build
#                        rates will be in 2045+, let the model decide."
# Years not in this dict fall back to LID_PERCENTAGE_DEFAULT.
LID_PERCENTAGE_DEFAULT = 0.5
LID_PERCENTAGE_BY_YEAR: dict = {
    2023: 0.05, 2024: 0.05, 2025: 0.05, 2026: 0.05, 2027: 0.05,
    2028: 0.05, 2029: 0.05, 2030: 0.1,
    2031: 0.1,  2032: 0.1,  2033: 0.1,  2034: 0.1,  2035: 0.1,
    2036: 0.1,  2037: 0.1,  2038: 0.1,  2039: 0.1,  2040: 0.2,
    2041: 0.20,  2042: 0.20,  2043: 0.20,  2044: 0.20,  2045: 0.20,
    2046: 0.20,  2047: 0.20,  2048: 0.20,  2049: 0.20,  2050: 0.20,
}

# Per-prefix schedule override. Maps the 3-char tech-type prefix
# (e.g., "WON" for onshore wind, "GEO" for geothermal) to its own
# {year: pct} dict. Techs whose prefix appears here use this dict
# *for years that are present*; missing years fall back to
# LID_PERCENTAGE_BY_YEAR. Techs whose prefix is not in this dict
# use LID_PERCENTAGE_BY_YEAR as usual. The override is intentionally
# coarse (per prefix, not per country) because relac_tx country-region
# heterogeneity is already absorbed by mult(cr, y).
LID_PERCENTAGE_BY_YEAR_BY_PREFIX: dict = {}

# --- Proportional mode parameters --------------------------------------------
# Slack on the proportional-share lid:
#   lid(t, y) = LID_SECURITY_FACTOR * tech_share(t) * pool_delta(cr, y)
# Setting this to exactly 1.0 means each tech's lid equals its proportional
# share of the year's pool growth. Values >= 1.0 add slack to avoid binding
# the optimizer at the strict proportional split. 1.1 is a debugging knob
# for unblocking solver edge cases; values much above 1.5 dilute the
# proportional-allocation narrative.
LID_SECURITY_FACTOR = 1.1

# --- Demand ramp (used by both modes) ----------------------------------------
# When LID_RAMP_FROM_DEMAND is True, mult(cr, y) is computed and applied:
#   uniform mode      -> pct(cr, y) = base_pct(y) * mult(cr, y)
#   proportional mode -> scaled_pool(cr, y) = pool(cr, y) * mult(cr, y)
# When False, mult collapses to 1.0 everywhere (uniform mode becomes flat
# pct schedule; proportional mode becomes share * unscaled pool delta,
# which is typically zero since residual is roughly flat).
LID_RAMP_FROM_DEMAND = True

DEMAND_FILE_NAME = "A-O_Demand.xlsx"
DEMAND_SHEET = "Demand_Projection"
DEMAND_REFERENCE_YEAR = 2024
DEMAND_TYPE_FILTER = "Demand"   # value of "Demand/Share" column to keep
DEMAND_FUEL_COL = "Fuel/Tech"
DEMAND_TYPE_COL = "Demand/Share"
DEMAND_CR_SLICE = slice(3, 8)   # ELCBGDXX03 -> BGDXX

# V1 untie rule: when MinCapInvestment(y) >= proposed MaxCapInv(y), push
# MaxCapInv up by this multiplier. Matches MAX_MULTIPLIER in B1b.
UNTIE_MULTIPLIER = 1.01

# --- Absolute lid for unfleeted gen techs ------------------------------------
# Per-prefix absolute lid in GW/year for GENERATION techs that have NO existing
# fleet (zero ResidualCapacity) and NO required builds (zero MinCapInvestment).
# Without this, such techs are not in the ALLOWED set and the script leaves
# their MaxCapInv untouched — meaning they stay completely unconstrained and
# the optimizer can over-deploy them (e.g. PWRWAV* getting 26.5 GW in MEX
# 2025 of a technology with ~0 GW deployed worldwide).
#
# Default policy: WAV = 0 (wave is non-commercial; ban new investment in BAU).
# Other prefixes default to NO entry => techs in those prefixes stay
# untouched (prior behavior preserved). Configure additional prefixes via
# YAML, e.g.:
#     absolute_by_prefix:
#       GEO: 0.2     # 0.2 GW/year for geothermal in countries without fleet
#       WAV: 0
#
# When LID_RAMP_FROM_DEMAND is True the absolute value is multiplied by
# mult(cr, y) so fast-growing crs get proportionally more headroom (at the
# reference year mult=1, so the cap equals the configured value).
LID_ABSOLUTE_BY_PREFIX: dict = {
    "WAV": 0.0,
}

# --- Per-tech flat overrides --------------------------------------------------
# Map of EXACT tech name -> constant MaxCapInv value (GW/year). When a tech
# appears here, the lid script writes the given value in EVERY year, bypassing
# both the pool-based lid formula and the preserved_manual rule. Use to enforce
# a "flat schedule" on specific tech+country combinations whose D3-derived
# step+spike pattern is not desired. The standard untie rule still applies — if
# MinCapInv exceeds the flat value in any year, that cell is bumped to
# MinCapInv * UNTIE_MULTIPLIER (preserves LP feasibility).
LID_FLAT_OVERRIDES_BY_TECH: dict = {}


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------
def _rmtree_robust(path: Path, attempts: int = 5) -> None:
    """shutil.rmtree with retries.

    On Windows, .xlsx files saved via openpyxl are sometimes briefly held by
    the OS after `wb.save()` returns, causing `shutil.rmtree` to raise
    PermissionError [WinError 32]. Force a GC to release any lingering Python
    refs, back off, and retry. Linux/macOS hits the success path on attempt 0.
    """
    for i in range(attempts):
        try:
            shutil.rmtree(path)
            return
        except PermissionError:
            gc.collect()
            time.sleep(0.1 * (i + 1))
    # Final attempt — let it raise if the lock still hasn't released.
    shutil.rmtree(path)


def find_latest_backup(input_dir: Path) -> Path | None:
    """Return the most recent _PRE_LID_* sibling backup of input_dir, or None."""
    parent = input_dir.parent
    candidates = sorted(
        (p for p in parent.iterdir()
         if p.is_dir() and p.name.startswith(f"{input_dir.name}_PRE_LID_")),
        key=lambda p: p.name,
    )
    return candidates[-1] if candidates else None


def restore_from_backup(input_dir: Path, backup_dir: Path | None = None) -> Path:
    """Restore the input directory from a _PRE_LID_* backup.

    If `backup_dir` is None, use the most recent _PRE_LID_* sibling backup.
    Removes the current input_dir (after a safety copy in case the user wants
    to undo the restore) and replaces it with the backup contents.

    Returns the path of the backup that was used.
    """
    input_dir = Path(input_dir)
    if backup_dir is None:
        backup_dir = find_latest_backup(input_dir)
        if backup_dir is None:
            raise FileNotFoundError(
                f"No _PRE_LID_* backup found next to {input_dir}. "
                f"Pass --restore-from <folder> to specify one."
            )
    else:
        backup_dir = Path(backup_dir)
        if not backup_dir.is_dir():
            raise FileNotFoundError(f"Backup folder does not exist: {backup_dir}")

    # Safety: keep what's currently in input_dir as a "POST_LID" snapshot in
    # case the user runs --restore by mistake. Same parent, timestamped.
    if input_dir.is_dir():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot = input_dir.parent / f"{input_dir.name}_POST_LID_pre_restore_{stamp}"
        if not snapshot.exists():
            shutil.copytree(input_dir, snapshot)
        _rmtree_robust(input_dir)
    shutil.copytree(backup_dir, input_dir)
    return backup_dir


# ---------------------------------------------------------------------------
# YAML config loading
# ---------------------------------------------------------------------------
def _parse_year_key(key) -> list[int]:
    """Accept '2030', 2030, or '2031-2040' and return the list of years it covers."""
    if isinstance(key, int):
        return [key]
    s = str(key).strip()
    if "-" in s:
        lo, hi = s.split("-", 1)
        return list(range(int(lo), int(hi) + 1))
    return [int(s)]


def load_config(yaml_path: Path) -> dict:
    """Load and validate the YAML configuration.

    All keys are optional; missing keys fall through to the module-level
    defaults. The schedule accepts both single-year keys (2030) and ranges
    (2031-2040), the latter expanded year-by-year.
    """
    cfg = _load_yaml(yaml_path)
    if cfg is None:
        cfg = {}

    out: dict = {}

    rule_mode = cfg.get("rule_mode")
    if rule_mode is not None:
        rule_mode = str(rule_mode).strip()
        if rule_mode not in ("uniform", "proportional"):
            raise ValueError(
                f"rule_mode={rule_mode!r} is not recognized in {yaml_path}. "
                f"Expected 'uniform' or 'proportional'."
            )
        out["rule_mode"] = rule_mode

    if "percentage_default" in cfg:
        out["percentage_default"] = float(cfg["percentage_default"])

    if "percentage_by_year" in cfg:
        expanded: dict = {}
        for raw_key, raw_val in (cfg["percentage_by_year"] or {}).items():
            value = float(raw_val)
            for y in _parse_year_key(raw_key):
                expanded[y] = value
        out["percentage_by_year"] = expanded

    if "percentage_by_year_by_prefix" in cfg:
        expanded_pref: dict = {}
        raw_block = cfg["percentage_by_year_by_prefix"] or {}
        for prefix, prefix_sched in raw_block.items():
            prefix_norm = str(prefix).strip().upper()
            if not prefix_norm:
                continue
            years_dict: dict = {}
            for raw_key, raw_val in (prefix_sched or {}).items():
                value = float(raw_val)
                for y in _parse_year_key(raw_key):
                    years_dict[y] = value
            expanded_pref[prefix_norm] = years_dict
        out["percentage_by_year_by_prefix"] = expanded_pref

    if "absolute_by_prefix" in cfg:
        absolute_map: dict = {}
        for prefix, value in (cfg["absolute_by_prefix"] or {}).items():
            prefix_norm = str(prefix).strip().upper()
            if not prefix_norm:
                continue
            absolute_map[prefix_norm] = float(value)
        out["absolute_by_prefix"] = absolute_map

    if "flat_overrides_by_tech" in cfg:
        flat_map: dict = {}
        for tech, value in (cfg["flat_overrides_by_tech"] or {}).items():
            tech_norm = str(tech).strip().upper()
            if not tech_norm:
                continue
            flat_map[tech_norm] = float(value)
        out["flat_overrides_by_tech"] = flat_map

    if "security_factor" in cfg:
        out["security_factor"] = float(cfg["security_factor"])

    if "ramp_from_demand" in cfg:
        out["ramp_from_demand"] = bool(cfg["ramp_from_demand"])

    if "zero_is_placeholder_in_lid_rows" in cfg:
        out["zero_is_placeholder_in_lid_rows"] = bool(
            cfg["zero_is_placeholder_in_lid_rows"]
        )

    if "force_overwrite" in cfg:
        out["force_overwrite"] = bool(cfg["force_overwrite"])

    return out


def apply_config(cfg: dict) -> None:
    """Mutate the module-level lid constants in place.

    The script's helper functions reference these constants directly, so
    overriding them here propagates to every downstream call without touching
    any function signatures.
    """
    global LID_RULE_MODE, LID_PERCENTAGE_DEFAULT, LID_PERCENTAGE_BY_YEAR
    global LID_PERCENTAGE_BY_YEAR_BY_PREFIX, LID_ABSOLUTE_BY_PREFIX
    global LID_FLAT_OVERRIDES_BY_TECH
    global LID_SECURITY_FACTOR, LID_RAMP_FROM_DEMAND
    global ZERO_IS_PLACEHOLDER_IN_LID_ROWS, FORCE_OVERWRITE
    if "rule_mode" in cfg:
        LID_RULE_MODE = cfg["rule_mode"]
    if "percentage_default" in cfg:
        LID_PERCENTAGE_DEFAULT = cfg["percentage_default"]
    if "percentage_by_year" in cfg:
        LID_PERCENTAGE_BY_YEAR = cfg["percentage_by_year"]
    if "percentage_by_year_by_prefix" in cfg:
        LID_PERCENTAGE_BY_YEAR_BY_PREFIX = cfg["percentage_by_year_by_prefix"]
    if "absolute_by_prefix" in cfg:
        LID_ABSOLUTE_BY_PREFIX = cfg["absolute_by_prefix"]
    if "flat_overrides_by_tech" in cfg:
        LID_FLAT_OVERRIDES_BY_TECH = cfg["flat_overrides_by_tech"]
    if "security_factor" in cfg:
        LID_SECURITY_FACTOR = cfg["security_factor"]
    if "ramp_from_demand" in cfg:
        LID_RAMP_FROM_DEMAND = cfg["ramp_from_demand"]
    if "zero_is_placeholder_in_lid_rows" in cfg:
        ZERO_IS_PLACEHOLDER_IN_LID_ROWS = cfg["zero_is_placeholder_in_lid_rows"]
    if "force_overwrite" in cfg:
        FORCE_OVERWRITE = cfg["force_overwrite"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def tech_prefix(tech: str | None) -> str:
    """Return the 3-char tech-type prefix from a PWR* tech name.

    Tech names follow PWR<PREFIX><CR>XX where PREFIX is 3 chars at
    positions 3:6 (e.g., PWRWONURYXX -> WON, PWRGEOCRIXX -> GEO).
    Returns '' if the tech name doesn't fit the pattern; callers should
    treat '' as 'no per-prefix override applies'.
    """
    if not tech or len(tech) < 6 or not str(tech).startswith("PWR"):
        return ""
    return str(tech)[3:6].upper()


def lid_pct_for_cr_year(cr: str, year: int,
                        demand_mult_map: dict | None = None,
                        tech: str | None = None) -> float:
    """Return the *uniform-mode* lid percentage for (country_region, year).

    This function is used by uniform mode to compute pct(cr, y). Proportional
    mode does not call this — it computes lid directly via tech_share and
    pool_delta (see proportional_lid_for_tech_year).

    Formula:
        base_pct(y) = LID_PERCENTAGE_BY_YEAR_BY_PREFIX[prefix(tech)].get(y)  if present
                    | LID_PERCENTAGE_BY_YEAR.get(y, LID_PERCENTAGE_DEFAULT)  otherwise
        pct(cr, y)  = base_pct(y) * mult(cr, y)              if ramp on
                    = base_pct(y)                            if ramp off

    The base_pct schedule encodes the per-decade plateau ("tight near-term,
    loose late-horizon"). The demand multiplier layers on top, scaling pct
    linearly with each cr's demand growth from the reference year. So a
    region whose demand triples gets a lid that is 3x what the schedule
    alone would imply.

    Per-prefix override (optional, `tech` argument): if the tech's 3-char
    prefix has an entry in LID_PERCENTAGE_BY_YEAR_BY_PREFIX with the given
    year, that pct is used in place of the global schedule. Missing years
    in the prefix override fall back to the global schedule. Used to bias
    the lid harder against specific technology families (e.g., wind, geo)
    without tightening the lid on every gen tech.

    At the reference year, mult=1 by construction, so pct equals base_pct
    regardless of the ramp setting.
    """
    base_pct = None
    if tech and LID_PERCENTAGE_BY_YEAR_BY_PREFIX:
        prefix = tech_prefix(tech)
        if prefix:
            prefix_sched = LID_PERCENTAGE_BY_YEAR_BY_PREFIX.get(prefix)
            if prefix_sched and year in prefix_sched:
                base_pct = float(prefix_sched[year])
    if base_pct is None:
        if year in LID_PERCENTAGE_BY_YEAR:
            base_pct = float(LID_PERCENTAGE_BY_YEAR[year])
        else:
            base_pct = LID_PERCENTAGE_DEFAULT
    if LID_RAMP_FROM_DEMAND and demand_mult_map:
        mult = demand_mult_map.get((cr, year), 1.0)
        return base_pct * mult
    return base_pct


def lid_pct_for_year(year: int) -> float:
    """Backwards-compat shim: flat lid for `year`, ignoring cr and demand.
    Equivalent to lid_pct_for_cr_year with no ramp."""
    return float(LID_PERCENTAGE_BY_YEAR.get(year, LID_PERCENTAGE_DEFAULT))


def load_generation_techs(tech_types_path: Path) -> set:
    """Load TECH_TYPES.csv and return the set of techs in GENERATION_CATEGORY.

    Raises FileNotFoundError if the file is missing — TECH_TYPES.csv is the
    authoritative source for what counts as a generation tech, and silently
    falling back to a heuristic would be a footgun. To opt out, set
    RESTRICT_TO_GENERATION = False at the top of this script.
    """
    tech_types_path = Path(tech_types_path)
    if not tech_types_path.is_file():
        raise FileNotFoundError(
            f"TECH_TYPES.csv not found at {tech_types_path}. "
            f"Place it next to this script, or set "
            f"RESTRICT_TO_GENERATION = False to disable the filter."
        )
    df = pd.read_csv(tech_types_path)
    cat_col = TECH_TYPES_CATEGORY_COL
    tech_col = TECH_TYPES_TECH_COL
    missing = [c for c in (cat_col, tech_col) if c not in df.columns]
    if missing:
        raise ValueError(
            f"TECH_TYPES.csv missing columns {missing}. "
            f"Found {list(df.columns)}."
        )
    return set(df.loc[df[cat_col] == GENERATION_CATEGORY, tech_col].dropna())


def build_demand_multiplier_map(demand_path: Path,
                                ref_year: int = DEMAND_REFERENCE_YEAR) -> dict:
    """Read A-O_Demand.xlsx and return {(cr, year): demand(y) / demand(ref_year)}.

    Aggregates demand-type rows by country+region (chars 3..7 of the Fuel/Tech
    code, e.g. ELCBGDXX03 -> BGDXX). Returns an empty dict if the demand file
    is missing or doesn't have the expected structure — callers should treat
    an empty map as 'no ramp data, fall back to flat default'.
    """
    demand_path = Path(demand_path)
    if not demand_path.is_file():
        return {}
    try:
        dp = pd.read_excel(demand_path, sheet_name=DEMAND_SHEET)
    except Exception:
        return {}
    if DEMAND_TYPE_COL not in dp.columns or DEMAND_FUEL_COL not in dp.columns:
        return {}
    # Year headers may arrive as strings ("2024") or ints (2024) depending on
    # upstream writers. Accept either; map back to int for the output keys.
    year_to_col: dict = {}
    for c in dp.columns:
        if isinstance(c, int) and 1900 <= c <= 2200:
            year_to_col[c] = c
        elif isinstance(c, str) and c.isdigit() and 1900 <= int(c) <= 2200:
            year_to_col[int(c)] = c
    if ref_year not in year_to_col:
        return {}

    rows = dp[dp[DEMAND_TYPE_COL] == DEMAND_TYPE_FILTER].copy()
    if rows.empty:
        return {}
    rows["cr"] = rows[DEMAND_FUEL_COL].astype(str).str[DEMAND_CR_SLICE]
    orig_cols = [year_to_col[y] for y in sorted(year_to_col)]
    by_cr = rows.groupby("cr")[orig_cols].sum()

    ref_col = year_to_col[ref_year]
    out: dict = {}
    for cr, series in by_cr.iterrows():
        ref = float(series[ref_col])
        if ref <= 0:
            continue
        for y, col in year_to_col.items():
            out[(cr, y)] = float(series[col]) / ref
    return out


def values_differ(a, b, tol: float = 1e-12) -> bool:
    """Return True if `a` and `b` should be considered different cell values."""
    if a is None and b is None:
        return False
    if a is None or b is None:
        return True
    try:
        return abs(float(a) - float(b)) > tol
    except (TypeError, ValueError):
        return a != b


def find_year_columns(ws) -> dict:
    """Scan row 1 for integer year headers; return {year: column_index_1based}."""
    year_to_col = {}
    for col_idx in range(1, ws.max_column + 1):
        val = ws.cell(row=1, column=col_idx).value
        if isinstance(val, int) and 1900 <= val <= 2200:
            year_to_col[val] = col_idx
    return year_to_col


def find_named_columns(ws, names) -> dict:
    """Return {name: column_index_1based} for headers matching `names`."""
    found = {}
    for col_idx in range(1, ws.max_column + 1):
        val = ws.cell(row=1, column=col_idx).value
        if val in names:
            found[val] = col_idx
    return found


def identify_allowed_techs(df: pd.DataFrame, year_cols: list,
                           generation_techs: set | None = None) -> set:
    """Return the set of techs eligible for the lid + untie rule.

    Eligibility = (ResidualCapacity > 0 OR MinCapInvestment > 0 in any year)
    AND (in `generation_techs` if RESTRICT_TO_GENERATION and the set is given).

    `generation_techs` is the set returned by load_generation_techs(). When
    None, no category filter is applied — useful for tests of the unfiltered
    behavior. Production callers should always pass it.
    """
    res = df[df["Parameter"] == RES_PARAM]
    mci = df[df["Parameter"] == MIN_INV_PARAM]
    res_max = res.set_index("Tech")[year_cols].fillna(0).max(axis=1)
    mci_max = mci.set_index("Tech")[year_cols].fillna(0).max(axis=1)
    allowed = set(res_max[res_max > 0].index) | set(mci_max[mci_max > 0].index)
    if generation_techs is not None and RESTRICT_TO_GENERATION:
        allowed = allowed & generation_techs
    return allowed


def country_region_for(tech: str) -> str | None:
    """Extract country+region code from a PWR* tech name.

    Returns e.g. 'BGDXX' for PWRHYDBGDXX, 'INDNE' for PWRHYDINDNE.
    Returns None for tech codes that don't fit the PWR* length-11 convention
    (e.g. TRN* transmission interconnects of length 13) — those should be
    excluded from pool computation and pool-based lid application.
    """
    if not isinstance(tech, str) or len(tech) != PWR_TECH_LENGTH:
        return None
    return tech[COUNTRY_REGION_SLICE]


def build_pool_map(df: pd.DataFrame, allowed: set, year_cols: list) -> dict:
    """Return {(country_region, year): pool_total} where pool_total is the
    sum of ResidualCapacity across all ALLOWED PWR* techs in that
    country+region for that year. Non-PWR* techs (TRN*, etc.) and non-allowed
    techs do not contribute to the pool.
    """
    res = df[(df["Parameter"] == RES_PARAM) & (df["Tech"].isin(allowed))].copy()
    res["cr"] = res["Tech"].apply(country_region_for)
    # Drop techs whose country_region couldn't be parsed (e.g. TRN*)
    res = res[res["cr"].notna()]
    pool_map: dict = {}
    for cr, sub in res.groupby("cr"):
        for y in year_cols:
            pool_map[(cr, y)] = float(sub[y].fillna(0).sum())
    return pool_map


def build_mininv_map(df: pd.DataFrame, year_cols: list) -> dict:
    """Return {(tech, year): min_inv} lookup, NaN normalized to 0.0."""
    mci = df[df["Parameter"] == MIN_INV_PARAM]
    mininv_map: dict = {}
    for _, row in mci.iterrows():
        tech = row["Tech"]
        for y in year_cols:
            v = row[y]
            mininv_map[(tech, y)] = 0.0 if pd.isna(v) else float(v)
    return mininv_map


def build_tech_share_map(df: pd.DataFrame, allowed: set,
                         ref_year: int = DEMAND_REFERENCE_YEAR) -> dict:
    """Return {tech: share} where share = ResidualCapacity(t, ref_year)
    / pool(cr(t), ref_year). Used by proportional mode to distribute
    pool growth among allowed gen techs in a cr.

    Shares for techs in the same cr sum to 1.0 (modulo float). Techs with
    zero residual at ref_year get share=0 — they receive no proportional
    allocation, only whatever the untie rule provides via MinCapInv.
    """
    res = df[(df["Parameter"] == RES_PARAM) & (df["Tech"].isin(allowed))].copy()
    res["cr"] = res["Tech"].apply(country_region_for)
    res = res[res["cr"].notna()]
    # Per-cr ref-year totals
    cr_totals: dict = {}
    for cr, sub in res.groupby("cr"):
        cr_totals[cr] = float(sub[ref_year].fillna(0).sum())
    # Per-tech share
    share_map: dict = {}
    for _, row in res.iterrows():
        tech = row["Tech"]
        cr = row["cr"]
        cr_total = cr_totals.get(cr, 0.0)
        ref_val = float(row[ref_year]) if pd.notna(row[ref_year]) else 0.0
        share_map[tech] = (ref_val / cr_total) if cr_total > 0 else 0.0
    return share_map


def build_scaled_pool_map(pool_map: dict,
                          demand_mult_map: dict | None) -> dict:
    """Return {(cr, year): scaled_pool} where scaled_pool = pool * mult.

    If demand_mult_map is None or LID_RAMP_FROM_DEMAND is False, mult collapses
    to 1.0 and scaled_pool == pool (consistent with how lid_pct_for_cr_year
    treats the ramp-off case).
    """
    use_mult = LID_RAMP_FROM_DEMAND and demand_mult_map is not None
    out: dict = {}
    for (cr, y), pool in pool_map.items():
        if use_mult:
            mult = demand_mult_map.get((cr, y), 1.0)
        else:
            mult = 1.0
        out[(cr, y)] = pool * mult
    return out


def build_pool_delta_map(scaled_pool_map: dict, year_cols: list) -> dict:
    """Return {(cr, year): pool_delta} where pool_delta = max(0,
    scaled_pool(y) - scaled_pool(y-1)). For the earliest year in year_cols,
    delta = 0 (no prior year to delta against).

    The max(0, ...) guard ensures negative or flat demand growth in any year
    yields zero new headroom rather than a negative lid. Per project hygiene:
    we don't model demand dips, but if a year happens to be flat or slightly
    declining due to projection methodology, this prevents propagation of
    nonsense values into the LP.
    """
    sorted_years = sorted(year_cols)
    crs = sorted({cr for (cr, _) in scaled_pool_map.keys()})
    out: dict = {}
    for cr in crs:
        for i, y in enumerate(sorted_years):
            if i == 0:
                out[(cr, y)] = 0.0
                continue
            prev_y = sorted_years[i - 1]
            cur = scaled_pool_map.get((cr, y), 0.0)
            prev = scaled_pool_map.get((cr, prev_y), 0.0)
            delta = cur - prev
            out[(cr, y)] = delta if delta > 0 else 0.0
    return out


def identify_speculative_techs(df: pd.DataFrame, allowed: set,
                               generation_techs: set | None) -> set:
    """Gen techs with NO fleet AND NO required builds whose prefix is in
    LID_ABSOLUTE_BY_PREFIX. These get the absolute lid (pool-based formula
    would yield 0 for them since pool=0).

    Returns the empty set if LID_ABSOLUTE_BY_PREFIX is empty or
    RESTRICT_TO_GENERATION is off (the feature is intentionally GEN-only —
    storage/interconnect speculative caps need a different policy).
    """
    if not LID_ABSOLUTE_BY_PREFIX:
        return set()
    if not RESTRICT_TO_GENERATION or generation_techs is None:
        return set()
    eligible_prefixes = {p.upper() for p in LID_ABSOLUTE_BY_PREFIX.keys()}
    candidates = {
        t for t in generation_techs
        if t not in allowed and tech_prefix(t) in eligible_prefixes
        and country_region_for(t) is not None
    }
    return candidates


def absolute_lid_for_tech_year(tech: str, year: int,
                               demand_mult_map: dict | None) -> float:
    """Absolute-mode lid for speculative techs:
        lid = LID_ABSOLUTE_BY_PREFIX[prefix(tech)] * mult(cr, y)

    mult collapses to 1 when ramp is off or the cr is missing from the
    demand map. At the reference year mult=1 by construction.
    """
    prefix = tech_prefix(tech)
    base = LID_ABSOLUTE_BY_PREFIX.get(prefix)
    if base is None:
        return 0.0
    base = float(base)
    if LID_RAMP_FROM_DEMAND and demand_mult_map:
        cr = country_region_for(tech)
        if cr is not None:
            mult = demand_mult_map.get((cr, year), 1.0)
            return base * mult
    return base


def proportional_lid_for_tech_year(tech: str, year: int,
                                   tech_share_map: dict,
                                   pool_delta_map: dict) -> float:
    """Compute proportional-mode lid for (tech, year):
        lid = LID_SECURITY_FACTOR * tech_share(t) * pool_delta(cr, y)

    Returns 0.0 if cr cannot be parsed from tech (TRN* etc.) or if either
    share or delta is missing/zero.
    """
    cr = country_region_for(tech)
    if cr is None:
        return 0.0
    share = tech_share_map.get(tech, 0.0)
    delta = pool_delta_map.get((cr, year), 0.0)
    return LID_SECURITY_FACTOR * share * delta


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------
def apply_lid_to_sheet(ws, allowed: set, pool_map: dict,
                       mininv_map: dict,
                       demand_mult_map: dict | None = None,
                       tech_share_map: dict | None = None,
                       pool_delta_map: dict | None = None,
                       speculative_techs: set | None = None) -> dict:
    """
    Edit a worksheet in place, applying the lid + untie rule to the
    TotalAnnualMaxCapacityInvestment row of every PWR* tech in `allowed`.

    The lid formula depends on LID_RULE_MODE:
      "uniform"      - lid(t, y) = pct(cr, y) * pool(cr, y)
                       where pct(cr, y) = base_pct(y) * mult(cr, y).
                       Same lid for every allowed tech in cr per year.
      "proportional" - lid(t, y) = LID_SECURITY_FACTOR * tech_share(t)
                                   * pool_delta(cr, y).
                       Per-tech, weighted by 2024 fleet share.

    For proportional mode, callers must pass tech_share_map and
    pool_delta_map; for uniform mode they're ignored.

    Techs not in `allowed`, and TRN* transmission interconnects (whose names
    don't fit the PWR* country+region format), are entirely untouched.
    """
    if LID_RULE_MODE not in ("uniform", "proportional"):
        raise ValueError(
            f"LID_RULE_MODE={LID_RULE_MODE!r} is not recognized. "
            f"Expected 'uniform' or 'proportional'."
        )
    if LID_RULE_MODE == "proportional" and (
        tech_share_map is None or pool_delta_map is None
    ):
        raise ValueError(
            "proportional mode requires tech_share_map and pool_delta_map; "
            "got None. The caller (run) should build these via "
            "build_tech_share_map and build_pool_delta_map."
        )
    speculative_techs = speculative_techs or set()
    process_set = allowed | speculative_techs

    year_cols = find_year_columns(ws)
    headers = find_named_columns(ws, ["Tech", "Parameter", PROJ_MODE_COL])
    if "Tech" not in headers or "Parameter" not in headers:
        raise ValueError(
            f"Sheet '{ws.title}' missing required columns: "
            f"found {list(headers.keys())}"
        )
    tech_col = headers["Tech"]
    param_col = headers["Parameter"]
    proj_mode_col = headers.get(PROJ_MODE_COL)

    # Snapshot the uniform-mode lid pct per (cr, year). Always logged for
    # traceability — under proportional mode this is informational only.
    pct_used = {
        f"{cr}_{y}": lid_pct_for_cr_year(cr, y, demand_mult_map)
        for (cr, y) in pool_map.keys()
    }

    log = {
        "sheet": ws.title,
        "years_found": sorted(year_cols.keys()),
        "allowed_count": len(allowed),
        "speculative_count": len(speculative_techs),
        "rule_mode": LID_RULE_MODE,
        "changes": [],
        "preserved": [],
        "projection_mode_flips": [],
        "skipped_non_pwr_techs": [],
        "pool_map": {  # serializable version: {"BGDXX_2030": 7.123, ...}
            f"{cr}_{y}": v for (cr, y), v in pool_map.items()
        },
        "lid_pct_by_cr_year": pct_used,
        "demand_mult_by_cr_year": (
            {f"{cr}_{y}": v for (cr, y), v in demand_mult_map.items()}
            if demand_mult_map else {}
        ),
        "tech_share": (
            {t: s for t, s in tech_share_map.items()}
            if tech_share_map else {}
        ),
        "pool_delta_by_cr_year": (
            {f"{cr}_{y}": v for (cr, y), v in pool_delta_map.items()}
            if pool_delta_map else {}
        ),
        "security_factor": (
            LID_SECURITY_FACTOR if LID_RULE_MODE == "proportional" else None
        ),
        "absolute_by_prefix": {
            p: float(v) for p, v in LID_ABSOLUTE_BY_PREFIX.items()
        },
        "flat_overrides_by_tech": {
            t: float(v) for t, v in LID_FLAT_OVERRIDES_BY_TECH.items()
        },
        "speculative_techs": sorted(speculative_techs),
    }

    for row_idx in range(2, ws.max_row + 1):
        tech = ws.cell(row=row_idx, column=tech_col).value
        param = ws.cell(row=row_idx, column=param_col).value
        if tech is None or tech not in process_set or param != MAX_INV_PARAM:
            continue
        is_speculative = tech in speculative_techs

        cr = country_region_for(tech)
        if cr is None:
            # TRN* and other non-PWR* techs: skip — leave manual cal alone.
            if tech not in log["skipped_non_pwr_techs"]:
                log["skipped_non_pwr_techs"].append(tech)
            continue

        # Determine whether THIS row contains any 9999 placeholder. When
        # ZERO_IS_PLACEHOLDER_IN_LID_ROWS is on, the answer toggles whether 0s
        # in this same row are also treated as placeholders (relac_tx fix —
        # see module-level comment on the constant).
        row_has_placeholder_9999 = False
        if ZERO_IS_PLACEHOLDER_IN_LID_ROWS:
            for _yr, _col in year_cols.items():
                _v = ws.cell(row=row_idx, column=_col).value
                if (isinstance(_v, (int, float)) and not pd.isna(_v)
                        and float(_v) == float(PLACEHOLDER_VALUE)):
                    row_has_placeholder_9999 = True
                    break

        row_was_modified = False

        is_flat_override = tech in LID_FLAT_OVERRIDES_BY_TECH

        for year, col in year_cols.items():
            cell = ws.cell(row=row_idx, column=col)
            old = cell.value
            pool = pool_map.get((cr, year), 0.0)
            min_inv = mininv_map.get((tech, year), 0.0)

            # Flat override short-circuit: write a constant value across all
            # years, bypassing the pool-based formula and the preserved_manual
            # rule. The untie rule below still applies. Used to enforce a
            # CTO-mandated flat MaxCapInv schedule for specific tech+country
            # combinations (configured via flat_overrides_by_tech in YAML).
            if is_flat_override:
                lid = LID_FLAT_OVERRIDES_BY_TECH[tech]
                proposed = lid
                reason = "flat_override"
                if min_inv > 0 and proposed <= min_inv:
                    proposed = min_inv * UNTIE_MULTIPLIER
                    reason = "untie_min_inv"
                if values_differ(old, proposed):
                    cell.value = proposed
                    row_was_modified = True
                    log["changes"].append({
                        "tech": tech,
                        "country_region": cr,
                        "year": year,
                        "old": old,
                        "new": proposed,
                        "reason": reason,
                        "pool": pool,
                        "min_inv": min_inv,
                        "lid": lid,
                    })
                else:
                    log["preserved"].append(
                        {"tech": tech, "year": year, "value": old}
                    )
                continue

            # Compute lid per the active mode (or absolute, if speculative).
            if is_speculative:
                # Unfleeted tech whose prefix is in LID_ABSOLUTE_BY_PREFIX.
                # Pool-based formulas would yield 0 here; use the absolute
                # cap instead so the optimizer can't build unbounded MW of
                # an emerging tech with no real-world deployment anchor.
                lid = absolute_lid_for_tech_year(tech, year, demand_mult_map)
            elif LID_RULE_MODE == "uniform":
                pct = lid_pct_for_cr_year(cr, year, demand_mult_map, tech=tech)
                # Layer the demand multiplier onto pct * pool. Note that
                # lid_pct_for_cr_year already applies mult once, so the
                # final formula is lid = base_pct(y) * pool * mult(cr, y),
                # where base_pct may come from the prefix-specific override
                # if the tech's prefix is in LID_PERCENTAGE_BY_YEAR_BY_PREFIX.
                lid = pct * pool
            else:  # "proportional"
                lid = proportional_lid_for_tech_year(
                    tech, year, tech_share_map, pool_delta_map
                )

            # Decide the proposed value (before untie):
            #   placeholder cell -> lid; manual value -> preserve.
            # In rows that contain at least one 9999 and the relac_tx flag is
            # on, treat 0 as another placeholder for this row only.
            # If FORCE_OVERWRITE is on, treat any positive numeric value as a
            # placeholder too — used to iterate on the schedule without
            # restoring the xlsx between runs. Zeros in rows without any
            # 9999 (e.g., intentional bans like PWRNGS* in policy-prohibited
            # countries) are still preserved either way.
            # Speculative techs: the absolute lid from LID_ABSOLUTE_BY_PREFIX is
            # authoritative regardless of what's in the cell. Source data often
            # has a coincidental 0 (not None, not 9999) for unfleeted techs;
            # without this override that 0 would be treated as a manual value and
            # the configured cap (e.g., GEO=0.2) would never be written.
            if is_speculative:
                is_placeholder = True
            else:
                is_placeholder = (
                    old is None
                    or (isinstance(old, (int, float))
                        and not pd.isna(old)
                        and float(old) == float(PLACEHOLDER_VALUE))
                    or (ZERO_IS_PLACEHOLDER_IN_LID_ROWS
                        and row_has_placeholder_9999
                        and isinstance(old, (int, float))
                        and not pd.isna(old)
                        and float(old) == 0.0)
                    or (FORCE_OVERWRITE
                        and isinstance(old, (int, float))
                        and not pd.isna(old)
                        and float(old) > 0.0)
                )
            if is_placeholder:
                proposed = lid
                # Distinguish overwrites of prior positive values (force flag)
                # from fresh placeholder fills. Suffix '_absolute' marks lids
                # coming from LID_ABSOLUTE_BY_PREFIX (speculative techs).
                if (FORCE_OVERWRITE
                        and isinstance(old, (int, float))
                        and not pd.isna(old)
                        and float(old) > 0.0):
                    reason = "lid_overwrite"
                else:
                    reason = "lid_fill"
                if is_speculative:
                    reason = f"{reason}_absolute"
            else:
                proposed = float(old) if isinstance(old, (int, float)) else old
                reason = "preserved_manual"

            # V1 untie rule: ensure proposed > min_inv.
            if min_inv > 0 and (proposed is None or proposed <= min_inv):
                proposed = min_inv * UNTIE_MULTIPLIER
                reason = "untie_min_inv"

            if values_differ(old, proposed):
                cell.value = proposed
                row_was_modified = True
                log["changes"].append(
                    {
                        "tech": tech,
                        "country_region": cr,
                        "year": year,
                        "old": old,
                        "new": proposed,
                        "reason": reason,
                        "pool": pool,
                        "min_inv": min_inv,
                        "lid": lid,
                    }
                )
            else:
                log["preserved"].append(
                    {"tech": tech, "year": year, "value": old}
                )

        # Flip Projection.Mode to "User defined" for any row in process_set whose
        # mode is empty-equivalent (None, "", "EMPTY", whitespace). Runs even when
        # row_was_modified=False — re-runs where cells happen to already equal the
        # lid (e.g., WAV=0 over source-data 0) would otherwise leave mode="EMPTY"
        # and the model would ignore the cells. Legitimate projection modes
        # (Yearly percent change, Interpolate to final value, ...) are preserved.
        if proj_mode_col is not None:
            mode_cell = ws.cell(row=row_idx, column=proj_mode_col)
            cur = mode_cell.value
            cur_norm = cur.strip() if isinstance(cur, str) else cur
            if cur_norm is None or cur_norm == "" or cur_norm == PROJ_MODE_EMPTY:
                log["projection_mode_flips"].append({
                    "tech": tech, "old_mode": cur,
                })
                mode_cell.value = PROJ_MODE_USER

    return log


def edit_parametrization(filepath: Path, sheets: list,
                         generation_techs: set | None = None,
                         demand_mult_map: dict | None = None) -> dict:
    """Apply the lid + untie rule to `sheets` in the parametrization workbook."""
    df_all = pd.read_excel(filepath, sheet_name=None)
    wb = load_workbook(filepath)

    file_log = {"file": str(filepath), "sheets": []}

    try:
        for sheet in sheets:
            if sheet not in wb.sheetnames:
                file_log["sheets"].append(
                    {"sheet": sheet, "skipped": "sheet not present in workbook"}
                )
                continue

            df = df_all[sheet]
            year_cols = [c for c in df.columns if isinstance(c, int)]
            if not year_cols:
                file_log["sheets"].append(
                    {"sheet": sheet, "skipped": "no integer year columns found"}
                )
                continue

            allowed = identify_allowed_techs(df, year_cols, generation_techs)
            speculative = identify_speculative_techs(
                df, allowed, generation_techs
            )
            pool_map = build_pool_map(df, allowed, year_cols)
            mininv_map = build_mininv_map(df, year_cols)

            # Proportional-mode auxiliary maps. Cheap to build, computed
            # regardless of mode so the log captures them either way.
            tech_share_map = build_tech_share_map(df, allowed)
            scaled_pool_map = build_scaled_pool_map(pool_map, demand_mult_map)
            pool_delta_map = build_pool_delta_map(scaled_pool_map, year_cols)

            ws = wb[sheet]
            sheet_log = apply_lid_to_sheet(
                ws, allowed, pool_map, mininv_map, demand_mult_map,
                tech_share_map=tech_share_map,
                pool_delta_map=pool_delta_map,
                speculative_techs=speculative,
            )
            sheet_log["allowed_techs"] = sorted(allowed)
            file_log["sheets"].append(sheet_log)

        wb.save(filepath)
    finally:
        # Explicitly release Windows file handles so a subsequent
        # shutil.rmtree (e.g. in restore_from_backup or pytest tmp_path
        # cleanup) doesn't hit PermissionError [WinError 32].
        wb.close()
    return file_log


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def run(input_dir, sheets: list = None,
        yaml_path: Path | None = None,
        cli_overrides: dict | None = None) -> dict:
    """End-to-end: edit and write JSON log. Returns the log dict.

    When `yaml_path` is None, the script looks for YAML_FILE_NAME next to
    itself (where the orchestrator stages the per-scenario override). If
    found, its values replace the module-level defaults for this process.

    `cli_overrides`: dict applied AFTER the YAML so CLI flags win. Same
    schema as the YAML's parsed config (e.g. {"force_overwrite": True}).
    """
    input_dir = Path(input_dir)
    sheets = sheets or DEFAULT_TARGET_SHEETS

    # Optional YAML override (per-scenario). Located next to this script —
    # the orchestrator stages it there from rules_scripts/configs/<scenario>/.
    if yaml_path is None:
        yaml_path = Path(__file__).resolve().parent / YAML_FILE_NAME
    yaml_loaded = False
    if yaml_path.is_file():
        apply_config(load_config(yaml_path))
        yaml_loaded = True
    if cli_overrides:
        apply_config(cli_overrides)

    paramfile = input_dir / PARAM_FILE_NAME
    if not paramfile.exists():
        raise FileNotFoundError(f"{paramfile} not found")

    # Load the GENERATION tech list. TECH_TYPES.csv is shared by other A3
    # stages (e.g. patch_ao_c2a.py), so it lives in A3_process/, one level
    # above this script (which now lives in A3_process/rules_scripts/).
    generation_techs = None
    tech_types_path = None
    if RESTRICT_TO_GENERATION:
        script_dir = Path(__file__).resolve().parent
        tech_types_path = script_dir.parent / TECH_TYPES_FILE
        generation_techs = load_generation_techs(tech_types_path)

    # Load the per-cr demand multipliers (from the input dir).
    demand_mult_map: dict = {}
    demand_path = input_dir / DEMAND_FILE_NAME
    if LID_RAMP_FROM_DEMAND:
        demand_mult_map = build_demand_multiplier_map(
            demand_path, ref_year=DEMAND_REFERENCE_YEAR
        )

    log = edit_parametrization(
        paramfile, sheets, generation_techs, demand_mult_map
    )
    log["timestamp"] = datetime.now().isoformat()
    log["lid_percentage_default"] = LID_PERCENTAGE_DEFAULT
    log["lid_percentage_by_year"] = {
        str(k): v for k, v in LID_PERCENTAGE_BY_YEAR.items()
    }
    log["lid_percentage_by_year_by_prefix"] = {
        prefix: {str(k): v for k, v in sched.items()}
        for prefix, sched in LID_PERCENTAGE_BY_YEAR_BY_PREFIX.items()
    }
    log["lid_absolute_by_prefix"] = {
        p: float(v) for p, v in LID_ABSOLUTE_BY_PREFIX.items()
    }
    log["lid_flat_overrides_by_tech"] = {
        t: float(v) for t, v in LID_FLAT_OVERRIDES_BY_TECH.items()
    }
    log["lid_ramp_from_demand"] = LID_RAMP_FROM_DEMAND
    log["lid_rule_mode"] = LID_RULE_MODE
    log["lid_security_factor"] = (
        LID_SECURITY_FACTOR if LID_RULE_MODE == "proportional" else None
    )
    log["zero_is_placeholder_in_lid_rows"] = ZERO_IS_PLACEHOLDER_IN_LID_ROWS
    log["force_overwrite"] = FORCE_OVERWRITE
    log["restrict_to_generation"] = RESTRICT_TO_GENERATION
    log["generation_techs_count"] = (
        len(generation_techs) if generation_techs is not None else None
    )
    log["tech_types_file"] = str(tech_types_path) if tech_types_path else None
    log["demand_file"] = str(demand_path) if LID_RAMP_FROM_DEMAND else None
    log["demand_reference_year"] = (
        DEMAND_REFERENCE_YEAR if LID_RAMP_FROM_DEMAND else None
    )
    log["demand_mult_loaded"] = bool(demand_mult_map)
    log["yaml_config_path"] = str(yaml_path) if yaml_loaded else None

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = input_dir / f"lid_rule_changes_{stamp}.json"
    log_path.write_text(json.dumps(log, indent=2, default=str))
    log["log_path"] = str(log_path)

    return log


def print_summary(log: dict) -> None:
    """Pretty-print the run summary."""
    bar = "=" * 72
    print(bar)
    print("MaxCapacityInvestment lid + untie rule — applied")
    print(bar)
    print(f"Edited file   : {log['file']}")
    print(f"Rule mode     : {LID_RULE_MODE}"
          + (f"  (security factor = {LID_SECURITY_FACTOR})"
             if LID_RULE_MODE == "proportional" else ""))
    print(f"Lid base pct  : {LID_PERCENTAGE_DEFAULT * 100:.3f}% "
          f"(anchored at {DEMAND_REFERENCE_YEAR})")
    print(f"Demand ramp   : {'ON' if log.get('lid_ramp_from_demand') else 'OFF'}"
          f"{' (per country+region)' if log.get('demand_mult_loaded') else ''}")
    if log.get("force_overwrite"):
        print("Force-overwrite: ON — positive prior values in GEN MaxCapInv "
              "are overwritten with the new lid")
    print(f"GEN-only      : {'ON' if log.get('restrict_to_generation') else 'OFF'}"
          f" ({log.get('generation_techs_count')} GENERATION techs"
          f" loaded from {log.get('tech_types_file')})"
          if log.get('restrict_to_generation') else "")
    if LID_PERCENTAGE_BY_YEAR and LID_RULE_MODE == "uniform":
        # Collapse contiguous-equal pct runs for readable display.
        items = sorted(LID_PERCENTAGE_BY_YEAR.items())
        groups = []
        cur_start, cur_pct = items[0]
        cur_end = cur_start
        for y, p in items[1:]:
            if p == cur_pct and y == cur_end + 1:
                cur_end = y
            else:
                groups.append((cur_start, cur_end, cur_pct))
                cur_start, cur_end, cur_pct = y, y, p
        groups.append((cur_start, cur_end, cur_pct))
        sched = ", ".join(
            f"{a}-{b}:{p*100:g}%" if a != b else f"{a}:{p*100:g}%"
            for a, b, p in groups
        )
        print(f"Year schedule : {sched}")
    if LID_PERCENTAGE_BY_YEAR_BY_PREFIX and LID_RULE_MODE == "uniform":
        for prefix in sorted(LID_PERCENTAGE_BY_YEAR_BY_PREFIX):
            items = sorted(LID_PERCENTAGE_BY_YEAR_BY_PREFIX[prefix].items())
            if not items:
                continue
            groups = []
            cur_start, cur_pct = items[0]
            cur_end = cur_start
            for y, p in items[1:]:
                if p == cur_pct and y == cur_end + 1:
                    cur_end = y
                else:
                    groups.append((cur_start, cur_end, cur_pct))
                    cur_start, cur_end, cur_pct = y, y, p
            groups.append((cur_start, cur_end, cur_pct))
            sched = ", ".join(
                f"{a}-{b}:{p*100:g}%" if a != b else f"{a}:{p*100:g}%"
                for a, b, p in groups
            )
            print(f"  prefix {prefix:<4}  : {sched}")
    print()
    for s in log["sheets"]:
        if "skipped" in s:
            print(f"[SKIPPED] '{s['sheet']}': {s['skipped']}")
            continue
        years = s["years_found"]
        print(f"Sheet: '{s['sheet']}'")
        print(f"  Years          : {years[0]}..{years[-1]} ({len(years)} years)")
        print(f"  ALLOWED techs  : {s['allowed_count']}")
        spec_count = s.get("speculative_count", 0)
        if spec_count:
            spec_list = s.get("speculative_techs", [])
            preview = ", ".join(spec_list[:6])
            if len(spec_list) > 6:
                preview += " ..."
            print(f"  SPECULATIVE techs (absolute lid) : {spec_count}"
                  f"  [{preview}]")
        print(f"  Skipped non-PWR techs (e.g. TRN*) : "
              f"{len(s.get('skipped_non_pwr_techs', []))}")
        # Show the country+region pools at first and last year
        pool_keys = sorted(set(k.rsplit("_", 1)[0] for k in s["pool_map"].keys()))
        if pool_keys and years:
            print(f"  Country+region pools: {len(pool_keys)} "
                  f"({', '.join(pool_keys[:6])}{' ...' if len(pool_keys) > 6 else ''})")
        # Show the spread of pct used at first vs last year
        pct_map = s.get("lid_pct_by_cr_year", {})
        if pct_map and pool_keys:
            y_first, y_last = years[0], years[-1]
            sample_cr = pool_keys[0]
            pct_first = pct_map.get(f"{sample_cr}_{y_first}")
            pct_last = pct_map.get(f"{sample_cr}_{y_last}")
            if pct_first is not None and pct_last is not None:
                print(f"  Lid pct ({sample_cr}): "
                      f"{pct_first*100:.3f}% in {y_first} -> "
                      f"{pct_last*100:.3f}% in {y_last}")
        from collections import Counter
        reason_counts = Counter(c.get("reason", "?") for c in s["changes"])
        n_lid = reason_counts.get("lid_fill", 0)
        n_overwrite = reason_counts.get("lid_overwrite", 0)
        n_lid_abs = reason_counts.get("lid_fill_absolute", 0)
        n_ovw_abs = reason_counts.get("lid_overwrite_absolute", 0)
        n_untie = reason_counts.get("untie_min_inv", 0)
        n_other = (sum(reason_counts.values())
                   - n_lid - n_overwrite - n_lid_abs - n_ovw_abs - n_untie)
        print(f"  MaxInv cells written:")
        print(f"    - filled with lid (pct * pool)    : {n_lid}")
        if n_overwrite:
            print(f"    - overwritten by lid (force flag)  : {n_overwrite}")
        if n_lid_abs:
            print(f"    - filled with absolute lid (GW/yr) : {n_lid_abs}")
        if n_ovw_abs:
            print(f"    - overwritten by absolute lid      : {n_ovw_abs}")
        print(f"    - bumped by untie rule (>= MinInv) : {n_untie}")
        if n_other:
            print(f"    - other                            : {n_other}")
        print(f"  Manual values preserved              : {len(s['preserved'])}")
        print(f"  Projection.Mode flips (EMPTY -> User defined) : "
              f"{len(s['projection_mode_flips'])}")
    if log.get("log_path"):
        print(f"\nDetailed change log written to: {log['log_path']}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("A1_Outputs/A1_Outputs_BAU"),
        help="Directory containing the AO files (default: A1_Outputs/A1_Outputs_BAU)",
    )
    parser.add_argument(
        "--sheets",
        nargs="+",
        default=DEFAULT_TARGET_SHEETS,
        help=f"Sheets to apply the rule to (default: {DEFAULT_TARGET_SHEETS})",
    )
    parser.add_argument(
        "--restore",
        action="store_true",
        help="Restore input dir from the most recent legacy _PRE_LID_* backup, "
             "if one still exists alongside the scenario dir, then exit. "
             "Saves a snapshot of the current input dir as _POST_LID_pre_restore_<ts>/ "
             "before overwriting, so the restore itself is reversible.",
    )
    parser.add_argument(
        "--restore-from",
        type=Path,
        default=None,
        help="Restore input dir from this specific (legacy) backup folder, then exit.",
    )
    parser.add_argument(
        "--yaml",
        type=Path,
        default=None,
        help=f"Override YAML config path (default: {YAML_FILE_NAME} next to this script).",
    )
    parser.add_argument(
        "--force-overwrite",
        action="store_true",
        help="Treat every positive numeric value in MaxCapInv cells of "
             "GENERATION techs as a placeholder. Use to iterate on the lid "
             "schedule without restoring the xlsx between runs. Zeros in "
             "rows that have no 9999 anywhere (intentional bans) are still "
             "preserved. CLI flag overrides any YAML setting.",
    )
    args = parser.parse_args()

    # Restore-only paths: do nothing else.
    if args.restore or args.restore_from is not None:
        try:
            used = restore_from_backup(args.input_dir, args.restore_from)
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print(f"Restored {args.input_dir} from {used}")
        return 0

    cli_overrides: dict = {}
    if args.force_overwrite:
        cli_overrides["force_overwrite"] = True

    try:
        log = run(args.input_dir, args.sheets, args.yaml, cli_overrides=cli_overrides)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print_summary(log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
