"""
test_ini_file_generator.py
==========================
Tests for ini_file_generator.py

Verifies that the generated INI content is correctly structured and matches
the format expected by testXpert III (as shown in Porsche_config.ini).
"""

import configparser
import io
from pathlib import Path

import pytest

from ini_file_generator import IniFileGenerator, SECTION_ORDER
from parameter_mapper import MappingSuggestion

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _suggestion(column, param_id, section, name="", confidence=0.9):
    return MappingSuggestion(
        column=column,
        parameter_id=param_id,
        parameter_name=name,
        mapping_section=section,
        confidence=confidence,
        reason="",
    )


FULL_SUGGESTIONS = [
    _suggestion("SampleID",   1701, "SpecimenMapping", "Sample ID"),
    _suggestion("Kundenname", 1065, "SeriesMapping",   "Customer name"),
    _suggestion("Teilnummer", 1703, "SpecimenMapping", "Part number"),
    _suggestion("Dicke",      1031, "NumericMapping",  "Specimen thickness"),
    _suggestion("Breite",     1032, "NumericMapping",  "Specimen width"),
]


def _parse(content: str) -> configparser.RawConfigParser:
    cfg = configparser.RawConfigParser()
    cfg.read_string(content)
    return cfg


# ---------------------------------------------------------------------------
# Connection section
# ---------------------------------------------------------------------------

class TestConnectionSection:
    def test_dsn_written(self):
        gen = IniFileGenerator()
        cfg = _parse(gen.generate("Porsche_DB", "TestData", FULL_SUGGESTIONS))
        assert cfg.get("Connection", "ODBC") == "Porsche_DB"

    def test_table_written(self):
        gen = IniFileGenerator()
        cfg = _parse(gen.generate("Porsche_DB", "TestData", FULL_SUGGESTIONS))
        assert cfg.get("Connection", "Table") == "TestData"

    def test_key_column_auto_detected_from_sample_id(self):
        """KeyColumn should be S:<column mapped to param 1701>."""
        gen = IniFileGenerator()
        cfg = _parse(gen.generate("Porsche_DB", "TestData", FULL_SUGGESTIONS))
        assert cfg.get("Connection", "KeyColumn") == "S:SampleID"

    def test_key_column_explicit_override(self):
        gen = IniFileGenerator()
        cfg = _parse(gen.generate("Porsche_DB", "TestData", FULL_SUGGESTIONS, key_column="MyKey"))
        assert cfg.get("Connection", "KeyColumn") == "S:MyKey"

    def test_key_column_name_is_bare_column(self):
        """KeyColumnName must hold the SQL column name without the S: prefix."""
        gen = IniFileGenerator()
        cfg = _parse(gen.generate("Porsche_DB", "TestData", FULL_SUGGESTIONS))
        assert cfg.get("Connection", "KeyColumnName") == "SampleID"

    def test_key_column_name_follows_override(self):
        gen = IniFileGenerator()
        cfg = _parse(gen.generate("Porsche_DB", "TestData", FULL_SUGGESTIONS, key_column="MyKey"))
        assert cfg.get("Connection", "KeyColumnName") == "MyKey"

    def test_row_num_column_default(self):
        gen = IniFileGenerator()
        cfg = _parse(gen.generate("Porsche_DB", "TestData", FULL_SUGGESTIONS))
        assert cfg.get("Connection", "RowNumColumn") == "RowNum"

    def test_row_num_column_custom(self):
        gen = IniFileGenerator()
        cfg = _parse(gen.generate("Porsche_DB", "TestData", FULL_SUGGESTIONS, row_num_column="ID"))
        assert cfg.get("Connection", "RowNumColumn") == "ID"


# ---------------------------------------------------------------------------
# Mapping sections
# ---------------------------------------------------------------------------

