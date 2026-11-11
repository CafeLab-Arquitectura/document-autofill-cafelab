"""Dobles de prueba de los puertos. Ningún test llama a Google Cloud."""

from app.application.ports import ExtractionFailed
from app.domain.document import Document
from app.domain.extraction import ExtractedEntity, RawExtraction

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
    def extract(self, document: Document) -> RawExtraction:
        raise ExtractionFailed("ServiceUnavailable")
