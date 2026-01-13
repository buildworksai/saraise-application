import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from rest_framework.test import APIRequestFactory, force_authenticate

from src.modules.security_access_control.health import check_security_module_health
from src.modules.security_access_control.models import Permission, Role


@pytest.mark.django_db
def test_security_health_ok():
    user = get_user_model().objects.create_user(
        username="health-user",
        email="health@example.com",
        password="testpass123",
    )
    Role.objects.create(name="Role", code="role", tenant_id="00000000-0000-0000-0000-000000000001")
    Permission.objects.create(module="crm", object="customers", action="read")

    request = APIRequestFactory().get("/api/v1/security-access-control/health/")
    force_authenticate(request, user=user)
    response = check_security_module_health(request)
    assert response.status_code == 200
    assert response.data["status"] == "healthy"
    assert response.data["checks"]["database"] == "ok"
    assert response.data["checks"]["redis"] == "ok"


@pytest.mark.django_db
def test_security_health_unhealthy(monkeypatch):
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

    request = APIRequestFactory().get("/api/v1/security-access-control/health/")
    force_authenticate(request, user=user)
    response = check_security_module_health(request)
    assert response.status_code == 503
    assert response.data["status"] == "unhealthy"
