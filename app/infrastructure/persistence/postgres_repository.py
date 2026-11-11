"""Repositorio PostgreSQL (Supabase) de document_autofill.document_extractions.

Supabase en modo transacción (pooler, puerto 6543) no soporta prepared statements.
psycopg 3 los crea solo después de repetir una consulta varias veces (prepare_threshold).
Con prepare_threshold=None no los crea nunca.
"""

from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool, PoolTimeout

from app.application.ports import NewExtraction, RepositoryUnavailable, StoredExtraction
from app.infrastructure.persistence.extraction_json import (
    extraction_from_json,
    extraction_to_json,
)

TABLE = "document_autofill.document_extractions"

_FIND = f"SELECT id, result FROM {TABLE} WHERE user_id = %s AND file_hash = %s"

_INSERT = f"""
    INSERT INTO {TABLE} (user_id, file_hash, result, processor_version)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (user_id, file_hash) DO NOTHING
    RETURNING id, result
"""

POOL_MIN_SIZE = 1
POOL_MAX_SIZE = 5
POOL_TIMEOUT_SECONDS = 5
CONNECT_TIMEOUT_SECONDS = 5


class PostgresExtractionRepository:
    def __init__(self, database_url: str) -> None:
        self._pool = ConnectionPool(
            conninfo=database_url,
            min_size=POOL_MIN_SIZE,
            max_size=POOL_MAX_SIZE,
            timeout=POOL_TIMEOUT_SECONDS,
            kwargs={
                "autocommit": True,
                "prepare_threshold": None,  # Sin prepared statements (pooler de Supabase)
                "connect_timeout": CONNECT_TIMEOUT_SECONDS,
                "row_factory": dict_row,
            },
            # Supabase cierra conexiones inactivas: se revisan antes de usarlas.
            check=ConnectionPool.check_connection,
            open=False,
        )

    def open(self) -> None:
        # wait=False: el servicio arranca aunque la base todavía no responda.
        self._pool.open(wait=False)

    def close(self) -> None:
        self._pool.close()

    def find(self, user_id: int, file_hash: str) -> StoredExtraction | None:
        row = self._fetch_one(_FIND, (user_id, file_hash))
        return _to_stored(row) if row else None

    def save(self, new: NewExtraction) -> StoredExtraction:
        row = self._fetch_one(
            _INSERT,
            (new.user_id, new.file_hash, Jsonb(extraction_to_json(new.extraction)),
             new.processor_version),
        )
        if row:
            return _to_stored(row)

        # Conflicto del UNIQUE: otra petición igual se guardó primero. Se devuelve esa.
        existing = self.find(new.user_id, new.file_hash)
        if existing is None:  # No debería pasar: el registro no se borra.
            raise RepositoryUnavailable("Conflicto sin registro existente")
        return existing

    def _fetch_one(self, query: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
        try:
            with self._pool.connection() as connection:
                return connection.execute(query, params).fetchone()
        except (psycopg.Error, PoolTimeout) as error:
            raise RepositoryUnavailable(type(error).__name__) from error


def _to_stored(row: dict[str, Any]) -> StoredExtraction:
    return StoredExtraction(id=row["id"], extraction=extraction_from_json(row["result"]))
