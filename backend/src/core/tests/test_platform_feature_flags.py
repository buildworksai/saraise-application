import uuid
from types import SimpleNamespace

import pytest
from django.test import override_settings

from src.core.platform_feature_flags import PlatformFeatureFlagService
from src.modules.platform_management.models import FeatureFlag, PlatformSetting


@pytest.mark.django_db
@override_settings(SARAISE_MODE="development")
def test_local_feature_flags_default_disabled_enabled_and_rollout(monkeypatch):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()

    assert PlatformFeatureFlagService.is_feature_enabled("missing", tenant_id, default=True) is True

    FeatureFlag.objects.create(name="disabled", tenant_id=tenant_id, enabled=False)
    assert PlatformFeatureFlagService.is_feature_enabled("disabled", tenant_id, default=True) is False

    FeatureFlag.objects.create(name="enabled", tenant_id=tenant_id, enabled=True)
    assert PlatformFeatureFlagService.is_feature_enabled("enabled", tenant_id, user_id=user_id) is True

    FeatureFlag.objects.create(name="zero-rollout", tenant_id=tenant_id, enabled=True, rollout_percentage=0)
    assert PlatformFeatureFlagService.is_feature_enabled("zero-rollout", tenant_id, user_id=user_id) is False

    def broken_filter(*_args, **_kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(FeatureFlag.objects, "filter", broken_filter)
    assert PlatformFeatureFlagService.is_feature_enabled("enabled", tenant_id, default=True) is True


@pytest.mark.django_db
@override_settings(SARAISE_MODE="development")
def test_local_settings_return_values_defaults_and_fail_closed(monkeypatch):
    tenant_id = uuid.uuid4()

    assert PlatformFeatureFlagService.get_setting("missing", tenant_id, default="fallback") == "fallback"

    PlatformSetting.objects.create(key="retention_days", tenant_id=tenant_id, value="30")
    assert PlatformFeatureFlagService.get_setting("retention_days", tenant_id, default="fallback") == "30"

    def broken_filter(*_args, **_kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(PlatformSetting.objects, "filter", broken_filter)
    assert PlatformFeatureFlagService.get_setting("retention_days", tenant_id, default="fallback") == "fallback"


@override_settings(SARAISE_MODE="saas")
def test_saas_feature_flags_use_control_plane_response_paths(monkeypatch):
    tenant_id = uuid.uuid4()
    captured = []

    def fake_get(url, *, params, timeout):
        captured.append((url, params, timeout))
        return SimpleNamespace(status_code=200, json=lambda: [{"enabled": True, "rollout_percentage": 100}])

    monkeypatch.setattr("src.core.platform_feature_flags.requests.get", fake_get)
    assert PlatformFeatureFlagService.is_feature_enabled("remote", tenant_id, default=False) is True
    assert captured[-1][1] == {"name": "remote", "tenant_id": str(tenant_id)}
    assert captured[-1][2] == 2

    monkeypatch.setattr(
        "src.core.platform_feature_flags.requests.get",
        lambda *_args, **_kwargs: SimpleNamespace(status_code=503, json=lambda: []),
    )
    assert PlatformFeatureFlagService.is_feature_enabled("remote", tenant_id, default=True) is True

    monkeypatch.setattr(
        "src.core.platform_feature_flags.requests.get",
        lambda *_args, **_kwargs: SimpleNamespace(status_code=200, json=lambda: []),
    )
    assert PlatformFeatureFlagService.is_feature_enabled("remote", tenant_id, default=True) is True

    monkeypatch.setattr(
        "src.core.platform_feature_flags.requests.get",
        lambda *_args, **_kwargs: SimpleNamespace(
            status_code=200,
            json=lambda: [{"enabled": False, "rollout_percentage": 100}],
        ),
    )
    assert PlatformFeatureFlagService.is_feature_enabled("remote", tenant_id, default=True) is False

    monkeypatch.setattr(
        "src.core.platform_feature_flags.requests.get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("control plane down")),
    )
    assert PlatformFeatureFlagService.is_feature_enabled("remote", tenant_id, default=True) is True


@override_settings(SARAISE_MODE="saas")
def test_saas_settings_use_control_plane_response_paths(monkeypatch):
    tenant_id = uuid.uuid4()
    captured = []

    def fake_get(url, *, params, timeout):
        captured.append((url, params, timeout))
        return SimpleNamespace(status_code=200, json=lambda: [{"value": "enabled"}])

    monkeypatch.setattr("src.core.platform_feature_flags.requests.get", fake_get)
    assert PlatformFeatureFlagService.get_setting("mode", tenant_id, default="fallback") == "enabled"
    assert captured[-1][1] == {"key": "mode", "tenant_id": str(tenant_id)}
    assert captured[-1][2] == 2

    monkeypatch.setattr(
        "src.core.platform_feature_flags.requests.get",
        lambda *_args, **_kwargs: SimpleNamespace(status_code=500, json=lambda: []),
    )
    assert PlatformFeatureFlagService.get_setting("mode", tenant_id, default="fallback") == "fallback"

    monkeypatch.setattr(
        "src.core.platform_feature_flags.requests.get",
        lambda *_args, **_kwargs: SimpleNamespace(status_code=200, json=lambda: []),
    )
    assert PlatformFeatureFlagService.get_setting("mode", tenant_id, default="fallback") == "fallback"

    monkeypatch.setattr(
        "src.core.platform_feature_flags.requests.get",
        lambda *_args, **_kwargs: SimpleNamespace(status_code=200, json=lambda: [{}]),
    )
    assert PlatformFeatureFlagService.get_setting("mode", tenant_id, default="fallback") == "fallback"

    monkeypatch.setattr(
        "src.core.platform_feature_flags.requests.get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("control plane down")),
    )
    assert PlatformFeatureFlagService.get_setting("mode", tenant_id, default="fallback") == "fallback"
