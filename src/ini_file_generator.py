"""
ini_file_generator.py
=====================
Generates a testXpert III compatible INI configuration file from database
connection info and parameter mapping suggestions.

Output format matches Porsche_config.ini:

    [Connection]
    ODBC=<dsn>
    Table=<table>
    KeyColumn=S:<specimen_id_column>
    KeyColumnName=<specimen_id_column>
    RowNumColumn=<row_num_col>

    [SeriesMapping]
    Count=N
    Col1=...
    Param1=...

    [SpecimenMapping]
    Count=N
    ...

    [NumericMapping]
    Count=N
    ...
"""

from __future__ import annotations

from pathlib import Path

from parameter_mapper import MappingSuggestion

SECTION_ORDER = ["SeriesMapping", "SpecimenMapping", "NumericMapping"]
SPECIMEN_ID_PARAM = 1701  # "Sample ID" — used to auto-detect KeyColumn


class IniFileGenerator:
    """
    Builds a testXpert III INI file from mapping suggestions.

    Typical workflow:
        gen = IniFileGenerator()
        content = gen.generate(dsn, table, suggestions)
        gen.save(content, output_path)
    """

    def generate(
        self,
        dsn: str,
        table: str,
        suggestions: list[MappingSuggestion],
        key_column: str | None = None,
        row_num_column: str = "RowNum",
    ) -> str:
        """
        Generate INI file content as a string.

        Args:
            dsn: ODBC DSN name.
            table: Table name in the database.
            suggestions: Mapping suggestions from ParameterMapper.
                         Suggestions with parameter_id=None are skipped.
            key_column: Specimen key column name. If None, auto-detected as
                        the column mapped to parameter_id 1701 (Sample ID).
            row_num_column: Name of the row-number column (default: "RowNum").

        Returns:
            Full INI file content as a string.
        """
        mapped = [s for s in suggestions if s.parameter_id is not None]

        if key_column is None:
            key_column = self._detect_key_column(mapped)

        # Group suggestions by their mapping section
        sections: dict[str, list[MappingSuggestion]] = {s: [] for s in SECTION_ORDER}
        for suggestion in mapped:
            if suggestion.mapping_section in sections:
                sections[suggestion.mapping_section].append(suggestion)

        lines: list[str] = []
        lines += self._connection_section(dsn, table, key_column, row_num_column)
        for section_name in SECTION_ORDER:
            if sections[section_name]:
                lines += self._mapping_section(section_name, sections[section_name])

        return "\n".join(lines) + "\n"

    def save(self, content: str, path: str | Path) -> Path:
        """
        Write INI content to a file.

        Args:
            content: String returned by generate().
            path: Output file path (parent directories are created if needed).

        Returns:
            The resolved absolute output path.
        """
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
        return output.resolve()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _detect_key_column(self, mapped: list[MappingSuggestion]) -> str:
        """Return the column mapped to SPECIMEN_ID_PARAM, or the first SpecimenMapping column."""
        for s in mapped:
            if s.parameter_id == SPECIMEN_ID_PARAM:
                return s.column
        for s in mapped:
            if s.mapping_section == "SpecimenMapping":
                return s.column
        return ""

    def _connection_section(
        self,
        dsn: str,
        table: str,
        key_column: str,
        row_num_column: str,
    ) -> list[str]:
        key_value = f"S:{key_column}" if key_column else ""
        return [
            "[Connection]",
            f"ODBC={dsn}",
            f"Table={table}",
            f"KeyColumn={key_value}",
            f"KeyColumnName={key_column}",
            f"RowNumColumn={row_num_column}",
            "",
        ]

    def _mapping_section(
        self,
        section_name: str,
        entries: list[MappingSuggestion],
    ) -> list[str]:
        lines = [f"[{section_name}]", f"Count={len(entries)}"]
        for i, entry in enumerate(entries, 1):
            lines.append(f"Col{i}={entry.column}")
            lines.append(f"Param{i}={entry.parameter_id}")
        lines.append("")
        return lines
