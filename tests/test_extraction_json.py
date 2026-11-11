import json

from app.domain.extraction import (
    Extraction,
    ExtractionWarning,
    FieldName,
    FieldSuggestion,
    WarningCode,
)
from app.infrastructure.persistence.extraction_json import (
    extraction_from_json,
    extraction_to_json,
)

EXTRACTION = Extraction(
    fields={
        FieldName.LOT_NAME: FieldSuggestion("Finca El Mirador L-14", 0.93),
        FieldName.ALTITUDE_METERS: FieldSuggestion(1650, 0.97),
        FieldName.INITIAL_WEIGHT: FieldSuggestion(60.5, 1.0),
        FieldName.CERTIFICATIONS: FieldSuggestion(["ORGANIC", "FAIR_TRADE"], 0.8),
        FieldName.ORIGIN: FieldSuggestion(None, None),
    },
    warnings=[
        ExtractionWarning(FieldName.ORIGIN, WarningCode.NOT_FOUND, "No se encontró en el documento.")
    ],
)


def test_result_has_the_same_shape_as_the_http_response():
    data = extraction_to_json(EXTRACTION)

    assert data["fields"]["lotName"] == {"value": "Finca El Mirador L-14", "confidence": 0.93}
    assert data["warnings"] == [
        {"field": "origin", "code": "NOT_FOUND", "message": "No se encontró en el documento."}
    ]


def test_round_trip_through_json_keeps_types():
    restored = extraction_from_json(json.loads(json.dumps(extraction_to_json(EXTRACTION))))

    assert restored == EXTRACTION
    assert type(restored.fields[FieldName.ALTITUDE_METERS].value) is int
    assert type(restored.fields[FieldName.INITIAL_WEIGHT].value) is float
