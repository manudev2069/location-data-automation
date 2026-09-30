# Location Data Automation - MULTI FILE SELECT

## Exactly how this version works

The program DOES NOT scan the `input` folder.

The program DOES NOT automatically process every file in the project.

You decide which files to process AFTER pressing Run.

### Step 1
Open `main.py` in VS Code.

### Step 2
Click:

**▶ Run Python File**

### Step 3
A GUI opens with:

**Select File(s)**

Click it.

### Step 4
A normal Windows file picker opens.

You can select:
- one CSV
- multiple CSV files
- one Excel file
- multiple Excel files
- a mixture of CSV + XLSX

To select multiple files in Windows:
- hold `Ctrl` and click individual files, OR
- hold `Shift` to select a range.

Then click **Open**.

### Step 5
The selected files appear in the GUI list.

Example:

```text
Files selected: 3

Master Location Ranking.xlsx
Colleges.csv
Institutes.csv
```

### Step 6
Click:

**▶ Start Automation**

The GUI processes only the files you selected.

It does NOT scan other files in the folder.

## Progress

The progress bar is for ALL selected files combined.

It shows:
- current file
- current stage
- percentage
- processed rows / total rows
- total Valid
- total Unknown

Example:

```text
File 2 of 3: Colleges.csv
Verifying city: city

████████████████░░░░░░░
67.4%

250,000 / 371,000 rows
```

## Output

Every selected file gets its own output folder.

Example:

```text
output/
├── Master Location Ranking/
│   ├── validated_data.csv
│   ├── unknown_data.csv
│   └── validation_report.csv
│
├── Colleges/
│   ├── validated_data.csv
│   ├── unknown_data.csv
│   └── validation_report.csv
│
└── Institutes/
    ├── validated_data.csv
    ├── unknown_data.csv
    └── validation_report.csv
```

## Supported input

- `.csv`
- `.xlsx`

The program does not require files to be placed in an `input` folder.

You can select files from Desktop, Downloads, OneDrive, any project folder,
or any other accessible location.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Required packages:

- pandas
- openpyxl

No `rapidfuzz` dependency is required.

## Important

Before production use, replace `reference/locations.csv` with the team's
complete approved Location Master.

Only rows marked `Validation_Status = Valid` are written to
`validated_data.csv`.
