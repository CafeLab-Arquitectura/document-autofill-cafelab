"""Punto de entrada: crea la aplicación FastAPI y une las capas.

Se usa como fábrica, así la configuración se valida al arrancar y no al importar:
    python -m app.main
    uvicorn app.main:create_app --factory
"""

import sys

import uvicorn
from fastapi import FastAPI

from app.application.autofill_document import AutofillDocument
from app.application.ports import DocumentExtractor, DocumentInspector
from app.infrastructure.config import ConfigurationError, Settings, get_settings
from app.infrastructure.document_ai.fake_extractor import FakeDocumentExtractor
from app.infrastructure.files.document_inspector import FileDocumentInspector
from app.interfaces.http.autofill_router import router as autofill_router
from app.interfaces.http.error_handlers import register_error_handlers
from app.interfaces.http.health_router import router as health_router


def create_app(
    settings: Settings | None = None,
    extractor: DocumentExtractor | None = None,
    inspector: DocumentInspector | None = None,
) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(
        title="document-autofill-cafelab",
        version="0.1.0",
        description=(
            "Lee una guía de remisión (Formato X) con Document AI y devuelve los datos "
            "del lote de café como sugerencias para autocompletar el formulario."
        ),
    )
    app.state.settings = settings
    app.state.autofill_use_case = AutofillDocument(
        inspector=inspector or FileDocumentInspector(),
        # Adaptador falso hasta la Fase 3, donde entra el de Document AI.
        extractor=extractor or FakeDocumentExtractor(),
        max_file_bytes=settings.max_file_bytes,
    )

    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(autofill_router)
    return app


def run() -> None:
    try:
        settings = get_settings()
    except ConfigurationError as error:
        print(error, file=sys.stderr)
        sys.exit(1)
    uvicorn.run(create_app(settings), host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    run()
