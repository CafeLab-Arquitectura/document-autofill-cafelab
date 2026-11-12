"""Adaptador de Document AI con respuestas simuladas. Ningún test llama a Google Cloud."""

import pytest
from google.api_core import exceptions as google_exceptions
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import documentai

from app.application.ports import ExtractionFailed
from app.domain.document import Document, DocumentFormat
from app.domain.extraction import ExtractedEntity, FieldName, RawExtraction
from app.domain.field_mapping import map_extraction
from app.infrastructure.config import load_settings
from app.infrastructure.document_ai.documentai_extractor import (
    DocumentAiExtractor,
    processor_resource_name,
)
from tests.conftest import VALID_ENV

DOCUMENT = Document(content=b"%PDF-1.7 ...", format=DocumentFormat.PDF)


def entity(type_: str, mention_text: str = "", confidence: float = 0.9, normalized: str = ""):
    return documentai.Document.Entity(
        type_=type_,
        mention_text=mention_text,
        confidence=confidence,
        normalized_value=documentai.Document.Entity.NormalizedValue(text=normalized),
    )


def process_response(*entities) -> documentai.ProcessResponse:
    return documentai.ProcessResponse(document=documentai.Document(entities=list(entities)))


class FakeClient:
    """Imita DocumentProcessorServiceClient.process_document."""

    def __init__(self, response=None, error: Exception | None = None):
        self.response = response or process_response()
        self.error = error
        self.calls: list[dict] = []

    def process_document(self, request, timeout=None, retry=None):
        self.calls.append({"request": request, "timeout": timeout, "retry": retry})
        if self.error is not None:
            raise self.error
        return self.response


def make_extractor(client, **settings_overrides) -> DocumentAiExtractor:
    return DocumentAiExtractor(load_settings(**{**VALID_ENV, **settings_overrides}), client=client)


# Petición


def test_processor_name_uses_default_version_when_none_is_set():
    settings = load_settings(**VALID_ENV)

    assert processor_resource_name(settings) == (
        "projects/test-project/locations/us/processors/test-processor"
    )


def test_processor_name_includes_version_when_set():
    settings = load_settings(**VALID_ENV, docai_processor_version="v-zero-shot")

    assert processor_resource_name(settings).endswith(
        "/processors/test-processor/processorVersions/v-zero-shot"
    )


def test_request_sends_content_mime_type_and_timeout_without_library_retries():
    client = FakeClient()

    make_extractor(client, docai_timeout_seconds=10).extract(DOCUMENT)

    call = client.calls[0]
    assert call["request"].name == "projects/test-project/locations/us/processors/test-processor"
    assert call["request"].raw_document.content == DOCUMENT.content
    assert call["request"].raw_document.mime_type == "application/pdf"
    assert call["timeout"] == 10
    assert call["retry"] is None


# Traducción de la respuesta (anticorrupción)


def test_response_is_translated_to_service_objects():
    client = FakeClient(
        process_response(
            entity("lot_name", "Finca El Mirador L-14", 0.93),
            entity("altitude_meters", "1,650 msnm", 0.97),
        )
    )

    result = make_extractor(client, docai_processor_version="v1").extract(DOCUMENT)

    assert result == RawExtraction(
        entities=(
            ExtractedEntity("lot_name", "Finca El Mirador L-14", 0.93),
            ExtractedEntity("altitude_meters", "1,650 msnm", 0.97),
        ),
        processor_version="v1",
    )
    assert all(type(e) is ExtractedEntity for e in result.entities)


def test_float32_confidence_is_rounded():
    client = FakeClient(process_response(entity("origin", "Jaén", 0.8)))

    [extracted] = make_extractor(client).extract(DOCUMENT).entities

    assert extracted.confidence == 0.8


def test_normalized_value_is_used_when_mention_text_is_empty():
    client = FakeClient(process_response(entity("altitude_meters", "", 0.9, normalized="1650")))

    [extracted] = make_extractor(client).extract(DOCUMENT).entities

    assert extracted.text == "1650"


def test_empty_document_gives_no_entities():
    assert make_extractor(FakeClient()).extract(DOCUMENT).entities == ()


# Errores: nunca sale una excepción de Google


@pytest.mark.parametrize(
    "error",
    [
        google_exceptions.ServiceUnavailable("caído"),
        google_exceptions.DeadlineExceeded("timeout"),
        google_exceptions.InternalServerError("500"),
        google_exceptions.InvalidArgument("400"),
        google_exceptions.PermissionDenied("403"),
        google_exceptions.NotFound("404"),
        DefaultCredentialsError("sin credenciales"),
    ],
)
def test_google_errors_become_extraction_failed(error):
    with pytest.raises(ExtractionFailed):
        make_extractor(FakeClient(error=error)).extract(DOCUMENT)


def test_unreadable_credentials_become_extraction_failed(tmp_path):
    credentials = tmp_path / "credenciales.json"
    credentials.write_text("{}", encoding="utf-8")
    extractor = DocumentAiExtractor(
        load_settings(**VALID_ENV, google_application_credentials=str(credentials))
    )

    with pytest.raises(ExtractionFailed):
        extractor.extract(DOCUMENT)


# De punta a punta: respuesta simulada -> campos de la respuesta


def test_simulated_formato_x_response_maps_to_management_fields():
    client = FakeClient(
        process_response(
            entity("lot_name", "Blend Valle Sur VS-31", 1.0),
            entity("supplier_name", "Finca Familiar Ejemplo Sur", 1.0),
            entity("coffee_type", "MEZCLA", 1.0),
            entity("origin", "Quillabamba, Cusco, Perú", 1.0),
            entity("processing_method", "honey", 0.55),
            entity("altitude_meters", "1,450 msnm", 1.0),
            entity("initial_weight_kg", "46", 1.0),
        )
    )

    raw = make_extractor(client).extract(DOCUMENT)
    extraction = map_extraction(raw, confidence_threshold=0.7)

    assert extraction.fields[FieldName.COFFEE_TYPE].value == "Mezcla"
    assert extraction.fields[FieldName.PROCESSING_METHOD].value == "Honey"
    assert extraction.fields[FieldName.ALTITUDE_METERS].value == 1450
    assert extraction.fields[FieldName.INITIAL_WEIGHT].value == 46
    assert {(w.field, w.code.value) for w in extraction.warnings} == {
        (FieldName.PROCESSING_METHOD, "LOW_CONFIDENCE"),
        (FieldName.CERTIFICATIONS, "NOT_FOUND"),
    }
