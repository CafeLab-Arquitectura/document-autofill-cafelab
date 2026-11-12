"""Archivos de prueba generados en memoria (no se versionan binarios)."""

from io import BytesIO

from PIL import Image
from pypdf import PdfWriter


def pdf(pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def image(fmt: str = "PNG") -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (40, 20), "white").save(buffer, format=fmt)
    return buffer.getvalue()
