from saraise_backend.settings import _parse_allowed_hosts


def test_allowed_hosts_env_takes_precedence_in_development() -> None:
    assert _parse_allowed_hosts("development", "localhost,backend,backend:8000") == [
        "localhost",
        "backend",
        "backend:8000",
    ]


def test_allowed_hosts_development_fallback_keeps_local_defaults() -> None:
    assert _parse_allowed_hosts("development", "") == ["localhost", "127.0.0.1", "0.0.0.0"]


def test_allowed_hosts_non_development_requires_configuration() -> None:
    assert _parse_allowed_hosts("self-hosted", "") == []
