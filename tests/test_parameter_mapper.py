"""
test_parameter_mapper.py
========================
Tests for parameter_mapper.py

Covers Test.md items:
  3. Column headers are sent to parameter_mapper.py correctly
  4. Mapping of column headers with testxpert_parameters.json works
"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from parameter_mapper import (
    GITHUB_MODELS_BASE_URL,
    MappingSuggestion,
    ParameterMapper,
    build_column_context,
    load_parameter_catalog,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = PROJECT_ROOT / "Config" / "testxpert_parameters.json"

# Columns matching the known Porsche_DB / Porsche_config.ini schema
SAMPLE_COLUMNS = [
    {"name": "SampleID",   "type": "VARCHAR", "size": 50},
    {"name": "Kundenname", "type": "VARCHAR", "size": 100},
    {"name": "Teilnummer", "type": "VARCHAR", "size": 50},
    {"name": "Dicke",      "type": "DOUBLE",  "size": 15},
    {"name": "Breite",     "type": "DOUBLE",  "size": 15},
]

SAMPLE_ROWS = [
    ["S001", "Porsche AG", "PN-001", "2.5", "10.0"],
    ["S002", "Porsche AG", "PN-002", "3.0", "12.0"],
]

# GitHub Models response that maps every column to a real catalog entry
MOCK_GITHUB_MODELS_RESPONSE = {
    "mappings": [
        {"column": "SampleID",   "parameter_id": 1701, "parameter_name": "Sample ID",
         "mapping_section": "SpecimenMapping", "confidence": 0.95, "reason": "Direct match"},
        {"column": "Kundenname", "parameter_id": 1065, "parameter_name": "Customer name",
         "mapping_section": "SeriesMapping",   "confidence": 0.90, "reason": "German for customer name"},
        {"column": "Teilnummer", "parameter_id": 1703, "parameter_name": "Part number",
         "mapping_section": "SpecimenMapping", "confidence": 0.88, "reason": "German for part number"},
        {"column": "Dicke",      "parameter_id": 1031, "parameter_name": "Specimen thickness",
         "mapping_section": "NumericMapping",  "confidence": 0.92, "reason": "German for thickness"},
        {"column": "Breite",     "parameter_id": 1032, "parameter_name": "Specimen width",
         "mapping_section": "NumericMapping",  "confidence": 0.91, "reason": "German for width"},
    ]
}


def _make_mapper_with_mock_response(mock_response: dict) -> tuple[ParameterMapper, MagicMock]:
    """Return (ParameterMapper, mock_client) with a stubbed GitHub Models API."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices[0].message.content = json.dumps(mock_response)

    with (
        patch.dict("os.environ", {"GITHUB_TOKEN": "test-key"}),
        patch("openai.OpenAI", return_value=mock_client),
    ):
        mapper = ParameterMapper()

    return mapper, mock_client


# ===========================================================================
# Test 3 — Column headers are sent to parameter_mapper.py
# ===========================================================================

class TestColumnHeaderTransfer:
    """Test.md item 3: Column headers are correctly handed to the mapper."""

    def test_build_column_context_includes_all_column_names(self):
        """build_column_context() preserves every column name."""
        context = build_column_context(SAMPLE_COLUMNS, SAMPLE_ROWS)
        names = [c["name"] for c in context]

        for col in SAMPLE_COLUMNS:
            assert col["name"] in names

    def test_build_column_context_preserves_type_and_size(self):
        """build_column_context() keeps type and size from the schema."""
        context = build_column_context(SAMPLE_COLUMNS)
        dicke = next(c for c in context if c["name"] == "Dicke")

        assert dicke["type"] == "DOUBLE"
        assert dicke["size"] == 15

    def test_build_column_context_attaches_sample_values(self):
        """build_column_context() attaches up to 3 non-null sample values."""
        context = build_column_context(SAMPLE_COLUMNS, SAMPLE_ROWS)
        sample_id = next(c for c in context if c["name"] == "SampleID")

        assert "sample_values" in sample_id
        assert "S001" in sample_id["sample_values"]
        assert len(sample_id["sample_values"]) <= 3

    def test_build_column_context_no_sample_rows(self):
        """build_column_context() works without sample rows."""
        context = build_column_context(SAMPLE_COLUMNS)

        assert len(context) == len(SAMPLE_COLUMNS)
        for col in context:
            assert col["sample_values"] == []

    def test_build_column_context_skips_null_values(self):
        """build_column_context() skips None / 'NULL' / empty string values."""
        cols = [{"name": "X", "type": "VARCHAR", "size": 10}]
        rows = [[None], ["NULL"], [""], ["real_value"]]
        context = build_column_context(cols, rows)

        assert context[0]["sample_values"] == ["real_value"]


# ===========================================================================
# Test 4 — Mapping with testxpert_parameters.json
# ===========================================================================

