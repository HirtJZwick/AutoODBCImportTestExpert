"""
main.py
=======
Entry point for the testXpert Database Mapping Tool.
For now, this is a simple CLI test to verify the database connection works.

Usage:
    python main.py
"""

from pathlib import Path

from database_connector import DatabaseConnector
from ini_file_generator import IniFileGenerator
from parameter_mapper import (
    ParameterMapper,
    build_column_context,
    load_parameter_catalog,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PARAMETER_CATALOG_PATH = PROJECT_ROOT / "Config" / "testxpert_parameters.json"
API_KEY_FILE = PROJECT_ROOT / "api_key.txt"


def load_api_key() -> str:
    """Read the API key from api_key.txt."""
    if not API_KEY_FILE.exists():
        raise FileNotFoundError(
            f"API key file not found: {API_KEY_FILE}\n"
            "Create api_key.txt in the project root and paste your GitHub Models token into it."
        )
    return API_KEY_FILE.read_text(encoding="utf-8").strip()


def print_mapping_suggestions(suggestions):
    """Print AI-generated mapping suggestions in a compact table."""
    if not suggestions:
        print("  (no mapping suggestions returned)")
        return

    print(f"  {'Column':<25} {'Parameter':<28} {'Section':<18} {'Conf.'}")
    print(f"  {'-'*25} {'-'*28} {'-'*18} {'-'*6}")

    for suggestion in suggestions:
        if suggestion.parameter_id is None:
            parameter = "(unmapped)"
            section = "-"
        else:
            parameter = f"{suggestion.parameter_id} - {suggestion.parameter_name}"
            section = suggestion.mapping_section or "-"

        print(
            f"  {suggestion.column:<25} "
            f"{parameter:<28} "
            f"{section:<18} "
            f"{suggestion.confidence:.2f}"
        )

        if suggestion.reason:
            print(f"    Reason: {suggestion.reason}")


def main():
    print("=" * 55)
    print("  testXpert III — Database Mapping Tool")
    print("  Step 1: Database Connection Test")
    print("=" * 55)

    # --- Create the connector ---
    db = DatabaseConnector()

    # --- Get DSN name from user ---
    print("\nEnter the ODBC Data Source Name (DSN).")
    print("(This is the name you configured in Windows ODBC Administrator)")
    dsn = input("\n> DSN name: ").strip()

    if not dsn:
        print("No DSN entered. Exiting.")
        return

    # --- Connect ---
    print(f"\nConnecting to '{dsn}'...")
    try:
        db.connect(dsn)
        print(f"✓ Connected successfully!")
    except ConnectionError as e:
        print(f"✗ Connection failed:\n  {e}")
        return

    # --- List tables ---
    print("\n--- Tables in database ---")
    try:
        tables = db.get_tables()
        if not tables:
            print("  (no tables found)")
            db.close()
            return

        for i, table in enumerate(tables, 1):
            print(f"  {i}. {table}")

    except RuntimeError as e:
        print(f"  Error: {e}")
        db.close()
        return

    # --- Let user pick a table ---
    print(f"\nWhich table do you want to inspect? (1-{len(tables)})")
    choice = input("> Table number: ").strip()

    try:
        table_idx = int(choice) - 1
        if table_idx < 0 or table_idx >= len(tables):
            raise ValueError()
        selected_table = tables[table_idx]
    except ValueError:
        print("Invalid choice. Exiting.")
        db.close()
        return

    # --- Show columns ---
    print(f"\n--- Columns in '{selected_table}' ---")
    try:
        columns = db.get_columns(selected_table)
        print(f"  {'Column Name':<25} {'Type':<15} {'Size'}")
        print(f"  {'-'*25} {'-'*15} {'-'*6}")
        for col in columns:
            print(f"  {col['name']:<25} {col['type']:<15} {col['size']}")
    except RuntimeError as e:
        print(f"  Error: {e}")
        db.close()
        return

    # --- Show sample data ---
    print(f"\n--- Sample data (first 3 rows) ---")
    rows = []
    try:
        rows = db.get_sample_data(selected_table, num_rows=3)
        if not rows:
            print("  (table is empty)")
        else:
            # Print column headers
            col_names = [col["name"] for col in columns]
            header = " | ".join(f"{name:<15}" for name in col_names)
            print(f"  {header}")
            print(f"  {'-' * len(header)}")

            # Print each row
            for row in rows:
                row_str = " | ".join(f"{val:<15}" for val in row)
                print(f"  {row_str}")

    except RuntimeError as e:
        print(f"  Error: {e}")

    # --- Suggest testXpert parameter mappings ---
    print("\n--- Suggested testXpert parameter mappings ---")
    try:
        column_context = build_column_context(columns, rows)
        parameter_catalog = load_parameter_catalog(str(PARAMETER_CATALOG_PATH))
        mapper = ParameterMapper(api_key=load_api_key())
        suggestions = mapper.suggest_mappings(column_context, parameter_catalog)
        print_mapping_suggestions(suggestions)
    except FileNotFoundError:
        print(f"  Parameter catalog not found: {PARAMETER_CATALOG_PATH}")
    except RuntimeError as e:
        print(f"  Mapping skipped: {e}")
    except ValueError as e:
        print(f"  Mapping skipped: {e}")

    # --- Clean up ---
    db.close()
    print(f"\n✓ Connection closed.")

    # --- Generate INI file ---
    print("\n--- Generate INI file ---")

    mapped_count = sum(1 for s in suggestions if s.parameter_id is not None)
    if mapped_count == 0:
        print("  No confirmed mappings — cannot generate INI file.")
        return

    print(f"  {mapped_count} of {len(suggestions)} columns will be written to the INI.")
    answer = input("\nGenerate INI file from these mappings? (y/n): ").strip().lower()

    if answer != "y":
        print("Skipped.")
        return

    default_out = str(PROJECT_ROOT / "Config" / f"{dsn}_config.ini")
    print(f"\nOutput path (Enter for default: {default_out}):")
    out_path = input("> ").strip() or default_out

    try:
        gen = IniFileGenerator()
        content = gen.generate(dsn, selected_table, suggestions)
        saved = gen.save(content, out_path)

        print(f"\n✓ INI file saved to: {saved}")
        print("\n--- Generated content ---")
        print(content)

    except Exception as e:
        print(f"✗ Failed to generate INI file: {e}")
        return


if __name__ == "__main__":
    main()
