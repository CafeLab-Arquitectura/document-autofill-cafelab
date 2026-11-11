from app.domain.extraction import ExtractedEntity, FieldName, RawExtraction, WarningCode
from app.domain.field_mapping import map_extraction


def test_missing_fields_are_null_with_not_found_warning():
    extraction = map_extraction(RawExtraction(entities=(ExtractedEntity("lot_name", "L-1", 0.9),)))

    assert extraction.fields[FieldName.ORIGIN].value is None
    assert extraction.fields[FieldName.ORIGIN].confidence is None
    not_found = {w.field for w in extraction.warnings if w.code is WarningCode.NOT_FOUND}
    assert not_found == set(FieldName) - {FieldName.LOT_NAME}


def test_blank_values_count_as_not_found():
    extraction = map_extraction(RawExtraction(entities=(ExtractedEntity("origin", "   ", 0.9),)))

    assert extraction.fields[FieldName.ORIGIN].value is None


def test_single_field_keeps_the_most_confident_value():
    raw = RawExtraction(
        entities=(
            ExtractedEntity("origin", "Jaén", 0.6),
            ExtractedEntity("origin", "Villa Rica", 0.9),
        )
    )

    assert map_extraction(raw).fields[FieldName.ORIGIN].value == "Villa Rica"


def test_certifications_are_a_list_with_the_lowest_confidence():
    raw = RawExtraction(
        entities=(
            ExtractedEntity("certifications", "ORGANIC", 0.9),
            ExtractedEntity("certifications", "FAIR_TRADE", 0.75),
        )
    )

    field = map_extraction(raw).fields[FieldName.CERTIFICATIONS]

    assert field.value == ["ORGANIC", "FAIR_TRADE"]
    assert field.confidence == 0.75


def test_unknown_entities_are_ignored():
    raw = RawExtraction(entities=(ExtractedEntity("otro_campo", "x", 0.9),))

    assert len(map_extraction(raw).fields) == len(FieldName)
