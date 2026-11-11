"""Contrato HTTP del endpoint de autocompletado."""

from pydantic import BaseModel, ConfigDict, Field

from app.application.autofill_document import AutofillResult
from app.domain.extraction import FieldName, FieldSuggestion, WarningCode


class ErrorMessage(BaseModel):
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
    model_config = ConfigDict(populate_by_name=True)

    lot_name: FieldOut = Field(alias=FieldName.LOT_NAME)
    supplier_name: FieldOut = Field(alias=FieldName.SUPPLIER_NAME)
    coffee_type: FieldOut = Field(alias=FieldName.COFFEE_TYPE)
    origin: FieldOut = Field(alias=FieldName.ORIGIN)
    processing_method: FieldOut = Field(alias=FieldName.PROCESSING_METHOD)
    altitude_meters: FieldOut = Field(alias=FieldName.ALTITUDE_METERS)
    initial_weight: FieldOut = Field(alias=FieldName.INITIAL_WEIGHT)
    certifications: FieldOut = Field(alias=FieldName.CERTIFICATIONS)


class WarningOut(BaseModel):
    field: FieldName
    code: WarningCode
    message: str


class AutofillResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

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
