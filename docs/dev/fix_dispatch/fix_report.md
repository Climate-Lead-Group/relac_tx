# Fix Report: candidate_floors.csv build (second pass)

Covers Step 1 (Peru/Uruguay diagnosis), the CF-fill and tier-classification
decisions from Steps 2-3, a genuine aggregation bug found and fixed during
Step 4, and the Step 5 automated review results. No em dashes are used in
this report.

## Step 1: Peru and Uruguay

Both countries' reported totals (143,168 MW for Peru, 33,455 MW for Uruguay)
turned out to share the exact same root cause: a naive sum of `capacity_mw`
across all rows for that country ignores the `cumulative_or_annual` column
that pass 1 already attached to every row.

### Peru (PER)
`out_PER.csv` (125 rows) contains two different views of the same underlying
pipeline: 105 genuine annual project-level rows (`cumulative_or_annual`=
annual, one row per named EPO-approved wind/solar project, summing to
22,019.9 MW) and 20 CUMULATIVE technology-by-year rollup rows (Cuadro 5
"epo_approved_all" and Cuadro 6 "epo_approved_with_concession", an alternate
aggregate presentation of the same 105 projects). A naive sum of all 125 rows
double-counts: 143,167.9 MW.

Fix: kept only the 105 `annual` rows; dropped the 20 cumulative rollup rows
entirely from the capacity-forcing computation (`fix_per_ury.py`). Corrected
total: 22,019.9 MW, which matches `PER_PSR_BASE.pdf`'s own stated headline of
22,021 MW through 2030 (p.11), independently confirmed in pass 1's
verification step.

### Uruguay (URY)
All 60 rows for the chosen central scenario (Caso B) are tagged
`cumulative_or_annual`=cumulative: installed MW by year for WON/SPV/OIL,
2024-2043, not annual additions. This is not a scenario-duplication bug (the
pass-1 merge already filtered to Caso B only); it is a cumulative-vs-annual
handling gap. Summing 20 years of a monotonically growing cumulative series
naturally overstates new capacity by roughly an order of magnitude:
33,455.0 MW naive sum.

Fix: derived annual additions per technology by differencing consecutive
years of the cumulative series (`fix_per_ury.py`), baseline 0 since Caso B's
own 2024 value is already 0 for all three technologies. No negative diffs
were found (the series is genuinely monotonic, as pass 1 had already
verified). Corrected total: 4,081 MW (WON 2,245 + SPV 1,215 + OIL 621),
matching pass 1's own verified headline and Uruguay's plausible system scale
(current installed base approximately 5.3 GW).

Both fixes are in `fix_per_ury.py`, applied to `lac_capacity_additions.csv`
to produce `lac_capacity_additions_fixed.csv`, the input to every subsequent
step.

## Step 2: CF gap filling

630 of 878 rows (post Peru/Uruguay fix: 610 of 833) had `cf_basis`=none.
Filled per `fill_cf_gaps.py` using the stated hierarchy:

