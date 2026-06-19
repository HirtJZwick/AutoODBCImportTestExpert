# testXpert III — Organization Data Import

A tool to automate the import of customer/organization data into testXpert III
without having to manually create custom parameters.

---

## The Problem

Importing customer-specific data (customer name, job number, material, specimen
dimensions, etc.) into testXpert III currently requires:

- Manually defining custom parameters in the XML configuration
- Re-doing the work for every new customer

This is fragile, time-consuming, and doesn't scale.

---

## The Solution

Instead of creating new parameters, this project uses **ZIMT scripts** to read
data directly from the customer's database (via ODBC) and write it into the
**existing built-in parameters** of testXpert III.

The workflow is:

1. The customer provides their database (Access, Oracle, SQL Server, ...)
2. A Python tool analyzes the database schema and suggests how each column
   should map to a built-in testXpert parameter
3. The tool generates an INI config file describing the mapping
4. A single generic ZIMT script reads the INI and imports the data before each test

The ZIMT script is the same for every customer — only the INI file changes.

---

## How the ZIMT Script looks like

; ============================================
; Generic Database Import Script
; Reads mapping from customer INI config file
; ============================================

; --- Load connection settings ---
Var sConfigFile String = "C:\ProgramData\zwick\configs\generated_ini_file.ini"
Var sODBC String = GetIniString(sConfigFile, "Connection", "ODBC")
Var sTable String = GetIniString(sConfigFile, "Connection", "Table")
Var sKey String = GetIniString(sConfigFile, "Connection", "KeyColumn")
Var sRowCol String = GetIniString(sConfigFile, "Connection", "RowNumColumn")

DataBase sODBC, sTable, sKey

Var nRow Num = P[48144]
Var sCondition String = sRowCol + "=" + NumToStr(nRow)

; --- Import Specimen-level text parameters ---
Var nSpecCount Num = GetIniNum(sConfigFile, "SpecimenMapping", "Count")
Var i Num = 1
While i <= nSpecCount
    Var sCol String = GetIniString(sConfigFile, "SpecimenMapping", "Col" + NumToStr(i))
    Var nParam Num = GetIniNum(sConfigFile, "SpecimenMapping", "Param" + NumToStr(i))
    Var sVal String = ReadDataBaseString(sCol, sCondition, 1)
    CheckDataBase
    T[nParam] = sVal
    i = i + 1
EndWhile

; --- Import Numeric specimen-level parameters ---
Var nNumCount Num = GetIniNum(sConfigFile, "NumericMapping", "Count")
i = 1
While i <= nNumCount
    Var sCol2 String = GetIniString(sConfigFile, "NumericMapping", "Col" + NumToStr(i))
    Var nParam2 Num = GetIniNum(sConfigFile, "NumericMapping", "Param" + NumToStr(i))
    Var nVal Num = ReadDataBaseNum(sCol2, sCondition, 1)
    CheckDataBase
    P[nParam2] = nVal
    i = i + 1
EndWhile

; --- Import Series-level parameters (only on first specimen) ---
If P[48144] = 1
    Var nSerCount Num = GetIniNum(sConfigFile, "SeriesMapping", "Count")
    i = 1
    While i <= nSerCount
        Var sCol3 String = GetIniString(sConfigFile, "SeriesMapping", "Col" + NumToStr(i))
        Var nParam3 Num = GetIniNum(sConfigFile, "SeriesMapping", "Param" + NumToStr(i))
        Var sVal3 String = ReadDataBaseString(sCol3, sCondition, 1)
        CheckDataBase
        T[nParam3] = sVal3
        i = i + 1
    EndWhile
EndIf



## How the INI File Works

The INI file is a simple mapping between the customer's database column names
and the internal testXpert parameter IDs.

Example for a Porsche database:

```ini
[Connection]
ODBC=Porsche_DB
Table=TestData
KeyColumn=S:SampleID
RowNumColumn=RowNum

[SeriesMapping]
Count=1
Col1=Kundenname
Param1=1065

[SpecimenMapping]
Count=2
Col1=SampleID
Param1=1701
Col2=Teilnummer
Param2=1703

[NumericMapping]
Count=2
Col1=Dicke
Param1=1031
Col2=Breite
Param2=1032
```

For a new customer with different column names (e.g. `Client`, `Thickness_mm`),
only the INI file is updated — the ZIMT script stays the same.

---

## Usage

```bash
python main.py
```

The tool will ask for the ODBC DSN, let you pick a table, and walk you through
generating the INI file.

The generated INI is then referenced by the generic ZIMT script in testXpert.

---

## Requirements

- Python 3.10+ (32-bit if the customer uses MS Access)
- pyodbc
- openai
- An ODBC DSN configured for the customer's database

Install Python dependencies with:

```bash
python -m pip install -r requirements.txt
```

## GitHub Models Mapping

The parameter mapper can use GitHub Models with `openai/gpt-5-mini` to suggest
mappings from customer database columns to built-in testXpert III parameters.
The project uses the `openai` Python package as a client library, but the API
request is sent to GitHub Models, not to an OpenAI account.

Set your GitHub Models token as an environment variable instead of storing it in
source code:

```powershell
setx GITHUB_TOKEN "your_github_models_token_here"
```

Alternatively, you can use `GITHUB_MODELS_TOKEN` if you want a more specific
variable name.

Restart VS Code after setting the variable permanently.

The mapper uses `Config/testxpert_parameters.json` as the allowed parameter
catalog. The model is only allowed to suggest IDs from that catalog, so expand
that file as more built-in testXpert parameters become available.

---


## Author

Johannes Hirt — Intern Service, ZwickRoell
