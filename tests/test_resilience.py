"""Timeout, un solo reintento ante errores transitorios y respuesta para completar a mano."""

import pytest
from fastapi.testclient import TestClient
from google.api_core import exceptions as google_exceptions
from google.auth.exceptions import DefaultCredentialsError, TransportError
from google.cloud import documentai

from app.application.ports import (
    ExtractionFailed,
    ExtractionTimeout,
    TransientExtractionError,
)
from app.application.retrying_extractor import RetryingDocumentExtractor
from app.domain.document import Document, DocumentFormat
from app.domain.extraction import RawExtraction
from app.infrastructure.config import load_settings
from app.infrastructure.document_ai.documentai_extractor import DocumentAiExtractor, classify_error
from app.main import create_app
from tests import sample_files
from tests.conftest import VALID_ENV

URL = "/api/v1/documents/autofill"
DOCUMENT = Document(content=b"%PDF-1.7", format=DocumentFormat.PDF)
OK = RawExtraction(entities=(), processor_version="v1")

MESSAGE_502 = "No se pudo leer el documento automáticamente. Completa el formulario manualmente."
MESSAGE_504 = (
    "La lectura automática del documento tardó demasiado. Completa el formulario manualmente."
)


class ScriptedExtractor:
    """Lanza los errores de la lista en orden; cuando se acaban, responde bien."""

    def __init__(self, *errors: Exception) -> None:
        self.errors = list(errors)
        self.calls = 0

    def extract(self, document: Document) -> RawExtraction:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return OK


# Política de reintento (capa de aplicación)


@pytest.mark.parametrize(
    "error", [TransientExtractionError("ServiceUnavailable"), ExtractionTimeout("DeadlineExceeded")]
)
def test_transient_error_recovers_on_the_single_retry(error):
    inner = ScriptedExtractor(error)

    result = RetryingDocumentExtractor(inner).extract(DOCUMENT)

    assert result == OK
    assert inner.calls == 2


@pytest.mark.parametrize(
    "errors",
    [
        (TransientExtractionError("ServiceUnavailable"), TransientExtractionError("InternalServerError")),
        (ExtractionTimeout("DeadlineExceeded"), ExtractionTimeout("DeadlineExceeded")),
    ],
)
def test_transient_error_twice_gives_up_after_one_retry(errors):
    inner = ScriptedExtractor(*errors)

    with pytest.raises(type(errors[1])):
        RetryingDocumentExtractor(inner).extract(DOCUMENT)

    assert inner.calls == 2


def test_waits_one_second_before_the_retry(retry_sleeps):
    RetryingDocumentExtractor(ScriptedExtractor(ExtractionTimeout("DeadlineExceeded"))).extract(
        DOCUMENT
    )

    assert retry_sleeps == [1.0]


def test_no_wait_after_the_last_attempt(retry_sleeps):
    inner = ScriptedExtractor(
        TransientExtractionError("ServiceUnavailable"), TransientExtractionError("ServiceUnavailable")
    )

    with pytest.raises(TransientExtractionError):
        RetryingDocumentExtractor(inner).extract(DOCUMENT)

    assert retry_sleeps == [1.0]


def test_no_wait_when_the_first_attempt_succeeds(retry_sleeps):
    RetryingDocumentExtractor(ScriptedExtractor()).extract(DOCUMENT)

    assert retry_sleeps == []


def test_permanent_error_is_not_retried(retry_sleeps):
    inner = ScriptedExtractor(ExtractionFailed("InvalidArgument"))

    with pytest.raises(ExtractionFailed):
        RetryingDocumentExtractor(inner).extract(DOCUMENT)

    assert inner.calls == 1
    assert retry_sleeps == []


