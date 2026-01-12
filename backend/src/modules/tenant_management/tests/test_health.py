import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from rest_framework.test import APIRequestFactory, force_authenticate

from ..health import health_check
from ..models import Tenant


@pytest.mark.django_db
def test_health_check_ok():
    Tenant.objects.create(name="Test Tenant", slug="test-tenant")
    request = APIRequestFactory().get("/api/v1/tenant-management/health/")
    user = get_user_model().objects.create_user(
        username="health-user",
        email="health@example.com",
        password="testpass123",
    )
    force_authenticate(request, user=user)
    response = health_check(request)
    assert response.status_code == 200
    assert response.data["status"] == "healthy"
    assert response.data["checks"]["database"] == "ok"
    assert response.data["checks"]["redis"] == "ok"
    assert response.data["checks"]["tenants"]["total"] >= 1


@pytest.mark.django_db
def test_health_check_unhealthy(monkeypatch):
    user = get_user_model().objects.create_user(
        username="health-user-2",
        email="health2@example.com",
        password="testpass123",
    )

    class BrokenCursor:
        def __enter__(self):
            raise Exception("db down")

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(connection, "cursor", lambda: BrokenCursor())
    monkeypatch.setattr(cache, "set", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cache, "get", lambda *_args, **_kwargs: "not_ok")
    request = APIRequestFactory().get("/api/v1/tenant-management/health/")
    force_authenticate(request, user=user)
    response = health_check(request)
    assert response.status_code == 503
    assert response.data["status"] == "unhealthy"
    assert "error" in response.data["checks"]["database"]
    assert "error" in response.data["checks"]["redis"]
