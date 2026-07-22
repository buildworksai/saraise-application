"""Non-sensitive liveness and readiness contracts."""

from rest_framework.permissions import AllowAny

from src.core.api import GovernedAPIViewMixin
from src.modules.data_migration.health import LivenessView, ReadinessView, readiness


def test_health_views_are_governed_and_public_internal() -> None:
    assert issubclass(LivenessView, GovernedAPIViewMixin)
    assert issubclass(ReadinessView, GovernedAPIViewMixin)
    assert LivenessView.permission_classes == (AllowAny,)
    assert ReadinessView.permission_classes == (AllowAny,)


def test_readiness_healthy() -> None:
    payload, status_code = readiness({"database": lambda: True, "cache": lambda: True})
    assert status_code == 200
    assert payload == {"status": "ready", "module": "data_migration", "components": {"database": "READY", "cache": "READY"}}


def test_readiness_false_result_is_degraded() -> None:
    payload, status_code = readiness({"outbox": lambda: False})
    assert status_code == 503
    assert payload["components"] == {"outbox": "DEGRADED"}


def test_readiness_exception_is_redacted() -> None:
    def explode() -> bool:
        raise RuntimeError("redis://user:secret@internal.example/0")

    payload, status_code = readiness({"cache": explode})
    assert status_code == 503
    assert payload["components"] == {"cache": "UNAVAILABLE"}
    assert "secret" not in str(payload)
    assert "internal.example" not in str(payload)
    assert "count" not in str(payload).lower()
