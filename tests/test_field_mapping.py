from app.domain.extraction import ExtractedEntity, FieldName, RawExtraction, WarningCode
from app.domain.field_mapping import map_extraction

THRESHOLD = 0.7


def extract(*entities: tuple[str, str, float], threshold: float = THRESHOLD):
    raw = RawExtraction(entities=tuple(ExtractedEntity(*entity) for entity in entities))
    return map_extraction(raw, threshold)


def warning_codes(extraction, field_name):
    return [w.code for w in extraction.warnings if w.field is field_name]


# NOT_FOUND


def test_missing_fields_are_null_with_not_found_warning():
    extraction = extract(("lot_name", "L-1", 0.9))

    assert extraction.fields[FieldName.ORIGIN].value is None
    assert extraction.fields[FieldName.ORIGIN].confidence is None
    not_found = {w.field for w in extraction.warnings if w.code is WarningCode.NOT_FOUND}
    assert not_found == set(FieldName) - {FieldName.LOT_NAME}


def test_blank_values_count_as_not_found():
    extraction = extract(("origin", "   ", 0.9))

    assert extraction.fields[FieldName.ORIGIN].value is None
    assert warning_codes(extraction, FieldName.ORIGIN) == [WarningCode.NOT_FOUND]


def test_unknown_entities_are_ignored():
    assert len(extract(("otro_campo", "x", 0.9)).fields) == len(FieldName)


# Valores normalizados


def test_full_guide_is_mapped_to_management_values():
    extraction = extract(
        ("lot_name", "Finca El Mirador L-14", 0.93),
        ("supplier_name", "Cooperativa Ejemplo", 0.88),
        ("coffee_type", "arabica", 0.91),
        ("origin", "Villa Rica, Oxapampa, Perú", 0.95),
        ("processing_method", "fermentacion anaerobica", 0.9),
        ("altitude_meters", "1,650 msnm", 0.97),
        ("initial_weight_kg", "69.5 kg", 0.96),
        ("certifications", "Orgánico", 0.8),
        ("certifications", "Comercio Justo", 0.85),
    )

    values = {name: suggestion.value for name, suggestion in extraction.fields.items()}
    assert values == {
        FieldName.LOT_NAME: "Finca El Mirador L-14",
        FieldName.SUPPLIER_NAME: "Cooperativa Ejemplo",
        FieldName.COFFEE_TYPE: "Arábica",
        FieldName.ORIGIN: "Villa Rica, Oxapampa, Perú",
        FieldName.PROCESSING_METHOD: "Fermentación anaeróbica",
        FieldName.ALTITUDE_METERS: 1650,
        FieldName.INITIAL_WEIGHT: 69.5,
        FieldName.CERTIFICATIONS: ["ORGANIC", "FAIR_TRADE"],
    }
    assert extraction.warnings == []


def test_single_field_keeps_the_most_confident_value():
    extraction = extract(("origin", "Jaén", 0.6), ("origin", "Villa Rica", 0.9))

    assert extraction.fields[FieldName.ORIGIN].value == "Villa Rica"
    assert extraction.fields[FieldName.ORIGIN].confidence == 0.9


def test_certifications_confidence_is_the_lowest():
    extraction = extract(("certifications", "ORGANIC", 0.9), ("certifications", "Fair Trade", 0.75))

    assert extraction.fields[FieldName.CERTIFICATIONS].confidence == 0.75


# Advertencias de valor


def test_invalid_coffee_type_keeps_confidence_and_warns():
    extraction = extract(("coffee_type", "Geisha", 0.9))

    assert extraction.fields[FieldName.COFFEE_TYPE].value is None
    assert extraction.fields[FieldName.COFFEE_TYPE].confidence == 0.9
    assert warning_codes(extraction, FieldName.COFFEE_TYPE) == [WarningCode.INVALID_VALUE]


def test_invalid_number_warns():
    extraction = extract(("initial_weight_kg", "1.650,5", 0.9))

    assert extraction.fields[FieldName.INITIAL_WEIGHT].value is None
    assert warning_codes(extraction, FieldName.INITIAL_WEIGHT) == [WarningCode.INVALID_NUMBER]


def test_unknown_certification_warns_and_keeps_the_rest():
    extraction = extract(("certifications", "Orgánico", 0.9), ("certifications", "UTZ", 0.9))

    assert extraction.fields[FieldName.CERTIFICATIONS].value == ["ORGANIC"]
    assert warning_codes(extraction, FieldName.CERTIFICATIONS) == [
        WarningCode.UNKNOWN_CERTIFICATION
    ]


# LOW_CONFIDENCE


def test_low_confidence_returns_the_value_with_a_warning():
    extraction = extract(("processing_method", "Lavado", 0.62))

    assert extraction.fields[FieldName.PROCESSING_METHOD].value == "Lavado"
    low = [w for w in extraction.warnings if w.code is WarningCode.LOW_CONFIDENCE]
    assert len(low) == 1
    assert low[0].field is FieldName.PROCESSING_METHOD
    assert low[0].message == "Revisar: confianza 0.62 menor al umbral 0.7"


def test_confidence_equal_to_threshold_has_no_warning():
    extraction = extract(("origin", "Villa Rica", 0.7))

    assert warning_codes(extraction, FieldName.ORIGIN) == []


def test_threshold_is_configurable():
    extraction = extract(("origin", "Villa Rica", 0.85), threshold=0.9)

    [warning] = [w for w in extraction.warnings if w.field is FieldName.ORIGIN]
    assert warning.code is WarningCode.LOW_CONFIDENCE
    assert warning.message == "Revisar: confianza 0.85 menor al umbral 0.9"


def test_no_low_confidence_warning_when_the_value_was_discarded():
    extraction = extract(("coffee_type", "Geisha", 0.3))

    assert warning_codes(extraction, FieldName.COFFEE_TYPE) == [WarningCode.INVALID_VALUE]
