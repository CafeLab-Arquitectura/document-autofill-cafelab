"""Puertos: lo que el caso de uso necesita del exterior. La infraestructura los implementa."""

from typing import Protocol

from app.domain.document import Document
from app.domain.extraction import RawExtraction


class ExtractionFailed(Exception):
    """El extractor no pudo leer el documento. El usuario debe completar el formulario a mano.

    Usada directamente, es un error permanente (por ejemplo un 4xx): no se reintenta.
    """


class TransientExtractionError(ExtractionFailed):
    """Error pasajero (5xx, UNAVAILABLE). Se puede reintentar una vez."""


class ExtractionTimeout(TransientExtractionError):
    """El extractor no respondió a tiempo (timeout, DEADLINE_EXCEEDED). Se puede reintentar una vez."""


class DocumentInspector(Protocol):
    def count_pages(self, document: Document) -> int:
        """Devuelve el número de páginas. Lanza InvalidDocument si el archivo está corrupto."""
        ...


class DocumentExtractor(Protocol):
    def extract(self, document: Document) -> RawExtraction:
        """Lee el documento y devuelve los valores encontrados, sin normalizar.

        Lanza ExtractionFailed si el servicio externo falla. Nunca deja salir
        tipos ni excepciones de la librería que use por dentro.
        """
        ...
