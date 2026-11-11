"""Configuración del servicio, leída de variables de entorno y validada al arrancar."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(RuntimeError):
    """La configuración es inválida. El mensaje nunca incluye los valores recibidos."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Document AI
    gcp_project_id: str = Field(min_length=1)
    docai_location: Literal["us", "eu"]
    docai_processor_id: str = Field(min_length=1)
    docai_processor_version: str | None = None
    docai_timeout_seconds: float = Field(default=10, gt=0)
    google_application_credentials: Path | None = None

    # Reglas del servicio
    confidence_threshold: float = Field(default=0.7, ge=0, le=1)
    max_file_mb: int = Field(default=10, gt=0)

    # Servidor
    port: int = Field(default=8000, ge=1, le=65535)

    @field_validator("gcp_project_id", "docai_processor_id")
    @classmethod
    def strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("no puede estar vacío")
        return value

    @field_validator("docai_location", mode="before")
    @classmethod
    def normalize_location(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("docai_processor_version", "google_application_credentials", mode="before")
    @classmethod
    def empty_as_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("google_application_credentials")
    @classmethod
    def credentials_file_exists(cls, value: Path | None) -> Path | None:
        if value is not None and not value.is_file():
            raise ValueError("el archivo de credenciales no existe")
        return value

    @property
    def max_file_bytes(self) -> int:
        return self.max_file_mb * 1024 * 1024


def load_settings(**overrides: object) -> Settings:
    """Crea la configuración o lanza ConfigurationError con los campos inválidos."""
    try:
        return Settings(**overrides)
    except ValidationError as error:
        problems = [
            f"{'.'.join(str(part) for part in issue['loc']).upper()}: {issue['msg']}"
            for issue in error.errors(include_input=False, include_url=False)
        ]
        raise ConfigurationError(
            "Configuración inválida:\n  - " + "\n  - ".join(problems)
        ) from None


@lru_cache
def get_settings() -> Settings:
    return load_settings()
