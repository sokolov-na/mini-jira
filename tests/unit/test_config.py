from pathlib import Path

import pytest
from pydantic import ValidationError

from mini_jira.config import Settings

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "case,error_type,message",
    [
        (
            "cors",
            "cors_origin_wildcard",
            "CORS origins must not contain wildcards",
        ),
        (
            "cookie",
            "refresh_cookie_secure_required",
            "SameSite=none requires a Secure refresh cookie",
        ),
    ],
)
def test_settings_custom_errors_have_stable_codes(
    case: str,
    error_type: str,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValidationError) as raised:
        Settings(
            database_url="postgresql+psycopg://unused@127.0.0.1/unused_test",
            jwt_secret_key="test-only-key-never-use-in-production",
            cors_origins=["https://private-origin.example/*"]
            if case == "cors"
            else [],
            refresh_cookie_samesite="none",
            refresh_cookie_secure=case == "cors",
        )
    error = raised.value.errors(include_input=False)[0]
    assert error["type"] == error_type
    assert error["msg"] == message
    assert "ctx" not in error
