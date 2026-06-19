# Copilot Instructions for AutoODBCImportProject

## Testing After Code Changes

After **every** code change to any file in `src/`, automatically run the test suite:

```
.\zwick_venv_py313_32\Scripts\python.exe -m pytest tests/ -v --tb=short
```

- If all tests pass: report the summary and continue.
- If any test fails: report the failure details and fix the issue before finishing the task.
- After running tests, append a one-line result to the `## Log of the tests conducted` section in `Test.md` using this format:

```
| <short description of change> | <YYYY-MM-DD HH:MM> | Passed / Failed | <pytest summary line> |
```

## Test Coverage

The test suite covers the 4 items defined in `Test.md`:

| Test file | Covers |
|---|---|
| `tests/test_database_connector.py` | DB connection (Test.md item 1) and table/column/data retrieval (item 2) |
| `tests/test_parameter_mapper.py` | Column header transfer to mapper (item 3) and parameter mapping (item 4) |

## Project Structure

- Source code: `src/`
- Tests: `tests/`
- Config: `Config/Porsche_config.ini`, `Config/testxpert_parameters.json`
- Python venv: `zwick_venv_py313_32\Scripts\python.exe`
