"""Prueba manual del procesador Custom Extractor de Document AI.

Envía un archivo local (PDF, JPG o PNG) al procesador y muestra cada campo
extraído con su confianza. No guarda nada.

Uso:
    python scripts/probar_procesador.py ruta/al/archivo.pdf

Variables de entorno:
    GCP_PROJECT_ID                  ID del proyecto de Google Cloud
    DOCAI_LOCATION                  us o eu
    DOCAI_PROCESSOR_ID              ID del procesador
    DOCAI_PROCESSOR_VERSION         ID de la versión (opcional; si falta, usa la predeterminada)
    GOOGLE_APPLICATION_CREDENTIALS  ruta al JSON de la cuenta de servicio
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from google.api_core.client_options import ClientOptions
from google.api_core.exceptions import GoogleAPICallError
from google.cloud import documentai

SCHEMA_FIELDS = (
    "lot_name",
    "supplier_name",
    "coffee_type",
    "origin",
    "processing_method",
    "altitude_meters",
    "initial_weight_kg",
    "certifications",
)

MIME_TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}

REQUIRED_ENV = ("GCP_PROJECT_ID", "DOCAI_LOCATION", "DOCAI_PROCESSOR_ID")
TIMEOUT_SECONDS = 30


def fail(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(1)


def read_config() -> dict[str, str | None]:
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        fail(f"faltan variables de entorno: {', '.join(missing)}")

    location = os.environ["DOCAI_LOCATION"].strip().lower()
    if location not in ("us", "eu"):
        fail("DOCAI_LOCATION debe ser 'us' o 'eu'")

    credentials = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if credentials and not Path(credentials).is_file():
        fail("GOOGLE_APPLICATION_CREDENTIALS apunta a un archivo que no existe")

    return {
        "project_id": os.environ["GCP_PROJECT_ID"].strip(),
        "location": location,
        "processor_id": os.environ["DOCAI_PROCESSOR_ID"].strip(),
        "processor_version": (os.environ.get("DOCAI_PROCESSOR_VERSION") or "").strip() or None,
    }


def processor_name(client: documentai.DocumentProcessorServiceClient, cfg: dict) -> str:
    if cfg["processor_version"]:
        return client.processor_version_path(
            cfg["project_id"], cfg["location"], cfg["processor_id"], cfg["processor_version"]
        )
    return client.processor_path(cfg["project_id"], cfg["location"], cfg["processor_id"])


def entity_rows(entities) -> list[tuple[str, float, str]]:
    """Aplana las entidades (y sus propiedades anidadas, si las hay)."""
    rows = []
    for entity in entities:
        text = entity.mention_text or entity.normalized_value.text or ""
        rows.append((entity.type_, entity.confidence, " ".join(text.split())))
        for prop in entity.properties:
            prop_text = prop.mention_text or prop.normalized_value.text or ""
            rows.append(
                (f"{entity.type_}.{prop.type_}", prop.confidence, " ".join(prop_text.split()))
            )
    return rows


def main() -> None:
    if len(sys.argv) != 2:
        fail("uso: python scripts/probar_procesador.py ruta/al/archivo")

    path = Path(sys.argv[1])
    if not path.is_file():
        fail(f"no existe el archivo: {path}")

    mime_type = MIME_TYPES.get(path.suffix.lower())
    if mime_type is None:
        fail("formato no permitido; usa .pdf, .jpg, .jpeg o .png")

    cfg = read_config()
    content = path.read_bytes()

    client = documentai.DocumentProcessorServiceClient(
        client_options=ClientOptions(api_endpoint=f"{cfg['location']}-documentai.googleapis.com")
    )
    name = processor_name(client, cfg)

    request = documentai.ProcessRequest(
        name=name,
        raw_document=documentai.RawDocument(content=content, mime_type=mime_type),
    )

    try:
        result = client.process_document(request=request, timeout=TIMEOUT_SECONDS)
    except GoogleAPICallError as error:
        fail(f"Document AI respondió {error.code} {type(error).__name__}: {error.message}")

    document = result.document
    rows = entity_rows(document.entities)

    print(f"Procesador: {name}")
    print(f"Archivo:    {path.name} ({mime_type}, {len(content) / 1024:.1f} KB)")
    print(f"Páginas:    {len(document.pages)}")
    print()
    print(f"{'CAMPO':<22}{'CONFIANZA':>9}  VALOR")
    for field, confidence, value in rows:
        print(f"{field:<22}{confidence:>9.2f}  {value}")

    found = {field.split(".")[0] for field, _, _ in rows}
    missing = [field for field in SCHEMA_FIELDS if field not in found]
    unexpected = sorted(found - set(SCHEMA_FIELDS))

    print()
    print(f"Campos del esquema no encontrados: {', '.join(missing) or '(ninguno)'}")
    if unexpected:
        print(f"Campos fuera del esquema esperado: {', '.join(unexpected)}")


if __name__ == "__main__":
    main()
