"""Caso de uso: obtener sugerencias de autocompletado a partir de una guía de remisión."""

import logging
from dataclasses import dataclass
from time import perf_counter

from app.application.log_context import bind, log_context, short_hash
from app.application.ports import (
    DocumentExtractor,
    DocumentInspector,
    ExtractionFailed,
    ExtractionRepository,
    ExtractionTimeout,
    NewExtraction,
    RepositoryUnavailable,
)
from app.domain.document import UploadedFile, accept_document, check_page_count, fingerprint
from app.domain.errors import DocumentRejected
from app.domain.extraction import Extraction
from app.domain.field_mapping import map_extraction

logger = logging.getLogger(__name__)


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
        started = perf_counter()
        with log_context(userId=user_id):
            try:
                result = self._execute(user_id, upload)
            except DocumentRejected as error:
                _log(logging.INFO, started, "rejected", reason=type(error).__name__)
                raise
            except ExtractionTimeout:
                _log(logging.WARNING, started, "docai_timeout")
                raise
            except ExtractionFailed as error:
                _log(logging.WARNING, started, "docai_failed", reason=str(error))
                raise
            except RepositoryUnavailable as error:
                _log(logging.ERROR, started, "db_unavailable", reason=str(error))
                raise
            _log(
                logging.INFO,
                started,
                "cached" if result.cached else "extracted",
                extractionId=result.extraction_id,
            )
            return result

    def _execute(self, user_id: int, upload: UploadedFile) -> AutofillResult:
        document = accept_document(upload, self._max_file_bytes)
        check_page_count(document, self._inspector.count_pages(document))
        file_hash = fingerprint(document.content, user_id)
        bind(fileHash=short_hash(file_hash))

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


def _log(level: int, started: float, result: str, **fields: object) -> None:
    """Una línea por petición. Nunca incluye el contenido del archivo ni los valores leídos."""
    duration_ms = round((perf_counter() - started) * 1000)
    logger.log(
        level,
        "autofill.request",
        extra={"fields": {"result": result, "durationMs": duration_ms, **fields}},
    )