# Clasificación de errores de Google (adaptador)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (google_exceptions.DeadlineExceeded("timeout"), ExtractionTimeout),
        (google_exceptions.GatewayTimeout("504"), ExtractionTimeout),
        (google_exceptions.ServiceUnavailable("UNAVAILABLE"), TransientExtractionError),
        (google_exceptions.InternalServerError("500"), TransientExtractionError),
        (google_exceptions.BadGateway("502"), TransientExtractionError),
        (TransportError("sin red"), TransientExtractionError),
        (google_exceptions.InvalidArgument("400"), ExtractionFailed),
        (google_exceptions.PermissionDenied("403"), ExtractionFailed),
        (google_exceptions.NotFound("404"), ExtractionFailed),
        (google_exceptions.ResourceExhausted("429"), ExtractionFailed),
        (DefaultCredentialsError("sin credenciales"), ExtractionFailed),
    ],
)
def test_google_errors_are_classified(error, expected):
    classified = classify_error(error)

    assert type(classified) is expected
    assert str(classified) == type(error).__name__  # nunca el mensaje de Google


class FlakyClient:
    """Cliente de Document AI simulado: falla con los errores dados y luego responde."""

    def __init__(self, *errors: Exception) -> None:
        self.errors = list(errors)
        self.calls: list[dict] = []

    def process_document(self, request, timeout=None, retry=None):
        self.calls.append({"timeout": timeout, "retry": retry})
        if self.errors:
            raise self.errors.pop(0)
        return documentai.ProcessResponse(document=documentai.Document())


def adapter(client) -> DocumentAiExtractor:
    return DocumentAiExtractor(load_settings(**VALID_ENV, docai_timeout_seconds=10), client=client)


def test_each_attempt_has_its_own_timeout_and_no_library_retries():
    client = FlakyClient(google_exceptions.DeadlineExceeded("timeout"))

    RetryingDocumentExtractor(adapter(client)).extract(DOCUMENT)

    assert client.calls == [{"timeout": 10, "retry": None}, {"timeout": 10, "retry": None}]


def test_4xx_from_google_is_not_retried():
    client = FlakyClient(google_exceptions.InvalidArgument("400"))

    with pytest.raises(ExtractionFailed):
        RetryingDocumentExtractor(adapter(client)).extract(DOCUMENT)

    assert len(client.calls) == 1


# Endpoint: 200 tras recuperarse, 502 / 504 si falla


def make_client(extractor) -> TestClient:
    return TestClient(create_app(load_settings(**VALID_ENV), extractor=extractor))


def post(client):
    return client.post(
        URL,
        headers={"X-User-Id": "42"},
        files={"file": ("guia.pdf", sample_files.pdf(), "application/pdf")},
    )


def test_endpoint_returns_200_when_the_retry_succeeds():
    extractor = ScriptedExtractor(TransientExtractionError("ServiceUnavailable"))

    response = post(make_client(extractor))

    assert response.status_code == 200
    assert extractor.calls == 2


@pytest.mark.parametrize(
    ("errors", "status", "message"),
    [
        (
            (TransientExtractionError("ServiceUnavailable"), TransientExtractionError("ServiceUnavailable")),
            502,
            MESSAGE_502,
        ),
        ((ExtractionTimeout("DeadlineExceeded"), ExtractionTimeout("DeadlineExceeded")), 504, MESSAGE_504),
        # El último error decide: si el reintento no fue timeout, es 502.
        ((ExtractionTimeout("DeadlineExceeded"), TransientExtractionError("ServiceUnavailable")), 502, MESSAGE_502),
        ((ExtractionFailed("PermissionDenied"),), 502, MESSAGE_502),
    ],
)
def test_endpoint_failure_asks_to_fill_the_form_manually(errors, status, message):
    response = post(make_client(ScriptedExtractor(*errors)))

    assert response.status_code == status
    assert response.json() == {"message": message}


def test_next_request_after_a_failure_calls_document_ai_again():
    extractor = ScriptedExtractor(
        TransientExtractionError("ServiceUnavailable"), TransientExtractionError("ServiceUnavailable")
    )
    client = make_client(extractor)

    assert post(client).status_code == 502
    second = post(client)

    assert second.status_code == 200
    assert extractor.calls == 3
