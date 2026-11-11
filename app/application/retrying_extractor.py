"""Política de reintento: UN solo reintento, solo ante errores transitorios.

Envuelve cualquier DocumentExtractor (patrón decorador), así la política no depende
de Google: el adaptador clasifica el error y aquí solo se decide si reintentar.
"""

import logging
from time import perf_counter

from app.application.ports import DocumentExtractor, ExtractionFailed, TransientExtractionError
from app.domain.document import Document
from app.domain.extraction import RawExtraction

logger = logging.getLogger(__name__)

MAX_RETRIES = 1


class RetryingDocumentExtractor:
    def __init__(self, extractor: DocumentExtractor, max_retries: int = MAX_RETRIES) -> None:
        self._extractor = extractor
        self._max_retries = max_retries

    def extract(self, document: Document) -> RawExtraction:
        attempt = 1
        while True:
            started = perf_counter()
            try:
                result = self._extractor.extract(document)
            except TransientExtractionError as error:
                will_retry = attempt <= self._max_retries
                _log_failure(attempt, started, error, will_retry)
                if not will_retry:
                    raise
                attempt += 1
            except ExtractionFailed as error:  # 4xx y errores permanentes: sin reintento
                _log_failure(attempt, started, error, will_retry=False)
                raise
            else:
                logger.info(
                    "docai.call",
                    extra={"fields": {"attempt": attempt, "durationMs": _ms(started), "ok": True}},
                )
                return result


def _log_failure(attempt: int, started: float, error: ExtractionFailed, will_retry: bool) -> None:
    logger.warning(
        "docai.call",
        extra={
            "fields": {
                "attempt": attempt,
                "durationMs": _ms(started),
                "ok": False,
                "errorType": type(error).__name__,
                "cause": str(error),  # solo el nombre del error de Google, nunca su mensaje
                "willRetry": will_retry,
            }
        },
    )


def _ms(started: float) -> int:
    return round((perf_counter() - started) * 1000)
