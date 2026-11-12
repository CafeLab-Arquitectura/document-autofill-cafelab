"""Errores del dominio. La capa HTTP decide qué código devolver para cada uno."""


class DocumentRejected(Exception):
    """El archivo recibido no cumple las reglas del servicio."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UnsupportedFileType(DocumentRejected):
    """El formato no es JPG, PNG ni PDF."""


class FileTooLarge(DocumentRejected):
    """El archivo supera el tamaño máximo."""


class InvalidDocument(DocumentRejected):
    """El archivo está vacío, corrupto o el PDF tiene más de una página."""
