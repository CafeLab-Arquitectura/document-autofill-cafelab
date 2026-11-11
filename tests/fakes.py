"""Dobles de prueba de los puertos. Ningún test llama a Google Cloud ni a una base real."""

import copy
import json
from itertools import count

from app.application.ports import (
    ExtractionFailed,
    NewExtraction,
    RepositoryUnavailable,
    StoredExtraction,
)
from app.domain.document import Document
from app.domain.extraction import ExtractedEntity, RawExtraction
from app.infrastructure.persistence.extraction_json import (
    extraction_from_json,
    extraction_to_json,
)

FAKE_ENTITIES: tuple[ExtractedEntity, ...] = (
    ExtractedEntity("lot_name", "Finca El Mirador L-14", 0.93),
    ExtractedEntity("supplier_name", "Cooperativa Agraria Ejemplo", 0.88),
    ExtractedEntity("coffee_type", "arabica", 0.91),
    ExtractedEntity("origin", "Villa Rica, Oxapampa, Perú", 0.95),
    ExtractedEntity("processing_method", "Lavado", 0.62),
    ExtractedEntity("altitude_meters", "1,650 msnm", 0.97),
    ExtractedEntity("initial_weight_kg", "69", 0.96),
    ExtractedEntity("certifications", "Orgánico", 0.80),
)


class FakeDocumentExtractor:
    """Devuelve siempre las mismas entidades y registra los documentos recibidos."""

    def __init__(self, entities: tuple[ExtractedEntity, ...] = FAKE_ENTITIES) -> None:
        self.entities = entities
        self.calls: list[Document] = []

    def extract(self, document: Document) -> RawExtraction:
        self.calls.append(document)
        return RawExtraction(entities=self.entities, processor_version="fake")


class FailingExtractor:
    def __init__(self) -> None:
        self.calls = 0

    def extract(self, document: Document) -> RawExtraction:
        self.calls += 1
        raise ExtractionFailed("ServiceUnavailable")


class InMemoryExtractionRepository:
    """Imita la tabla document_extractions, incluido el UNIQUE (user_id, file_hash).

    Guarda el resultado como JSON, igual que la columna jsonb, para probar
    también el ida y vuelta del formato.
    """

    def __init__(self) -> None:
        self.rows: dict[tuple[int, str], dict] = {}
        self._ids = count(1)

    def find(self, user_id: int, file_hash: str) -> StoredExtraction | None:
        row = self.rows.get((user_id, file_hash))
        return self._to_stored(row) if row else None

    def save(self, new: NewExtraction) -> StoredExtraction:
        key = (new.user_id, new.file_hash)
        if key not in self.rows:  # ON CONFLICT DO NOTHING
            self.rows[key] = {
                "id": next(self._ids),
                "result": json.dumps(extraction_to_json(new.extraction)),
                "processor_version": new.processor_version,
            }
        return self._to_stored(self.rows[key])

    @staticmethod
    def _to_stored(row: dict) -> StoredExtraction:
        return StoredExtraction(
            id=row["id"], extraction=extraction_from_json(json.loads(row["result"]))
        )


class RacingRepository(InMemoryExtractionRepository):
    """Simula dos peticiones iguales a la vez: find() no ve el registro
    porque la otra petición lo guarda justo antes de nuestro save()."""

    def __init__(self, winner: NewExtraction) -> None:
        super().__init__()
        self._winner = copy.deepcopy(winner)

    def find(self, user_id: int, file_hash: str) -> StoredExtraction | None:
        return None

    def save(self, new: NewExtraction) -> StoredExtraction:
        super().save(self._winner)
        return super().save(new)


class UnavailableRepository:
    def find(self, user_id: int, file_hash: str) -> StoredExtraction | None:
        raise RepositoryUnavailable("OperationalError")

    def save(self, new: NewExtraction) -> StoredExtraction:
        raise RepositoryUnavailable("OperationalError")
