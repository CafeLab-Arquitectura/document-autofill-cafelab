"""Datos de la petición que se agregan a cada línea de log (userId, hash abreviado).

Usa contextvars: cada petición tiene su propio contexto, aunque corran en paralelo.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_context: ContextVar[dict[str, Any]] = ContextVar("log_context", default={})

HASH_PREFIX_LENGTH = 12


def short_hash(file_hash: str) -> str:
    return file_hash[:HASH_PREFIX_LENGTH]


@contextmanager
def log_context(**fields: Any) -> Iterator[None]:
    token = _context.set({**_context.get(), **fields})
    try:
        yield
    finally:
        _context.reset(token)


def bind(**fields: Any) -> None:
    """Agrega datos al contexto actual (dentro de un `with log_context(...)`)."""
    _context.set({**_context.get(), **fields})


def current() -> dict[str, Any]:
    return dict(_context.get())
