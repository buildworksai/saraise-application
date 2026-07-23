"""Tenant CRM configuration defaults and read-only runtime access.

The immutable defaults in this module are the bootstrap configuration document,
not scattered business behaviour.  Tenant overrides are persisted by
``CRMConfigurationService`` and every consumer resolves through this module.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import UUID

from django.apps import apps

DEFAULT_CRM_CONFIGURATION: dict[str, Any] = {
    "field_limits": {
        "phone_min_digits": 7,
        "phone_max_digits": 15,
        "lead_name": 100,
        "lead_email": 255,
        "lead_phone": 50,
        "lead_status": 20,
        "account_name": 255,
        "account_industry": 100,
        "account_postal_code": 20,
        "account_country": 2,
        "contact_name": 100,
        "contact_email": 255,
        "contact_phone": 50,
        "opportunity_name": 255,
        "opportunity_amount_digits": 15,
        "opportunity_amount_decimals": 2,
        "opportunity_currency": 3,
        "opportunity_stage": 30,
        "opportunity_status": 10,
        "activity_subject": 500,
        "activity_outcome": 100,
        "activity_external_id": 255,
        "actor_id": 255,
        "correlation_id": 64,
        "async_idempotency_key": 180,
        "domain_override_reason": 1000,
        "transition_reason": 2000,
        "loss_reason": 4000,
        "provider_id": 160,
        "provider_evidence_string": 500,
    },
    "lead": {
        "default_score": 0,
        "default_grade": "D",
        "default_score_source": "rules",
        "default_status": "new",
        "score_min": 0,
        "score_max": 100,
        "grade_thresholds": {"A": 80, "B": 60, "C": 40, "D": 0},
        "qualification_threshold": 70,
        "field_score_weights": {"company": 20, "email": 15, "phone": 10, "title": 10},
        "source_score_weights": {"referral": 25, "event": 20, "web": 15, "social": 10, "api": 5},
        "terminal_states": ["converted", "lost"],
        "transitions": {
            "contact": {"from": ["new"], "to": "contacted"},
            "qualify": {"from": ["new", "contacted"], "to": "qualified"},
            "disqualify": {"from": ["new", "contacted", "qualified"], "to": "lost"},
            "convert": {"from": ["qualified"], "to": "converted"},
        },
    },
    "account": {
        "default_type": "prospect",
        "allowed_types": ["prospect", "customer", "partner"],
        "hierarchy_max_depth": 3,
    },
    "contact": {
        "default_engagement_score": 0,
        "engagement_score_min": 0,
        "engagement_score_max": 100,
        "enforce_account_email_domain": True,
        "engagement_lookback_days": 90,
        "engagement_points_per_interaction": 10,
    },
    "opportunity": {
        "default_currency": "USD",
        "default_probability": 10,
        "default_stage": "prospecting",
        "default_status": "open",
        "probability_min": 0,
        "probability_max": 100,
        "minimum_amount": "0.01",
        "closed_won_probability": 100,
        "closed_lost_probability": 0,
        "terminal_states": ["closed_won", "closed_lost"],
        "transitions": {
            "advance_to_qualification": {"from": ["prospecting"], "to": "qualification"},
            "advance_to_needs_analysis": {"from": ["qualification"], "to": "needs_analysis"},
            "advance_to_proposal": {"from": ["needs_analysis"], "to": "proposal"},
            "advance_to_negotiation": {"from": ["proposal"], "to": "negotiation"},
            "close_won": {
                "from": ["prospecting", "qualification", "needs_analysis", "proposal", "negotiation"],
                "to": "closed_won",
            },
            "close_lost": {
                "from": ["prospecting", "qualification", "needs_analysis", "proposal", "negotiation"],
                "to": "closed_lost",
            },
            "reopen_to_prospecting": {
                "from": ["qualification", "needs_analysis", "proposal", "negotiation"],
                "to": "prospecting",
            },
            "reopen_to_qualification": {
                "from": ["needs_analysis", "proposal", "negotiation"],
                "to": "qualification",
            },
            "reopen_to_needs_analysis": {
                "from": ["proposal", "negotiation"],
                "to": "needs_analysis",
            },
            "reopen_to_proposal": {"from": ["negotiation"], "to": "proposal"},
        },
        "stages": [
            {"name": "prospecting", "probability": 10, "semantic_token": "muted"},
            {"name": "qualification", "probability": 20, "semantic_token": "info"},
            {"name": "needs_analysis", "probability": 40, "semantic_token": "warning"},
            {"name": "proposal", "probability": 60, "semantic_token": "accent"},
            {"name": "negotiation", "probability": 80, "semantic_token": "positive"},
            {"name": "closed_won", "probability": 100, "semantic_token": "success"},
            {"name": "closed_lost", "probability": 0, "semantic_token": "danger"},
        ],
    },
    "activity": {"default_type": "task", "default_related_type": "Lead", "require_future_task_due_date": True},
    "hierarchy": {"max_nodes": 500, "max_children": 100, "page_size": 100},
    "forecast": {"default_period_days": 90, "minimum_period_days": 1, "maximum_period_days": 365},
    "providers": {
        "lead_scoring": None,
        "revenue_prediction": None,
        "score_min": 0,
        "score_max": 100,
        "confidence_min": "0",
        "confidence_max": "1",
        "maximum_evidence_factors": 50,
        "extension_schema_version": "1.0",
        "extension_priority_default": 100,
        "extension_priority_min": 0,
        "extension_priority_max": 10000,
        "retry_attempts": 3,
        "backoff_base_seconds": "0.1",
        "backoff_max_seconds": "2",
        "backoff_jitter_seconds": "0.1",
    },
    "jobs": {"stale_deal_days": 14, "stale_deal_min_days": 1, "stale_deal_max_days": 365, "iterator_chunk_size": 200},
    "pagination": {"default_page_size": 25, "maximum_page_size": 100},
    "api": {"quota_cost": 1},
    "conversion": {
        "create_account_by_default": True,
        "close_date_offset_days": 0,
        "use_current_version": True,
        "transition_key_prefix": "legacy-convert",
    },
    "health": {"cache_timeout_seconds": 10},
    "ui": {
        "score_bands": [
            {"minimum": 80, "grade": "A", "semantic_token": "success"},
            {"minimum": 60, "grade": "B", "semantic_token": "info"},
            {"minimum": 40, "grade": "C", "semantic_token": "warning"},
            {"minimum": 0, "grade": "D", "semantic_token": "danger"},
        ],
        "hierarchy_auto_expand_levels": 2,
        "hierarchy_indentation_pixels": 24,
        "minimum_pipeline_bar_percent": 2,
        "saved_page_size": 25,
        "dashboard_forecast_period_days": 90,
        "prediction_retry_enabled": True,
        "stale_deal_page_size": 25,
        "pipeline_fetch_limit": 100,
    },
}

DEFAULT_FEATURE_FLAGS: dict[str, bool] = {
    "async_lead_scoring": True,
    "revenue_prediction": True,
    "stale_deal_detection": True,
}
DEFAULT_ROLLOUT: dict[str, Any] = {"enabled": True, "percentage": 100, "roles": [], "cohorts": []}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Return a detached recursive merge without mutating either input."""

    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def effective_configuration(tenant_id: UUID, environment: str = "production") -> dict[str, Any]:
    """Resolve tenant configuration, falling back only to the validated bootstrap document."""

    try:
        model = apps.get_model("crm", "CRMConfiguration")
        row = model.objects.filter(tenant_id=tenant_id, environment=environment).only("document").first()
    except LookupError:
        row = None
    return deep_merge(DEFAULT_CRM_CONFIGURATION, row.document if row is not None else {})


def configuration_value(tenant_id: UUID, path: str, environment: str = "production") -> Any:
    value: Any = effective_configuration(tenant_id, environment)
    for segment in path.split("."):
        value = value[segment]
    return value