- 220 rows already had stated/derived CF, untouched.
- 3 rows filled from the same country's own median stated/derived CF for
  that technology (`proxy_incountry`): mostly a single Argentina URN row
  (Base-scenario nuclear given no CF of its own, borrowed from the same
  country's UNICEN-derived nuclear CF of 0.8999).
- 479 rows filled from the regional median across all 17 countries'
  stated/derived CFs for that technology (`proxy_regional`). Most countries
  in this dataset (Chile, Mexico, Panama, Peru, Paraguay, El Salvador,
  Guatemala, Bolivia) have zero stated/derived CF anywhere in their own
  extraction, so almost every non-storage row in those countries relies on
  the regional median.
- 2 rows (CSP, Mexico) filled from the fallback table: no country anywhere
  in the dataset has a stated or derived CSP value.
- 129 storage rows (LDS, SDS) forced to `cf_value`=0 per the task rule
  (storage does not generate net energy, no dispatch floor). 3 of these had
  a pre-existing "stated" CF in the source data (Honduras battery storage,
  0.17, an availability/dispatch factor, not a generation CF); that original
  value is preserved in the row's note for traceability but not used for
  `cf_value`/`floor_PJ`.

Regional median table computed (stated/derived pool only): BIO 0.2581, COA
0.85, GEO 0.8135, HYD 0.4847, NGS 0.2779, OIL 0.0883, SPV 0.2171, URN 0.8999,
WON 0.4291. Full in-country and regional tables are in `cf_fill_report.json`.

NOTE: the regional NGS median (0.2779) and BIO median (0.2581) turned out to
be implausibly low for a technology being FORCED to run at a floor (mostly
reflecting older, less-utilized peaker/backup CF values pulled into the
pooled median from a couple of countries). This was caught and corrected in
Step 5b below, not in Step 2 itself, since Step 2's job is to follow the
stated hierarchy mechanically; Step 5b is where plausibility gets checked.

## Step 3: FILTERED/FULL tier classification

Implemented in `tier_classify.py`. Country by country:

**BRA**: note field carries the PDE2034 category verbatim. "contratado" ->
FILTERED (11 rows: contracted/auction-awarded wind, solar, hydro, biomass).
"indicativa" or "MMGD" -> FULL only (56 rows: optimizer-chosen indicative
capacity plus the distributed-generation trend projection, neither of which
is an auction outcome).

**MEX**: scenario field distinguishes T4.1-T4.8 (PVIRCE, government/CFE-
programmed, firm commissioning dates, per the task brief) from T4.9
(particulares, private/market-driven, indicative). PVIRCE -> FILTERED (169
rows). Particulares -> FULL only (34 rows).

**COL**: the entire 22-row extraction comes from Tabla 4 "Cronograma
expansion fija" under the Escenario de referencia. Pass 1 already confirmed
this table contains ONLY named, already-awarded/under-construction projects
(Hidroituango II, Colectora 1 wind, CxC-auction solar, scheduled distributed
solar), with zero indicative optimizer-added capacity mixed in (that only
appears in the alternative expansion scenarios, section 7, which pass 1 did
not extract). No literal "comprometido" keyword appears in the notes, but the
scenario methodology itself makes this determination unambiguous. All 22 COL
rows -> FILTERED.

**HND**: Tabla 8 (p.33) explicitly lists two 2026 "proyectos comprometidos"
that pass 1 folded into Tabla 43's 2026 column: Solar PV Patuca (44 MW) and
Bateria Amarateca (75 MW / 300 MWh). The SPV row naming "Patuca" and the
unique 75 MW SDS row in 2026 -> FILTERED (2 rows, 119 MW). The remaining 35
rows (the rest of the indicative Escenario V least-regret optimization) ->
FULL only.

**GTM, PAN, CRI**: investigated specifically for the signals the task brief
named, and NONE could be substantiated in this pass's extracted data (see
"GTM PEG-5 investigation" and "HND LPI, PAN, CRI notes" below). Per the
task's own fallback rule ("if ambiguous, default to FULL only and note the
ambiguity"), all three countries' rows -> FULL only, same as the 9 countries
the task brief explicitly listed as having no split.

**The 9 brief-listed countries** (CHL, BOL, NIC, SLV, ECU, DOM, ARG, PRY,
URY): all rows -> FULL only, per the task brief.

### GTM PEG-5 investigation (why GTM ended up FULL-only despite a specific brief claim)

The task brief states: "GTM: PEG-5 adjudicated projects (1,505 MW across 57
projects, supply-start 2030-2033) = FILTERED." This was checked directly
against `GTM_PEIG_2024-2054.pdf` (pages 88, 92, 94, 142-144, all mentioning
PEG-5). The document itself says: "En algunos escenarios, se tomara en cuenta
un supuesto del PEG-5 para la incorporacion de 1,200 MW" (p.88, an ASSUMPTION
of 1,200 MW, not 1,505 MW, not "adjudicated"), and explicitly recommends
(p.144) that the PEG-5-2024 tender process START in early 2024 and conclude
adjudication "a mas tardar en el ano 2025". This document predates the
tender's conclusion; it treats PEG-5 as a future hypothetical, and only
PEG-4 (a separate, already-concluded tender, "mas de 200 MW") is described as
"adjudicadas". Since the current date in this pass is well after the
document's own 2025 target for PEG-5's conclusion, the 1,505 MW / 57-project
figure the task brief cites is plausibly a real, more recent result that
postdates this PDF, but it is not present in it. No technology breakdown for
those 57 projects was given in the task brief either. Per "no invented
data", this figure was NOT added to candidate_floors.csv (adding it would
require guessing a technology split across 57 unnamed projects). GTM's
FILTERED tier is empty; this gap is disclosed here rather than silently
resolved either way.

