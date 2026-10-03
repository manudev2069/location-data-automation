# Location Data Automation - Final Fast Adaptive CSV Version

Generic, CSV-only data validation automation for large and differently structured datasets.

## Run
1. Open the project in VS Code.
2. Run `main.py` using **Run Python File**.
3. In the GUI, select one or multiple CSV files.
4. Click **Start Automation**.

## Adaptive schema
The system infers semantic roles from column names, sample values and reference/source evidence. Examples:
- `city`, `city_name`, `City Name`, `location_city` -> CITY
- `state`, `state_full_name`, `State Name`, `location_state` -> STATE
- `state_code`, `state_short_code`, `State Code` -> STATE_CODE
- `country`, `country_name`, `Country Name`, `location_country` -> COUNTRY
- `area`, `area_name`, `locality`, `district` -> AREA

Ambiguous fields are not blindly guessed.

## Fast location verification
The validator builds an in-memory hierarchy from the current CSV and verifies location relationships using unique normalized combinations:
- City + State + Country
- State + Country
- State Code -> State Name mapping

An optional reference file in `reference/locations.csv` is used where applicable. This prevents a small/incomplete reference file from incorrectly marking an entire master dataset as Unknown.

## Outputs
For each input file:

```text
output/<file-stem>/
├── validated_data.csv
├── unknown_data.csv
├── validation_report.csv
└── schema_report.csv
```

Only rows with `Validation_Status = Valid` are written to `validated_data.csv`.

## Learning
Approved/safe corrections are stored in:

```text
learning/learned_corrections.csv
```

Future runs can reuse previously learned corrections.

## CSV only
Excel/XLSX input is intentionally not supported. The project does not require `openpyxl`.

## Important
Source-hierarchy verification means the system verifies consistency within the incoming dataset. It is not an independent government/third-party authority check. For externally authoritative verification, provide a trusted master/reference dataset.
