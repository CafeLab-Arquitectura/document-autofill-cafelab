"""Respuestas de error con el mismo formato que los otros servicios: {"message": "..."}."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.errors import DocumentRejected, FileTooLarge, InvalidDocument, UnsupportedFileType

_DOCUMENT_ERROR_STATUS: dict[type[DocumentRejected], int] = {
    UnsupportedFileType: 415,
    FileTooLarge: 413,
    InvalidDocument: 422,
}


def error_response(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"message": message})


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, error: StarletteHTTPException) -> JSONResponse:
        return error_response(error.status_code, str(error.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, error: RequestValidationError) -> JSONResponse:
        fields = ", ".join(".".join(str(part) for part in e["loc"]) for e in error.errors())
        return error_response(422, f"Solicitud inválida: {fields}")

    @app.exception_handler(DocumentRejected)
    async def document_rejected(_: Request, error: DocumentRejected) -> JSONResponse:
        return error_response(_DOCUMENT_ERROR_STATUS.get(type(error), 422), error.message)
