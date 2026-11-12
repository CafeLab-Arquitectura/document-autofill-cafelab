from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile
from starlette.concurrency import run_in_threadpool

from app.application.autofill_document import AutofillDocument
from app.domain.document import UploadedFile
from app.domain.errors import InvalidDocument
from app.interfaces.http.error_handlers import (
    EXTRACTION_FAILED_MESSAGE,
    EXTRACTION_TIMEOUT_MESSAGE,
)
from app.interfaces.http.identity import UNAUTHORIZED_MESSAGE, require_user_id
from app.interfaces.http.schemas import AutofillResponse, ErrorMessage

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

FILE_FIELD = "file"


def _error(description: str, *examples: str) -> dict:
    """Respuesta de error para OpenAPI, con un ejemplo por cada mensaje posible."""
    return {
        "model": ErrorMessage,
        "description": description,
        "content": {
            "application/json": {
                "examples": {
                    f"ejemplo{n}": {"value": {"message": message}}
                    for n, message in enumerate(examples, start=1)
                }
            }
        },
    }


ERROR_RESPONSES = {
    401: _error("Falta X-User-Id o no es un entero positivo.", UNAUTHORIZED_MESSAGE),
    413: _error("El archivo supera MAX_FILE_MB (10 MB).", "El archivo supera el máximo de 10 MB."),
    415: _error("El contenido no es JPG, PNG ni PDF.", "Formato no permitido. Usa JPG, PNG o PDF."),
    422: _error(
        "Archivo vacío, corrupto, protegido, ausente, repetido o PDF de más de 1 página.",
        "El PDF tiene 2 páginas; solo se acepta un PDF de 1 página.",
        "El archivo está vacío.",
        "El archivo está corrupto o no se puede leer.",
        "Falta el archivo en el campo 'file'.",
    ),
    502: _error(
        "Document AI falló (después de un reintento si el error era transitorio). "
        "El usuario debe completar el formulario manualmente.",
        EXTRACTION_FAILED_MESSAGE,
    ),
    504: _error(
        "Document AI no respondió a tiempo, tampoco en el reintento. "
        "El usuario debe completar el formulario manualmente.",
        EXTRACTION_TIMEOUT_MESSAGE,
    ),
}


def get_autofill_use_case(request: Request) -> AutofillDocument:
    return request.app.state.autofill_use_case


@router.post(
    "/autofill",
    response_model=AutofillResponse,
    response_model_by_alias=True,
    summary="Sugerencias para el formulario de lote a partir de una guía de remisión",
    description=(
        "Recibe **un solo archivo** (JPG, PNG o PDF de 1 página, máximo 10 MB) en el campo "
        "`file` y lo lee con Document AI (Custom Extractor, sin entrenamiento).\n\n"
        "Devuelve los datos del lote como **sugerencias**: no crea ni valida el lote, eso "
        "sigue siendo de Management. Los campos dudosos traen advertencias en `warnings`.\n\n"
        "No se guarda nada: cada petición llama a Document AI (`extractionId` siempre null "
        "y `cached` siempre false)."
    ),
    responses=ERROR_RESPONSES,
)
async def autofill(
    request: Request,
    user_id: Annotated[int, Depends(require_user_id)],
    use_case: Annotated[AutofillDocument, Depends(get_autofill_use_case)],
    file: Annotated[
        UploadFile | None,
        File(description="Guía de remisión (Formato X): JPG, PNG o PDF de 1 página, máximo 10 MB."),
    ] = None,
) -> AutofillResponse:
    form = await request.form()
    if len(form.getlist(FILE_FIELD)) > 1:
        raise InvalidDocument("Envía un solo archivo por petición.")
    if file is None:
        raise InvalidDocument("Falta el archivo en el campo 'file'.")

    # Se lee como máximo un byte más que el límite: basta para saber si lo supera.
    content = await file.read(request.app.state.settings.max_file_bytes + 1)
    upload = UploadedFile(content=content, filename=file.filename, content_type=file.content_type)

    result = await run_in_threadpool(use_case.execute, user_id, upload)
    return AutofillResponse.from_result(result)
