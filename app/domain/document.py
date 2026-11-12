"""El documento subido y las reglas que debe cumplir antes de procesarse."""

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePath

from app.domain.errors import FileTooLarge, InvalidDocument, UnsupportedFileType


class DocumentFormat(StrEnum):
    PDF = "application/pdf"
    JPEG = "image/jpeg"
    PNG = "image/png"

    @property
    def mime_type(self) -> str:
        return self.value


_SIGNATURES: tuple[tuple[bytes, DocumentFormat], ...] = (
    (b"%PDF-", DocumentFormat.PDF),
    (b"\xff\xd8\xff", DocumentFormat.JPEG),
    (b"\x89PNG\r\n\x1a\n", DocumentFormat.PNG),
)

_DECLARED_FORMATS: dict[str, DocumentFormat] = {
    "application/pdf": DocumentFormat.PDF,
    "image/jpeg": DocumentFormat.JPEG,
    "image/jpg": DocumentFormat.JPEG,
    "image/png": DocumentFormat.PNG,
    ".pdf": DocumentFormat.PDF,
    ".jpg": DocumentFormat.JPEG,
    ".jpeg": DocumentFormat.JPEG,
    ".png": DocumentFormat.PNG,
}

MAX_PDF_PAGES = 1


@dataclass(frozen=True)
class UploadedFile:
    """Lo que llegó en la petición, sin validar."""

    content: bytes
    filename: str | None
    content_type: str | None


@dataclass(frozen=True)
class Document:
    """Un archivo que ya pasó las reglas de formato y tamaño."""

    content: bytes
    format: DocumentFormat


def detect_format(content: bytes) -> DocumentFormat | None:
    """Reconoce el formato por los primeros bytes; no confía en el nombre ni en el Content-Type."""
    for signature, document_format in _SIGNATURES:
        if content.startswith(signature):
            return document_format
    return None


def _declared_format(upload: UploadedFile) -> DocumentFormat | None:
    content_type = (upload.content_type or "").split(";")[0].strip().lower()
    extension = PurePath(upload.filename or "").suffix.lower()
    return _DECLARED_FORMATS.get(content_type) or _DECLARED_FORMATS.get(extension)


def accept_document(upload: UploadedFile, max_bytes: int) -> Document:
    """Aplica las reglas de tamaño y formato.

    - Más de `max_bytes`: FileTooLarge (413).
    - Vacío: InvalidDocument (422).
    - Contenido que no es PDF, JPG ni PNG:
        - si se declaró como uno de esos formatos, está corrupto: InvalidDocument (422);
        - si no, UnsupportedFileType (415).
    """
    if len(upload.content) > max_bytes:
        raise FileTooLarge(f"El archivo supera el máximo de {max_bytes // (1024 * 1024)} MB.")
    if not upload.content:
        raise InvalidDocument("El archivo está vacío.")

    detected = detect_format(upload.content)
    if detected is None:
        if _declared_format(upload) is not None:
            raise InvalidDocument("El archivo está corrupto o no se puede leer.")
        raise UnsupportedFileType("Formato no permitido. Usa JPG, PNG o PDF.")

    return Document(content=upload.content, format=detected)


def check_page_count(document: Document, page_count: int) -> None:
    if document.format is DocumentFormat.PDF and page_count > MAX_PDF_PAGES:
        raise InvalidDocument(
            f"El PDF tiene {page_count} páginas; solo se acepta un PDF de 1 página."
        )


def fingerprint(content: bytes, user_id: int) -> str:
    """SHA-256 de los bytes del archivo seguidos del userId en decimal (ASCII)."""
    return hashlib.sha256(content + str(user_id).encode("ascii")).hexdigest()
