"""Adaptador FALSO de Document AI: devuelve siempre los mismos datos.

Sirve para probar el flujo de punta a punta sin llamar a Google Cloud.
El adaptador real lo reemplaza en la Fase 3.
"""

from app.domain.document import Document
from app.domain.extraction import ExtractedEntity, RawExtraction

FAKE_ENTITIES: tuple[ExtractedEntity, ...] = (
    ExtractedEntity("lot_name", "Finca El Mirador L-14", 0.93),
    ExtractedEntity("supplier_name", "Cooperativa Agraria Ejemplo", 0.88),
    ExtractedEntity("coffee_type", "Arábica", 0.91),
    ExtractedEntity("origin", "Villa Rica, Oxapampa, Perú", 0.95),
    ExtractedEntity("processing_method", "Lavado", 0.62),
    ExtractedEntity("altitude_meters", "1,650 msnm", 0.97),
    ExtractedEntity("initial_weight_kg", "69", 0.96),
    ExtractedEntity("certifications", "ORGANIC", 0.80),
)


class FakeDocumentExtractor:
    def extract(self, document: Document) -> RawExtraction:
        return RawExtraction(entities=FAKE_ENTITIES, processor_version="fake")
