"""Idempotencia: mismo archivo + mismo usuario = mismo resultado, sin volver a llamar a Document AI."""

import pytest
from fastapi.testclient import TestClient

from app.application.autofill_document import AutofillDocument
from app.application.ports import NewExtraction, RepositoryUnavailable
from app.domain.document import UploadedFile, fingerprint
from app.domain.extraction import Extraction, FieldName, FieldSuggestion
from app.infrastructure.files.document_inspector import FileDocumentInspector
from app.main import create_app
from tests import sample_files
from tests.fakes import (
    FailingExtractor,
    FakeDocumentExtractor,
    InMemoryExtractionRepository,
    RacingRepository,
    UnavailableRepository,
)

URL = "/api/v1/documents/autofill"
PDF = sample_files.pdf()


def make_use_case(extractor, repository):
    return AutofillDocument(
        FileDocumentInspector(), extractor, repository, 10 * 1024 * 1024, confidence_threshold=0.7
    )


def upload(content=PDF):
    return UploadedFile(content=content, filename="guia.pdf", content_type="application/pdf")


# Caso de uso


def test_first_request_calls_document_ai_and_saves_the_result():
    extractor, repository = FakeDocumentExtractor(), InMemoryExtractionRepository()

    result = make_use_case(extractor, repository).execute(42, upload())

    assert result.cached is False
    assert result.extraction_id == 1
    assert len(extractor.calls) == 1
    assert list(repository.rows) == [(42, fingerprint(PDF, 42))]


def test_repeated_file_returns_saved_result_without_calling_document_ai():
    extractor, repository = FakeDocumentExtractor(), InMemoryExtractionRepository()
    use_case = make_use_case(extractor, repository)

    first = use_case.execute(42, upload())
    second = use_case.execute(42, upload())

    assert second.cached is True
    assert second.extraction_id == first.extraction_id
    assert second.extraction == first.extraction
    assert len(extractor.calls) == 1


def test_same_file_from_another_user_is_processed_again():
    extractor, repository = FakeDocumentExtractor(), InMemoryExtractionRepository()
    use_case = make_use_case(extractor, repository)

    first = use_case.execute(1, upload())
    second = use_case.execute(2, upload())

    assert second.cached is False
    assert second.extraction_id != first.extraction_id
    assert len(extractor.calls) == 2


def test_different_file_from_same_user_is_processed_again():
    extractor, repository = FakeDocumentExtractor(), InMemoryExtractionRepository()
    use_case = make_use_case(extractor, repository)

    use_case.execute(1, upload(sample_files.pdf()))
    result = use_case.execute(1, upload(sample_files.image("PNG")))

    assert result.cached is False
    assert len(extractor.calls) == 2


def test_concurrent_duplicate_returns_the_record_saved_first():
    """Dos peticiones iguales a la vez: la segunda choca con el UNIQUE y recibe la primera."""
    winner_extraction = Extraction(
        fields={FieldName.LOT_NAME: FieldSuggestion("Guardado primero", 0.99)}
    )
    winner = NewExtraction(42, fingerprint(PDF, 42), winner_extraction, "v1")
    repository = RacingRepository(winner)

    result = make_use_case(FakeDocumentExtractor(), repository).execute(42, upload())

    assert result.extraction_id == 1
    assert result.extraction == winner_extraction
    assert len(repository.rows) == 1


def test_failed_extraction_is_not_saved():
    repository = InMemoryExtractionRepository()

    with pytest.raises(Exception):
        make_use_case(FailingExtractor(), repository).execute(42, upload())

    assert repository.rows == {}


def test_rejected_file_is_not_saved():
    repository = InMemoryExtractionRepository()

    with pytest.raises(Exception):
        make_use_case(FakeDocumentExtractor(), repository).execute(42, upload(b""))

    assert repository.rows == {}


def test_database_down_does_not_call_document_ai():
    extractor = FakeDocumentExtractor()

    with pytest.raises(RepositoryUnavailable):
        make_use_case(extractor, UnavailableRepository()).execute(42, upload())

    assert extractor.calls == []


def test_saved_result_keeps_the_warnings_it_was_created_with():
    """Si después cambia CONFIDENCE_THRESHOLD, lo guardado no se recalcula."""
    extractor, repository = FakeDocumentExtractor(), InMemoryExtractionRepository()
    first = make_use_case(extractor, repository).execute(42, upload())

    stricter = AutofillDocument(
        FileDocumentInspector(), extractor, repository, 10 * 1024 * 1024, confidence_threshold=0.99
    )
    second = stricter.execute(42, upload())

    assert second.cached is True
    assert second.extraction.warnings == first.extraction.warnings


# Endpoint


def post(client, user_id="42"):
    return client.post(
        URL, headers={"X-User-Id": user_id}, files={"file": ("guia.pdf", PDF, "application/pdf")}
    )


def test_endpoint_returns_cached_true_on_second_request(client, fake_extractor):
    first = post(client).json()
    second = post(client).json()

    assert first["cached"] is False
    assert second["cached"] is True
    assert second["extractionId"] == first["extractionId"]
    assert second["fields"] == first["fields"]
    assert second["warnings"] == first["warnings"]
    assert len(fake_extractor.calls) == 1


def test_endpoint_returns_503_when_database_is_down(settings):
    client = TestClient(
        create_app(settings, extractor=FakeDocumentExtractor(), repository=UnavailableRepository())
    )

    response = post(client)

    assert response.status_code == 503
    assert response.json() == {
        "message": "El servicio de autocompletado no está disponible. "
        "Completa el formulario manualmente."
    }
