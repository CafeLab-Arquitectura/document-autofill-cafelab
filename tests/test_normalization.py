import pytest

from app.domain.extraction import WarningCode
from app.domain.normalization import (
    normalize_certifications,
    normalize_non_negative_number,
    normalize_option,
    normalize_text,
    parse_number,
)
from app.domain.vocabulary import COFFEE_TYPE_INDEX, PROCESSING_METHOD_INDEX

# Texto


def test_text_collapses_whitespace():
    assert normalize_text("  Villa Rica,\n  Oxapampa  ").value == "Villa Rica, Oxapampa"


# Listas de valores (coffeeType, processingMethod)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("arabica", "Arábica"),
        ("ARÁBICA", "Arábica"),
        ("  Arabica ", "Arábica"),
        ("robusta", "Robusta"),
        ("MEZCLA", "Mezcla"),
    ],
)
def test_coffee_type_ignores_case_and_accents(text, expected):
    assert normalize_option(text, COFFEE_TYPE_INDEX).value == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("lavado", "Lavado"),
        ("NATURAL", "Natural"),
        ("honey", "Honey"),
        ("fermentacion anaerobica", "Fermentación anaeróbica"),
        ("Fermentación   Anaeróbica", "Fermentación anaeróbica"),
        ("maceracion carbonica", "Maceración carbónica"),
    ],
)
def test_processing_method_ignores_case_and_accents(text, expected):
    assert normalize_option(text, PROCESSING_METHOD_INDEX).value == expected


@pytest.mark.parametrize("text", ["Geisha", "Arábica lavado", "Semi lavado"])
def test_value_outside_the_list_is_null_with_invalid_value(text):
    result = normalize_option(text, COFFEE_TYPE_INDEX)

    assert result.value is None
    assert [issue.code for issue in result.issues] == [WarningCode.INVALID_VALUE]


# Números: punto = decimal; coma + 3 dígitos = miles; coma + otra cantidad = decimal


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1650", 1650),
        ("1,650 msnm", 1650),
        ("1,650", 1650),
        ("12,345,678", 12345678),
        ("69", 69),
        ("69 kg", 69),
        ("69.5", 69.5),
        ("1,650.25 kg", 1650.25),
        ("69.0", 69),
        ("0", 0),
        ("60,5", 60.5),
        ("60,5 kg", 60.5),
        ("69,25", 69.25),
        ("1,65", 1.65),
        ("60,0", 60),
        ("60,500", 60500),  # coma + 3 dígitos: siempre miles
        ("69 kg.", 69),
    ],
)
def test_parse_number(text, expected):
    result = parse_number(text)

    assert result == expected
    assert type(result) is type(expected)


@pytest.mark.parametrize(
    "text",
    [
        "1.650,5",  # punto y coma mezclados al estilo europeo
        "1,65,000",  # grupos de miles mal formados
        "1,650,5",
        "1650 - 1800 msnm",  # más de un número
        "mil seiscientos",
        "",
    ],
)
def test_parse_number_rejects_ambiguous_text(text):
    assert parse_number(text) is None


@pytest.mark.parametrize("text", ["-5", "-1,650 msnm", "-60,5", "1.650,5", "sin dato"])
def test_invalid_or_negative_number_is_null_with_invalid_number(text):
    result = normalize_non_negative_number(text)

    assert result.value is None
    assert [issue.code for issue in result.issues] == [WarningCode.INVALID_NUMBER]


# Certificaciones


@pytest.mark.parametrize(
    ("texts", "expected"),
    [
        (["ORGANIC"], ["ORGANIC"]),
        (["organic"], ["ORGANIC"]),
        (["Orgánico"], ["ORGANIC"]),
        (["orgánica"], ["ORGANIC"]),
        (["Fair Trade"], ["FAIR_TRADE"]),
        (["fair-trade"], ["FAIR_TRADE"]),
        (["Fairtrade"], ["FAIR_TRADE"]),
        (["Comercio Justo"], ["FAIR_TRADE"]),
        (["Rainforest Alliance"], ["RAINFOREST"]),
        (["rainforest"], ["RAINFOREST"]),
    ],
)
def test_certifications_in_spanish_and_english(texts, expected):
    result = normalize_certifications(texts)

    assert result.value == expected
    assert result.issues == []


def test_certifications_written_in_one_line_are_split():
    result = normalize_certifications(["Orgánico, Comercio Justo y Rainforest Alliance"])

    assert result.value == ["ORGANIC", "FAIR_TRADE", "RAINFOREST"]


def test_duplicate_certifications_are_kept_once():
    assert normalize_certifications(["Orgánico", "ORGANIC"]).value == ["ORGANIC"]


def test_unknown_certification_is_dropped_with_warning():
    result = normalize_certifications(["Orgánico", "UTZ"])

    assert result.value == ["ORGANIC"]
    assert [issue.code for issue in result.issues] == [WarningCode.UNKNOWN_CERTIFICATION]
    assert "'UTZ'" in result.issues[0].message


def test_only_unknown_certifications_give_an_empty_list():
    result = normalize_certifications(["UTZ", "4C"])

    assert result.value == []
    assert len(result.issues) == 2
