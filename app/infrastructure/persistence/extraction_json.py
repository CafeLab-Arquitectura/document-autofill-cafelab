"""Formato de la columna result (jsonb): el mismo de "fields" y "warnings" en la respuesta HTTP."""

from typing import Any

from app.domain.extraction import (
    Extraction,
    ExtractionWarning,
    FieldName,
    FieldSuggestion,
    WarningCode,
)


def extraction_to_json(extraction: Extraction) -> dict[str, Any]:
    return {
        "fields": {
            name.value: {"value": suggestion.value, "confidence": suggestion.confidence}
            for name, suggestion in extraction.fields.items()
        },
        "warnings": [
            {"field": w.field.value, "code": w.code.value, "message": w.message}
            for w in extraction.warnings
        ],
    }


def extraction_from_json(data: dict[str, Any]) -> Extraction:
    return Extraction(
        fields={
            FieldName(name): FieldSuggestion(value=item["value"], confidence=item["confidence"])
            for name, item in data["fields"].items()
        },
        warnings=[
            ExtractionWarning(FieldName(w["field"]), WarningCode(w["code"]), w["message"])
            for w in data["warnings"]
        ],
    )
