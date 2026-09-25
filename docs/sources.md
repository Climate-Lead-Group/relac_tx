# Data Sources

This page catalogues where the data behind RELAC TX comes from: the external datasets and
national planning documents used to calibrate the model, and how internal assumptions and
tool defaults are distinguished from them.

The record here is a summary. The authoritative, parameter-by-parameter citation — which
sheet, which technology, which years, which exact source and how it was transformed — lives
in a `Fuentes` sheet added to the end of `A-O_Parametrization.xlsx`, `A-O_Demand.xlsx` and
`A-Xtra_Storage.xlsx` for every scenario (see {doc}`data-reference`). That sheet is generated
from the master table `inputs/config/data_sources.csv` by
[`add_fuentes_sheet.py`](../scripts/tools/data_patches/add_fuentes_sheet.py); editing a
source means editing the CSV and re-running that script, never the sheet itself.

## Primary external sources

| Source | What it provides |
|---|---|
| OLACDE — annual generation-by-source statistics and energy balance matrix (regional energy information system, Latin America and the Caribbean) | Existing generation mix shares by country (calibrates minimum/maximum generation floors); base-year (2023–2024) electricity demand, from generation plus net imports/exports; historical bilateral interconnection flows |
| National official electricity- and transmission-expansion planning documents (one set per country) | Minimum mandatory investment floors for generation and transmission, 2023–2039 (only committed/contracted/in-service projects); high-demand-growth scenarios, 2025–2050; for the Optimal (OPT) scenario, planned projects dated 2040–2050. See the country table below |
| IEA — World Energy Outlook 2020 (WEO 2020), via OSeMOSYS Global | Generation-technology capital and fixed costs (2019 USD/kW). OSeMOSYS Global maps each country to the closest WEO region (South America → Brazil; Mexico, Central America and the Caribbean → United States) and interpolates between the WEO's 2019/2030/2040 values, holding them constant after 2040 |
| IEA — World Energy Outlook 2025, Net Zero Emissions scenario | Haiti's 2025–2050 demand trajectory, in the absence of a national planning document (creates a step from OLACDE's 2024 value to the IEA's 2025 value) |
| World Bank — Commodity Markets Outlook, October 2024, via OSeMOSYS Global | International prices for coal, crude oil and natural gas, marked up 1.3× (OSeMOSYS Global's surcharge for imported fuels) |
| NREL — Annual Technology Baseline (ATB) 2024 | Storage capital costs (power and energy components, short- and long-duration); default technology operational lifetimes used throughout the model |
| PLEXOS-World 2015 dataset (Brinkerink et al., 2021), via Renewables.ninja and IRENA, through OSeMOSYS Global | Hourly 2015 capacity-factor profiles for solar PV, solar thermal and wind; monthly hydro profiles; hourly national demand profiles |
| Global Transmission Database v1.1 (Brinkerink et al., 2024), through OSeMOSYS Global | Existing cross-border interconnection capacity, refined against national transmission plans; gaps in some countries' plans were filled by IDB collaborators |
| DOE / Sandia — Global Energy Storage Database (GESDB), through OSeMOSYS Global | Existing storage capacity by country, from commissioned projects (only Argentina, Bolivia, Brazil, Haiti and Mexico have non-zero values) |
| ACER (2026), *European Resource Adequacy Assessment 2025* (ERAA), Annex III — ENTSO-E's scarcity price cap | Variable cost of the backstop technology (PWRBCK), used as the penalty for unserved energy — see {doc}`data-reference` for why this is a conservative feasibility penalty and not an estimate of the social cost of outages |

## National planning documents

Nineteen countries each contribute their own official planning document(s) for three
different things: generation-investment floors, transmission-investment floors, and the
high-demand growth scenario used from 2025 onward (a handful of countries publish no "high"
scenario and their central scenario is used instead — the exact case-by-case detail is in
`inputs/config/data_sources.csv`). The table below lists, per country, the primary document
used for the demand-growth scenario:

| Country | Document |
|---|---|
| Argentina | *Lineamientos y Escenarios para la Transición Energética al 2050* (Secretaría de Energía) |
| Bolivia | *Plan Eléctrico Referencial 2035* |
| Brazil | *Plano Decenal de Expansão de Energia 2034* and *Plano Nacional de Energia 2050* (EPE) |
| Barbados | *Barbados Action Plan / Roadmap 2030* |
| Chile | *Planificación Energética de Largo Plazo 2023–2027* (Ministerio de Energía) |
| Colombia | *Plan de Expansión de Referencia Generación 2025–2039* (UPME) |
| Costa Rica | *Plan de Expansión de la Generación 2024–2040* (ICE) |
| Dominican Republic | *Plan Energético Nacional 2022–2037* (CNE) |
| Ecuador | *Plan Maestro de Electricidad 2023–2032* |
| Guatemala | *Plan de Expansión de la Generación 2020–2050* (MEM / CNEE) |
| Honduras | *Plan Indicativo de Expansión de la Generación 2026–2035* (ENEE / CND) |
| Haiti | none — see IEA WEO 2025 (NZE) above |
| Mexico | *Programa de Desarrollo del Sistema Eléctrico Nacional 2024–2038* (PRODESEN, SENER) |
| Nicaragua | *Plan Indicativo de Expansión de la Generación 2021–2035* (MEM) |
| Panama | *Plan de Expansión del Sistema Interconectado Nacional 2025–2039*, Tomo II (ETESA) |
| Peru | Annex D.1 of COES report DP-02-2022 (SEIN Transmission Plan 2023–2032) |
| Paraguay | *Plan Maestro de Generación 2024–2043* (ANDE) |
| El Salvador | *Plan Indicativo de la Expansión de la Generación 2024–2038* (CNE) |
| Uruguay | *Plan de Expansión de la Generación 2024–2043* (UTE) |

## Assumptions set by the modelling team

Some parameters are not taken from an external source; they were set directly by the CLG
modelling team, generally to keep the optimisation well-behaved rather than to represent a
published forecast:

- **Annual capacity-growth caps** for new generation investment (a declining percentage of
  each country's existing capacity, by technology). Introduced because, without a cap, the
  model's cost-minimisation produced unrealistic, disproportionate capacity build-outs.
- **Solar and wind annual capacity ceilings** in the Reference (BAU) scenario, for the same
  reason; the team's supporting documentation for these specific ceilings is not archived in
  the repository.
- **Internal transmission network cost estimates**, per country, carried over from an earlier
  version of the model (August 2025); the original estimation methodology is not documented.
- **Internal transmission network technical lifetime** (50 years, all countries).
- **The trend (Vegetativo A / INV) scenario's transmission investment cap**, derived from the
  Reference scenario's own model results rather than from any external document.

## OSeMOSYS Global internal defaults

A number of parameters are neither externally sourced nor a team assumption — they are
default values or structural conventions built into the OSeMOSYS Global tool itself, applied
uniformly by the software rather than calibrated to this region:

- Technology availability factors and reserve-margin tags.
- The temporal structure (12 timeslices: 4 seasons × 3 daily blocks) and the physical
  capacity-to-energy conversion constant.
- Default unit costs for transmission lines (converter and per-km costs) and their fixed
  O&M rate.
- Fixed default fuel costs for uranium, biomass and waste.
- The storage-to-technology linkage structure (which technology charges and discharges each
  storage reservoir) — a modelling-structure choice, not a data value.
