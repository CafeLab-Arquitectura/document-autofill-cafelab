"""Contrato HTTP del endpoint de autocompletado."""

from pydantic import BaseModel, ConfigDict, Field

from app.application.autofill_document import AutofillResult
from app.domain.extraction import FieldName, FieldSuggestion, WarningCode


class ErrorMessage(BaseModel):
    """Formato de error común a los servicios de CaféLab."""

    message: str


class FieldOut(BaseModel):
    value: str | int | float | list[str] | None = Field(
        description="Valor sugerido; null si no se encontró o no es válido."
    )
    confidence: float | None = Field(description="Confianza de Document AI (0 a 1).")

    @classmethod
    def from_domain(cls, suggestion: FieldSuggestion) -> "FieldOut":
        return cls(value=suggestion.value, confidence=suggestion.confidence)


class FieldsOut(BaseModel):
    """Los 8 campos del formulario de lote. Cada uno trae value y confidence."""

    model_config = ConfigDict(populate_by_name=True)

    lot_name: FieldOut = Field(alias=FieldName.LOT_NAME, description="Texto. Fila 'Nombre del lote'.")
    supplier_name: FieldOut = Field(
        alias=FieldName.SUPPLIER_NAME,
        description="Texto informativo (sección 2). El usuario elige el supplierId a mano.",
    )
    coffee_type: FieldOut = Field(
        alias=FieldName.COFFEE_TYPE, description="Arábica, Robusta o Mezcla."
    )
    origin: FieldOut = Field(alias=FieldName.ORIGIN, description="Texto. Fila 'Origen'.")
    processing_method: FieldOut = Field(
        alias=FieldName.PROCESSING_METHOD,
        description="Lavado, Natural, Honey, Fermentación anaeróbica o Maceración carbónica.",
    )
    altitude_meters: FieldOut = Field(
        alias=FieldName.ALTITUDE_METERS, description="Número >= 0, en metros sobre el nivel del mar."
    )
    initial_weight: FieldOut = Field(
        alias=FieldName.INITIAL_WEIGHT, description="Número >= 0, en kg (peso neto)."
    )
    certifications: FieldOut = Field(
        alias=FieldName.CERTIFICATIONS,
        description="Lista con ORGANIC, FAIR_TRADE o RAINFOREST. Opcional.",
    )


class WarningOut(BaseModel):
    """Aviso sobre un campo: el front puede resaltarlo para que el usuario lo revise."""

    field: FieldName
    code: WarningCode = Field(
        description=(
            "NOT_FOUND: no está en el documento. INVALID_VALUE: valor fuera de la lista. "
            "INVALID_NUMBER: no es un número >= 0. UNKNOWN_CERTIFICATION: certificación "
            "descartada. LOW_CONFIDENCE: confianza menor a CONFIDENCE_THRESHOLD."
        )
    )
    message: str


RESPONSE_EXAMPLE = {
    "extractionId": None,
    "cached": False,
    "fields": {
        "lotName": {"value": "Finca El Mirador L-14", "confidence": 0.93},
        "supplierName": {"value": "Cooperativa Agraria Ejemplo", "confidence": 0.88},
        "coffeeType": {"value": "Arábica", "confidence": 0.91},
        "origin": {"value": "Villa Rica, Oxapampa, Perú", "confidence": 0.95},
        "processingMethod": {"value": "Lavado", "confidence": 0.62},
        "altitudeMeters": {"value": 1650, "confidence": 0.97},
        "initialWeight": {"value": 69, "confidence": 0.96},
        "certifications": {"value": ["ORGANIC"], "confidence": 0.8},
    },
    "warnings": [
        {
            "field": "processingMethod",
            "code": "LOW_CONFIDENCE",
            "message": "Revisar: confianza 0.62 menor al umbral 0.7",
        }
    ],
}


class AutofillResponse(BaseModel):
    """Sugerencias para autocompletar el formulario. No crea ni valida el lote."""

    model_config = ConfigDict(populate_by_name=True, json_schema_extra={"example": RESPONSE_EXAMPLE})

    # Se mantienen para no cambiar el contrato con el front. Sin persistencia,
    # no hay id guardado ni caché: siempre null y false.
    extraction_id: int | None = Field(
        alias="extractionId",
        description="Siempre null: el servicio no guarda las extracciones.",
    )
    cached: bool = Field(
        description="Siempre false: cada petición se procesa con Document AI (no hay caché)."
    )
    fields: FieldsOut
    warnings: list[WarningOut]

    @classmethod
    def from_result(cls, result: AutofillResult) -> "AutofillResponse":
        extraction = result.extraction
        return cls(
            extraction_id=None,
            cached=False,
            fields=FieldsOut(
                **{name.value: FieldOut.from_domain(s) for name, s in extraction.fields.items()}
            ),
            warnings=[
                WarningOut(field=w.field, code=w.code, message=w.message)
                for w in extraction.warnings
            ],
        )
