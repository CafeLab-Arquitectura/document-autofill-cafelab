import pytest
from fastapi.testclient import TestClient

from app.infrastructure.config import load_settings
from app.main import create_app
from tests import sample_files
from tests.conftest import VALID_ENV

URL = "/api/v1/documents/autofill"
AUTH = {"X-User-Id": "42"}


def post(client, files=None, headers=AUTH):
    return client.post(URL, files=files, headers=headers)


def pdf_upload(content=None, name="guia.pdf", content_type="application/pdf"):
    return {"file": (name, sample_files.pdf() if content is None else content, content_type)}


# 200


@pytest.mark.parametrize(
    ("name", "content", "content_type"),
    [
        ("guia.pdf", sample_files.pdf(), "application/pdf"),
        ("foto.png", sample_files.image("PNG"), "image/png"),
        ("foto.jpg", sample_files.image("JPEG"), "image/jpeg"),
    ],
)
def test_accepts_pdf_png_and_jpg(client, name, content, content_type):
    response = post(client, {"file": (name, content, content_type)})

    assert response.status_code == 200


def test_returns_response_contract(client):
    body = post(client, pdf_upload()).json()

    assert set(body) == {"extractionId", "cached", "fields", "warnings"}
    assert body["cached"] is False
    assert set(body["fields"]) == {
        "lotName", "supplierName", "coffeeType", "origin",
        "processingMethod", "altitudeMeters", "initialWeight", "certifications",
    }
    assert body["fields"]["lotName"] == {"value": "Finca El Mirador L-14", "confidence": 0.93}
    assert body["fields"]["certifications"] == {"value": ["ORGANIC"], "confidence": 0.8}
    assert isinstance(body["warnings"], list)


def test_format_comes_from_content_not_from_name(client):
    """Un PDF real con nombre .png se procesa como PDF."""
    response = post(client, {"file": ("foto.png", sample_files.pdf(), "image/png")})

    assert response.status_code == 200


# 401


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-User-Id": ""},
        {"X-User-Id": "abc"},
        {"X-User-Id": "1.5"},
        {"X-User-Id": "-5"},
        {"X-User-Id": "0"},
        {"X-User-Id": "99999999999999999999"},
    ],
)
def test_rejects_missing_or_invalid_user_id(client, headers):
    response = post(client, pdf_upload(), headers=headers)

    assert response.status_code == 401
    assert "X-User-Id" in response.json()["message"]


def test_identity_is_checked_before_the_file(client):
    response = post(client, files=None, headers={})

    assert response.status_code == 401


# 413


def test_rejects_file_over_the_limit():
    client = TestClient(create_app(load_settings(**VALID_ENV, max_file_mb=1)))
    too_big = b"%PDF-" + b"0" * (1024 * 1024)

    response = post(client, pdf_upload(too_big))

    assert response.status_code == 413
    assert response.json() == {"message": "El archivo supera el máximo de 1 MB."}


# 415


@pytest.mark.parametrize(
    ("name", "content", "content_type"),
    [
        ("notas.txt", b"hola", "text/plain"),
        ("guia.docx", b"PK\x03\x04contenido", "application/octet-stream"),
        ("foto.gif", b"GIF89a....", "image/gif"),
    ],
)
def test_rejects_unsupported_format(client, name, content, content_type):
    response = post(client, {"file": (name, content, content_type)})

    assert response.status_code == 415
    assert response.json() == {"message": "Formato no permitido. Usa JPG, PNG o PDF."}


# 422


def test_rejects_pdf_with_more_than_one_page(client):
    response = post(client, pdf_upload(sample_files.pdf(pages=2)))

    assert response.status_code == 422
    assert "2 páginas" in response.json()["message"]


def test_rejects_empty_file(client):
    response = post(client, pdf_upload(b""))

    assert response.status_code == 422
    assert response.json() == {"message": "El archivo está vacío."}


@pytest.mark.parametrize(
    ("name", "content", "content_type"),
    [
        ("guia.pdf", b"%PDF-1.7 esto no es un pdf", "application/pdf"),
        ("foto.png", b"\x89PNG\r\n\x1a\n datos rotos", "image/png"),
        ("foto.jpg", b"no es una imagen", "image/jpeg"),
    ],
)
def test_rejects_corrupt_file(client, name, content, content_type):
    response = post(client, {"file": (name, content, content_type)})

    assert response.status_code == 422
    assert response.json() == {"message": "El archivo está corrupto o no se puede leer."}


def test_rejects_request_without_file(client):
    response = client.post(URL, headers=AUTH, data={"otro": "campo"})

    assert response.status_code == 422
    assert response.json() == {"message": "Falta el archivo en el campo 'file'."}


def test_rejects_more_than_one_file(client):
    files = [
        ("file", ("a.pdf", sample_files.pdf(), "application/pdf")),
        ("file", ("b.pdf", sample_files.pdf(), "application/pdf")),
    ]

    response = post(client, files)

    assert response.status_code == 422
    assert response.json() == {"message": "Envía un solo archivo por petición."}
