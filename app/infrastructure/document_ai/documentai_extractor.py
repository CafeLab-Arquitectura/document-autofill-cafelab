"""Adaptador de Google Cloud Document AI (Custom Extractor).

Es la capa anticorrupción: ningún tipo ni excepción de la librería de Google sale
de este módulo. Devuelve RawExtraction y, si algo falla, lanza ExtractionFailed.

El timeout ya se aplica aquí. El reintento y la diferencia entre 502 y 504 llegan en la Fase 5.
"""

import threading

from google.api_core.client_options import ClientOptions
from google.api_core.exceptions import GoogleAPIError
from google.auth.exceptions import GoogleAuthError
from google.cloud import documentai
from google.oauth2 import service_account

from app.application.ports import ExtractionFailed
from app.domain.document import Document
from app.domain.extraction import ExtractedEntity, RawExtraction
from app.infrastructure.config import Settings

CONFIDENCE_DECIMALS = 2


def processor_resource_name(settings: Settings) -> str:
    name = (
        f"projects/{settings.gcp_project_id}/locations/{settings.docai_location}"
        f"/processors/{settings.docai_processor_id}"
    )
    if settings.docai_processor_version:
        name += f"/processorVersions/{settings.docai_processor_version}"
    return name


def to_extraction(document: documentai.Document, processor_version: str | None) -> RawExtraction:
    """Traduce el Document de Google a objetos del servicio."""
    entities = tuple(
        ExtractedEntity(
            name=entity.type_,
            text=entity.mention_text or entity.normalized_value.text or "",
            # Document AI usa float32 (0.800000011...); se redondea para la respuesta.
            confidence=round(entity.confidence, CONFIDENCE_DECIMALS),
        )
        for entity in document.entities
    )
    return RawExtraction(entities=entities, processor_version=processor_version)


class DocumentAiExtractor:
    def __init__(
        self,
        settings: Settings,
        client: documentai.DocumentProcessorServiceClient | None = None,
    ) -> None:
        self._settings = settings
        self._name = processor_resource_name(settings)
        self._client = client
        self._client_lock = threading.Lock()

    def extract(self, document: Document) -> RawExtraction:
        request = documentai.ProcessRequest(
            name=self._name,
            raw_document=documentai.RawDocument(
                content=document.content, mime_type=document.format.mime_type
            ),
        )
        client = self._get_client()
        try:
            response = client.process_document(
                request=request,
                timeout=self._settings.docai_timeout_seconds,
                # La librería reintenta por su cuenta hasta 300 s. Se desactiva:
                # el servicio decide sus propios reintentos.
                retry=None,
            )
        except (GoogleAPIError, GoogleAuthError) as error:
            raise ExtractionFailed(type(error).__name__) from error

        return to_extraction(response.document, self._settings.docai_processor_version)

    def _get_client(self) -> documentai.DocumentProcessorServiceClient:
        # El cliente se crea en la primera petición, así el servicio arranca
        # aunque las credenciales aún no estén disponibles.
        with self._client_lock:
            if self._client is None:
                try:
                    self._client = self._create_client()
                except (GoogleAuthError, OSError, ValueError) as error:
                    # Credenciales ilegibles o inválidas.
                    raise ExtractionFailed(type(error).__name__) from error
            return self._client

    def _create_client(self) -> documentai.DocumentProcessorServiceClient:
        credentials_file = self._settings.google_application_credentials
        credentials = (
            service_account.Credentials.from_service_account_file(str(credentials_file))
            if credentials_file
            else None  # Credenciales por defecto del entorno (ADC)
        )
        return documentai.DocumentProcessorServiceClient(
            credentials=credentials,
            client_options=ClientOptions(
                api_endpoint=f"{self._settings.docai_location}-documentai.googleapis.com"
            ),
        )
