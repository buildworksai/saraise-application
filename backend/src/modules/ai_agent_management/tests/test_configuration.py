"""Tenant configuration contract, history, portability, and fail-closed tests."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from rest_framework import status

from src.core.access.permissions import RequiresAccess
from src.modules.ai_agent_management.models import AgentManagementConfiguration, AgentManagementConfigurationVersion
from src.modules.ai_agent_management.services import ConfigurationService
from src.modules.ai_agent_management.urls import router


@pytest.mark.django_db
def test_configuration_versions_export_import_and_rollback_are_immutable(tenant_id, actor_id):
    bootstrap_correlation = uuid4()
    current = ConfigurationService.current(tenant_id, actor_id, bootstrap_correlation)
    assert current.version == 1
    bootstrap = AgentManagementConfigurationVersion.objects.get(
        tenant_id=tenant_id,
        environment="production",
        version=1,
    )
    assert bootstrap.changed_by == actor_id
    assert bootstrap.correlation_id == bootstrap_correlation

    changed = ConfigurationService.defaults()
    changed["provider"]["max_tokens"] = 8192
    update_correlation = uuid4()
    updated = ConfigurationService.replace(
        tenant_id,
        actor_id,
        update_correlation,
        changed,
        expected_version=1,
    )
    assert updated.version == 2
    history = AgentManagementConfigurationVersion.objects.get(
        tenant_id=tenant_id,
        environment="production",
        version=2,
    )
    assert history.previous_document["provider"]["max_tokens"] != 8192
    assert history.document["provider"]["max_tokens"] == 8192
    assert history.correlation_id == update_correlation

    exported = ConfigurationService.export_document(tenant_id, actor_id, uuid4())
    assert exported["schema"] == "saraise.ai-agent-management.configuration/v1"
    assert exported["configuration"] == changed

    rolled_back = ConfigurationService.rollback(tenant_id, actor_id, uuid4(), 1)
    assert rolled_back.version == 3
    assert rolled_back.document == ConfigurationService.defaults()

    with pytest.raises(ValidationError):
        history.save()
    with pytest.raises(ValidationError):
        AgentManagementConfigurationVersion.objects.filter(pk=history.pk).update(version=99)
    with pytest.raises(ValidationError):
        AgentManagementConfigurationVersion.objects.filter(pk=history.pk).delete()


@pytest.mark.django_db
def test_configuration_rejects_unsafe_and_cross_tenant_values(tenant_id, other_tenant_id, actor_id):
    current = ConfigurationService.current(tenant_id, actor_id, uuid4())
    foreign = ConfigurationService.current(other_tenant_id, uuid4(), uuid4())
    unsafe = ConfigurationService.defaults()
    unsafe["egress"]["forbidden_ip_addresses"].remove("169.254.169.254")
    with pytest.raises(ValidationError):
        ConfigurationService.replace(
            tenant_id,
            actor_id,
            uuid4(),
            unsafe,
            expected_version=current.version,
        )
    invalid_graph = ConfigurationService.defaults()
    invalid_graph["agent"]["execution_state_transitions"]["completed"] = ["running"]
    with pytest.raises(ValidationError):
        ConfigurationService.validate_document(invalid_graph)
    current.refresh_from_db()
    foreign.refresh_from_db()
    assert current.version == 1
    assert foreign.version == 1
    assert current.id != foreign.id


@pytest.mark.django_db
def test_configuration_accepts_inclusive_threshold_boundaries_and_rejects_order_inversions():
    boundary = ConfigurationService.defaults()
    boundary["evaluation"]["quality_warn_threshold"] = 1
    boundary["evaluation"]["quality_pass_threshold"] = 1
    boundary["evaluation"]["hallucination_warn_threshold"] = 0
    boundary["evaluation"]["hallucination_pass_threshold"] = 0
    boundary["ui"]["saturation_warning_threshold"] = 1
    boundary["ui"]["saturation_critical_threshold"] = 1

    validated = ConfigurationService.validate_document(boundary)
    assert validated["evaluation"]["quality_warn_threshold"] == 1
    assert validated["evaluation"]["quality_pass_threshold"] == 1
    assert validated["evaluation"]["hallucination_warn_threshold"] == 0
    assert validated["evaluation"]["hallucination_pass_threshold"] == 0
    assert validated["ui"]["saturation_warning_threshold"] == 1
    assert validated["ui"]["saturation_critical_threshold"] == 1

    invalid = ConfigurationService.defaults()
    invalid["evaluation"]["efficiency_warn_threshold"] = 0.8
    invalid["evaluation"]["efficiency_pass_threshold"] = 0.7
    with pytest.raises(ValidationError) as caught:
        ConfigurationService.validate_document(invalid)
    assert "evaluation.efficiency_warn_threshold" in caught.value.message_dict

    invalid = ConfigurationService.defaults()
    invalid["ui"]["saturation_warning_threshold"] = 0.9
    invalid["ui"]["saturation_critical_threshold"] = 0.8
    with pytest.raises(ValidationError) as caught:
        ConfigurationService.validate_document(invalid)
    assert "ui.saturation_warning_threshold" in caught.value.message_dict


NUMERIC_BOUNDS = (
    ("provider", "max_tokens", 1, 1_000_000, True),
    ("provider", "temperature", 0, 2, False),
    ("provider", "timeout_seconds", 1, 600, True),
    ("provider", "max_retries", 0, 20, True),
    ("provider", "retry_backoff_seconds", 0, 60, False),
    ("provider", "circuit_failure_threshold", 1, 100, True),
    ("provider", "circuit_reset_seconds", 1, 3600, True),
    ("runner", "maximum_messages", 1, 10_000, True),
    ("registry", "key_maximum_length", 1, 255, True),
    ("agent", "transition_key_maximum_length", 16, 1024, True),
    ("agent", "execution_idempotency_key_maximum_length", 16, 1024, True),
    ("agent", "search_maximum_length", 1, 4096, True),
    ("agent", "transition_reason_maximum_length", 1, 4096, True),
    ("agent", "error_code_maximum_length", 1, 255, True),
    ("schedule", "default_priority", -100, 100, True),
    ("schedule", "priority_minimum", -100, 100, True),
    ("schedule", "priority_maximum", -100, 100, True),
    ("schedule", "default_maximum_retries", 0, 65535, True),
    ("schedule", "maximum_retries_limit", 0, 65535, True),
    ("schedule", "dispatch_batch_minimum", 1, 1000, True),
    ("schedule", "dispatch_batch_maximum", 1, 1000, True),
    ("health", "cache_probe_timeout_seconds", 1, 300, True),
    ("health", "minimum_rls_table_count", 1, 1000, True),
    ("health", "outbox_stale_minutes", 1, 1440, True),
    ("evaluation", "quality_pass_threshold", 0, 1, False),
    ("evaluation", "quality_warn_threshold", 0, 1, False),
    ("evaluation", "hallucination_pass_threshold", 0, 1, False),
    ("evaluation", "hallucination_warn_threshold", 0, 1, False),
    ("evaluation", "max_token_fallback", 1, 1_000_000, True),
    ("evaluation", "characters_per_estimated_token", 1, 20, True),
    ("evaluation", "minimum_useful_output_length", 0, 10_000, True),
    ("evaluation", "short_output_penalty", 0, 1, False),
    ("evaluation", "efficiency_pass_threshold", 0, 1, False),
    ("evaluation", "efficiency_warn_threshold", 0, 1, False),
    ("secret", "rotation_interval_minimum_days", 1, 3650, True),
    ("ui", "agent_page_size", 1, 100, True),
    ("ui", "execution_page_size", 1, 100, True),
    ("ui", "execution_poll_interval_ms", 1000, 300_000, True),
    ("ui", "approval_page_size", 1, 100, True),
    ("ui", "approval_poll_interval_ms", 1000, 300_000, True),
    ("ui", "schedule_page_size", 1, 100, True),
    ("ui", "selection_page_size", 1, 100, True),
    ("ui", "usage_page_size", 1, 100, True),
    ("ui", "summary_page_size", 1, 100, True),
    ("ui", "health_poll_interval_ms", 5_000, 300_000, True),
    ("ui", "saturation_warning_threshold", 0, 1, False),
    ("ui", "saturation_critical_threshold", 0, 1, False),
)

# Fields whose boundary participates in a cross-field ordering check (tested
# separately in test_configuration_accepts_inclusive_threshold_boundaries_and_rejects_order_inversions
# and in test_configuration_rejects_weakened_runtime_guards_and_duplicate_navigation),
# so pinning them individually to their own extreme here would trip the *other*
# check first and mask the exact boundary under test.
_ORDER_CONSTRAINED = {
    ("schedule", "default_priority"),
    ("schedule", "priority_minimum"),
    ("schedule", "priority_maximum"),
    ("schedule", "default_maximum_retries"),
    ("schedule", "maximum_retries_limit"),
    ("schedule", "dispatch_batch_minimum"),
    ("schedule", "dispatch_batch_maximum"),
    ("evaluation", "quality_pass_threshold"),
    ("evaluation", "quality_warn_threshold"),
    ("evaluation", "hallucination_pass_threshold"),
    ("evaluation", "hallucination_warn_threshold"),
    ("evaluation", "efficiency_pass_threshold"),
    ("evaluation", "efficiency_warn_threshold"),
    ("ui", "saturation_warning_threshold"),
    ("ui", "saturation_critical_threshold"),
}


@pytest.mark.parametrize("section,key,minimum,maximum,integer", NUMERIC_BOUNDS)
def test_numeric_bound_rejects_values_just_outside_the_configured_range(section, key, minimum, maximum, integer):
    step = 1 if integer else 0.01
    below = ConfigurationService.defaults()
    below[section][key] = minimum - step
    with pytest.raises(ValidationError) as caught_below:
        ConfigurationService.validate_document(below)
    assert f"{section}.{key}" in caught_below.value.message_dict

    above = ConfigurationService.defaults()
    above[section][key] = maximum + step
    with pytest.raises(ValidationError) as caught_above:
        ConfigurationService.validate_document(above)
    assert f"{section}.{key}" in caught_above.value.message_dict

    if integer:
        fractional = ConfigurationService.defaults()
        fractional[section][key] = minimum + 0.5
        with pytest.raises(ValidationError) as caught_fraction:
            ConfigurationService.validate_document(fractional)
        assert f"{section}.{key}" in caught_fraction.value.message_dict


@pytest.mark.parametrize(
    "section,key,minimum,maximum,integer",
    [bound for bound in NUMERIC_BOUNDS if (bound[0], bound[1]) not in _ORDER_CONSTRAINED],
)
def test_numeric_bound_accepts_the_exact_configured_boundaries(section, key, minimum, maximum, integer):
    at_minimum = ConfigurationService.defaults()
    at_minimum[section][key] = minimum
    validated_min = ConfigurationService.validate_document(at_minimum)
    assert validated_min[section][key] == minimum

    at_maximum = ConfigurationService.defaults()
    at_maximum[section][key] = maximum
    validated_max = ConfigurationService.validate_document(at_maximum)
    assert validated_max[section][key] == maximum


def test_configuration_versions_reports_exact_invalid_tenant_field() -> None:
    with pytest.raises(ValidationError) as caught:
        ConfigurationService.versions("not-a-uuid")  # type: ignore[arg-type]
    assert caught.value.message_dict == {"tenant_id": ["Must be a valid UUID."]}


@pytest.mark.django_db
def test_configuration_api_is_typed_and_tenant_scoped(
    authenticated_tenant_a_client,
    tenant_a,
    monkeypatch,
):
    monkeypatch.setattr(RequiresAccess, "has_permission", lambda self, request, view: True)
    monkeypatch.setattr(RequiresAccess, "has_object_permission", lambda self, request, view, obj: True)
    response = authenticated_tenant_a_client.get("/api/v2/ai-agent-management/configuration/?environment=production")
    assert response.status_code == status.HTTP_200_OK
    current = response.json()["data"]
    document = current["document"]
    document["ui"]["agent_page_size"] = 50
    update = authenticated_tenant_a_client.post(
        "/api/v2/ai-agent-management/configuration/",
        {
            "environment": "production",
            "expected_version": current["version"],
            "document": document,
        },
        format="json",
    )
    assert update.status_code == status.HTTP_200_OK
    assert update.json()["data"]["document"]["ui"]["agent_page_size"] == 50
    assert AgentManagementConfiguration.objects.filter(tenant_id=tenant_a.id).count() == 1


@pytest.mark.django_db
def test_every_registered_tenant_queryset_is_empty_without_tenant_context():
    request = SimpleNamespace(user=AnonymousUser(), query_params={})
    for prefix, viewset_type, _basename in router.registry:
        viewset = viewset_type()
        viewset.request = request
        viewset.action = "list"
        queryset = viewset.get_queryset()
        assert not queryset.exists(), prefix
