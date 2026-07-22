"""Sanitized module readiness tests."""

from __future__ import annotations

from unittest.mock import patch

from src.modules.business_intelligence.health import check_health


def test_health_never_exposes_raw_dependency_exception() -> None:
    with patch("src.modules.business_intelligence.health.connection.cursor", side_effect=RuntimeError("secret dsn")):
        result = check_health()
    rendered = str(result)
    assert result["status"] == "unavailable"
    assert "secret dsn" not in rendered
