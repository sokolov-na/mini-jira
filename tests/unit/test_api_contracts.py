import pytest

from mini_jira.main import api

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "path,method,status,model",
    [
        ("/auth/register", "post", "201", "AccessTokenResponse"),
        ("/auth/login", "post", "200", "AccessTokenResponse"),
        ("/auth/refresh", "post", "200", "AccessTokenResponse"),
        ("/auth/password/update", "patch", "200", "AccessTokenResponse"),
        ("/users/me", "get", "200", "UserDTO"),
        ("/users/me", "patch", "200", "UserDTO"),
    ],
)
def test_openapi_declares_response_models(
    path: str, method: str, status: str, model: str
) -> None:
    schema = api.openapi()
    response = schema["paths"][path][method]["responses"][status]
    assert response["content"]["application/json"]["schema"] == {
        "$ref": f"#/components/schemas/{model}"
    }
    tokens = schema["components"]["schemas"]["AccessTokenResponse"]
    assert "access_token" in tokens["required"]
    assert tokens["properties"]["token_type"]["const"] == "bearer"


@pytest.mark.parametrize(
    "path,status",
    [
        ("/auth/logout", "200"),
        ("/auth/password/reset", "202"),
        ("/auth/password/reset/confirm", "200"),
    ],
)
def test_openapi_preserves_null_responses(path: str, status: str) -> None:
    response = api.openapi()["paths"][path]["post"]["responses"][status]
    assert response["content"]["application/json"]["schema"]["type"] == "null"


def test_openapi_delete_has_no_body() -> None:
    response = api.openapi()["paths"]["/users/me"]["delete"]["responses"][
        "204"
    ]
    assert "content" not in response


def test_openapi_health_has_string_values() -> None:
    response = api.openapi()["paths"]["/health"]["get"]["responses"]["200"]
    schema = response["content"]["application/json"]["schema"]
    assert schema["type"] == "object"
    assert schema["additionalProperties"]["type"] == "string"
