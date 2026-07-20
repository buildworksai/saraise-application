"""Concrete identity factories and session-authenticated clients for tests.

The application uses :class:`Organization` as its tenant identity in
development/self-hosted mode and :class:`Tenant` in SaaS mode.  The fixtures in
this module follow that distinction, so they exercise ``UserProfile.clean``
instead of bypassing it.  Test modules can expose the fixtures with::

    pytest_plugins = ["src.core.testing.factories"]

Factory Boy's ``Meta.model`` always points at a concrete Django model here.  In
particular, none of these factories bind the many abstract ``TenantBaseModel``
classes used by individual modules.
"""

from __future__ import annotations

from typing import Any, TypeAlias

import factory
import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpRequest
from django.middleware.csrf import get_token
from rest_framework.test import APIClient

from src.core.licensing.models import Organization
from src.core.user_models import UserProfile
from src.modules.tenant_management.models import Tenant

TEST_PASSWORD = "saraise-test-password"  # pragma: allowlist secret

User = get_user_model()
TenantIdentity: TypeAlias = Organization | Tenant


class OrganizationFactory(factory.django.DjangoModelFactory):
    """Create a concrete self-hosted/development tenant identity."""

    class Meta:
        model = Organization

    name = factory.Sequence(lambda number: f"Test Organization {number}")
    domain = factory.Sequence(lambda number: f"tenant-{number}.example.test")


class TenantFactory(factory.django.DjangoModelFactory):
    """Create a concrete SaaS tenant identity."""

    class Meta:
        model = Tenant

    name = factory.Sequence(lambda number: f"Test Tenant {number}")
    slug = factory.Sequence(lambda number: f"test-tenant-{number}")
    subdomain = factory.Sequence(lambda number: f"test-tenant-{number}")
    status = Tenant.TenantStatus.ACTIVE


class UserFactory(factory.django.DjangoModelFactory):
    """Create an active Django user with a usable, deterministic password."""

    class Meta:
        model = User

    username = factory.Sequence(lambda number: f"test-user-{number}")
    email = factory.LazyAttribute(lambda user: f"{user.username}@example.test")
    password = factory.PostGenerationMethodCall("set_password", TEST_PASSWORD)
    is_active = True


class UserProfileFactory(factory.django.DjangoModelFactory):
    """Create or configure the concrete profile associated with a user.

    ``UserProfile`` is created by a Django signal when ``UserFactory`` saves a
    user.  Updating that real row here avoids disabling the signal and prevents
    duplicate one-to-one records.
    """

    class Meta:
        model = UserProfile

    user = factory.SubFactory(UserFactory)

    @classmethod
    def _create(cls, model_class: type[UserProfile], *args: Any, **kwargs: Any) -> UserProfile:
        user = kwargs.pop("user")
        profile, _ = model_class.objects.get_or_create(user=user)
        for field_name, value in kwargs.items():
            setattr(profile, field_name, value)
        profile.save()
        return profile


class TenantUserProfileFactory(UserProfileFactory):
    """Create a profile bound to a real organization or SaaS tenant."""

    class Meta:
        model = UserProfile
        exclude = ("organization",)

    organization = factory.SubFactory(OrganizationFactory)
    tenant_id = factory.LazyAttribute(lambda profile: str(profile.organization.id))
    tenant_role = "tenant_admin"
    platform_role = None


class PlatformUserProfileFactory(UserProfileFactory):
    """Create a platform-scoped profile, which deliberately has no tenant."""

    class Meta:
        model = UserProfile

    tenant_id = None
    tenant_role = None
    platform_role = "platform_owner"


class TenantUserFactory(UserFactory):
    """Create a user and profile bound to ``organization``.

    Despite the parameter name, ``organization`` may be either an
    ``Organization`` or a SaaS ``Tenant``.  Passing the concrete identity is
    required when tests need multiple users to share the same tenant.
    """

    class Meta:
        model = User
        exclude = ("organization", "tenant_role")

    organization = factory.SubFactory(OrganizationFactory)
    tenant_role = "tenant_admin"
    profile = factory.RelatedFactory(
        TenantUserProfileFactory,
        factory_related_name="user",
        organization=factory.SelfAttribute("..organization"),
        tenant_role=factory.SelfAttribute("..tenant_role"),
    )


class PlatformUserFactory(UserFactory):
    """Create a platform owner with a valid, non-tenant profile."""

    class Meta:
        model = User
        exclude = ("platform_role",)

    platform_role = "platform_owner"
    profile = factory.RelatedFactory(
        PlatformUserProfileFactory,
        factory_related_name="user",
        platform_role=factory.SelfAttribute("..platform_role"),
    )


def create_tenant_identity(label: str) -> TenantIdentity:
    """Create the tenant identity appropriate for the active operating mode."""

    normalized_label = label.lower().replace("_", "-").replace(" ", "-")
    if settings.SARAISE_MODE == "saas":
        return TenantFactory(
            name=f"Test Tenant {label.upper()}",
            slug=f"test-tenant-{normalized_label}",
            subdomain=f"test-tenant-{normalized_label}",
        )
    return OrganizationFactory(
        name=f"Test Organization {label.upper()}",
        domain=f"tenant-{normalized_label}.example.test",
    )


