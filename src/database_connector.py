"""
database_connector.py
=====================
Handles ODBC connections to any database (MS Access, Oracle, SQL Server, etc.)
Provides methods to list tables, read column schemas, and fetch sample data.

Dependencies:
    pip install pyodbc

Usage:
    from database_connector import DatabaseConnector

    db = DatabaseConnector()
    db.connect("My_ODBC_DSN")
    tables = db.get_tables()
    columns = db.get_columns("TableName")
    samples = db.get_sample_data("TableName", num_rows=3)
    db.close()
"""

import pyodbc

class DatabaseConnector:
    """
    Connects to any ODBC data source and reads schema + sample data.

    Typical workflow:
        1. connect(dsn_name)   — open connection
        2. get_tables()        — see what tables exist
        3. get_columns(table)  — see column names/types
        4. get_sample_data(table) — peek at actual data
        5. close()             — clean up
    """

    def __init__(self):
        """Initialize with no active connection."""
        self._connection = None   # pyodbc connection object
        self._cursor = None       # pyodbc cursor object

    # =============================================================
    # Properties
    # =============================================================

    @property
    def is_connected(self):
        """Check if we currently have an open database connection."""
        return self._connection is not None

    # =============================================================
    # Connection Management
    # =============================================================

    def connect(self, dsn_name):
        """
        Connect to an ODBC data source by its DSN name.

        Args:
            dsn_name (str): The name of the ODBC Data Source (as configured
                            in Windows ODBC Data Source Administrator).

        Returns:
            True if connection was successful.

        Raises:
            ConnectionError: If the connection fails (wrong DSN, driver
                             not found, database file missing, etc.)

        Example:
            db = DatabaseConnector()
            db.connect("Smaller_Test")
        """
        # Close any existing connection first
        self.close()

        try:
            self._connection = pyodbc.connect(f"DSN={dsn_name}")
            self._cursor = self._connection.cursor()
            return True

        except pyodbc.InterfaceError as e:
            raise ConnectionError(
                f"ODBC DSN '{dsn_name}' not found. "
                f"Check Windows ODBC Data Source Administrator.\n"
                f"Details: {e}"
            )
        except pyodbc.Error as e:
            raise ConnectionError(
                f"Failed to connect to '{dsn_name}'.\n"
                f"Details: {e}"
            )

    def close(self):
        """
        Close the database connection and release resources.
        Safe to call even if not connected (does nothing).
        """
        if self._cursor:
            try:
                self._cursor.close()
            except Exception:
                pass
            self._cursor = None

        if self._connection:
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None

    def __del__(self):
        """Automatically close connection when the object is destroyed."""
        self.close()

    # =============================================================
    # Schema Reading
    # =============================================================

    def _ensure_connected(self):
        """Helper: raise an error if not connected."""
        if not self.is_connected:
            raise RuntimeError(
                "Not connected to any database. Call connect() first."
            )

    def get_tables(self):
        """
        List all table names in the connected database.

        Returns:
            list[str]: Table names, e.g. ["Table1", "Customers", "Orders"]

        Raises:
            RuntimeError: If not connected to a database.
        """
        self._ensure_connected()

        try:
            tables = []
            for row in self._cursor.tables(tableType="TABLE"):
                tables.append(row.table_name)
            return tables

        except pyodbc.Error as e:
            raise RuntimeError(f"Failed to list tables: {e}")

    def get_columns(self, table_name):
        """
        Get column information for a specific table.

        Args:
            table_name (str): Name of the table to inspect.

        Returns:
            list[dict]: Each dict has keys:
                - "name" (str):  Column name, e.g. "CustomerName"
                - "type" (str):  Data type, e.g. "VARCHAR", "INTEGER"
                - "size" (int):  Column size / max length

        Raises:
            RuntimeError: If not connected or table doesn't exist.

        Example:
            columns = db.get_columns("Table1")
            for col in columns:
                print(f"{col['name']}  ({col['type']}, size={col['size']})")
        """
        self._ensure_connected()

        try:
            columns = []
            for col in self._cursor.columns(table=table_name):
                columns.append({
                    "name": col.column_name,
                    "type": col.type_name,
                    "size": col.column_size,
                })
            return columns

        except pyodbc.Error as e:
            raise RuntimeError(
                f"Failed to read columns from '{table_name}': {e}"
            )

    def get_sample_data(self, table_name, num_rows=3):
        """
        Fetch the first N rows from a table as sample data.

        Tries multiple SQL dialects to work across databases:
          1. SELECT TOP N ...       (MS Access, SQL Server)
          2. SELECT ... WHERE ROWNUM <= N  (Oracle)
          3. SELECT ... LIMIT N     (MySQL, PostgreSQL, SQLite)

        Args:
            table_name (str): Name of the table to read.
            num_rows (int):   Number of rows to fetch (default: 3).

        Returns:
            list[list[str]]: Each inner list is one row of string values.
                             NULL values are returned as the string "NULL".

        Raises:
            RuntimeError: If not connected or all queries fail.

        Example:
            rows = db.get_sample_data("Table1", num_rows=5)
            for row in rows:
                print(row)
        """
        self._ensure_connected()

        # We try three different SQL dialects because different databases
        # use different syntax for limiting the number of results.
        queries = [
            # Dialect 1: MS Access / SQL Server
            f"SELECT TOP {num_rows} * FROM [{table_name}]",
            # Dialect 2: Oracle
            f"SELECT * FROM {table_name} WHERE ROWNUM <= {num_rows}",
            # Dialect 3: MySQL / PostgreSQL / SQLite
            f"SELECT * FROM {table_name} LIMIT {num_rows}",
        ]

        for query in queries:
            try:
                self._cursor.execute(query)
                raw_rows = self._cursor.fetchall()

                # Convert every cell to a string (or "NULL")
                rows = []
                for raw_row in raw_rows:
                    row = []
                    for cell in raw_row:
                        if cell is None:
                            row.append("NULL")
                        else:
                            row.append(str(cell))
                    rows.append(row)
                return rows

            except pyodbc.Error:
                # This dialect didn't work — try the next one
                continue

        # None of the dialects worked
        raise RuntimeError(
            f"Failed to read sample data from '{table_name}'. "
            f"The table may not exist or the SQL dialect is not supported."
        )