### HND LPI, PAN, CRI notes

- **HND**: no "LPI" acronym and no tender text matching "800 MW 2027 + 300 MW
  2028 + 400 MW 2030" was found anywhere in `HND_PIEG_2026-2035.pdf` (checked
  by keyword search across all pages). Like GTM's PEG-5, this may be real,
  more recent information not present in this planning document; not added
  without a source or technology breakdown. HND's FILTERED tier already has
  a real, plan-sourced 119 MW from Tabla 8 (Patuca + Amarateca, above).
- **PAN**: the task brief named "Cuadro A4.1... capacidad firme" as the
  FILTERED signal. Pass 1 already established that Cuadro A4.1 does not
  physically exist in `PAN_PESIN_2025-2039_TomoII.pdf` (full-text search
  found zero matches); the only usable schedule is Tabla 7.3, which gives
  each project a named commercial "Agente" and entry month but no firm/
  under-construction flag. Most projects have a real named company (not
  "GENERICA", which is reserved for a handful of placeholder thermal
  candidates), which is suggestive of a real interconnection-queue project
  but is not the same as a stated "capacidad firme" flag. Defaulted to FULL
  only per the fallback rule; the ambiguity (named agent vs. a genuine
  firm-capacity flag) is noted here rather than guessed.
- **CRI**: the task brief named Tabla 15.1's "proyectos confirmados" as the
  FILTERED signal. Pass 1's extraction of Tabla 15.1 does not preserve a
  per-row confirmed/indicative flag (every line item was extracted uniformly
  as part of the Plan Recomendado schedule). Guessing a cutoff year (e.g.
  "early years are confirmed, later years are indicative") would be
  inventing a rule the source does not state at the row level pass 1
  captured, so this was not done. Defaulted to FULL only.

## Step 4: model conversion, and a real aggregation bug found and fixed

`TECHNOLOGY` (`PWR`+fuel+country+`XX`) is country+fuel level, not
plant-level. Peru has 33 separate solar projects all commissioning in 2026
alone; Mexico has up to 8 separate regional entries for the same fuel in the
same year (42 of 65 distinct Mexico tech-year combinations have more than one
underlying source row). An early version of `build_candidate_floors.py` kept
one row per source vintage without aggregating vintages that land on the
same (country, tech, year); this silently DROPPED every vintage but one
whenever two source rows shared a key. It was caught by Step 5d's own
sanity check: Peru's total collapsed to 2.5 GW (expected 3-25 GW) and
Mexico showed FILTERED GW exceeding FULL GW, which is structurally
impossible since FILTERED is a subset of FULL.

Fixed by rewriting the aggregation to sum, not overwrite: every vintage is
expanded from its own commissioning year through 2050, then for each
(country, tech, YEAR) all still-active vintages (commissioning_year <= YEAR)
are SUMMED (forced_GW summed; floor_PJ summed as the sum of each vintage's
own forced_GW x its own CF x 31.536, i.e. a properly blended floor across
vintages that may carry different CFs). This is also what a real OSeMOSYS
parameter table requires: one value per (TECHNOLOGY, YEAR), never duplicate
keys (`write_floors.py`'s own docstring flags duplicate tech-year rows as a
GLPK error). Full per-project detail (every individual vintage, its own
year/MW/CF/source) is preserved in `candidate_floors_vintage_detail.csv`
since the main file's note field would otherwise need to list all 33 of
Peru's simultaneous 2026 solar projects inline.

`period_block` rows are distributed evenly across their declared year range
before this aggregation; `total_only` rows are assigned to the midpoint year
of their period_start/period_end. Vintages with a resulting commissioning
year outside 2023-2050 are dropped (Ecuador's 2018-2022 historical rows: 27
vintages; Chile's 2055/2060 vintages: 13; Guatemala's 2051-2054 slice of its
2044-2054 period block: 4; one Dominican Republic and one Nicaragua
period-block slice landing on 2022 each: 2 and 1 respectively).