def authenticated_api_client(
    user: Any,
    *,
    password: str = TEST_PASSWORD,
    enforce_csrf_checks: bool = True,
) -> APIClient:
    """Return a DRF client authenticated through Django's real session backend.

    CSRF enforcement is enabled by default.  The client receives a valid CSRF
    cookie/header pair so unsafe methods still traverse the production CSRF
    authentication path rather than using DRF's ``force_authenticate`` escape
    hatch.
    """

    client = APIClient(enforce_csrf_checks=enforce_csrf_checks)
    username_field = user.USERNAME_FIELD
    credentials = {
        username_field: getattr(user, username_field),
        "password": password,
    }
    if not client.login(**credentials):
        raise AssertionError(f"Could not establish a test session for user {user.pk}")

    if enforce_csrf_checks:
        request = HttpRequest()
        csrf_token = get_token(request)
        client.cookies[settings.CSRF_COOKIE_NAME] = csrf_token
        client.credentials(HTTP_X_CSRFTOKEN=csrf_token)

    return client


@pytest.fixture
def api_client() -> APIClient:
    """Return an anonymous DRF client with production-like CSRF enforcement."""

    return APIClient(enforce_csrf_checks=True)


@pytest.fixture
def tenant_a(db: Any) -> TenantIdentity:
    """Create tenant A using the active mode's concrete identity model."""

    return create_tenant_identity("a")


@pytest.fixture
def tenant_b(db: Any) -> TenantIdentity:
    """Create tenant B using the active mode's concrete identity model."""

    return create_tenant_identity("b")


@pytest.fixture
def tenant_pair(tenant_a: TenantIdentity, tenant_b: TenantIdentity) -> tuple[TenantIdentity, TenantIdentity]:
    """Return the two distinct tenant identities used by isolation tests."""

    return tenant_a, tenant_b


@pytest.fixture
def tenant_a_user(db: Any, tenant_a: TenantIdentity) -> Any:
    """Create a tenant administrator for tenant A."""

    return TenantUserFactory(
        username="tenant-a-user",
        email="tenant-a-user@example.test",
        organization=tenant_a,
    )


@pytest.fixture
def tenant_b_user(db: Any, tenant_b: TenantIdentity) -> Any:
    """Create a tenant administrator for tenant B."""

    return TenantUserFactory(
        username="tenant-b-user",
        email="tenant-b-user@example.test",
        organization=tenant_b,
    )


@pytest.fixture
def platform_user(db: Any) -> Any:
    """Create a platform owner with no tenant assignment."""

    return PlatformUserFactory(
        username="platform-user",
        email="platform-user@example.test",
    )


@pytest.fixture
def tenant_a_profile(tenant_a_user: Any) -> UserProfile:
    """Return tenant A's fully validated profile."""

    return tenant_a_user.profile


@pytest.fixture
def tenant_b_profile(tenant_b_user: Any) -> UserProfile:
    """Return tenant B's fully validated profile."""

    return tenant_b_user.profile


@pytest.fixture
def platform_profile(platform_user: Any) -> UserProfile:
    """Return the platform user's fully validated profile."""

    return platform_user.profile


@pytest.fixture
def authenticated_tenant_a_client(tenant_a_user: Any) -> APIClient:
    """Return a session-authenticated, CSRF-enforcing tenant A client."""

    return authenticated_api_client(tenant_a_user)


@pytest.fixture
def authenticated_tenant_b_client(tenant_b_user: Any) -> APIClient:
    """Return a session-authenticated, CSRF-enforcing tenant B client."""

    return authenticated_api_client(tenant_b_user)


@pytest.fixture
def authenticated_platform_client(platform_user: Any) -> APIClient:
    """Return a session-authenticated, CSRF-enforcing platform client."""

    return authenticated_api_client(platform_user)


@pytest.fixture
def tenant_a_client(authenticated_tenant_a_client: APIClient) -> APIClient:
    """Concise alias for ``authenticated_tenant_a_client``."""

    return authenticated_tenant_a_client


@pytest.fixture
def tenant_b_client(authenticated_tenant_b_client: APIClient) -> APIClient:
    """Concise alias for ``authenticated_tenant_b_client``."""

    return authenticated_tenant_b_client


@pytest.fixture
def platform_client(authenticated_platform_client: APIClient) -> APIClient:
    """Concise alias for ``authenticated_platform_client``."""

    return authenticated_platform_client


@pytest.fixture
def authenticated_client_a(authenticated_tenant_a_client: APIClient) -> APIClient:
    """Compatibility alias for the session-authenticated tenant A client."""

    return authenticated_tenant_a_client


@pytest.fixture
def authenticated_client_b(authenticated_tenant_b_client: APIClient) -> APIClient:
    """Compatibility alias for the session-authenticated tenant B client."""

    return authenticated_tenant_b_client
