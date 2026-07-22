from __future__ import annotations

from ..health import get_module_health, parser_readiness_probe


def test_required_parser_registry_is_real() -> None:
    result = parser_readiness_probe()
    assert result.healthy
    assert result.details["registered_count"] >= 6


def test_health_response_contains_only_sanitized_component_evidence(db: object) -> None:
    report = get_module_health()
    rendered = str(report.payload).lower()
    assert "password" not in rendered and "traceback" not in rendered and "/users/" not in rendered
    assert report.status in {"healthy", "degraded", "unavailable"}