class TestMappingSections:
    def test_series_mapping_count(self):
        gen = IniFileGenerator()
        cfg = _parse(gen.generate("DB", "T", FULL_SUGGESTIONS))
        assert cfg.getint("SeriesMapping", "Count") == 1

    def test_specimen_mapping_count(self):
        gen = IniFileGenerator()
        cfg = _parse(gen.generate("DB", "T", FULL_SUGGESTIONS))
        assert cfg.getint("SpecimenMapping", "Count") == 2

    def test_numeric_mapping_count(self):
        gen = IniFileGenerator()
        cfg = _parse(gen.generate("DB", "T", FULL_SUGGESTIONS))
        assert cfg.getint("NumericMapping", "Count") == 2

    def test_col_param_pairs_written(self):
        gen = IniFileGenerator()
        cfg = _parse(gen.generate("DB", "T", FULL_SUGGESTIONS))
        assert cfg.get("SeriesMapping", "Col1") == "Kundenname"
        assert cfg.getint("SeriesMapping", "Param1") == 1065

    def test_all_specimen_cols_written(self):
        gen = IniFileGenerator()
        cfg = _parse(gen.generate("DB", "T", FULL_SUGGESTIONS))
        cols = {cfg.get("SpecimenMapping", "Col1"), cfg.get("SpecimenMapping", "Col2")}
        assert cols == {"SampleID", "Teilnummer"}

    def test_empty_section_omitted(self):
        """A section with no mapped columns must not appear in the output."""
        suggestions = [
            _suggestion("Dicke", 1031, "NumericMapping"),
        ]
        gen = IniFileGenerator()
        content = gen.generate("DB", "T", suggestions)
        assert "[SeriesMapping]" not in content
        assert "[SpecimenMapping]" not in content
        assert "[NumericMapping]" in content


# ---------------------------------------------------------------------------
# Unmapped suggestions
# ---------------------------------------------------------------------------

class TestUnmappedSuggestions:
    def test_unmapped_columns_excluded(self):
        """Suggestions with parameter_id=None must not appear in the INI."""
        suggestions = [
            _suggestion("SampleID", 1701, "SpecimenMapping"),
            MappingSuggestion(
                column="UnknownCol",
                parameter_id=None,
                parameter_name=None,
                mapping_section=None,
                confidence=0.0,
                reason="No match",
            ),
        ]
        gen = IniFileGenerator()
        content = gen.generate("DB", "T", suggestions)
        assert "UnknownCol" not in content
        assert cfg_count(content, "SpecimenMapping") == 1

    def test_all_unmapped_produces_empty_mapping_sections(self):
        suggestions = [
            MappingSuggestion("A", None, None, None, 0.0, ""),
            MappingSuggestion("B", None, None, None, 0.0, ""),
        ]
        gen = IniFileGenerator()
        content = gen.generate("DB", "T", suggestions)
        for section in SECTION_ORDER:
            assert f"[{section}]" not in content


# ---------------------------------------------------------------------------
# File saving
# ---------------------------------------------------------------------------

class TestSave:
    def test_save_creates_file(self, tmp_path):
        gen = IniFileGenerator()
        content = gen.generate("Porsche_DB", "TestData", FULL_SUGGESTIONS)
        out = tmp_path / "output.ini"
        saved = gen.save(content, out)

        assert saved.exists()
        assert saved.read_text(encoding="utf-8") == content

    def test_save_creates_parent_directories(self, tmp_path):
        gen = IniFileGenerator()
        content = gen.generate("DB", "T", FULL_SUGGESTIONS)
        out = tmp_path / "nested" / "dir" / "out.ini"
        gen.save(content, out)
        assert out.exists()

    def test_save_returns_absolute_path(self, tmp_path):
        gen = IniFileGenerator()
        content = gen.generate("DB", "T", FULL_SUGGESTIONS)
        saved = gen.save(content, tmp_path / "out.ini")
        assert saved.is_absolute()


# ---------------------------------------------------------------------------
# Porsche_config.ini regression
# ---------------------------------------------------------------------------

class TestPorscheConfigRegression:
    """Verify the generator reproduces the known Porsche_config.ini structure."""

    def test_reproduces_porsche_config(self):
        gen = IniFileGenerator()
        content = gen.generate("Porsche_DB", "TestData", FULL_SUGGESTIONS)
        cfg = _parse(content)

        assert cfg.get("Connection", "ODBC") == "Porsche_DB"
        assert cfg.get("Connection", "Table") == "TestData"
        assert cfg.get("Connection", "KeyColumn") == "S:SampleID"
        assert cfg.getint("SeriesMapping", "Count") == 1
        assert cfg.getint("SpecimenMapping", "Count") == 2
        assert cfg.getint("NumericMapping", "Count") == 2


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def cfg_count(content: str, section: str) -> int:
    cfg = _parse(content)
    return cfg.getint(section, "Count")
