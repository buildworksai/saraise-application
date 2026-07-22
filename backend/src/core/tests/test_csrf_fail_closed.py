"""Regression tests: RelaxedCsrfSessionAuthentication must fail CLOSED on CSRF.

Two independent validation councils (asset_management, backup_recovery) flagged the same
defect in shared foundation code: ``authenticate()`` wrapped ``super().authenticate()`` in a
blanket ``except Exception: pass``. DRF's SessionAuthentication calls ``enforce_csrf()`` from
inside ``authenticate()`` and raises PermissionDenied when an unsafe method arrives without a
valid CSRF token — so that blanket handler swallowed the denial, and the middleware-user
fallback below it then accepted the request. Any POST/PUT/PATCH/DELETE carrying only a session
cookie bypassed CSRF entirely, across every module mounted on this authenticator.

These tests pin the fixed contract. They fail against the pre-fix implementation.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from src.core.authentication import RelaxedCsrfSessionAuthentication


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="csrf-probe", password="irrelevant")


def _drf_request(django_request, user):
    """Wrap a raw Django request the way DRF does, with middleware having set request.user."""
    django_request.user = user
    return Request(django_request, authenticators=[RelaxedCsrfSessionAuthentication()])


@pytest.mark.django_db
@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_unsafe_method_without_csrf_token_is_rejected(method, user):
    """An unsafe method with a session user but no CSRF token must NOT authenticate.

    This is the exploitable case: enforce_csrf() raises, and the fallback must not rescue it.
    """
    factory = APIRequestFactory(enforce_csrf_checks=True)
    django_request = getattr(factory, method)("/api/v1/anything/", {}, format="json")
    request = _drf_request(django_request, user)

    with pytest.raises(PermissionDenied):
        RelaxedCsrfSessionAuthentication().authenticate(request)


@pytest.mark.django_db
@pytest.mark.parametrize("method", ["get", "head", "options"])
def test_safe_method_without_csrf_token_is_allowed(method, user):
    """Safe methods legitimately need no CSRF token — the fix must not over-correct."""
    factory = APIRequestFactory(enforce_csrf_checks=True)
    django_request = getattr(factory, method)("/api/v1/anything/")
    request = _drf_request(django_request, user)

    result = RelaxedCsrfSessionAuthentication().authenticate(request)

    assert result is not None, "safe methods must still authenticate via the middleware fallback"
    assert result[0] == user


@pytest.mark.django_db
def test_anonymous_user_does_not_authenticate():
    """The middleware fallback must never promote AnonymousUser to an authenticated identity."""
    factory = APIRequestFactory(enforce_csrf_checks=True)
    django_request = factory.get("/api/v1/anything/")
    request = _drf_request(django_request, AnonymousUser())

    assert RelaxedCsrfSessionAuthentication().authenticate(request) is None
