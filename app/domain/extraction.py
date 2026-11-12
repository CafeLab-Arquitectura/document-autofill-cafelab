"""Modelos de la extracción: lo que entrega el extractor y lo que devuelve el servicio."""

from dataclasses import dataclass, field
from enum import StrEnum

FieldValue = str | int | float | list[str] | None


class FieldName(StrEnum):
    """Campos de la respuesta, con el nombre que usa Management."""

    LOT_NAME = "lotName"
    SUPPLIER_NAME = "supplierName"
    COFFEE_TYPE = "coffeeType"
    ORIGIN = "origin"
    PROCESSING_METHOD = "processingMethod"
    ALTITUDE_METERS = "altitudeMeters"
    INITIAL_WEIGHT = "initialWeight"
    CERTIFICATIONS = "certifications"


class WarningCode(StrEnum):
    NOT_FOUND = "NOT_FOUND"
    INVALID_VALUE = "INVALID_VALUE"
    INVALID_NUMBER = "INVALID_NUMBER"
    UNKNOWN_CERTIFICATION = "UNKNOWN_CERTIFICATION"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"


@dataclass(frozen=True)
class ExtractedEntity:
    """Un valor leído del documento, tal como lo entrega el extractor."""

    name: str
    text: str
    confidence: float


@dataclass(frozen=True)
class RawExtraction:
    """Respuesta del extractor traducida a objetos del servicio."""

    entities: tuple[ExtractedEntity, ...]
    processor_version: str | None = None


@dataclass(frozen=True)
class FieldSuggestion:
    value: FieldValue
    confidence: float | None


@dataclass(frozen=True)
class ExtractionWarning:
    field: FieldName
    code: WarningCode
    message: str


@dataclass(frozen=True)
class Extraction:
    """Sugerencias para el formulario, con sus advertencias."""

    fields: dict[FieldName, FieldSuggestion]
    warnings: list[ExtractionWarning] = field(default_factory=list)
