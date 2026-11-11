"""Identidad del usuario.

Igual que los otros microservicios, este servicio no valida el JWT: confía en la
cabecera X-User-Id que inyecta el API Gateway después de validar el token.
No hay valor por defecto: sin una X-User-Id válida, la respuesta es 401.
"""

import re
from typing import Annotated

from fastapi import Header, HTTPException, status

USER_ID_HEADER = "X-User-Id"
_MAX_BIGINT = 2**63 - 1  # user_id se guarda como bigint
_DIGITS = re.compile(r"[0-9]+")


def require_user_id(
    x_user_id: Annotated[
        str | None,
        Header(alias=USER_ID_HEADER, description="Id del usuario, inyectado por el API Gateway."),
    ] = None,
) -> int:
    value = (x_user_id or "").strip()
    if not _DIGITS.fullmatch(value) or not 0 < int(value) <= _MAX_BIGINT:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no autenticado: falta la cabecera X-User-Id o no es válida.",
        )
    return int(value)
