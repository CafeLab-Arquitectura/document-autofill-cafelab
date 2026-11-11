"""Pasa las entidades del extractor a los campos de la respuesta y aplica las reglas.

Advertencias:
- NOT_FOUND: el campo no está en el documento (valor null, confianza null).
- INVALID_VALUE: coffeeType o processingMethod fuera de la lista (valor null).
- INVALID_NUMBER: altitudeMeters o initialWeight no es un número >= 0 (valor null).
- UNKNOWN_CERTIFICATION: una certificación no reconocida (se descarta de la lista).
- LOW_CONFIDENCE: confianza menor al umbral; el valor se devuelve igual.
"""

from collections.abc import Callable

from app.domain.extraction import (
    ExtractedEntity,
    Extraction,
    ExtractionWarning,
    FieldName,
    FieldSuggestion,
    RawExtraction,
    WarningCode,
)
from app.domain.normalization import (
    Normalized,
    normalize_certifications,
    normalize_non_negative_number,
    normalize_option,
    normalize_text,
)
from app.domain.vocabulary import COFFEE_TYPE_INDEX, PROCESSING_METHOD_INDEX

# Nombre del campo en el Custom Extractor -> nombre en la respuesta.
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

# Regla de cada campo de un solo valor.
SINGLE_VALUE_RULES: dict[FieldName, Callable[[str], Normalized]] = {
    FieldName.LOT_NAME: normalize_text,
    FieldName.SUPPLIER_NAME: normalize_text,
    FieldName.ORIGIN: normalize_text,
    FieldName.COFFEE_TYPE: lambda text: normalize_option(text, COFFEE_TYPE_INDEX),
    FieldName.PROCESSING_METHOD: lambda text: normalize_option(text, PROCESSING_METHOD_INDEX),
    FieldName.ALTITUDE_METERS: normalize_non_negative_number,
    FieldName.INITIAL_WEIGHT: normalize_non_negative_number,
}

NOT_FOUND_MESSAGE = "No se encontró en el documento."


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


def _normalize(field_name: FieldName, found: list[ExtractedEntity]) -> tuple[Normalized, float]:
    if field_name is FieldName.CERTIFICATIONS:
        # Varias certificaciones: la confianza del campo es la más baja.
        return (
            normalize_certifications([entity.text for entity in found]),
            min(entity.confidence for entity in found),
        )
    # Un solo valor: si el modelo devolvió varios, se usa el de mayor confianza.
    best = max(found, key=lambda entity: entity.confidence)
    return SINGLE_VALUE_RULES[field_name](best.text), best.confidence


def _low_confidence_message(confidence: float, threshold: float) -> str:
    return f"Revisar: confianza {confidence:.2f} menor al umbral {threshold:g}"


def map_extraction(raw: RawExtraction, confidence_threshold: float) -> Extraction:
    grouped = _group_by_field(raw.entities)
    fields: dict[FieldName, FieldSuggestion] = {}
    warnings: list[ExtractionWarning] = []

    for field_name in FieldName:
        found = grouped.get(field_name)
        if not found:
            fields[field_name] = FieldSuggestion(value=None, confidence=None)
            warnings.append(ExtractionWarning(field_name, WarningCode.NOT_FOUND, NOT_FOUND_MESSAGE))
            continue

        normalized, confidence = _normalize(field_name, found)
        fields[field_name] = FieldSuggestion(value=normalized.value, confidence=confidence)
        warnings.extend(
            ExtractionWarning(field_name, issue.code, issue.message) for issue in normalized.issues
        )
        if normalized.value is not None and confidence < confidence_threshold:
            warnings.append(
                ExtractionWarning(
                    field_name,
                    WarningCode.LOW_CONFIDENCE,
                    _low_confidence_message(confidence, confidence_threshold),
                )
            )

    return Extraction(fields=fields, warnings=warnings)
