import pytest

from tests.fixtures.database import validate_test_database_url

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "value",
    [
        "postgresql+psycopg://user:pass@localhost/mini_jira",
        "postgresql+psycopg://user:pass@localhost/postgres",
        "sqlite:///app_test",
        "not-a-url",
        "postgresql+psycopg:///mini_jira_test",
        "postgresql+psycopg://user:pass@localhost/mini_jira_test?dbname=production",
        "postgresql+psycopg://user:pass@localhost/mini_jira_test?service=production",
    ],
)
def test_database_guard_rejects_unsafe_urls(value: str) -> None:
    with pytest.raises(ValueError):
        validate_test_database_url(value)


def test_database_guard_accepts_explicit_test_database() -> None:
    url = validate_test_database_url(
        "postgresql+psycopg://test:local-test-password@localhost/mini_jira_test"
    )
    assert url.database == "mini_jira_test"
