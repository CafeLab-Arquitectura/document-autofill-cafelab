"""Pasa las entidades del extractor a los campos de la respuesta.

Por ahora solo renombra los campos, agrupa las certificaciones y marca los campos
que faltan (NOT_FOUND). La normalización de valores y el resto de advertencias
se agregan en la Fase 3.
"""

from app.domain.extraction import (
    ExtractedEntity,
    Extraction,
    ExtractionWarning,
    FieldName,
    FieldSuggestion,
    RawExtraction,
    WarningCode,
)

EXTRACTOR_FIELDS: dict[str, FieldName] = {
    "lot_name": FieldName.LOT_NAME,
    "supplier_name": FieldName.SUPPLIER_NAME,
    "coffee_type": FieldName.COFFEE_TYPE,
    "origin": FieldName.ORIGIN,
    "processing_method": FieldName.PROCESSING_METHOD,
    "altitude_meters": FieldName.ALTITUDE_METERS,
    "initial_weight_kg": FieldName.INITIAL_WEIGHT,
    "certifications": FieldName.CERTIFICATIONS,
}

REPEATED_FIELDS = frozenset({FieldName.CERTIFICATIONS})


def _group_by_field(entities: tuple[ExtractedEntity, ...]) -> dict[FieldName, list[ExtractedEntity]]:
    grouped: dict[FieldName, list[ExtractedEntity]] = {}
    for entity in entities:
        field_name = EXTRACTOR_FIELDS.get(entity.name)
        text = entity.text.strip()
        if field_name is None or not text:
            continue
        grouped.setdefault(field_name, []).append(
            ExtractedEntity(entity.name, text, entity.confidence)
        )
    return grouped


def map_extraction(raw: RawExtraction) -> Extraction:
    grouped = _group_by_field(raw.entities)
    fields: dict[FieldName, FieldSuggestion] = {}
    warnings: list[ExtractionWarning] = []

    for field_name in FieldName:
        found = grouped.get(field_name)
        if not found:
            fields[field_name] = FieldSuggestion(value=None, confidence=None)
            warnings.append(
                ExtractionWarning(
                    field_name, WarningCode.NOT_FOUND, "No se encontró en el documento."
                )
            )
        elif field_name in REPEATED_FIELDS:
            fields[field_name] = FieldSuggestion(
                value=[entity.text for entity in found],
                confidence=min(entity.confidence for entity in found),
            )
        else:
            best = max(found, key=lambda entity: entity.confidence)
            fields[field_name] = FieldSuggestion(value=best.text, confidence=best.confidence)

    return Extraction(fields=fields, warnings=warnings)
