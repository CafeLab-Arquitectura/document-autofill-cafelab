"""Reglas de normalización de cada tipo de campo.

Cada función recibe el texto leído y devuelve el valor normalizado junto con las
advertencias que correspondan. No agrega validaciones fuera de las reglas de Management.
"""

import re
from dataclasses import dataclass, field

from app.domain.extraction import FieldValue, WarningCode
from app.domain.vocabulary import (
    ALLOWED_CERTIFICATIONS,
    CERTIFICATION_ALIASES,
    certification_key,
    text_key,
)


@dataclass(frozen=True)
class Issue:
    code: WarningCode
    message: str


@dataclass(frozen=True)
class Normalized:
    value: FieldValue
    issues: list[Issue] = field(default_factory=list)


def normalize_text(text: str) -> Normalized:
    return Normalized(value=" ".join(text.split()))


def normalize_option(text: str, index: dict[str, str]) -> Normalized:
    """Devuelve el valor exacto de la lista, comparando sin tildes ni mayúsculas."""
    match = index.get(text_key(text))
    if match is not None:
        return Normalized(value=match)
    allowed = ", ".join(index.values())
    return Normalized(
        value=None,
        issues=[Issue(WarningCode.INVALID_VALUE, f"'{text}' no es un valor permitido ({allowed}).")],
    )


# Un número: dígitos con coma de miles opcional y punto decimal opcional.
_NUMBER_TOKEN = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
_WELL_FORMED = re.compile(r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")


def parse_number(text: str) -> int | float | None:
    """Coma = miles y punto = decimales: "1,650 msnm" -> 1650; "69.5" -> 69.5.

    Devuelve None si no hay exactamente un número bien escrito ("69,5", "1650-1800").
    """
    tokens = _NUMBER_TOKEN.findall(text)
    if len(tokens) != 1 or not _WELL_FORMED.fullmatch(tokens[0]):
        return None
    number = float(tokens[0].replace(",", ""))
    return int(number) if number.is_integer() else number


def normalize_non_negative_number(text: str) -> Normalized:
    number = parse_number(text)
    if number is None or number < 0:
        return Normalized(
            value=None,
            issues=[
                Issue(WarningCode.INVALID_NUMBER, f"'{text}' no es un número mayor o igual a 0.")
            ],
        )
    return Normalized(value=number)


# Separadores de una lista escrita en una sola línea: "Orgánico, Comercio Justo".
_LIST_SEPARATORS = re.compile(r"[,;/]|\s+y\s+|\s+and\s+", re.IGNORECASE)


def normalize_certifications(texts: list[str]) -> Normalized:
    """Lleva cada certificación a ORGANIC, FAIR_TRADE o RAINFOREST y descarta las demás."""
    values: list[str] = []
    issues: list[Issue] = []
    for text in texts:
        for part in _LIST_SEPARATORS.split(text):
            part = " ".join(part.split())
            if not part:
                continue
            certification = CERTIFICATION_ALIASES.get(certification_key(part))
            if certification is None:
                allowed = ", ".join(ALLOWED_CERTIFICATIONS)
                issues.append(
                    Issue(
                        WarningCode.UNKNOWN_CERTIFICATION,
                        f"'{part}' no es una certificación reconocida ({allowed}); se descartó.",
                    )
                )
            elif certification not in values:
                values.append(certification)
    return Normalized(value=values, issues=issues)
