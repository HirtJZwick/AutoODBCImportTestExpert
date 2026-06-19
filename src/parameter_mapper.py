"""
parameter_mapper.py
===================
Suggests mappings from customer database columns to built-in testXpert III
parameter IDs using GitHub Models.

The mapper expects two inputs:
    1. database column metadata, optionally with sample values
    2. a catalog of allowed testXpert parameters

The model is only allowed to choose IDs from the provided catalog. Unknown or
uncertain mappings are returned with parameter_id = None so the user can decide.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any


GITHUB_MODELS_BASE_URL = "https://models.github.ai/inference"
DEFAULT_MODEL = "openai/gpt-5-mini"


@dataclass
class MappingSuggestion:
    """One suggested database-column to testXpert-parameter mapping."""

    column: str
    parameter_id: int | None
    parameter_name: str | None
    mapping_section: str | None
    confidence: float
    reason: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "MappingSuggestion":
        parameter_id = value.get("parameter_id")
        if parameter_id is not None:
            parameter_id = int(parameter_id)

        confidence = value.get("confidence", 0)
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.0

        return cls(
            column=str(value.get("column", "")),
            parameter_id=parameter_id,
            parameter_name=value.get("parameter_name"),
            mapping_section=value.get("mapping_section"),
            confidence=max(0.0, min(1.0, confidence)),
            reason=str(value.get("reason", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "column": self.column,
            "parameter_id": self.parameter_id,
            "parameter_name": self.parameter_name,
            "mapping_section": self.mapping_section,
            "confidence": self.confidence,
            "reason": self.reason,
        }


class ParameterMapper:
    """GitHub Models-backed mapper for testXpert parameter suggestions."""

    def __init__(self, model: str = DEFAULT_MODEL, api_key: str | None = None):
        self.model = model
        self.api_key = (
            api_key
            or os.environ.get("GITHUB_MODELS_TOKEN")
            or os.environ.get("GITHUB_TOKEN")
        )

        if not self.api_key:
            raise RuntimeError(
                "GITHUB_TOKEN or GITHUB_MODELS_TOKEN is not set. Set one in "
                "your environment or pass api_key=... when creating ParameterMapper."
            )

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The openai package is not installed. Install it with: "
                "python -m pip install openai"
            ) from exc

        self.client = OpenAI(
            base_url=GITHUB_MODELS_BASE_URL,
            api_key=self.api_key,
        )

    def suggest_mappings(
        self,
        columns: list[dict[str, Any]],
        parameter_catalog: list[dict[str, Any]],
    ) -> list[MappingSuggestion]:
        """
        Ask the model to map database columns to allowed testXpert parameters.

        Args:
            columns: Database column metadata. Each item should include at least
                name, type, and size. sample_values is optional.
            parameter_catalog: Allowed testXpert parameters. Each item should
                include id, name, mapping_section, and optionally description.

        Returns:
            A list of normalized MappingSuggestion objects.
        """
        if not columns:
            return []

        if not parameter_catalog:
            raise ValueError("parameter_catalog must not be empty")

        payload = self._build_payload(columns, parameter_catalog)
        raw_text = self._call_model(payload)
        raw_result = self._parse_json(raw_text)
        suggestions = self._extract_suggestions(raw_result)
        return self._validate_suggestions(suggestions, columns, parameter_catalog)

    def _call_model(self, payload: dict[str, Any]) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "You map customer database columns to built-in testXpert III "
                    "parameters. Return only valid JSON. Do not invent parameter "
                    "IDs. If no good match exists, use null values and low "
                    "confidence."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(payload, indent=2, ensure_ascii=False),
            },
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
        )
        return response.choices[0].message.content or ""

    def _build_payload(
        self,
        columns: list[dict[str, Any]],
        parameter_catalog: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "task": "Map database columns to testXpert III built-in parameters.",
            "rules": [
                "Only use parameter IDs that exist in parameter_catalog.",
                "Prefer semantic meaning over exact spelling.",
                "German, English, French, and abbreviated column names may occur.",
                "Numeric measurement columns should map to numeric/specimen dimensions when appropriate.",
                "Return confidence as a number from 0 to 1.",
                "Use parameter_id null when no reliable match exists.",
                "Use mapping_section from the chosen catalog entry.",
            ],
            "database_columns": columns,
            "parameter_catalog": parameter_catalog,
            "required_json_output": {
                "mappings": [
                    {
                        "column": "database column name",
                        "parameter_id": "integer or null",
                        "parameter_name": "matched parameter name or null",
                        "mapping_section": "SeriesMapping, SpecimenMapping, NumericMapping, or null",
                        "confidence": "number from 0 to 1",
                        "reason": "short explanation",
                    }
                ]
            },
        }

    def _parse_json(self, text: str) -> Any:
        cleaned = text.strip()

        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`").strip()
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "OpenAI returned text that was not valid JSON. Raw response: "
                f"{text[:500]}"
            ) from exc

    def _extract_suggestions(self, raw_result: Any) -> list[MappingSuggestion]:
        if isinstance(raw_result, dict):
            raw_mappings = raw_result.get("mappings", [])
        elif isinstance(raw_result, list):
            raw_mappings = raw_result
        else:
            raise RuntimeError("OpenAI returned JSON in an unexpected shape.")

        if not isinstance(raw_mappings, list):
            raise RuntimeError("OpenAI returned mappings in an unexpected shape.")

        return [
            MappingSuggestion.from_dict(item)
            for item in raw_mappings
            if isinstance(item, dict)
        ]

    def _validate_suggestions(
        self,
        suggestions: list[MappingSuggestion],
        columns: list[dict[str, Any]],
        parameter_catalog: list[dict[str, Any]],
    ) -> list[MappingSuggestion]:
        allowed_columns = {str(column.get("name", "")) for column in columns}
        catalog_by_id = {
            int(parameter["id"]): parameter
            for parameter in parameter_catalog
            if parameter.get("id") is not None
        }

        validated = []
        for suggestion in suggestions:
            if suggestion.column not in allowed_columns:
                continue

            if suggestion.parameter_id is None:
                validated.append(suggestion)
                continue

            catalog_entry = catalog_by_id.get(suggestion.parameter_id)
            if catalog_entry is None:
                suggestion.parameter_id = None
                suggestion.parameter_name = None
                suggestion.mapping_section = None
                suggestion.confidence = 0.0
                suggestion.reason = "Model suggested a parameter ID outside the catalog."
            else:
                suggestion.parameter_name = str(catalog_entry.get("name", suggestion.parameter_name))
                suggestion.mapping_section = str(catalog_entry.get("mapping_section", suggestion.mapping_section))

            validated.append(suggestion)

        return validated


def build_column_context(
    columns: list[dict[str, Any]],
    sample_rows: list[list[Any]] | None = None,
) -> list[dict[str, Any]]:
    """Attach per-column sample values to the schema returned by DatabaseConnector."""
    sample_rows = sample_rows or []
    column_context = []

    for index, column in enumerate(columns):
        sample_values = []
        for row in sample_rows:
            if index < len(row):
                value = row[index]
                if value not in (None, "NULL", ""):
                    sample_values.append(str(value))

        column_context.append(
            {
                "name": column.get("name"),
                "type": column.get("type"),
                "size": column.get("size"),
                "sample_values": sample_values[:3],
            }
        )

    return column_context


def load_parameter_catalog(path: str) -> list[dict[str, Any]]:
    """Load the allowed testXpert parameter catalog from a JSON file."""
    with open(path, "r", encoding="utf-8") as file:
        catalog = json.load(file)

    if not isinstance(catalog, list):
        raise ValueError("Parameter catalog must be a JSON array.")

    return catalog
