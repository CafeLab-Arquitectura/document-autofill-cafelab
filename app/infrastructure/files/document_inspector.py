"""Comprueba que el archivo se pueda leer y cuenta sus páginas (pypdf para PDF, Pillow para imágenes)."""

from io import BytesIO

from PIL import Image
from pypdf import PdfReader

from app.domain.document import Document, DocumentFormat
from app.domain.errors import InvalidDocument

_CORRUPT_MESSAGE = "El archivo está corrupto o no se puede leer."


class FileDocumentInspector:
    def count_pages(self, document: Document) -> int:
        if document.format is DocumentFormat.PDF:
            return self._count_pdf_pages(document.content)
        self._verify_image(document.content)
        return 1

    @staticmethod
    def _count_pdf_pages(content: bytes) -> int:
        try:
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted:
                raise InvalidDocument("El PDF está protegido con contraseña.")
            pages = len(reader.pages)
        except InvalidDocument:
            raise
        except Exception as error:  # pypdf lanza varios tipos ante archivos dañados
            raise InvalidDocument(_CORRUPT_MESSAGE) from error

        if pages == 0:
            raise InvalidDocument("El PDF no tiene páginas.")
        return pages

    @staticmethod
    def _verify_image(content: bytes) -> None:
        try:
            with Image.open(BytesIO(content)) as image:
                image.verify()
        except Exception as error:  # Pillow lanza varios tipos ante imágenes dañadas
            raise InvalidDocument(_CORRUPT_MESSAGE) from error