class TestParameterMapping:
    """Test.md item 4: Column-to-parameter mapping works correctly."""

    # --- catalog loading ---

    def test_load_catalog_succeeds(self):
        """load_parameter_catalog() reads the real Config JSON without errors."""
        catalog = load_parameter_catalog(str(CATALOG_PATH))
        assert isinstance(catalog, list)
        assert len(catalog) > 0

    def test_catalog_has_required_keys(self):
        """Every catalog entry has at least id, name, and mapping_section."""
        catalog = load_parameter_catalog(str(CATALOG_PATH))
        for entry in catalog:
            assert "id" in entry
            assert "name" in entry
            assert "mapping_section" in entry

    def test_catalog_contains_porsche_config_parameters(self):
        """Catalog contains all parameter IDs referenced in Porsche_config.ini."""
        catalog = load_parameter_catalog(str(CATALOG_PATH))
        ids = {p["id"] for p in catalog}

        assert 1065 in ids, "Customer name (1065) missing"
        assert 1701 in ids, "Sample ID (1701) missing"
        assert 1703 in ids, "Part number (1703) missing"
        assert 1031 in ids, "Specimen thickness (1031) missing"
        assert 1032 in ids, "Specimen width (1032) missing"

    # --- suggest_mappings ---

    def test_suggest_mappings_returns_one_suggestion_per_column(self):
        """suggest_mappings() returns exactly one suggestion per input column."""
        catalog = load_parameter_catalog(str(CATALOG_PATH))
        context = build_column_context(SAMPLE_COLUMNS, SAMPLE_ROWS)
        mapper, mock_client = _make_mapper_with_mock_response(MOCK_GITHUB_MODELS_RESPONSE)

        suggestions = mapper.suggest_mappings(context, catalog)

        assert len(suggestions) == len(SAMPLE_COLUMNS)

    def test_suggest_mappings_returns_mapping_suggestion_objects(self):
        """suggest_mappings() returns MappingSuggestion instances."""
        catalog = load_parameter_catalog(str(CATALOG_PATH))
        context = build_column_context(SAMPLE_COLUMNS, SAMPLE_ROWS)
        mapper, _ = _make_mapper_with_mock_response(MOCK_GITHUB_MODELS_RESPONSE)

        suggestions = mapper.suggest_mappings(context, catalog)

        assert all(isinstance(s, MappingSuggestion) for s in suggestions)

    def test_suggest_mappings_confidence_in_range(self):
        """All confidence scores are clamped to [0.0, 1.0]."""
        catalog = load_parameter_catalog(str(CATALOG_PATH))
        context = build_column_context(SAMPLE_COLUMNS, SAMPLE_ROWS)
        mapper, _ = _make_mapper_with_mock_response(MOCK_GITHUB_MODELS_RESPONSE)

        suggestions = mapper.suggest_mappings(context, catalog)

        for s in suggestions:
            assert 0.0 <= s.confidence <= 1.0

    def test_suggest_mappings_rejects_ids_outside_catalog(self):
        """A parameter_id not in the catalog is nullified by the validator."""
        catalog = load_parameter_catalog(str(CATALOG_PATH))
        context = build_column_context(SAMPLE_COLUMNS[:1])

        bad_response = {
            "mappings": [{
                "column": "SampleID",
                "parameter_id": 99999,
                "parameter_name": "Invented",
                "mapping_section": "SpecimenMapping",
                "confidence": 0.99,
                "reason": "Model hallucinated this ID",
            }]
        }
        mapper, _ = _make_mapper_with_mock_response(bad_response)
        suggestions = mapper.suggest_mappings(context, catalog)

        assert suggestions[0].parameter_id is None
        assert suggestions[0].confidence == 0.0

    def test_suggest_mappings_empty_columns_returns_empty(self):
        """suggest_mappings() returns an empty list for zero input columns."""
        catalog = load_parameter_catalog(str(CATALOG_PATH))
        mapper, _ = _make_mapper_with_mock_response({})

        result = mapper.suggest_mappings([], catalog)
        assert result == []

    def test_suggest_mappings_empty_catalog_raises(self):
        """suggest_mappings() raises ValueError when catalog is empty."""
        context = build_column_context(SAMPLE_COLUMNS[:1])
        mapper, _ = _make_mapper_with_mock_response({})

        with pytest.raises(ValueError, match="catalog"):
            mapper.suggest_mappings(context, [])

    # --- API key guard ---

    def test_mapper_uses_github_models_endpoint(self):
        """ParameterMapper configures the OpenAI client for GitHub Models."""
        mock_client = MagicMock()

        with (
            patch.dict("os.environ", {"GITHUB_TOKEN": "test-key"}),
            patch("openai.OpenAI", return_value=mock_client) as openai_class,
        ):
            ParameterMapper()

        openai_class.assert_called_once_with(
            base_url=GITHUB_MODELS_BASE_URL,
            api_key="test-key",
        )

    def test_mapper_accepts_github_models_token(self):
        """ParameterMapper also accepts GITHUB_MODELS_TOKEN."""
        mock_client = MagicMock()

        with (
            patch.dict("os.environ", {"GITHUB_TOKEN": "", "GITHUB_MODELS_TOKEN": "test-key"}),
            patch("openai.OpenAI", return_value=mock_client),
        ):
            mapper = ParameterMapper()

        assert mapper.api_key == "test-key"

    def test_mapper_raises_without_api_key(self):
        """ParameterMapper raises RuntimeError when no GitHub Models token is set."""
        with patch.dict("os.environ", {"GITHUB_TOKEN": "", "GITHUB_MODELS_TOKEN": ""}):
            with pytest.raises(RuntimeError, match="GITHUB_TOKEN"):
                ParameterMapper()
