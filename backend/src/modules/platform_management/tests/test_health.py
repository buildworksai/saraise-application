import pytest
from django.core.cache import cache
from django.db import connection

from src.modules.platform_management.health import check_cache_health, check_database_health, update_health_metrics
from src.modules.platform_management.models import SystemHealth


@pytest.mark.django_db
class TestHealthChecks:
    """Test cases for health check functions."""

    def test_check_database_health(self):
        """Test: Database health check."""
        result = check_database_health()
        assert "status" in result
        assert result["status"] == "healthy"

    def test_check_cache_health(self):
        """Test: Cache health check."""
        result = check_cache_health()
        assert "status" in result
        assert result["status"] in ["healthy", "degraded", "unhealthy"]

    def test_update_health_metrics(self):
        """Test: Update health metrics."""
        update_health_metrics()

        # Check database health record
        db_health = SystemHealth.objects.filter(service_name="database").first()
        assert db_health is not None
        assert db_health.status in ["healthy", "degraded", "unhealthy"]

        # Check cache health record
        cache_health = SystemHealth.objects.filter(service_name="cache").first()
        assert cache_health is not None
        assert cache_health.status in ["healthy", "degraded", "unhealthy"]


def test_check_database_health_unhealthy(monkeypatch):
    """Test: Database health check returns unhealthy on error."""

    class BrokenCursor:
        def __enter__(self):
            raise Exception("db down")

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(connection, "cursor", lambda: BrokenCursor())
    result = check_database_health()
    assert result["status"] == "unhealthy"
    assert "db down" in result["error_message"]


def test_check_cache_health_unhealthy(monkeypatch):
    """Test: Cache health check returns unhealthy on error."""

    def raise_error(*_args, **_kwargs):
        raise Exception("cache down")

    monkeypatch.setattr(cache, "set", raise_error)
    result = check_cache_health()
    assert result["status"] == "unhealthy"
    assert "cache down" in result["error_message"]


def test_check_cache_health_degraded(monkeypatch):
    """Test: Cache health check returns degraded on unexpected response."""
    monkeypatch.setattr(cache, "set", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cache, "get", lambda *_args, **_kwargs: "not_ok")
    result = check_cache_health()
    assert result["status"] == "degraded"
