import pytest

from app.infrastructure.config import ConfigurationError, load_settings
from tests.conftest import VALID_ENV


def test_defaults_are_applied():
    settings = load_settings(**VALID_ENV)

    assert settings.confidence_threshold == 0.7
    assert settings.max_file_mb == 10
    assert settings.max_file_bytes == 10 * 1024 * 1024
    assert settings.docai_timeout_seconds == 10
    assert settings.docai_processor_version is None
    assert settings.port == 8000


def test_reads_environment_variables(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "env-project")
    monkeypatch.setenv("DOCAI_LOCATION", " EU ")
    monkeypatch.setenv("DOCAI_PROCESSOR_ID", "env-processor")
    monkeypatch.setenv("DOCAI_PROCESSOR_VERSION", "")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host:6543/postgres")
    monkeypatch.setenv("CONFIDENCE_THRESHOLD", "0.8")

    settings = load_settings()

    assert settings.gcp_project_id == "env-project"
    assert settings.docai_location == "eu"
    assert settings.docai_processor_version is None
    assert settings.confidence_threshold == 0.8


def test_missing_required_variables_are_listed():
    with pytest.raises(ConfigurationError) as error:
        load_settings()

    message = str(error.value)
    for name in ("GCP_PROJECT_ID", "DOCAI_LOCATION", "DOCAI_PROCESSOR_ID", "DATABASE_URL"):
        assert name in message


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("docai_location", "asia"),
        ("confidence_threshold", 1.5),
        ("max_file_mb", 0),
        ("docai_timeout_seconds", 0),
        ("gcp_project_id", "   "),
        ("database_url", "mysql://u:p@host/db"),
        ("google_application_credentials", "no/existe/credenciales.json"),
    ],
)
def test_invalid_values_are_rejected(field, value):
    with pytest.raises(ConfigurationError) as error:
        load_settings(**{**VALID_ENV, field: value})

    assert field.upper() in str(error.value)


def test_error_message_never_contains_secret_values():
    secret_url = "mysql://user:SUPER_SECRET@host/db"

    with pytest.raises(ConfigurationError) as error:
        load_settings(**{**VALID_ENV, "database_url": secret_url})

    assert "SUPER_SECRET" not in str(error.value)
