"""Caso de uso: obtener sugerencias de autocompletado a partir de una guía de remisión."""

from dataclasses import dataclass

from app.application.ports import DocumentExtractor, DocumentInspector
from app.domain.document import UploadedFile, accept_document, check_page_count, fingerprint
from app.domain.extraction import Extraction
from app.domain.field_mapping import map_extraction


@dataclass(frozen=True)
class AutofillResult:
    extraction: Extraction
    file_hash: str
    extraction_id: int | None = None  # Se asigna al guardar (Fase 4)
    cached: bool = False


class AutofillDocument:
    def __init__(
        self,
        inspector: DocumentInspector,
        extractor: DocumentExtractor,
        max_file_bytes: int,
        confidence_threshold: float,
    ) -> None:
        self._inspector = inspector
        self._extractor = extractor
        self._max_file_bytes = max_file_bytes
        self._confidence_threshold = confidence_threshold

    def execute(self, user_id: int, upload: UploadedFile) -> AutofillResult:
        document = accept_document(upload, self._max_file_bytes)
        check_page_count(document, self._inspector.count_pages(document))

        file_hash = fingerprint(document.content, user_id)
        raw = self._extractor.extract(document)

        return AutofillResult(
            extraction=map_extraction(raw, self._confidence_threshold),
            file_hash=file_hash,
        )
