# Country Management

RELAC TX includes tools for validating country data, generating templates for new countries, and consolidating sub-regional data.

## Technology-Country Matrix

The Technology-Country Matrix controls which technology-country combinations are active in the model. See {doc}`pipeline` (Stage A0) for generation instructions.

### Editing the Matrix

After generating `Tech_Country_Matrix.xlsx`:

1. Open the **Matrix** sheet.
2. Change any cell from `YES` to `NO` to disable a technology for a country.
3. Change from `NO` to `YES` to enable it.
4. Implausible combinations (highlighted in red) can be overridden if desired.

### NGS Unification

In the **NGS_Unification** sheet:

- Set a country to `YES` to merge CCG (Combined Cycle Gas) and OCG (Open Cycle Gas) into a single NGS (Natural Gas) technology.
- Set to `NO` to keep them separate.
- Aggregation follows the rules defined in the **Aggregation_Rules** sheet.

---

## Country Data Validator

**Script:** `scripts/tools/Z_validate_country_data.py`

Verifies that a country has complete and consistent data in the OSeMOSYS input CSV files.

### Usage

```bash
# Validate all countries
python scripts/tools/Z_validate_country_data.py

# Validate a specific country
python scripts/tools/Z_validate_country_data.py --country ARG

# Generate detailed report
python scripts/tools/Z_validate_country_data.py --country ARG --report

# Quiet mode (summary only)
python scripts/tools/Z_validate_country_data.py --quiet
```

### Command-Line Options

| Flag | Description |
|------|-------------|
| `--country`, `-c` | ISO-3 country code or `all` (default: all) |
| `--report`, `-r` | Generate a detailed validation report |
| `--quiet`, `-q` | Suppress verbose output |

### Validations Performed

The validator checks:

1. **SET membership**: Country appears in TECHNOLOGY, FUEL, EMISSION, and STORAGE sets.
2. **Technology type counts**: Minimum number of technologies per prefix:
   - PWR (Power): minimum expected
   - MIN (Mining): minimum expected
   - RNW (Renewable): minimum expected
3. **Required parameters**: Data exists for all required OSeMOSYS parameters (CapitalCost, FixedCost, VariableCost, ResidualCapacity, OperationalLife, CapacityToActivityUnit, etc.).
4. **Value ranges**: Parameter values fall within physically reasonable ranges.
5. **Demand profiles**: SpecifiedDemandProfile sums to approximately 1.0 per fuel/tech per year.
6. **Storage**: Storage technologies have matching parameters (CapitalCostStorage, OperationalLifeStorage, etc.).
7. **Referential integrity**: Technologies referenced in parameter files exist in the TECHNOLOGY set, and fuels exist in the FUEL set.

### Output Format

Results are displayed as:

- **PASS**: Check succeeded.
- **FAIL**: Critical issue that will cause model errors.
- **WARN**: Potential issue that should be reviewed.

---

## New Country Template Generator

**Script:** `scripts/tools/Z_generate_country_template.py`

Creates a complete set of CSV files with the minimum structure needed to add a new country to the model, using an existing country as a reference.

### Usage

```bash
# Read configuration from YAML
python scripts/tools/Z_generate_country_template.py

# Override via command line
python scripts/tools/Z_generate_country_template.py --new BLZ --ref GTM --region XX

# With interconnections to specific neighbors
python scripts/tools/Z_generate_country_template.py --new BLZ --ref GTM -i GTM MEX
```

### Command-Line Options

| Flag | Description |
|------|-------------|
| `--new`, `-n` | 3-letter ISO code for the new country |
| `--ref`, `-r` | 3-letter ISO code of the reference country to clone |
| `--output`, `-o` | Output directory path |
| `--interconnections`, `-i` | List of neighbor country codes for TRN links |
| `--region` | Region suffix (default: `XX`) |

### YAML Configuration

Alternatively, configure in `Config_country_codes.yaml`:

```yaml
template_generation:
  - new_country: BLZ
    reference_country: GTM
    region: XX
    centerpoint_lat: 17.19
    centerpoint_lon: -88.49
    interconnections: []    # Empty = no interconnections
```

### What It Generates

The script creates a `templates/{CODE}/` directory containing:

1. **SET CSVs**: TECHNOLOGY, FUEL, EMISSION, STORAGE entries for the new country.
2. **Parameter CSVs**: All OSeMOSYS parameter files with the new country's data (cloned and adapted from the reference).
3. **`merge_into_inputs.py`**: A helper script to merge the new country's files into the main `OG_csvs_inputs/` directory.

### Interconnection Handling

The generator handles various interconnection scenarios:

| Scenario | Behavior |
|----------|----------|
| No `interconnections` key | Copies the reference country's interconnection topology |
| `interconnections: []` (empty list) | No interconnections for the new country |
| `interconnections: [BOL, PRY]` | Creates TRN links to the specified neighbors |
| Fewer/more neighbors than reference | Dynamically adjusts TRN entries |

### TRN Code Structure

Cross-border **interconnection** technologies encode both endpoints (each with its own region):

```
TRN{COUNTRY1}{REGION1}{COUNTRY2}{REGION2}
```

For example: `TRNARGXXBOLXX` = interconnection between Argentina (region XX) and Bolivia (region XX).

:::{note}
Per-country transmission and dispatch technologies use a single-country form `{TYPE}{COUNTRY}{REGION}` instead — e.g. `RNWTRNARGXX`, `PWRTRNARGXX`, `RNWRPOARGXX`, `RNWNLIARGXX`, `TRNRPOARGXX`, `TRNNLIARGXX`, `DSPTRNARGXX`. These are added by Stage A2, not by the template generator.
:::

The generator correctly handles:
- Position-aware country code replacement.
- Alphabetical ordering of country pairs in interconnection codes.
- Fuel and mode-of-operation code transformations.

### Integration Workflow

After generating the template:

```bash
# 1. Generate the template
python scripts/tools/Z_generate_country_template.py

# 2. Review and customize the generated CSVs
# Edit files in templates/BLZ/ as needed

# 3. Merge into the main dataset
cd templates/BLZ/
python merge_into_inputs.py

# 4. Validate the new country's data
python scripts/tools/Z_validate_country_data.py --country BLZ --report
```

---

## Region Consolidation

Region consolidation merges multiple sub-regional datasets into a single unified region. This is useful when a country is modeled with geographic granularity but you want aggregated results.

### Configuration

Edit `Config_region_consolidation.yaml`:

```yaml
enabled: true

countries:
  BRA:
    regions: ["CN", "NW", "NE", "CW", "SO", "SE", "WE"]
    unified_region: "XX"
```

### Aggregation Rules

When consolidating regions, parameters are combined according to these rules:

**Averaged** (cost-like parameters):
- AvailabilityFactor, CapacityFactor, CapitalCost, FixedCost, VariableCost
- InputActivityRatio, OutputActivityRatio
- CapacityToActivityUnit, OperationalLife

**Summed** (quantity-like parameters):
- ResidualCapacity, SpecifiedAnnualDemand
- TotalAnnualMaxCapacity, TotalAnnualMaxCapacityInvestment
- StorageLevelStart, ResidualStorageCapacity

**Disabled** (skipped):
- CapacityOfOneTechnologyUnit, RETagTechnology
- TotalAnnualMinCapacity

### Processing

When enabled, region consolidation runs as part of Stage A1 preprocessing. It:

1. Groups data by country (across sub-regions).
2. Applies averaging or summing per the rules.
3. Replaces region codes with the unified region code.
4. Removes internal interconnections that become self-loops after merging.
