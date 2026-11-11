"""Caso de uso: obtener sugerencias de autocompletado a partir de una guía de remisión."""

from dataclasses import dataclass

from app.application.ports import (
    DocumentExtractor,
    DocumentInspector,
    ExtractionRepository,
    NewExtraction,
)
from app.domain.document import UploadedFile, accept_document, check_page_count, fingerprint
from app.domain.extraction import Extraction
from app.domain.field_mapping import map_extraction


@dataclass(frozen=True)
class AutofillResult:
    extraction_id: int
    extraction: Extraction
    file_hash: str
    cached: bool


class AutofillDocument:
    def __init__(
        self,
        inspector: DocumentInspector,
        extractor: DocumentExtractor,
        repository: ExtractionRepository,
        max_file_bytes: int,
        confidence_threshold: float,
    ) -> None:
        self._inspector = inspector
        self._extractor = extractor
        self._repository = repository
        self._max_file_bytes = max_file_bytes
        self._confidence_threshold = confidence_threshold

    def execute(self, user_id: int, upload: UploadedFile) -> AutofillResult:
        document = accept_document(upload, self._max_file_bytes)
        check_page_count(document, self._inspector.count_pages(document))
        file_hash = fingerprint(document.content, user_id)

        # Mismo archivo y mismo usuario: se devuelve lo guardado sin llamar a Document AI.
        stored = self._repository.find(user_id, file_hash)
        if stored is not None:
            return AutofillResult(stored.id, stored.extraction, file_hash, cached=True)

        raw = self._extractor.extract(document)
        extraction = map_extraction(raw, self._confidence_threshold)

        # Si otra petición igual se guardó primero, save() devuelve ese registro.
        stored = self._repository.save(
            NewExtraction(user_id, file_hash, extraction, raw.processor_version)
        )
        return AutofillResult(stored.id, stored.extraction, file_hash, cached=False)
