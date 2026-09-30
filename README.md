# Location Data Automation

Location Data Automation is a Python-based tool for validating, cleaning, correcting, and verifying CSV and Excel data before database processing.

## Features

- Select one or multiple CSV/Excel files
- Automatic data validation
- Detect special characters and invalid symbols
- Validate numeric fields
- Validate date fields
- Detect garbled or corrupted text
- Detect unknown or new columns
- Verify city, state, and country values
- Safely auto-correct common data issues
- Move invalid values to the `Unknown` field
- Generate validation status for each row
- Show real-time processing progress
- Generate separate output files for each input file

## Supported File Formats

- CSV (`.csv`)
- Excel (`.xlsx`)

## Project Structure

```text
Location_Data_Automation/
│
├── main.py
├── app.py
├── fast_validator.py
├── location_verifier_fast.py
├── requirements.txt
├── README.md
│
└── reference/
    └── locations.csv

    How It Works
CSV / Excel File
       ↓
Data Validation
       ↓
Special Character Check
       ↓
Numeric & Date Validation
       ↓
Garbled Text Detection
       ↓
Unknown Column Detection
       ↓
Location Verification
       ↓
Safe Auto Correction
       ↓
Re-Validation
       ↓
Valid Data
       ↓
validated_data.csv

Invalid or unresolved data is separated:

Invalid / Unknown Data
       ↓
unknown_data.csv
       ↓
Manual Review / Correction
Output

For every selected file, a separate output folder is created.

Example:

output/
│
├── Master Location Ranking/
│   ├── validated_data.csv
│   ├── unknown_data.csv
│   └── validation_report.csv
│
└── Colleges/
    ├── validated_data.csv
    ├── unknown_data.csv
    └── validation_report.csv
validated_data.csv

Contains only records that successfully pass the validation checks.

These records are intended for further database processing.

unknown_data.csv

Contains records with invalid, unknown, or unresolved values.

validation_report.csv

Contains validation details including:

Validation Status
Correction Status
Unknown Values
Unknown Columns
Validation Reasons
Example

If the input contains:

City = Srinagar$

The automation can safely correct it to:

City = Srinagar

The original problematic value is retained in the unknown information for tracking.

For an invalid numeric value:

city_rank = ABC

The invalid value is removed from the main field and recorded as unknown.

The row will be marked:

Validation_Status = Unknown

until the issue is resolved.

Installation

Install the required packages:

pip install -r requirements.txt
Run the Application

Run:

python main.py

A GUI window will open.

Click:

Select File(s)

Select one or multiple CSV/Excel files.

Then click:

▶ Start Automation

The application will process the selected files and generate the output automatically.

Validation Status
Valid

The record has passed the required validation checks and is ready for the next processing stage.

Unknown

The record contains an invalid, unknown, or unresolved value and requires review.

Reference Data

The file:

reference/locations.csv

contains the reference location data used for location verification.

For production use, this sample reference data should be replaced with the organization's approved Location Master.

Technology
Python
Pandas
OpenPyXL
Tkinter
CSV
Excel
Reference-based Location Validation
Future Scope
PostgreSQL database integration
Automated database upload
Complete Location Master integration
Advanced data quality validation
Automated data quality reports
Scheduled validation
API-based validation