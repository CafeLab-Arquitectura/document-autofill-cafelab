"""DESACTIVADO: la persistencia no se usa (ver app/infrastructure/persistence/__init__.py).

Prueba el repositorio contra un PostgreSQL de PRUEBA.

Se salta si no está definida TEST_DATABASE_URL. Úsala SOLO con una base local o
desechable (por ejemplo, un contenedor de Docker), nunca con la de producción:
el test crea el esquema con la migración y borra las filas que inserta.

    TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres pytest tests/integration
"""

import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg", reason="persistencia desactivada: psycopg no está instalado")

from app.infrastructure.persistence.contracts import NewExtraction
from app.domain.extraction import Extraction, FieldName, FieldSuggestion
from app.infrastructure.persistence.postgres_repository import PostgresExtractionRepository

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
MIGRATION = Path(__file__).parents[2] / "db" / "migrations" / "001_create_document_extractions.sql"

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL no definida")


def new_extraction(user_id: int, file_hash: str, lot_name: str = "L-1") -> NewExtraction:
    extraction = Extraction(fields={FieldName.LOT_NAME: FieldSuggestion(lot_name, 0.9)})
    return NewExtraction(user_id, file_hash, extraction, "v1")


@pytest.fixture
def repository():
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as connection:
        connection.execute(MIGRATION.read_text(encoding="utf-8"))

    repo = PostgresExtractionRepository(TEST_DATABASE_URL)
    repo.open()
    yield repo
    repo.close()


@pytest.fixture
def user_id(repository):
    user = secrets.randbelow(10**12) + 10**12  # usuario aleatorio, no choca con otros datos
    yield user
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as connection:
        connection.execute(
            "DELETE FROM document_autofill.document_extractions WHERE user_id = %s", (user,)
        )


def test_find_returns_none_when_nothing_is_saved(repository, user_id):
    assert repository.find(user_id, "a" * 64) is None


def test_save_then_find_returns_the_same_record(repository, user_id):
    saved = repository.save(new_extraction(user_id, "b" * 64))

    found = repository.find(user_id, "b" * 64)

    assert found == saved


def test_duplicate_save_returns_the_first_record(repository, user_id):
    first = repository.save(new_extraction(user_id, "c" * 64, lot_name="primero"))
    second = repository.save(new_extraction(user_id, "c" * 64, lot_name="segundo"))

    assert second == first
    assert second.extraction.fields[FieldName.LOT_NAME].value == "primero"


def test_concurrent_saves_create_a_single_record(repository, user_id):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(lambda i: repository.save(new_extraction(user_id, "d" * 64, f"r{i}")), range(4))
        )

    assert len({result.id for result in results}) == 1