## Step 5: automated review

**5a** (folded into `build_candidate_floors.py` directly, not injected after
the fact, so it aggregates correctly with existing plan data): Angra 3
nuclear (BRA, 1.405 GW, 2031, 66% built) is a genuinely new (country, tech)
pair, no existing BRA URN rows. Chile's 4.16 GW storage-under-construction
(2025-2027) aggregates with 27 pre-existing CHL SDS rows from the plan
itself. Dominican Republic's 1.6 GW new gas (2026-2030) aggregates with 1
pre-existing DOM NGS row. Bolivia, Nicaragua, El Salvador, Ecuador,
Argentina, Paraguay, and Uruguay: correctly left at 0, no firmly committed
new capacity identified; their FILTERED tier stays empty.

**5b**: checked 30 (country, tech) curves with final forced_GW >= 0.5 GW and
a proxy `cf_basis`. Corrected 6: MEX and PAN and SLV's NGS regional-median CF
(0.2779, below the 0.30 plausibility floor for gas capacity being forced to
run) corrected to the fallback table's 0.55; ARG and CHL's BIO regional-
median CF (0.2581, below the 0.30 floor) corrected to the fallback table's
0.55. This directly addresses the low-NGS/BIO-median issue flagged in Step 2.
The other 24 checked curves (BRA URN, DOM NGS, MEX/ARG/BOL/CHL/ECU/GTM/PAN/
PER/PRY HYD/SPV/WON, etc.) were within their plausibility bands and kept
as-is. cf_basis for corrected rows is suffixed `_corrected_5b` for
traceability.

**5c**: printed the 15 largest FILTERED (country, TECHNOLOGY) aggregates by
forced_GW (led by MEX SPV 25.0 GW, MEX WON 20.4 GW, MEX NGS 18.9 GW post-
correction, COL SPV 10.6 GW, MEX SDS 8.65 GW). None carried an indicative/
aspirational marker; 0 demotions were needed.

**5d**: 0 problems on the final run. Country totals all under the 200 GW
ceiling (largest: CHL 105.0 GW, ARG 54.7 GW, MEX 80.9 GW). Peru: 22.02 GW
(within the 3-25 GW plausibility band). Uruguay: 4.08 GW (within the 3-5.5 GW
band). FILTERED <= FULL holds for every country. Proxy CF bounds hold for
every remaining proxy row (stated/derived low-CF thermal peakers, e.g. Costa
Rica's OIL rows at 3-9%, are correctly exempted from this bound since they
are the plan's own numbers, not a proxy fill).

Final tally: 6 of 17 countries have a non-empty FILTERED tier (BRA, CHL,
COL, DOM, HND, MEX); 11 are FULL-only (ARG, BOL, CRI, ECU, GTM, NIC, PAN,
PER, PRY, SLV, URY).

## Deliverables

- `candidate_floors.csv`: final, 5,106 rows. Columns:
  `tier,Scenario,TECHNOLOGY,country,fuel,YEAR,forced_GW,CF,floor_PJ,cf_basis,value_type,scenario_source,commissioning_year,note`.
  The `Scenario` column (BAU/INV/OPT/VGB, matching `relac_io.py`'s
  `SCENARIOS` list) is included alongside `tier` so this file is a drop-in
  replacement for the existing placeholder that `write_floors.py` reads;
  FILTERED rows carry Scenario BAU and INV, FULL rows (all committed plus
  indicative capacity) carry Scenario OPT and VGB.
- `candidate_floors_summary.csv`: one row per country per tier.
- `candidate_floors_vintage_detail.csv`: every individual project/vintage
  before aggregation, for full traceability back to the pass-1 extraction.
- Rerunnable scripts, in pipeline order: `fix_per_ury.py`,
  `fill_cf_gaps.py`, `tier_classify.py`, `build_candidate_floors.py`,
  `review_and_finalize.py`, `build_summary.py`.
- This file lives in the working folder (`_Dataset_Power`), not the shared
  `cirelac/fix_dispatch_solved` folder, per instruction; nothing in that
  shared folder was modified.
