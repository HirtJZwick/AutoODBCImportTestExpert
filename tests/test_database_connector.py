"""
test_database_connector.py
===========================
Tests for database_connector.py

Covers Test.md items:
  1. Application can connect to the database (Porsche_DB)
  2. Table data can be retrieved and visualized (columns + sample rows)
"""

import pytest
import pyodbc
from unittest.mock import MagicMock, patch

from database_connector import DatabaseConnector


# ---------------------------------------------------------------------------
# Helper: produce a connected DatabaseConnector with a mocked pyodbc cursor
# ---------------------------------------------------------------------------

def _make_connected_db():
    """Return (db, mock_cursor) with a mocked pyodbc connection."""
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    with patch("database_connector.pyodbc.connect", return_value=mock_conn):
        db = DatabaseConnector()
        db.connect("Porsche_DB")

    # Replace the cursor so we can control it after connect()
    db._cursor = mock_cursor
    return db, mock_cursor


# ===========================================================================
# Test 1 — Database connection
# ===========================================================================

class TestDatabaseConnection:
    """Test.md item 1: Application can connect to the database Porsche_DB."""

    def test_connect_success_returns_true(self):
        """connect() returns True and sets is_connected on a valid DSN."""
        mock_conn = MagicMock()
        with patch("database_connector.pyodbc.connect", return_value=mock_conn):
            db = DatabaseConnector()
            result = db.connect("Porsche_DB")

        assert result is True
        assert db.is_connected is True

    def test_connect_calls_correct_dsn_string(self):
        """connect() passes DSN=<name> to pyodbc.connect."""
        mock_conn = MagicMock()
        with patch("database_connector.pyodbc.connect", return_value=mock_conn) as mock_pyodbc:
            db = DatabaseConnector()
            db.connect("Porsche_DB")

        mock_pyodbc.assert_called_once_with("DSN=Porsche_DB")

    def test_is_connected_false_before_connect(self):
        """is_connected is False before any connection attempt."""
        db = DatabaseConnector()
        assert db.is_connected is False

    def test_connect_invalid_dsn_raises_connection_error(self):
        """connect() raises ConnectionError for an unknown DSN."""
        with patch(
            "database_connector.pyodbc.connect",
            side_effect=pyodbc.InterfaceError("DSN not found"),
        ):
            db = DatabaseConnector()
            with pytest.raises(ConnectionError, match="Porsche_DB"):
                db.connect("Porsche_DB")

    def test_connect_other_pyodbc_error_raises_connection_error(self):
        """connect() wraps any pyodbc.Error as a ConnectionError."""
        with patch(
            "database_connector.pyodbc.connect",
            side_effect=pyodbc.Error("generic error"),
        ):
            db = DatabaseConnector()
            with pytest.raises(ConnectionError):
                db.connect("Porsche_DB")

    def test_close_resets_is_connected(self):
        """close() resets is_connected to False."""
        mock_conn = MagicMock()
        with patch("database_connector.pyodbc.connect", return_value=mock_conn):
            db = DatabaseConnector()
            db.connect("Porsche_DB")

        assert db.is_connected is True
        db.close()
        assert db.is_connected is False

    def test_close_is_safe_when_not_connected(self):
        """close() does not raise even when called without a prior connect."""
        db = DatabaseConnector()
        db.close()  # should not raise


# ===========================================================================
# Test 2 — Table retrieval and data visualization
# ===========================================================================

class TestTableRetrieval:
    """Test.md item 2: Table data can be retrieved and visualized."""

    def test_get_tables_returns_list_of_names(self):
        """get_tables() returns a plain list of table name strings."""
        db, mock_cursor = _make_connected_db()

        mock_row = MagicMock()
        mock_row.table_name = "TestData"
        mock_cursor.tables.return_value = [mock_row]

        tables = db.get_tables()
        assert isinstance(tables, list)
        assert "TestData" in tables

    def test_get_tables_without_connection_raises(self):
        """get_tables() raises RuntimeError when not connected."""
        db = DatabaseConnector()
        with pytest.raises(RuntimeError, match="Not connected"):
            db.get_tables()

    def test_get_columns_returns_name_type_size_dicts(self):
        """get_columns() returns dicts with name, type, and size keys."""
        db, mock_cursor = _make_connected_db()

        mock_col = MagicMock()
        mock_col.column_name = "SampleID"
        mock_col.type_name = "VARCHAR"
        mock_col.column_size = 50
        mock_cursor.columns.return_value = [mock_col]

        columns = db.get_columns("TestData")

        assert len(columns) == 1
        assert columns[0] == {"name": "SampleID", "type": "VARCHAR", "size": 50}

    def test_get_columns_multiple_columns(self):
        """get_columns() handles tables with multiple columns."""
        db, mock_cursor = _make_connected_db()

        col_specs = [
            ("SampleID", "VARCHAR", 50),
            ("Dicke", "DOUBLE", 15),
            ("Breite", "DOUBLE", 15),
        ]
        mock_cursor.columns.return_value = [
            MagicMock(column_name=n, type_name=t, column_size=s)
            for n, t, s in col_specs
        ]

        columns = db.get_columns("TestData")
        names = [c["name"] for c in columns]

        assert names == ["SampleID", "Dicke", "Breite"]

    def test_get_sample_data_returns_string_rows(self):
        """get_sample_data() returns rows as lists of strings."""
        db, mock_cursor = _make_connected_db()
        mock_cursor.fetchall.return_value = [("S001", "Porsche AG"), ("S002", "Porsche AG")]

        rows = db.get_sample_data("TestData", num_rows=2)

        assert len(rows) == 2
        assert rows[0] == ["S001", "Porsche AG"]

    def test_get_sample_data_converts_none_to_null_string(self):
        """get_sample_data() converts None cells to the string 'NULL'."""
        db, mock_cursor = _make_connected_db()
        mock_cursor.fetchall.return_value = [("S001", None)]

        rows = db.get_sample_data("TestData", num_rows=1)

        assert rows[0][1] == "NULL"

    def test_get_sample_data_without_connection_raises(self):
        """get_sample_data() raises RuntimeError when not connected."""
        db = DatabaseConnector()
        with pytest.raises(RuntimeError, match="Not connected"):
            db.get_sample_data("TestData")
