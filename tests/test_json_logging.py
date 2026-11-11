"""Logs estructurados: userId, hash abreviado, tiempo y resultado; nunca el archivo."""

import io
import json
import logging

import pytest

from app.application.autofill_document import AutofillDocument
from app.application.ports import ExtractionTimeout
from app.application.retrying_extractor import RetryingDocumentExtractor
from app.domain.document import UploadedFile, fingerprint
from app.infrastructure.files.document_inspector import FileDocumentInspector
from app.infrastructure.json_logging import JsonFormatter
from tests import sample_files
from tests.fakes import FakeDocumentExtractor

PDF = sample_files.pdf()


@pytest.fixture
def json_logs():
    """Captura las líneas JSON tal como saldrían por stdout."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    def lines() -> list[dict]:
        return [json.loads(line) for line in stream.getvalue().splitlines()]

    lines.raw = stream.getvalue  # type: ignore[attr-defined]
    yield lines

    root.removeHandler(handler)
    root.setLevel(previous_level)


def use_case(extractor):
    return AutofillDocument(
        FileDocumentInspector(),
        RetryingDocumentExtractor(extractor),
        10 * 1024 * 1024,
        confidence_threshold=0.7,
    )


def upload(content=PDF):
    return UploadedFile(content=content, filename="guia.pdf", content_type="application/pdf")


def request_logs(lines):
    return [line for line in lines() if line["event"] == "autofill.request"]


def test_request_log_has_user_short_hash_duration_and_result(json_logs):
    use_case(FakeDocumentExtractor()).execute(42, upload())

    [log] = request_logs(json_logs)
    assert log["level"] == "INFO"
    assert log["userId"] == 42
    assert log["fileHash"] == fingerprint(PDF, 42)[:12]
    assert log["result"] == "extracted"
    assert isinstance(log["durationMs"], int)


def test_repeated_file_is_processed_again(json_logs):
    """Sin persistencia no hay caché: el mismo archivo vuelve a llamar a Document AI."""
    extractor = FakeDocumentExtractor()
    service = use_case(extractor)
    service.execute(42, upload())
    service.execute(42, upload())

    assert [log["result"] for log in request_logs(json_logs)] == ["extracted", "extracted"]
    assert len(extractor.calls) == 2


def test_docai_calls_are_logged_with_attempts(json_logs):
    class TimeoutOnce(FakeDocumentExtractor):
        def extract(self, document):
            if not self.calls:
                self.calls.append(document)
                raise ExtractionTimeout("DeadlineExceeded")
            return super().extract(document)

    use_case(TimeoutOnce()).execute(42, upload())

    calls = [line for line in json_logs() if line["event"] == "docai.call"]
    assert [(c["attempt"], c["ok"]) for c in calls] == [(1, False), (2, True)]
    assert calls[0]["errorType"] == "ExtractionTimeout"
    assert calls[0]["willRetry"] is True
    assert all(c["userId"] == 42 and c["fileHash"] for c in calls)


def test_rejected_file_is_logged_without_hash(json_logs):
    with pytest.raises(Exception):
        use_case(FakeDocumentExtractor()).execute(42, upload(b""))

    [log] = request_logs(json_logs)
    assert log["result"] == "rejected"
    assert log["reason"] == "InvalidDocument"
    assert "fileHash" not in log


def test_logs_never_include_file_content_full_hash_or_extracted_values(json_logs):
    use_case(FakeDocumentExtractor()).execute(42, upload())

    raw = json_logs.raw()
    assert "%PDF" not in raw
    assert fingerprint(PDF, 42) not in raw
    assert "Finca El Mirador" not in raw


def test_context_does_not_leak_between_requests(json_logs):
    service = use_case(FakeDocumentExtractor())
    service.execute(1, upload())
    logging.getLogger("otro").info("fuera de una petición")

    outside = [line for line in json_logs() if line["event"] == "fuera de una petición"][0]
    assert "userId" not in outside
    assert "fileHash" not in outside
