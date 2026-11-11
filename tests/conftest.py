import pytest
from fastapi.testclient import TestClient

from app.application import retrying_extractor

from app.infrastructure.config import Settings, load_settings
from app.main import create_app
from tests.fakes import FakeDocumentExtractor

VALID_ENV = {
    "gcp_project_id": "test-project",
    "docai_location": "us",
    "docai_processor_id": "test-processor",
}


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Evita que los tests lean el .env local o variables reales de la máquina."""
    monkeypatch.chdir(__import__("pathlib").Path(__file__).parent)
    for name in (
        "GCP_PROJECT_ID", "DOCAI_LOCATION", "DOCAI_PROCESSOR_ID", "DOCAI_PROCESSOR_VERSION",
        "GOOGLE_APPLICATION_CREDENTIALS", "CONFIDENCE_THRESHOLD",
        "MAX_FILE_MB", "DOCAI_TIMEOUT_SECONDS", "PORT",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def retry_sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Los tests no esperan la pausa del reintento; solo registran cuánto se habría esperado."""
    sleeps: list[float] = []
    monkeypatch.setattr(retrying_extractor, "_sleep", sleeps.append)
    return sleeps


@pytest.fixture
def settings() -> Settings:
    return load_settings(**VALID_ENV)


@pytest.fixture
def fake_extractor() -> FakeDocumentExtractor:
    return FakeDocumentExtractor()


@pytest.fixture
def client(settings: Settings, fake_extractor: FakeDocumentExtractor) -> TestClient:
    return TestClient(create_app(settings, extractor=fake_extractor))
