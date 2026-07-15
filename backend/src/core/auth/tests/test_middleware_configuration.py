"""Smoke tests for configured Django middleware."""

from django.conf import settings
from django.utils.module_loading import import_string


def test_all_configured_middleware_can_be_imported():
    """Prevent invalid middleware paths from breaking Django startup."""
    for middleware_path in settings.MIDDLEWARE:
        middleware_class = import_string(middleware_path)
        assert callable(middleware_class), f"Configured middleware is not callable: {middleware_path}"


def test_mode_aware_middleware_runs_after_authentication():
    """Ensure request.user exists before mode-aware session validation."""
    authentication_index = settings.MIDDLEWARE.index("django.contrib.auth.middleware.AuthenticationMiddleware")
    mode_aware_index = settings.MIDDLEWARE.index("src.core.auth.middleware.ModeAwareSessionMiddleware")
    tenant_context_index = settings.MIDDLEWARE.index("src.core.middleware.tenant_context.TenantContextMiddleware")

    assert authentication_index < mode_aware_index < tenant_context_index
