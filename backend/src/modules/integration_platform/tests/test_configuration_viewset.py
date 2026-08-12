"""Configuration controller regressions that do not require database access."""

from __future__ import annotations

from ..api import IntegrationPlatformConfigurationViewSet


def test_configuration_history_controller_exposes_pagination_helpers() -> None:
    view = IntegrationPlatformConfigurationViewSet()

    assert callable(view.paginate_queryset)
    assert callable(view.get_paginated_response)
