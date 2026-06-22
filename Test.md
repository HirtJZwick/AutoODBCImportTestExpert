## Tests to be conducted every time the source code changes in this project

1. Make sure that the appliacation is able to connect to the database Porsche_DB
2. Make sure the table of the database can be retrieved and the data visualized
3. Make sure that the column headers of the table are sent to parameter_mapper.py
4. Make sure that the mapping of the table columns header with the paramters in testxpert_parameters.json is working


## Log of the tests conducted (Format: Description of the Test, Date, Passed or Failed, if failed add here the cause of the fail)
| Automated pytest run | 2026-06-19 10:00 | Passed | ============================= 29 passed in 0.84s ============================== |
| Added ini_file_generator.py + main.py INI generation step | 2026-06-19 11:05 | Passed | 49 passed in 1.08s |
| Added zimt_script_generator.py (Specimen-ID lookup) + GUI Step 6 + INI KeyColumnName | 2026-06-22 12:45 | Passed | 68 passed in 2.14s |
| Removed ZimtScriptGenerator — replaced with static Config/generic_import.zimt | 2026-06-22 13:18 | Passed | 51 passed in 1.67s |
| Expanded parameter catalog (16 params from HTML) + inline mapping editor in GUI | 2026-06-22 13:39 | Passed | 51 passed in 1.62s |
| Changed mapping picker trigger from single click to double click | 2026-06-22 13:48 | Passed | 51 passed in 2.26s |
