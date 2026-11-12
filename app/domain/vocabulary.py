"""Valores que acepta Management, y equivalencias para reconocerlos en la guía."""

import unicodedata


def text_key(text: str) -> str:
    """Clave de comparación: sin tildes, sin distinguir mayúsculas y con espacios simples."""
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )
    return " ".join(without_accents.casefold().split())


def certification_key(text: str) -> str:
    """Clave de una certificación: mayúsculas, sin tildes, espacios y guiones como '_'."""
    key = text_key(text).upper()
    for separator in (" ", "-"):
        key = key.replace(separator, "_")
    return key


COFFEE_TYPES: tuple[str, ...] = ("Arábica", "Robusta", "Mezcla")

PROCESSING_METHODS: tuple[str, ...] = (
    "Lavado",
    "Natural",
    "Honey",
    "Fermentación anaeróbica",
    "Maceración carbónica",
)

ALLOWED_CERTIFICATIONS: tuple[str, ...] = ("ORGANIC", "FAIR_TRADE", "RAINFOREST")

# Equivalencias español / inglés, indexadas por certification_key().
# Para reconocer un nombre nuevo, basta con agregar una fila.
CERTIFICATION_ALIASES: dict[str, str] = {
    # ORGANIC
    "ORGANIC": "ORGANIC",
    "ORGANICO": "ORGANIC",
    "ORGANICA": "ORGANIC",
    # FAIR_TRADE
    "FAIR_TRADE": "FAIR_TRADE",
    "FAIRTRADE": "FAIR_TRADE",
    "COMERCIO_JUSTO": "FAIR_TRADE",
    # RAINFOREST
    "RAINFOREST": "RAINFOREST",
    "RAINFOREST_ALLIANCE": "RAINFOREST",
}

COFFEE_TYPE_INDEX: dict[str, str] = {text_key(value): value for value in COFFEE_TYPES}
PROCESSING_METHOD_INDEX: dict[str, str] = {text_key(value): value for value in PROCESSING_METHODS}
