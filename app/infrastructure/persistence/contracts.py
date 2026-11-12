"""DESACTIVADO: contratos del repositorio de extracciones. Ver app/infrastructure/persistence/__init__.py."""

from dataclasses import dataclass
from typing import Protocol

from app.domain.extraction import Extraction


class RepositoryUnavailable(Exception):
    """La base de datos no responde o falló la consulta."""


@dataclass(frozen=True)
class NewExtraction:
    user_id: int
    file_hash: str
    extraction: Extraction
    processor_version: str | None


@dataclass(frozen=True)
class StoredExtraction:
    id: int
    extraction: Extraction


class ExtractionRepository(Protocol):
    """Guarda solo lo leído (campos y advertencias), nunca el archivo."""

    def find(self, user_id: int, file_hash: str) -> StoredExtraction | None:
        ...

    def save(self, new: NewExtraction) -> StoredExtraction:
        """Si ya existe una extracción para (user_id, file_hash), devuelve la existente."""
        ...
