import hashlib

import pytest

from app.application.autofill_document import AutofillDocument
from app.domain.document import DocumentFormat, UploadedFile, accept_document, fingerprint
from app.domain.errors import FileTooLarge, InvalidDocument, UnsupportedFileType
from app.infrastructure.files.document_inspector import FileDocumentInspector
from tests import sample_files
from tests.fakes import FakeDocumentExtractor as SpyExtractor


def use_case(extractor, max_bytes=10 * 1024 * 1024):
    return AutofillDocument(FileDocumentInspector(), extractor, max_bytes, confidence_threshold=0.7)


def upload(content, name="guia.pdf", content_type="application/pdf"):
    return UploadedFile(content=content, filename=name, content_type=content_type)


def test_hash_is_sha256_of_file_bytes_plus_user_id():
    assert fingerprint(b"contenido", 42) == hashlib.sha256(b"contenido42").hexdigest()
    assert len(fingerprint(b"contenido", 42)) == 64


def test_same_file_gives_different_hash_per_user():
    content = sample_files.pdf()

    assert fingerprint(content, 1) == fingerprint(content, 1)
    assert fingerprint(content, 1) != fingerprint(content, 2)


def test_result_carries_the_file_hash():
    content = sample_files.pdf()

    result = use_case(SpyExtractor()).execute(7, upload(content))

    assert result.file_hash == fingerprint(content, 7)


def test_file_exactly_at_the_limit_is_accepted():
    content = b"%PDF-" + b"0" * 1019

    assert accept_document(upload(content), max_bytes=1024).format is DocumentFormat.PDF


@pytest.mark.parametrize(
    ("content", "error", "max_bytes"),
    [
        (b"", InvalidDocument, 1024),
        (b"hola", UnsupportedFileType, 1024),
        (b"%PDF-" + b"0" * 1020, FileTooLarge, 1024),
        (sample_files.pdf(pages=3), InvalidDocument, 10 * 1024 * 1024),
    ],
)
def test_extractor_is_not_called_when_the_file_is_rejected(content, error, max_bytes):
    extractor = SpyExtractor()

    with pytest.raises(error):
        use_case(extractor, max_bytes).execute(1, upload(content, name="x.bin", content_type=None))

    assert extractor.calls == []


def test_extractor_receives_the_detected_format():
    extractor = SpyExtractor()

    use_case(extractor).execute(1, upload(sample_files.image("JPEG"), "foto.jpg", "image/jpeg"))

    assert extractor.calls[0].format is DocumentFormat.JPEG
