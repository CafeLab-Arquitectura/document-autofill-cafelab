from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile
from starlette.concurrency import run_in_threadpool

from app.application.autofill_document import AutofillDocument
from app.domain.document import UploadedFile
from app.domain.errors import InvalidDocument
from app.interfaces.http.identity import require_user_id
from app.interfaces.http.schemas import AutofillResponse, ErrorMessage

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

FILE_FIELD = "file"


def get_autofill_use_case(request: Request) -> AutofillDocument:
    return request.app.state.autofill_use_case


@router.post(
    "/autofill",
    response_model=AutofillResponse,
    response_model_by_alias=True,
    summary="Sugerencias para el formulario de lote a partir de una guía de remisión",
    description=(
        "Recibe un solo archivo (JPG, PNG o PDF de 1 página, máximo 10 MB) en el campo "
        "`file`. Devuelve los datos leídos como sugerencias: no crea ni valida el lote."
    ),
    responses={
        401: {"model": ErrorMessage, "description": "Falta X-User-Id o no es válida."},
        413: {"model": ErrorMessage, "description": "El archivo supera el tamaño máximo."},
        415: {"model": ErrorMessage, "description": "Formato no permitido."},
        422: {
            "model": ErrorMessage,
            "description": "Archivo vacío, corrupto, ausente, repetido o PDF de más de 1 página.",
        },
        502: {
            "model": ErrorMessage,
            "description": "Document AI falló; completar el formulario manualmente.",
        },
    },
)
async def autofill(
    request: Request,
    user_id: Annotated[int, Depends(require_user_id)],
    use_case: Annotated[AutofillDocument, Depends(get_autofill_use_case)],
    file: Annotated[UploadFile | None, File(description="Guía de remisión.")] = None,
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
