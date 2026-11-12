"""El OpenAPI (/docs) muestra el endpoint, el contrato de respuesta y los códigos de error."""

import pytest

URL = "/api/v1/documents/autofill"
ERROR_CODES = {"401", "413", "415", "422", "502", "504"}
RESPONSE_FIELDS = {
    "lotName", "supplierName", "coffeeType", "origin",
    "processingMethod", "altitudeMeters", "initialWeight", "certifications",
}


@pytest.fixture
def spec(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    return response.json()


@pytest.fixture
def operation(spec):
    return spec["paths"][URL]["post"]


def schema(spec, name):
    return spec["components"]["schemas"][name]


def test_docs_page_is_served(client):
    assert client.get("/docs").status_code == 200


def test_endpoint_and_health_are_documented(spec):
    assert URL in spec["paths"]
    assert "post" in spec["paths"][URL]
    assert "/health" in spec["paths"]


def test_x_user_id_header_is_documented(operation):
    [header] = [p for p in operation["parameters"] if p["in"] == "header"]
    assert header["name"] == "X-User-Id"
    assert "401" in header["description"]


def test_request_is_multipart_with_file_field(spec, operation):
    content = operation["requestBody"]["content"]
    assert list(content) == ["multipart/form-data"]
    body_ref = content["multipart/form-data"]["schema"]["$ref"].split("/")[-1]
    assert "file" in schema(spec, body_ref)["properties"]


def test_all_status_codes_are_documented(operation):
    assert set(operation["responses"]) == {"200"} | ERROR_CODES


@pytest.mark.parametrize("code", sorted(ERROR_CODES))
def test_each_error_uses_message_format_and_has_an_example(operation, code):
    content = operation["responses"][code]["content"]["application/json"]
    assert content["schema"]["$ref"].endswith("/ErrorMessage")
    examples = content["examples"].values()
    assert examples
    assert all(set(example["value"]) == {"message"} for example in examples)


def test_502_and_504_ask_to_fill_the_form_manually(operation):
    for code in ("502", "504"):
        [example] = operation["responses"][code]["content"]["application/json"]["examples"].values()
        assert "Completa el formulario manualmente" in example["value"]["message"]


def test_response_contract_matches_the_team_contract(spec, operation):
    ref = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    response = schema(spec, ref.split("/")[-1])

    assert set(response["properties"]) == {"extractionId", "cached", "fields", "warnings"}
    assert set(schema(spec, "FieldsOut")["properties"]) == RESPONSE_FIELDS
    assert set(schema(spec, "FieldOut")["properties"]) == {"value", "confidence"}
    assert set(schema(spec, "WarningOut")["properties"]) == {"field", "code", "message"}


def test_response_example_has_every_field(spec):
    example = schema(spec, "AutofillResponse")["example"]

    assert set(example["fields"]) == RESPONSE_FIELDS
    assert example["warnings"][0]["code"] == "LOW_CONFIDENCE"


def test_every_field_and_warning_code_is_described(spec):
    fields = schema(spec, "FieldsOut")["properties"]
    assert all(field.get("description") for field in fields.values())
    assert set(schema(spec, "WarningCode")["enum"]) == {
        "NOT_FOUND", "INVALID_VALUE", "INVALID_NUMBER", "UNKNOWN_CERTIFICATION", "LOW_CONFIDENCE",
    }
