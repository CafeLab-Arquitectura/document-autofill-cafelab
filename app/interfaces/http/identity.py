"""Identidad del usuario.

Igual que los otros microservicios, este servicio no valida el JWT: confía en la
cabecera X-User-Id que inyecta el API Gateway después de validar el token.
No hay valor por defecto: sin una X-User-Id válida, la respuesta es 401.
"""

import re
from typing import Annotated

from fastapi import Header, HTTPException, status

USER_ID_HEADER = "X-User-Id"
_MAX_BIGINT = 2**63 - 1  # mismo rango que los ids (bigint) de los otros servicios
_DIGITS = re.compile(r"[0-9]+")

UNAUTHORIZED_MESSAGE = "Usuario no autenticado: falta la cabecera X-User-Id o no es válida."


def require_user_id(
    x_user_id: Annotated[
        str | None,
        Header(
            alias=USER_ID_HEADER,
            description=(
                "Obligatoria (401 si falta). Id numérico del usuario. La inyecta el API Gateway "
                "después de validar el JWT; en local se envía a mano."
            ),
            examples=["42"],
        ),
    ] = None,
) -> int:
    value = (x_user_id or "").strip()
    if not _DIGITS.fullmatch(value) or not 0 < int(value) <= _MAX_BIGINT:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=UNAUTHORIZED_MESSAGE,
        )
    return int(value)
