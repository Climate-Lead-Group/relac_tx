# Scenarios

The analysis is organised in four **scenario families**. Each family has a base scenario and, for the two main families, a set of sensitivity variants on repowering and on cost assumptions. Model codes (the identifiers used in configuration files and result CSVs) are shown in monospace.

| Family | Meaning | Base scenario | Variants |
|---|---|---|---|
| **OPT** | Optimal expansion | `BAC` | `BSR` without repowering · `BFA` / `BFB` fossil-fuel cost high / low · `BRA` / `BRB` renewables cost high / low |
| **ETT** | Trend (*tendencial*) expansion | `ISR` | `INV` with repowering · `IFA` / `IFB` fossil-fuel cost high / low · `IRA` / `IRB` renewables cost high / low |
| **PLAN** | Planned expansion (national plans only) | `OPC` | — |
| **ETT-GP** | Trend expansion with planned generation | `VSR` | — |

## Reading a scenario code

- **First letter:** `B` = optimal family (OPT), `I` = trend family (ETT).
- **Suffixes:**
  - `SR` — without repowering (*sin repotenciación*).
  - `FA` — fossil-fuel cost **high** (*combustible fósil alto*).
  - `FB` — fossil-fuel cost **low** (*combustible fósil bajo*).
  - `RA` — renewables cost **high** (*renovables alto*).
  - `RB` — renewables cost **low** (*renovables bajo*).
- `INV` is the trend family **with** repowering (the ETT base `ISR` is `INV` without repowering).

:::{note}
The multipliers of the renewables-high variants (`BRA`, `IRA`) are pending calibration; in the current configuration they equal those of `BRB` / `IRB`. Their results should be read as provisional.
:::

## How the scenarios are built

The four families derive from four input workbooks (`BAU`, `INV`, `OPT`, `VGB`) through the transmission-constraint chain of Stage B2: dispatch floors, cross-scenario transmission constraints and a registry of scenario transforms that create the variants by changing parameter values only. The full mapping from each code to its base workbook and generating script, together with the list of scenarios actually solved, is in the *Scenario codes* table of {doc}`../pipeline`.
