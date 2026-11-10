"""Punto de entrada: crea la aplicación FastAPI y une las capas.

Se usa como fábrica, así la configuración se valida al arrancar y no al importar:
    python -m app.main
    uvicorn app.main:create_app --factory
"""

import sys

import uvicorn
from fastapi import FastAPI

from app.infrastructure.config import ConfigurationError, Settings, get_settings
from app.interfaces.http.error_handlers import register_error_handlers
from app.interfaces.http.health_router import router as health_router


def create_app(settings: Settings | None = None) -> FastAPI:
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

    register_error_handlers(app)
    app.include_router(health_router)
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
