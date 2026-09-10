"""Branch/boundary coverage for src/modules/crm/services.py aimed at closing
mutation-testing gaps left by the higher-level contract tests in
test_services.py and test_configuration.py.

Every test here targets a specific comparison, boundary, or conditional branch
in services.py (mostly ``CRMConfigurationService.validate_document`` and its
helpers, which account for the bulk of the module's cyclomatic complexity) so
that an injected mutant (``<`` -> ``<=``, ``and`` -> ``or``, boundary off-by-one,
condition negation, ...) is provably killed by an assertion, not merely
executed.
"""

from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from src.modules.crm import services
from src.modules.crm.configuration import DEFAULT_CRM_CONFIGURATION, DEFAULT_FEATURE_FLAGS, deep_merge
from src.modules.crm.integrations import CRMIntegrationError
from src.modules.crm.models import (
    Account,
    AccountType,
    ActivityType,
    LeadStatus,
    OpportunityStage,
    OpportunityStatus,
    RelatedToType,
)
from src.modules.crm.services import (
    AccountService,
    ActivityService,
    ContactService,
    CRMConfigurationService,
    CRMIdempotencyService,
    CRMServiceError,
    ForecastingService,
    IntegrationService,
    LeadService,
    OpportunityService,
    StaleVersionError,
    _actor,
    _assign,
    _correlation,
    _validate_version,
)

from .factories import AccountFactory, ContactFactory, LeadFactory, OpportunityFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant_id():
    return uuid.uuid4()


@pytest.fixture
def actor_id():
    return uuid.uuid4()


def _doc(overrides):
    return deep_merge(DEFAULT_CRM_CONFIGURATION, overrides)


def _valid_document():
    return deepcopy(DEFAULT_CRM_CONFIGURATION)


# ---------------------------------------------------------------------------
# CRMConfigurationService._environment / _object / _integer
# ---------------------------------------------------------------------------


def test_environment_defaults_normalizes_and_rejects_unknown():
    assert CRMConfigurationService._environment(None) == "production"
    assert CRMConfigurationService._environment("  Staging  ") == "staging"
    with pytest.raises(CRMServiceError, match="Environment is not allowed"):
        CRMConfigurationService._environment("nonexistent-env")


def test_object_requires_dict():
    assert CRMConfigurationService._object({"a": 1}, "field") == {"a": 1}
    with pytest.raises(CRMServiceError, match="must be an object"):
        CRMConfigurationService._object([1, 2], "field")
    with pytest.raises(CRMServiceError, match="must be an object"):
        CRMConfigurationService._object(None, "field")


@pytest.mark.parametrize("value", [True, False, "5", 3.5, None])
def test_integer_rejects_non_plain_int(value):
    with pytest.raises(CRMServiceError, match="must be an integer"):
        CRMConfigurationService._integer(value, "field", 0, 10)


def test_integer_boundaries_are_inclusive():
    assert CRMConfigurationService._integer(0, "field", 0, 10) == 0
    assert CRMConfigurationService._integer(10, "field", 0, 10) == 10
    with pytest.raises(CRMServiceError, match="must be an integer"):
        CRMConfigurationService._integer(-1, "field", 0, 10)
    with pytest.raises(CRMServiceError, match="must be an integer"):
        CRMConfigurationService._integer(11, "field", 0, 10)


def test_reject_unknown_flags_top_level_and_nested_fields():
    with pytest.raises(CRMServiceError, match="unsupported fields"):
        CRMConfigurationService._reject_unknown({"ghost": 1}, {"real": 1}, "document")
    with pytest.raises(CRMServiceError, match="unsupported fields"):
        CRMConfigurationService._reject_unknown({"real": {"ghost": 1}}, {"real": {"known": 1}}, "document")
    # Recursion only descends when both sides are dicts; a non-dict override of
    # a dict template field is accepted here (validated elsewhere as _object).
    CRMConfigurationService._reject_unknown({"real": "scalar"}, {"real": {"known": 1}}, "document")


# ---------------------------------------------------------------------------
# validate_document: field_limits / phone digits
# ---------------------------------------------------------------------------


def test_phone_digit_bounds_reject_min_exceeding_max():
    # phone_min_digits is itself capped at its own default (7) by the physical
    # field-limit loop above this check, so both values must stay <= their
    # own physical ceilings (7 and 15 respectively) to reach this branch.
    with pytest.raises(CRMServiceError, match="Minimum phone digits cannot exceed"):
        CRMConfigurationService.validate_document(
            _doc({"field_limits": {"phone_min_digits": 7, "phone_max_digits": 6}})
        )
    # Equal is allowed (boundary, not strictly less-than).
    CRMConfigurationService.validate_document(_doc({"field_limits": {"phone_min_digits": 7, "phone_max_digits": 7}}))


def test_field_limit_out_of_range_is_rejected():
    physical_max = DEFAULT_CRM_CONFIGURATION["field_limits"]["lead_name"]
    with pytest.raises(CRMServiceError, match="field_limits.lead_name"):
        CRMConfigurationService.validate_document(_doc({"field_limits": {"lead_name": physical_max + 1}}))
    with pytest.raises(CRMServiceError, match="field_limits.lead_name"):
        CRMConfigurationService.validate_document(_doc({"field_limits": {"lead_name": 0}}))
    # Exactly the physical ceiling is allowed.
    CRMConfigurationService.validate_document(_doc({"field_limits": {"lead_name": physical_max}}))


# ---------------------------------------------------------------------------
# validate_document: lead section
# ---------------------------------------------------------------------------


def test_lead_score_bounds_are_enforced_and_chained():
    with pytest.raises(CRMServiceError, match="lead.score_min"):
        CRMConfigurationService.validate_document(_doc({"lead": {"score_min": -1}}))
    with pytest.raises(CRMServiceError, match="lead.score_max"):
        CRMConfigurationService.validate_document(_doc({"lead": {"score_min": 50, "score_max": 49}}))
    with pytest.raises(CRMServiceError, match="lead.default_score"):
        CRMConfigurationService.validate_document(
            _doc({"lead": {"score_min": 10, "score_max": 20, "default_score": 9}})
        )
    with pytest.raises(CRMServiceError, match="lead.default_score"):
        CRMConfigurationService.validate_document(
            _doc({"lead": {"score_min": 10, "score_max": 20, "default_score": 21}})
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"lead": {"default_grade": "Z"}},
        {"lead": {"default_score_source": "unknown"}},
        {"lead": {"default_status": "unknown"}},
    ],
)
def test_lead_defaults_enum_membership_each_checked_independently(overrides):
    with pytest.raises(CRMServiceError, match="Lead defaults contain an unsupported value"):
        CRMConfigurationService.validate_document(_doc(overrides))


def test_lead_qualification_threshold_bounds():
    with pytest.raises(CRMServiceError, match="lead.qualification_threshold"):
        CRMConfigurationService.validate_document(_doc({"lead": {"qualification_threshold": -1}}))
    with pytest.raises(CRMServiceError, match="lead.qualification_threshold"):
        CRMConfigurationService.validate_document(_doc({"lead": {"qualification_threshold": 101}}))
    CRMConfigurationService.validate_document(_doc({"lead": {"qualification_threshold": 0}}))
    CRMConfigurationService.validate_document(_doc({"lead": {"qualification_threshold": 100}}))


def test_grade_thresholds_must_define_exactly_a_b_c_d(monkeypatch):
    # validate_document always re-merges its input against
    # DEFAULT_CRM_CONFIGURATION internally (`deep_merge(DEFAULT, supplied)`),
    # and dict-valued fields merge key-by-key -- so a key missing from the
    # caller's payload is always refilled from the default template.  The
    # only way this branch is reachable is the real-world scenario it guards:
    # the *template itself* (schema evolution) losing a key that a persisted
    # tenant document still lacks too, so we simulate that directly.
    patched_default = deepcopy(DEFAULT_CRM_CONFIGURATION)
    del patched_default["lead"]["grade_thresholds"]["D"]
    monkeypatch.setattr(services, "DEFAULT_CRM_CONFIGURATION", patched_default)
    with pytest.raises(CRMServiceError, match="must define A, B, C, and D"):
        CRMConfigurationService.validate_document(deepcopy(patched_default))


def test_grade_thresholds_must_strictly_descend_to_score_minimum():
    with pytest.raises(CRMServiceError, match="must strictly descend"):
        CRMConfigurationService.validate_document(
            _doc({"lead": {"grade_thresholds": {"A": 80, "B": 80, "C": 40, "D": 0}}})
        )
    with pytest.raises(CRMServiceError, match="must strictly descend"):
        CRMConfigurationService.validate_document(
            _doc({"lead": {"grade_thresholds": {"A": 60, "B": 80, "C": 40, "D": 0}}})
        )
    with pytest.raises(CRMServiceError, match="must strictly descend"):
        CRMConfigurationService.validate_document(
            _doc({"lead": {"grade_thresholds": {"A": 80, "B": 60, "C": 40, "D": 5}}})
        )


def test_default_grade_must_match_default_score_and_thresholds():
    with pytest.raises(CRMServiceError, match="Default lead grade must match"):
        CRMConfigurationService.validate_document(_doc({"lead": {"default_score": 90, "default_grade": "B"}}))
    # Score of exactly a threshold boundary maps to that grade (>=).
    document = CRMConfigurationService.validate_document(_doc({"lead": {"default_score": 60, "default_grade": "B"}}))
    assert document["lead"]["default_grade"] == "B"


@pytest.mark.parametrize(
    ("section", "existing_key"),
    [("field_score_weights", "company"), ("source_score_weights", "referral")],
)
def test_lead_score_weight_sections_reject_bool_and_out_of_range_overrides(section, existing_key):
    # deep_merge only adds/overrides dict keys, never removes them, so an
    # empty-dict override can never make `weights` falsy through the public
    # API -- the `not weights` half of the guard is unreachable defensive
    # code.  What IS reachable is overriding one already-known weight with an
    # out-of-contract value, which is what a real tenant payload would send.
    with pytest.raises(CRMServiceError, match=f"lead.{section}"):
        CRMConfigurationService.validate_document(_doc({"lead": {section: {existing_key: True}}}))
    with pytest.raises(CRMServiceError, match=f"lead.{section}"):
        CRMConfigurationService.validate_document(_doc({"lead": {section: {existing_key: -1}}}))
    with pytest.raises(CRMServiceError, match=f"lead.{section}"):
        CRMConfigurationService.validate_document(_doc({"lead": {section: {existing_key: 101}}}))
    document = CRMConfigurationService.validate_document(_doc({"lead": {section: {existing_key: 0}}}))
    assert document["lead"][section][existing_key] == 0


# ---------------------------------------------------------------------------
# validate_document / _validate_transition_policy (lead + opportunity share it)
# ---------------------------------------------------------------------------


def test_transition_policy_terminal_states_must_be_list_and_cover_required_states():
    with pytest.raises(CRMServiceError, match="lead.terminal_states"):
        CRMConfigurationService.validate_document(_doc({"lead": {"terminal_states": "converted,lost"}}))
    with pytest.raises(CRMServiceError, match="lead.terminal_states"):
        CRMConfigurationService.validate_document(_doc({"lead": {"terminal_states": ["lost"]}}))
    with pytest.raises(CRMServiceError, match="lead.terminal_states"):
        CRMConfigurationService.validate_document(
            _doc({"lead": {"terminal_states": ["converted", "lost", "not-a-real-state"]}})
        )
    # Extra *valid* states beyond the required ones are fine (a narrowing tenant policy).
    CRMConfigurationService.validate_document(_doc({"lead": {"terminal_states": ["converted", "lost", "qualified"]}}))


def _lead_policy(**transitions_override):
    """A minimal, valid `lead` configuration section for _validate_transition_policy."""

    lead = deepcopy(DEFAULT_CRM_CONFIGURATION["lead"])
    lead["transitions"] = deep_merge(lead["transitions"], transitions_override)
    return lead


# The public entry point (validate_document) always re-merges its argument
# against DEFAULT_CRM_CONFIGURATION, so a *missing* transitions key can never
# survive to reach _validate_transition_policy from outside (see the
# grade_thresholds test above for the same structural reason). Exercise the
# classmethod directly with a hand-built `configuration` mapping instead --
# this is the actual unit under test and every one of its branches is
# reachable that way.
_TEMPLATE = DEFAULT_CRM_CONFIGURATION["lead"]["transitions"]
_STATES = set(LeadStatus.values)
_REQUIRED_TERMINAL = {LeadStatus.CONVERTED, LeadStatus.LOST}


def _validate_lead_policy(lead):
    CRMConfigurationService._validate_transition_policy(
        lead,
        section="lead",
        states=_STATES,
        required_terminal_states=_REQUIRED_TERMINAL,
        template=_TEMPLATE,
    )


def test_transition_policy_terminal_states_direct_validation():
    lead = deepcopy(DEFAULT_CRM_CONFIGURATION["lead"])
    lead["terminal_states"] = "converted,lost"
    with pytest.raises(CRMServiceError, match="lead.terminal_states"):
        _validate_lead_policy(lead)

    lead = deepcopy(DEFAULT_CRM_CONFIGURATION["lead"])
    lead["terminal_states"] = ["lost"]
    with pytest.raises(CRMServiceError, match="lead.terminal_states"):
        _validate_lead_policy(lead)

    lead = deepcopy(DEFAULT_CRM_CONFIGURATION["lead"])
    lead["terminal_states"] = ["converted", "lost", "not-a-real-state"]
    with pytest.raises(CRMServiceError, match="lead.terminal_states"):
        _validate_lead_policy(lead)


def test_transition_policy_transitions_must_cover_every_template_command_exactly():
    narrowed = deepcopy(DEFAULT_CRM_CONFIGURATION["lead"])
    del narrowed["transitions"]["convert"]
    with pytest.raises(CRMServiceError, match="lead.transitions must define every"):
        _validate_lead_policy(narrowed)

    widened = deepcopy(DEFAULT_CRM_CONFIGURATION["lead"])
    widened["transitions"]["extra_command"] = {"from": ["new"], "to": "contacted"}
    with pytest.raises(CRMServiceError, match="lead.transitions must define every"):
        _validate_lead_policy(widened)


def test_transition_policy_command_target_is_fixed():
    lead = _lead_policy(contact={"from": ["new"], "to": "qualified"})
    with pytest.raises(CRMServiceError, match="unsupported target"):
        _validate_lead_policy(lead)

    lead = deepcopy(DEFAULT_CRM_CONFIGURATION["lead"])
    lead["transitions"]["contact"] = {"from": ["new"], "to": "contacted", "extra": 1}
    with pytest.raises(CRMServiceError, match="unsupported target"):
        _validate_lead_policy(lead)


def test_transition_policy_sources_must_be_a_deduplicated_subset_of_template():
    lead = _lead_policy(contact={"from": "new", "to": "contacted"})
    with pytest.raises(CRMServiceError, match="unsupported source"):
        _validate_lead_policy(lead)

    lead = _lead_policy(contact={"from": ["new", "new"], "to": "contacted"})
    with pytest.raises(CRMServiceError, match="unsupported source"):
        _validate_lead_policy(lead)

    lead = _lead_policy(contact={"from": ["converted"], "to": "contacted"})
    with pytest.raises(CRMServiceError, match="unsupported source"):
        _validate_lead_policy(lead)

    # A strict subset of the template's sources is a legitimate narrowing policy.
    lead = _lead_policy(qualify={"from": ["new"], "to": "qualified"})
    _validate_lead_policy(lead)  # no raise


# ---------------------------------------------------------------------------
# validate_document: account section
# ---------------------------------------------------------------------------


def test_account_allowed_types_must_be_a_nonempty_list_of_known_values():
    with pytest.raises(CRMServiceError, match="Account types contain an unsupported value"):
        CRMConfigurationService.validate_document(_doc({"account": {"allowed_types": "prospect"}}))
    with pytest.raises(CRMServiceError, match="Account types contain an unsupported value"):
        CRMConfigurationService.validate_document(_doc({"account": {"allowed_types": []}}))
    with pytest.raises(CRMServiceError, match="Account types contain an unsupported value"):
        CRMConfigurationService.validate_document(_doc({"account": {"allowed_types": ["not-a-type"]}}))


def test_account_default_type_must_be_allowed():
    with pytest.raises(CRMServiceError, match="Default account type must be allowed"):
        CRMConfigurationService.validate_document(
            _doc({"account": {"allowed_types": ["prospect"], "default_type": "customer"}})
        )


def test_account_hierarchy_max_depth_bounds():
    with pytest.raises(CRMServiceError, match="account.hierarchy_max_depth"):
        CRMConfigurationService.validate_document(_doc({"account": {"hierarchy_max_depth": 0}}))
    with pytest.raises(CRMServiceError, match="account.hierarchy_max_depth"):
        CRMConfigurationService.validate_document(_doc({"account": {"hierarchy_max_depth": 21}}))


# ---------------------------------------------------------------------------
# validate_document: contact section
# ---------------------------------------------------------------------------


def test_contact_engagement_score_bounds_are_chained():
    with pytest.raises(CRMServiceError, match="contact.engagement_score_min"):
        CRMConfigurationService.validate_document(_doc({"contact": {"engagement_score_min": -1}}))
    with pytest.raises(CRMServiceError, match="contact.engagement_score_max"):
        CRMConfigurationService.validate_document(
            _doc({"contact": {"engagement_score_min": 50, "engagement_score_max": 49}})
        )
    with pytest.raises(CRMServiceError, match="contact.default_engagement_score"):
        CRMConfigurationService.validate_document(
            _doc(
                {
                    "contact": {
                        "engagement_score_min": 10,
                        "engagement_score_max": 20,
                        "default_engagement_score": 9,
                    }
                }
            )
        )


def test_contact_engagement_lookback_and_points_bounds():
    with pytest.raises(CRMServiceError, match="contact.engagement_lookback_days"):
        CRMConfigurationService.validate_document(_doc({"contact": {"engagement_lookback_days": 0}}))
    with pytest.raises(CRMServiceError, match="contact.engagement_lookback_days"):
        CRMConfigurationService.validate_document(_doc({"contact": {"engagement_lookback_days": 3651}}))
    with pytest.raises(CRMServiceError, match="contact.engagement_points_per_interaction"):
        CRMConfigurationService.validate_document(_doc({"contact": {"engagement_points_per_interaction": 0}}))
    with pytest.raises(CRMServiceError, match="contact.engagement_points_per_interaction"):
        CRMConfigurationService.validate_document(_doc({"contact": {"engagement_points_per_interaction": 101}}))


def test_contact_domain_enforcement_must_be_boolean():
    with pytest.raises(CRMServiceError, match="domain enforcement must be boolean"):
        CRMConfigurationService.validate_document(_doc({"contact": {"enforce_account_email_domain": "yes"}}))


# ---------------------------------------------------------------------------
# validate_document: opportunity section
# ---------------------------------------------------------------------------


def test_opportunity_probability_bounds_are_chained():
    with pytest.raises(CRMServiceError, match="opportunity.probability_min"):
        CRMConfigurationService.validate_document(_doc({"opportunity": {"probability_min": -1}}))
    with pytest.raises(CRMServiceError, match="opportunity.probability_max"):
        CRMConfigurationService.validate_document(_doc({"opportunity": {"probability_min": 50, "probability_max": 49}}))
    with pytest.raises(CRMServiceError, match="opportunity.default_probability"):
        CRMConfigurationService.validate_document(
            _doc({"opportunity": {"probability_min": 10, "probability_max": 20, "default_probability": 9}})
        )


def test_opportunity_stages_must_define_every_stage_exactly_once_with_no_duplicates():
    stages = deepcopy(DEFAULT_CRM_CONFIGURATION["opportunity"]["stages"])
    missing = [item for item in stages if item["name"] != OpportunityStage.CLOSED_LOST]
    with pytest.raises(CRMServiceError, match="must define every supported stage once"):
        CRMConfigurationService.validate_document(_doc({"opportunity": {"stages": missing}}))
    with pytest.raises(CRMServiceError, match="must define every supported stage once"):
        CRMConfigurationService.validate_document(_doc({"opportunity": {"stages": "not-a-list"}}))
    duplicated = stages + [deepcopy(stages[0])]
    with pytest.raises(CRMServiceError, match="must not contain duplicates"):
        CRMConfigurationService.validate_document(_doc({"opportunity": {"stages": duplicated}}))


def test_opportunity_stage_semantic_token_and_probability_are_validated_per_stage():
    stages = deepcopy(DEFAULT_CRM_CONFIGURATION["opportunity"]["stages"])
    stages[0]["semantic_token"] = "not-a-real-token"
    with pytest.raises(CRMServiceError, match="semantic token is invalid"):
        CRMConfigurationService.validate_document(_doc({"opportunity": {"stages": stages}}))

    stages = deepcopy(DEFAULT_CRM_CONFIGURATION["opportunity"]["stages"])
    stages[0]["probability"] = 101
    with pytest.raises(CRMServiceError, match="opportunity.stages"):
        CRMConfigurationService.validate_document(_doc({"opportunity": {"stages": stages}}))


def test_opportunity_default_stage_and_status_membership():
    with pytest.raises(CRMServiceError, match="Default opportunity stage is invalid"):
        CRMConfigurationService.validate_document(_doc({"opportunity": {"default_stage": "not-a-stage"}}))
    with pytest.raises(CRMServiceError, match="Default opportunity status is invalid"):
        CRMConfigurationService.validate_document(_doc({"opportunity": {"default_status": "not-a-status"}}))


def test_opportunity_default_currency_must_be_iso_4217():
    with pytest.raises(CRMServiceError, match="allowed ISO-4217 code"):
        CRMConfigurationService.validate_document(_doc({"opportunity": {"default_currency": "XXX_NOT_REAL"}}))
    with pytest.raises(CRMServiceError, match="allowed ISO-4217 code"):
        CRMConfigurationService.validate_document(_doc({"opportunity": {"default_currency": 840}}))


def test_opportunity_minimum_amount_must_be_a_positive_decimal():
    with pytest.raises(CRMServiceError, match="Minimum opportunity amount is invalid"):
        CRMConfigurationService.validate_document(_doc({"opportunity": {"minimum_amount": "not-a-number"}}))
    with pytest.raises(CRMServiceError, match="must be positive"):
        CRMConfigurationService.validate_document(_doc({"opportunity": {"minimum_amount": "0"}}))
    with pytest.raises(CRMServiceError, match="must be positive"):
        CRMConfigurationService.validate_document(_doc({"opportunity": {"minimum_amount": "-1"}}))
    document = CRMConfigurationService.validate_document(_doc({"opportunity": {"minimum_amount": "0.01"}}))
    assert document["opportunity"]["minimum_amount"] == "0.01"


# ---------------------------------------------------------------------------
# validate_document: activity / hierarchy / forecast / jobs / providers /
# pagination / ui / api / health / conversion
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"activity": {"default_type": "not-a-type"}},
        {"activity": {"default_related_type": "NotARelation"}},
    ],
)
def test_activity_defaults_membership(overrides):
    with pytest.raises(CRMServiceError, match="Activity defaults are invalid"):
        CRMConfigurationService.validate_document(_doc(overrides))


def test_activity_require_future_task_due_date_must_be_boolean():
    with pytest.raises(CRMServiceError, match="Task due-date policy must be boolean"):
        CRMConfigurationService.validate_document(_doc({"activity": {"require_future_task_due_date": "yes"}}))


def test_hierarchy_bounds_and_page_size_ceiling_tracks_max_nodes():
    with pytest.raises(CRMServiceError, match="hierarchy.max_nodes"):
        CRMConfigurationService.validate_document(_doc({"hierarchy": {"max_nodes": 0}}))
    with pytest.raises(CRMServiceError, match="hierarchy.max_children"):
        CRMConfigurationService.validate_document(_doc({"hierarchy": {"max_children": 0}}))
    with pytest.raises(CRMServiceError, match="hierarchy.page_size"):
        CRMConfigurationService.validate_document(_doc({"hierarchy": {"max_nodes": 10, "page_size": 11}}))
    document = CRMConfigurationService.validate_document(_doc({"hierarchy": {"max_nodes": 10, "page_size": 10}}))
    assert document["hierarchy"]["page_size"] == 10


def test_forecast_period_bounds_are_chained():
    with pytest.raises(CRMServiceError, match="forecast.minimum_period_days"):
        CRMConfigurationService.validate_document(_doc({"forecast": {"minimum_period_days": 0}}))
    with pytest.raises(CRMServiceError, match="forecast.maximum_period_days"):
        CRMConfigurationService.validate_document(
            _doc({"forecast": {"minimum_period_days": 10, "maximum_period_days": 9}})
        )
    with pytest.raises(CRMServiceError, match="forecast.default_period_days"):
        CRMConfigurationService.validate_document(
            _doc({"forecast": {"minimum_period_days": 10, "maximum_period_days": 20, "default_period_days": 9}})
        )


def test_jobs_stale_deal_and_iterator_chunk_bounds():
    with pytest.raises(CRMServiceError, match="jobs.stale_deal_min_days"):
        CRMConfigurationService.validate_document(_doc({"jobs": {"stale_deal_min_days": 0}}))
    with pytest.raises(CRMServiceError, match="jobs.stale_deal_max_days"):
        CRMConfigurationService.validate_document(_doc({"jobs": {"stale_deal_min_days": 10, "stale_deal_max_days": 9}}))
    with pytest.raises(CRMServiceError, match="jobs.stale_deal_days"):
        CRMConfigurationService.validate_document(
            _doc({"jobs": {"stale_deal_min_days": 10, "stale_deal_max_days": 20, "stale_deal_days": 9}})
        )
    with pytest.raises(CRMServiceError, match="jobs.iterator_chunk_size"):
        CRMConfigurationService.validate_document(_doc({"jobs": {"iterator_chunk_size": 0}}))
    with pytest.raises(CRMServiceError, match="jobs.iterator_chunk_size"):
        CRMConfigurationService.validate_document(_doc({"jobs": {"iterator_chunk_size": 5001}}))


def test_providers_evidence_priority_schema_and_retry_bounds():
    with pytest.raises(CRMServiceError, match="providers.maximum_evidence_factors"):
        CRMConfigurationService.validate_document(_doc({"providers": {"maximum_evidence_factors": 0}}))
    with pytest.raises(CRMServiceError, match="providers.extension_priority_max"):
        CRMConfigurationService.validate_document(
            _doc({"providers": {"extension_priority_min": 50, "extension_priority_max": 49}})
        )
    with pytest.raises(CRMServiceError, match="providers.extension_priority_default"):
        CRMConfigurationService.validate_document(
            _doc(
                {
                    "providers": {
                        "extension_priority_min": 10,
                        "extension_priority_max": 20,
                        "extension_priority_default": 9,
                    }
                }
            )
        )
    with pytest.raises(CRMServiceError, match="Provider schema version is unsupported"):
        CRMConfigurationService.validate_document(_doc({"providers": {"extension_schema_version": "2.0"}}))
    with pytest.raises(CRMServiceError, match="providers.retry_attempts"):
        CRMConfigurationService.validate_document(_doc({"providers": {"retry_attempts": 0}}))
    with pytest.raises(CRMServiceError, match="providers.retry_attempts"):
        CRMConfigurationService.validate_document(_doc({"providers": {"retry_attempts": 9}}))


def test_providers_backoff_must_be_decimal_and_within_bounds():
    with pytest.raises(CRMServiceError, match="must be decimal strings"):
        CRMConfigurationService.validate_document(_doc({"providers": {"backoff_base_seconds": "not-a-number"}}))
    with pytest.raises(CRMServiceError, match="backoff bounds are invalid"):
        CRMConfigurationService.validate_document(
            _doc({"providers": {"backoff_base_seconds": "5", "backoff_max_seconds": "4"}})
        )
    with pytest.raises(CRMServiceError, match="backoff bounds are invalid"):
        CRMConfigurationService.validate_document(_doc({"providers": {"backoff_max_seconds": "31"}}))
    with pytest.raises(CRMServiceError, match="backoff bounds are invalid"):
        CRMConfigurationService.validate_document(_doc({"providers": {"backoff_base_seconds": "-1"}}))
    with pytest.raises(CRMServiceError, match="backoff jitter is invalid"):
        CRMConfigurationService.validate_document(
            _doc({"providers": {"backoff_max_seconds": "2", "backoff_jitter_seconds": "3"}})
        )
    with pytest.raises(CRMServiceError, match="backoff jitter is invalid"):
        CRMConfigurationService.validate_document(_doc({"providers": {"backoff_jitter_seconds": "-1"}}))
    # Exact boundary equalities are all legal (base == max == 30, jitter == max).
    document = CRMConfigurationService.validate_document(
        _doc(
            {
                "providers": {
                    "backoff_base_seconds": "30",
                    "backoff_max_seconds": "30",
                    "backoff_jitter_seconds": "30",
                }
            }
        )
    )
    assert document["providers"]["backoff_max_seconds"] == "30"


def test_pagination_bounds():
    with pytest.raises(CRMServiceError, match="pagination.maximum_page_size"):
        CRMConfigurationService.validate_document(_doc({"pagination": {"maximum_page_size": 0}}))
    with pytest.raises(CRMServiceError, match="pagination.default_page_size"):
        CRMConfigurationService.validate_document(
            _doc({"pagination": {"maximum_page_size": 10, "default_page_size": 11}})
        )


def test_ui_bounds_reference_account_and_pagination_ceilings():
    with pytest.raises(CRMServiceError, match="ui.hierarchy_auto_expand_levels"):
        CRMConfigurationService.validate_document(
            _doc({"account": {"hierarchy_max_depth": 3}, "ui": {"hierarchy_auto_expand_levels": 4}})
        )
    with pytest.raises(CRMServiceError, match="ui.hierarchy_indentation_pixels"):
        CRMConfigurationService.validate_document(_doc({"ui": {"hierarchy_indentation_pixels": 7}}))
    with pytest.raises(CRMServiceError, match="ui.hierarchy_indentation_pixels"):
        CRMConfigurationService.validate_document(_doc({"ui": {"hierarchy_indentation_pixels": 65}}))
    with pytest.raises(CRMServiceError, match="ui.minimum_pipeline_bar_percent"):
        CRMConfigurationService.validate_document(_doc({"ui": {"minimum_pipeline_bar_percent": -1}}))
    with pytest.raises(CRMServiceError, match="ui.minimum_pipeline_bar_percent"):
        CRMConfigurationService.validate_document(_doc({"ui": {"minimum_pipeline_bar_percent": 101}}))
    with pytest.raises(CRMServiceError, match="ui.saved_page_size"):
        CRMConfigurationService.validate_document(
            _doc(
                {
                    "pagination": {"maximum_page_size": 10, "default_page_size": 10},
                    "ui": {"saved_page_size": 11},
                }
            )
        )
    with pytest.raises(CRMServiceError, match="ui.dashboard_forecast_period_days"):
        CRMConfigurationService.validate_document(
            _doc(
                {
                    "forecast": {
                        "minimum_period_days": 10,
                        "maximum_period_days": 20,
                        "default_period_days": 10,
                    },
                    "ui": {"dashboard_forecast_period_days": 9},
                }
            )
        )
    with pytest.raises(CRMServiceError, match="ui.stale_deal_page_size"):
        CRMConfigurationService.validate_document(
            _doc(
                {
                    "pagination": {"maximum_page_size": 10, "default_page_size": 10},
                    "ui": {"saved_page_size": 10, "stale_deal_page_size": 11},
                }
            )
        )
    with pytest.raises(CRMServiceError, match="ui.pipeline_fetch_limit"):
        CRMConfigurationService.validate_document(
            _doc(
                {
                    "pagination": {"maximum_page_size": 10, "default_page_size": 10},
                    "ui": {"saved_page_size": 10, "stale_deal_page_size": 10, "pipeline_fetch_limit": 11},
                }
            )
        )
    with pytest.raises(CRMServiceError, match="Prediction retry policy must be boolean"):
        CRMConfigurationService.validate_document(_doc({"ui": {"prediction_retry_enabled": "yes"}}))


def test_api_quota_cost_bounds():
    with pytest.raises(CRMServiceError, match="api.quota_cost"):
        CRMConfigurationService.validate_document(_doc({"api": {"quota_cost": 0}}))
    with pytest.raises(CRMServiceError, match="api.quota_cost"):
        CRMConfigurationService.validate_document(_doc({"api": {"quota_cost": 1001}}))


def test_health_cache_timeout_bounds():
    with pytest.raises(CRMServiceError, match="health.cache_timeout_seconds"):
        CRMConfigurationService.validate_document(_doc({"health": {"cache_timeout_seconds": 0}}))
    with pytest.raises(CRMServiceError, match="health.cache_timeout_seconds"):
        CRMConfigurationService.validate_document(_doc({"health": {"cache_timeout_seconds": 121}}))


def test_conversion_policies_and_bounds():
    with pytest.raises(CRMServiceError, match="Conversion policies must be boolean"):
        CRMConfigurationService.validate_document(_doc({"conversion": {"create_account_by_default": "yes"}}))
    with pytest.raises(CRMServiceError, match="Conversion policies must be boolean"):
        CRMConfigurationService.validate_document(_doc({"conversion": {"use_current_version": "yes"}}))
    with pytest.raises(CRMServiceError, match="conversion.close_date_offset_days"):
        CRMConfigurationService.validate_document(_doc({"conversion": {"close_date_offset_days": -1}}))
    with pytest.raises(CRMServiceError, match="transition-key prefix is invalid"):
        CRMConfigurationService.validate_document(_doc({"conversion": {"transition_key_prefix": "   "}}))
    with pytest.raises(CRMServiceError, match="transition-key prefix is invalid"):
        CRMConfigurationService.validate_document(_doc({"conversion": {"transition_key_prefix": "x" * 65}}))
    with pytest.raises(CRMServiceError, match="transition-key prefix is invalid"):
        CRMConfigurationService.validate_document(_doc({"conversion": {"transition_key_prefix": 12345}}))
    document = CRMConfigurationService.validate_document(_doc({"conversion": {"transition_key_prefix": "x" * 64}}))
    assert document["conversion"]["transition_key_prefix"] == "x" * 64


# ---------------------------------------------------------------------------
# validate_feature_flags / validate_rollout
# ---------------------------------------------------------------------------


def test_validate_feature_flags_rejects_unknown_keys_and_non_bool_values():
    with pytest.raises(CRMServiceError, match="supported boolean keys"):
        CRMConfigurationService.validate_feature_flags({"unknown_flag": True})
    with pytest.raises(CRMServiceError, match="supported boolean keys"):
        CRMConfigurationService.validate_feature_flags({"async_lead_scoring": "yes"})
    flags = CRMConfigurationService.validate_feature_flags({"async_lead_scoring": False})
    assert flags["async_lead_scoring"] is False
    assert set(flags) == set(DEFAULT_FEATURE_FLAGS)


def test_validate_rollout_rejects_unsupported_fields_and_bounds():
    with pytest.raises(CRMServiceError, match="Rollout contains unsupported fields"):
        CRMConfigurationService.validate_rollout({"unknown": 1})
    with pytest.raises(CRMServiceError, match="Rollout contains unsupported fields"):
        CRMConfigurationService.validate_rollout({"enabled": "yes"})
    with pytest.raises(CRMServiceError, match="rollout.percentage"):
        CRMConfigurationService.validate_rollout({"percentage": -1})
    with pytest.raises(CRMServiceError, match="rollout.percentage"):
        CRMConfigurationService.validate_rollout({"percentage": 101})


@pytest.mark.parametrize("field", ["roles", "cohorts"])
def test_validate_rollout_roles_and_cohorts_are_bounded_deduplicated_strings(field):
    with pytest.raises(CRMServiceError, match=f"Rollout {field} are invalid"):
        CRMConfigurationService.validate_rollout({field: "not-a-list"})
    with pytest.raises(CRMServiceError, match=f"Rollout {field} are invalid"):
        CRMConfigurationService.validate_rollout({field: ["x"] * 101})
    with pytest.raises(CRMServiceError, match=f"Rollout {field} are invalid"):
        CRMConfigurationService.validate_rollout({field: [""]})
    with pytest.raises(CRMServiceError, match=f"Rollout {field} are invalid"):
        CRMConfigurationService.validate_rollout({field: ["x" * 129]})
    with pytest.raises(CRMServiceError, match=f"Rollout {field} are invalid"):
        CRMConfigurationService.validate_rollout({field: [123]})
    rollout = CRMConfigurationService.validate_rollout({field: [" beta ", "beta", "alpha"]})
    assert rollout[field] == ["alpha", "beta"]


def test_preview_reports_diff_only_for_changed_sections(tenant_id):
    baseline = CRMConfigurationService.preview(tenant_id, payload={})
    assert baseline["diff"] == []
    assert baseline["valid"] is True

    changed = CRMConfigurationService.preview(
        tenant_id, payload={"document": {"lead": {"qualification_threshold": 55}}}
    )
    assert changed["diff"] == ["document"]
    assert changed["effective"]["document"]["lead"]["qualification_threshold"] == 55
    # Original persisted configuration is untouched by preview.
    assert CRMConfigurationService.get(tenant_id)["document"]["lead"]["qualification_threshold"] == 70


# ---------------------------------------------------------------------------
# Module-level helper functions used across every service
# ---------------------------------------------------------------------------


def test_actor_normalizes_strips_and_rejects_blank_or_oversized(tenant_id):
    assert _actor(None) is None
    assert _actor("  agent-7  ", tenant_id) == "agent-7"
    with pytest.raises(CRMServiceError, match="Actor identifier is invalid"):
        _actor("   ", tenant_id)
    with pytest.raises(CRMServiceError, match="Actor identifier is invalid"):
        _actor("x" * 256, tenant_id)
    # Exactly the configured ceiling is accepted.
    assert _actor("x" * 255, tenant_id) == "x" * 255


def test_correlation_generates_strips_and_rejects_oversized(tenant_id):
    assert _correlation("  req-123  ") == "req-123"
    generated = _correlation(None)
    assert generated.startswith("req_")
    with pytest.raises(CRMServiceError, match="Correlation identifier is invalid"):
        _correlation("x" * 65, tenant_id)
    assert _correlation("x" * 64, tenant_id) == "x" * 64


def test_validate_version_rejects_bool_non_int_and_non_positive():
    class Row:
        version = 5

    with pytest.raises(CRMServiceError, match="must be a positive integer"):
        _validate_version(Row(), True)
    with pytest.raises(CRMServiceError, match="must be a positive integer"):
        _validate_version(Row(), "5")
    with pytest.raises(CRMServiceError, match="must be a positive integer"):
        _validate_version(Row(), 0)
    with pytest.raises(StaleVersionError):
        _validate_version(Row(), 4)
    _validate_version(Row(), 5)  # no raise


def test_assign_rejects_unknown_and_immutable_fields_and_tracks_real_changes(tenant_id):
    account = AccountFactory(tenant_id=tenant_id, name="Original", industry="Tech")
    with pytest.raises(CRMServiceError, match="not supported"):
        _assign(account, {"not_a_real_field": 1}, forbidden=set())
    with pytest.raises(CRMServiceError, match="immutable"):
        _assign(account, {"id": uuid.uuid4()}, forbidden=set())
    with pytest.raises(CRMServiceError, match="immutable"):
        _assign(account, {"name": "New"}, forbidden={"name"})
    # Assigning the same value the field already has is a no-op, not a change.
    changed = _assign(account, {"industry": "Tech"}, forbidden=set())
    assert changed == []
    changed = _assign(account, {"industry": "Finance"}, forbidden=set())
    assert changed == ["industry"]


# ---------------------------------------------------------------------------
# LeadService remaining branches: legacy conversion payload, rule scoring,
# conversion decision/company/account/contact reuse rules
# ---------------------------------------------------------------------------


def test_prepare_legacy_conversion_respects_configured_version_and_account_policy(tenant_id):
    lead = LeadFactory(tenant_id=tenant_id, company="Acme")
    payload = LeadService.prepare_legacy_conversion(tenant_id, lead, {})
    assert payload["expected_version"] == lead.version
    assert payload["transition_key"] == f"legacy-convert:{lead.id}"
    assert payload["create_new_account"] is True
    assert payload["currency"] == "USD"

    CRMConfigurationService.write(
        tenant_id,
        payload={"document": {"conversion": {"use_current_version": False}}},
        actor_id="cfg-admin",
        correlation_id="cfg-legacy",
    )
    payload = LeadService.prepare_legacy_conversion(tenant_id, lead, {})
    assert "expected_version" not in payload
    # Caller-supplied values are never overridden (setdefault semantics).
    payload = LeadService.prepare_legacy_conversion(tenant_id, lead, {"currency": "EUR"})
    assert payload["currency"] == "EUR"


def test_rule_score_matches_only_a_known_lowercased_source(tenant_id):
    score, grade, explanation = LeadService._rule_score(tenant_id, {"source": "REFERRAL"})
    assert "source" in explanation["factors"]
    assert score == 25
    assert grade == "D"

    score, grade, explanation = LeadService._rule_score(tenant_id, {"source": "not-a-real-source"})
    assert "source" not in explanation["factors"]
    assert score == 0


def test_rule_score_caps_at_configured_maximum(tenant_id, monkeypatch):
    # Under the shipped defaults the maximum achievable rule score (80) never
    # reaches score_max (100), so the `min(..., score_max)` cap is only
    # reachable under a tenant configuration whose weights can exceed it.
    configuration = deepcopy(DEFAULT_CRM_CONFIGURATION)
    configuration["lead"]["field_score_weights"] = {"company": 60, "email": 50}
    configuration["lead"]["source_score_weights"] = {"referral": 30}
    monkeypatch.setattr(services, "effective_configuration", lambda _tenant_id: configuration)
    score, grade, explanation = LeadService._rule_score(
        tenant_id, {"company": "A", "email": "a@b.test", "source": "referral"}
    )
    assert score == 100
    assert grade == "A"


def test_convert_lead_requires_minimum_amount(tenant_id, actor_id):
    lead = LeadFactory(tenant_id=tenant_id, company="Acme")
    lead = LeadService.transition_lead(
        tenant_id,
        lead_id=lead.id,
        command="qualify",
        transition_key="q-amount",
        context={},
        expected_version=lead.version,
        actor_id=actor_id,
    )
    with pytest.raises(CRMServiceError) as exc:
        LeadService.convert_lead(
            tenant_id,
            lead_id=lead.id,
            data={"amount": "0", "create_new_account": True},
            expected_version=lead.version,
            transition_key="convert-below-min",
            actor_id=actor_id,
            correlation_id=None,
        )
    assert exc.value.error_code == "INVALID_AMOUNT"


def test_convert_lead_only_qualified_leads_may_convert(tenant_id, actor_id):
    lead = LeadFactory(tenant_id=tenant_id, company="Acme")  # still "new"
    with pytest.raises(CRMServiceError) as exc:
        LeadService.convert_lead(
            tenant_id,
            lead_id=lead.id,
            data={"amount": Decimal("100"), "create_new_account": True},
            expected_version=lead.version,
            transition_key="convert-not-qualified",
            actor_id=actor_id,
            correlation_id=None,
        )
    assert exc.value.error_code == "ILLEGAL_TRANSITION"


def _qualified_lead(tenant_id, actor_id, **overrides):
    lead = LeadFactory(tenant_id=tenant_id, **overrides)
    return LeadService.transition_lead(
        tenant_id,
        lead_id=lead.id,
        command="qualify",
        transition_key=f"q-{lead.id}",
        context={},
        expected_version=lead.version,
        actor_id=actor_id,
    )


def test_convert_lead_requires_exactly_one_account_decision(tenant_id, actor_id):
    lead = _qualified_lead(tenant_id, actor_id, company="Acme")
    other_account = AccountFactory(tenant_id=tenant_id)
    with pytest.raises(CRMServiceError) as exc_both:
        LeadService.convert_lead(
            tenant_id,
            lead_id=lead.id,
            data={
                "amount": Decimal("100"),
                "account_id": other_account.id,
                "create_new_account": True,
            },
            expected_version=lead.version,
            transition_key="convert-both",
            actor_id=actor_id,
            correlation_id=None,
        )
    assert exc_both.value.error_code == "CONVERSION_DECISION_REQUIRED"
    with pytest.raises(CRMServiceError) as exc_neither:
        LeadService.convert_lead(
            tenant_id,
            lead_id=lead.id,
            data={"amount": Decimal("100")},
            expected_version=lead.version,
            transition_key="convert-neither",
            actor_id=actor_id,
            correlation_id=None,
        )
    assert exc_neither.value.error_code == "CONVERSION_DECISION_REQUIRED"


def test_convert_lead_requires_company_when_creating_a_new_account(tenant_id, actor_id):
    lead = _qualified_lead(tenant_id, actor_id, company="   ")
    with pytest.raises(CRMServiceError) as exc:
        LeadService.convert_lead(
            tenant_id,
            lead_id=lead.id,
            data={"amount": Decimal("100"), "create_new_account": True},
            expected_version=lead.version,
            transition_key="convert-no-company",
            actor_id=actor_id,
            correlation_id=None,
        )
    assert exc.value.error_code == "ACCOUNT_REQUIRED"


def _convert_close_date():
    return timezone.localdate() + timedelta(days=30)


def test_convert_lead_reuses_existing_account_by_case_insensitive_name(tenant_id, actor_id):
    existing = AccountFactory(tenant_id=tenant_id, name="ACME CORP")
    lead = _qualified_lead(tenant_id, actor_id, company="acme corp", email="")
    baseline_accounts = Account.objects.filter(tenant_id=tenant_id).count()
    result = LeadService.convert_lead(
        tenant_id,
        lead_id=lead.id,
        data={"amount": Decimal("100"), "create_new_account": True, "close_date": _convert_close_date()},
        expected_version=lead.version,
        transition_key="convert-existing-account",
        actor_id=actor_id,
        correlation_id="reuse",
    )
    assert result.account.id == existing.id
    assert Account.objects.filter(tenant_id=tenant_id).count() == baseline_accounts


def test_convert_lead_reuses_existing_contact_by_case_insensitive_email(tenant_id, actor_id):
    account = AccountFactory(tenant_id=tenant_id, name="Acme")
    existing_contact = ContactFactory(tenant_id=tenant_id, account_id=account.id, email="LEAD@EXAMPLE.TEST")
    lead = _qualified_lead(tenant_id, actor_id, company="Acme", email="lead@example.test")
    result = LeadService.convert_lead(
        tenant_id,
        lead_id=lead.id,
        data={"amount": Decimal("100"), "account_id": account.id, "close_date": _convert_close_date()},
        expected_version=lead.version,
        transition_key="convert-existing-contact",
        actor_id=actor_id,
        correlation_id="reuse-contact",
    )
    assert result.contact.id == existing_contact.id


def test_convert_lead_without_email_but_with_a_name_still_creates_a_contact(tenant_id, actor_id):
    account = AccountFactory(tenant_id=tenant_id, name="Acme")
    lead = _qualified_lead(tenant_id, actor_id, company="Acme", email="", first_name="Ada", last_name="Lovelace")
    result = LeadService.convert_lead(
        tenant_id,
        lead_id=lead.id,
        data={"amount": Decimal("100"), "account_id": account.id, "close_date": _convert_close_date()},
        expected_version=lead.version,
        transition_key="convert-name-only-contact",
        actor_id=actor_id,
        correlation_id=None,
    )
    assert result.contact is not None
    assert result.contact.first_name == "Ada"


def test_convert_lead_with_no_email_and_no_first_name_still_uses_last_name_arm(tenant_id, actor_id):
    account = AccountFactory(tenant_id=tenant_id, name="Acme")
    lead = _qualified_lead(tenant_id, actor_id, company="Acme", email="", first_name="", last_name="Anon")
    # last_name is required by the model, so this exercises the "no email, no
    # first_name" arm of the `or` chain via the remaining last_name truthy check.
    result = LeadService.convert_lead(
        tenant_id,
        lead_id=lead.id,
        data={"amount": Decimal("100"), "account_id": account.id, "close_date": _convert_close_date()},
        expected_version=lead.version,
        transition_key="convert-lastname-only",
        actor_id=actor_id,
        correlation_id=None,
    )
    assert result.contact is not None
    assert result.contact.last_name == "Anon"


def test_score_lead_translates_invalid_provider_response(monkeypatch, tenant_id, actor_id):
    from src.modules.crm.integrations import InvalidIntegrationResponse

    lead = LeadFactory(tenant_id=tenant_id)

    class BrokenScorer:
        def score_lead(self, payload, *, correlation_id):
            raise InvalidIntegrationResponse("malformed payload")

    monkeypatch.setattr(services, "get_scoring_client", lambda: BrokenScorer())
    result = LeadService.score_lead(tenant_id, lead_id=lead.id, actor_id=actor_id)
    assert result.status == "failed"
    assert result.http_status == 503


def test_assign_lead_accepts_uuid_string_and_rejects_invalid_owner(tenant_id, actor_id):
    lead = LeadFactory(tenant_id=tenant_id)
    owner = uuid.uuid4()
    updated = LeadService.assign_lead(
        tenant_id, lead_id=lead.id, owner_id=str(owner), expected_version=lead.version, actor_id=actor_id
    )
    assert updated.owner_id == owner
    with pytest.raises(CRMServiceError) as exc:
        LeadService.assign_lead(
            tenant_id,
            lead_id=lead.id,
            owner_id="not-a-uuid",
            expected_version=updated.version,
            actor_id=actor_id,
        )
    assert exc.value.error_code == "INVALID_OWNER"


def test_update_lead_rescoring_only_triggers_on_scoring_relevant_fields(tenant_id, actor_id):
    lead = LeadFactory(tenant_id=tenant_id, company="Old Co")
    original_score = lead.score
    updated = LeadService.update_lead(
        tenant_id,
        lead_id=lead.id,
        data={"owner_id": uuid.uuid4()},
        expected_version=lead.version,
        actor_id=actor_id,
    )
    assert updated.score == original_score  # owner_id is not a scoring field

    rescored = LeadService.update_lead(
        tenant_id,
        lead_id=lead.id,
        data={"company": "New Co"},
        expected_version=updated.version,
        actor_id=actor_id,
    )
    assert rescored.score_source == services.LeadScoreSource.RULES


def test_update_lead_no_changes_is_a_pure_noop(tenant_id, actor_id):
    lead = LeadFactory(tenant_id=tenant_id, phone="+1 555 0100")
    lead.refresh_from_db()  # pick up any model-level normalization applied on save
    result = LeadService.update_lead(
        tenant_id,
        lead_id=lead.id,
        data={"phone": lead.phone},
        expected_version=lead.version,
        actor_id=actor_id,
    )
    assert result.version == lead.version


# ---------------------------------------------------------------------------
# AccountService remaining branches
# ---------------------------------------------------------------------------


def test_create_account_rejects_disallowed_type_and_immutable_fields_and_duplicates(tenant_id, actor_id):
    with pytest.raises(CRMServiceError, match="not enabled by tenant configuration"):
        AccountService.create_account(tenant_id, data={"name": "X", "account_type": "not-a-type"}, actor_id=actor_id)
    with pytest.raises(CRMServiceError, match="Server-owned account fields"):
        AccountService.create_account(tenant_id, data={"name": "X", "id": uuid.uuid4()}, actor_id=actor_id)
    AccountService.create_account(tenant_id, data={"name": "Unique Co"}, actor_id=actor_id)
    with pytest.raises(CRMServiceError) as exc:
        AccountService.create_account(tenant_id, data={"name": "UNIQUE CO"}, actor_id=actor_id)
    assert exc.value.error_code == "DUPLICATE_ACCOUNT"


def test_update_account_rejects_disallowed_type_change(tenant_id, actor_id):
    account = AccountFactory(tenant_id=tenant_id)
    with pytest.raises(CRMServiceError, match="not enabled by tenant configuration"):
        AccountService.update_account(
            tenant_id,
            account_id=account.id,
            data={"account_type": "not-a-type"},
            expected_version=account.version,
            actor_id=actor_id,
        )
    updated = AccountService.update_account(
        tenant_id,
        account_id=account.id,
        data={"account_type": AccountType.PARTNER},
        expected_version=account.version,
        actor_id=actor_id,
    )
    assert updated.account_type == AccountType.PARTNER


def test_delete_account_rejects_open_opportunities(tenant_id, actor_id):
    account = AccountFactory(tenant_id=tenant_id)
    OpportunityFactory(tenant_id=tenant_id, account_id=account.id, status=OpportunityStatus.OPEN)
    with pytest.raises(CRMServiceError) as exc:
        AccountService.delete_account(
            tenant_id, account_id=account.id, expected_version=account.version, actor_id=actor_id
        )
    assert exc.value.error_code == "ACCOUNT_HAS_OPEN_OPPORTUNITIES"


def test_get_hierarchy_enforces_node_child_and_depth_limits(tenant_id, monkeypatch):
    root = AccountFactory(tenant_id=tenant_id, name="Root")
    for index in range(3):
        AccountFactory(tenant_id=tenant_id, name=f"Child {index}", parent_account_id=root.id)

    configuration = deepcopy(DEFAULT_CRM_CONFIGURATION)
    configuration["hierarchy"]["max_children"] = 2
    monkeypatch.setattr(services, "effective_configuration", lambda _tenant_id: configuration)
    with pytest.raises(CRMServiceError, match="child limit"):
        AccountService.get_hierarchy(tenant_id, account_id=root.id)

    configuration = deepcopy(DEFAULT_CRM_CONFIGURATION)
    configuration["account"]["hierarchy_max_depth"] = 1
    monkeypatch.setattr(services, "effective_configuration", lambda _tenant_id: configuration)
    with pytest.raises(CRMServiceError, match="supported depth"):
        AccountService.get_hierarchy(tenant_id, account_id=root.id)


def test_get_hierarchy_detects_a_stored_cycle(tenant_id, monkeypatch):
    root = AccountFactory(tenant_id=tenant_id, name="Root")
    child = AccountFactory(tenant_id=tenant_id, name="Child", parent_account_id=root.id)
    # Bypass the service layer to plant an illegal cycle directly, the way a
    # corrupted row or bulk import could.
    Account.objects.filter(pk=root.pk).update(parent_account_id=child.id)
    with pytest.raises(CRMServiceError, match="cycle"):
        AccountService.get_hierarchy(tenant_id, account_id=root.id)


def test_get_hierarchy_alias_is_the_same_callable():
    assert AccountService.get_account_hierarchy is AccountService.get_hierarchy


def test_find_duplicates_matches_by_website_and_reports_extension_matches(tenant_id, monkeypatch):
    account = AccountFactory(tenant_id=tenant_id, name="Totally Different Name", website="https://match.example")

    class FakeMatch:
        external_reference = "ext-1"
        confidence = Decimal("0.9")
        evidence_codes = ("name_match",)

    class FakeProvider:
        def find_matches(self, context, *, normalized_name, website_domain):
            assert website_domain == "match.example"
            return [FakeMatch()]

    monkeypatch.setattr(services.extension_registry, "resolve", lambda capability: (FakeProvider(),))
    result = AccountService.find_duplicates(tenant_id, name="no-name-match", website="https://match.example")
    assert result.local_matches == (account,)
    assert result.enrichment_status == "available"
    assert result.external_matches[0]["external_reference"] == "ext-1"


def test_find_duplicates_reports_unavailable_on_integration_error(tenant_id, monkeypatch):
    class FailingProvider:
        def find_matches(self, context, *, normalized_name, website_domain):
            raise CRMIntegrationError("boom")

    monkeypatch.setattr(services.extension_registry, "resolve", lambda capability: (FailingProvider(),))
    result = AccountService.find_duplicates(tenant_id, name="anything")
    assert result.enrichment_status == "unavailable"
    assert result.external_matches == ()


# ---------------------------------------------------------------------------
# ContactService remaining branches
# ---------------------------------------------------------------------------


def test_create_contact_defaults_to_enforcing_domain_without_override(tenant_id, actor_id):
    account = AccountFactory(tenant_id=tenant_id, metadata={"email_domain": "acme.test"})
    with pytest.raises(Exception):
        ContactService.create_contact(
            tenant_id,
            data={"account_id": account.id, "last_name": "Mismatch", "email": "mismatch@elsewhere.test"},
            actor_id=actor_id,
            allow_domain_override=False,
        )


def test_create_contact_rejects_server_owned_fields(tenant_id, actor_id):
    account = AccountFactory(tenant_id=tenant_id)
    with pytest.raises(CRMServiceError, match="Server-owned contact fields"):
        ContactService.create_contact(
            tenant_id,
            data={"account_id": account.id, "last_name": "X", "engagement_score": 99},
            actor_id=actor_id,
        )


def test_recalculate_engagement_rejects_naive_datetime(tenant_id, actor_id):
    account = AccountFactory(tenant_id=tenant_id)
    contact = ContactFactory(tenant_id=tenant_id, account_id=account.id)
    from datetime import datetime

    with pytest.raises(CRMServiceError, match="as_of must include a timezone"):
        ContactService.recalculate_engagement(
            tenant_id, contact_id=contact.id, as_of=datetime(2026, 1, 1), actor_id=actor_id
        )


def test_recalculate_engagement_alias_is_the_same_callable():
    assert ContactService.update_engagement_score is ContactService.recalculate_engagement


# ---------------------------------------------------------------------------
# OpportunityService remaining branches
# ---------------------------------------------------------------------------


def test_create_opportunity_rejects_server_owned_fields_and_closed_stages(tenant_id, actor_id):
    account = AccountFactory(tenant_id=tenant_id)
    with pytest.raises(CRMServiceError, match="Server-owned opportunity fields"):
        OpportunityService.create_opportunity(
            tenant_id,
            data={**_opp_data(account), "status": OpportunityStatus.WON},
            actor_id=actor_id,
        )
    with pytest.raises(CRMServiceError, match="must use an open stage"):
        OpportunityService.create_opportunity(
            tenant_id,
            data={**_opp_data(account), "stage": OpportunityStage.CLOSED_WON},
            actor_id=actor_id,
        )
    with pytest.raises(CRMServiceError, match="must use an open stage"):
        OpportunityService.create_opportunity(
            tenant_id,
            data={**_opp_data(account), "stage": "not-a-real-stage"},
            actor_id=actor_id,
        )


def _opp_data(account):
    return {
        "account_id": account.id,
        "name": "Deal",
        "amount": Decimal("500"),
        "currency": "USD",
        "close_date": timezone.localdate() + timedelta(days=10),
    }


def test_transition_stage_requires_permission_for_reopen_commands(tenant_id, actor_id):
    account = AccountFactory(tenant_id=tenant_id)
    opportunity = OpportunityFactory(tenant_id=tenant_id, account_id=account.id, stage=OpportunityStage.PROPOSAL)
    with pytest.raises(CRMServiceError) as exc:
        OpportunityService.transition_stage(
            tenant_id,
            opportunity_id=opportunity.id,
            command="reopen_to_needs_analysis",
            transition_key="reopen-1",
            expected_version=opportunity.version,
            actor_id=actor_id,
            allow_backward=False,
        )
    assert exc.value.error_code == "REOPEN_PERMISSION_REQUIRED"
    reopened = OpportunityService.transition_stage(
        tenant_id,
        opportunity_id=opportunity.id,
        command="reopen_to_needs_analysis",
        transition_key="reopen-2",
        expected_version=opportunity.version,
        actor_id=actor_id,
        reason="Reopening for renegotiation",
        allow_backward=True,
    )
    assert reopened.stage == OpportunityStage.NEEDS_ANALYSIS


def test_close_lost_strips_loss_reason_whitespace(tenant_id, actor_id):
    account = AccountFactory(tenant_id=tenant_id)
    opportunity = OpportunityFactory(tenant_id=tenant_id, account_id=account.id)
    closed = OpportunityService.close_lost(
        tenant_id,
        opportunity_id=opportunity.id,
        loss_reason="  Budget cuts  ",
        transition_key="lost-strip",
        expected_version=opportunity.version,
        actor_id=actor_id,
    )
    assert closed.loss_reason == "Budget cuts"
    assert closed.status == OpportunityStatus.LOST


def test_acknowledge_sales_order_requires_nonblank_idempotency_key(tenant_id, actor_id):
    account = AccountFactory(tenant_id=tenant_id)
    opportunity = OpportunityFactory(tenant_id=tenant_id, account_id=account.id)
    with pytest.raises(CRMServiceError, match="Acknowledgement idempotency key is required"):
        OpportunityService.acknowledge_sales_order(
            tenant_id,
            opportunity_id=opportunity.id,
            order_id=uuid.uuid4(),
            acknowledgement_id=uuid.uuid4(),
            idempotency_key="   ",
            actor_id=actor_id,
            correlation_id=None,
        )


# ---------------------------------------------------------------------------
# ActivityService remaining branches
# ---------------------------------------------------------------------------


def test_validate_parent_rejects_unsupported_relation_type_and_missing_record(tenant_id):
    with pytest.raises(CRMServiceError, match="Unsupported related entity type"):
        ActivityService._validate_parent(tenant_id, "NotARelation", uuid.uuid4())
    with pytest.raises(CRMServiceError, match="Related CRM record was not found"):
        ActivityService._validate_parent(tenant_id, RelatedToType.LEAD, uuid.uuid4())


def test_activities_on_closed_opportunities_are_immutable_unless_allowed(tenant_id, actor_id):
    account = AccountFactory(tenant_id=tenant_id)
    opportunity = OpportunityFactory(tenant_id=tenant_id, account_id=account.id)
    OpportunityService.close_won(
        tenant_id,
        opportunity_id=opportunity.id,
        transition_key="close-for-activity-test",
        expected_version=opportunity.version,
        actor_id=actor_id,
    )
    with pytest.raises(CRMServiceError, match="Activities on closed opportunities are immutable"):
        ActivityService.create_activity(
            tenant_id,
            data={
                "activity_type": ActivityType.NOTE,
                "related_to_type": RelatedToType.OPPORTUNITY,
                "related_to_id": opportunity.id,
                "subject": "Should be blocked",
            },
            actor_id=actor_id,
        )
    allowed = ActivityService.create_activity(
        tenant_id,
        data={
            "activity_type": ActivityType.NOTE,
            "related_to_type": RelatedToType.OPPORTUNITY,
            "related_to_id": opportunity.id,
            "subject": "Explicitly allowed",
        },
        actor_id=actor_id,
        allow_closed_parent=True,
    )
    assert allowed.subject == "Explicitly allowed"


def test_create_activity_on_opportunity_bumps_version_and_last_activity(tenant_id, actor_id):
    account = AccountFactory(tenant_id=tenant_id)
    opportunity = OpportunityFactory(tenant_id=tenant_id, account_id=account.id)
    original_version = opportunity.version
    ActivityService.create_activity(
        tenant_id,
        data={
            "activity_type": ActivityType.NOTE,
            "related_to_type": RelatedToType.OPPORTUNITY,
            "related_to_id": opportunity.id,
            "subject": "Touch",
        },
        actor_id=actor_id,
    )
    opportunity.refresh_from_db()
    assert opportunity.version == original_version + 1
    assert opportunity.last_activity_at is not None


def test_create_activity_on_contact_only_recalculates_engagement_for_interaction_types(tenant_id, actor_id):
    account = AccountFactory(tenant_id=tenant_id)
    contact = ContactFactory(tenant_id=tenant_id, account_id=account.id)
    ActivityService.create_activity(
        tenant_id,
        data={
            "activity_type": ActivityType.NOTE,  # not an interaction type
            "related_to_type": RelatedToType.CONTACT,
            "related_to_id": contact.id,
            "subject": "Non-interaction note",
        },
        actor_id=actor_id,
    )
    contact.refresh_from_db()
    assert contact.engagement_score == 0

    ActivityService.create_activity(
        tenant_id,
        data={
            "activity_type": ActivityType.CALL,
            "related_to_type": RelatedToType.CONTACT,
            "related_to_id": contact.id,
            "subject": "Interaction call",
        },
        actor_id=actor_id,
    )
    contact.refresh_from_db()
    assert contact.engagement_score == 10


def test_update_activity_rejects_editing_completed_activities_and_blocks_forbidden_fields(tenant_id, actor_id):
    lead = LeadFactory(tenant_id=tenant_id)
    activity = ActivityService.create_activity(
        tenant_id,
        data={
            "activity_type": ActivityType.TASK,
            "related_to_type": RelatedToType.LEAD,
            "related_to_id": lead.id,
            "subject": "Task",
        },
        actor_id=actor_id,
    )
    with pytest.raises(CRMServiceError, match="immutable"):
        ActivityService.update_activity(
            tenant_id,
            activity_id=activity.id,
            data={"related_to_type": RelatedToType.ACCOUNT},
            expected_version=activity.version,
            actor_id=actor_id,
        )


def test_get_timeline_static_alias_and_ordering(tenant_id, actor_id):
    assert ActivityService.get_activity_timeline is ActivityService.get_timeline
    lead = LeadFactory(tenant_id=tenant_id)
    ActivityService.create_activity(
        tenant_id,
        data={
            "activity_type": ActivityType.NOTE,
            "related_to_type": RelatedToType.LEAD,
            "related_to_id": lead.id,
            "subject": "First",
        },
        actor_id=actor_id,
    )
    second = ActivityService.create_activity(
        tenant_id,
        data={
            "activity_type": ActivityType.NOTE,
            "related_to_type": RelatedToType.LEAD,
            "related_to_id": lead.id,
            "subject": "Second",
        },
        actor_id=actor_id,
    )
    timeline = list(ActivityService.get_timeline(tenant_id, related_to_type=RelatedToType.LEAD, related_to_id=lead.id))
    assert timeline[0].id == second.id  # newest first


def test_sync_external_activity_requires_all_fields(tenant_id):
    with pytest.raises(CRMServiceError, match="External activity event is incomplete"):
        ActivityService.sync_external_activity(
            tenant_id, event={"activity_type": ActivityType.CALL}, idempotency_key="k", correlation_id="c"
        )


# ---------------------------------------------------------------------------
# ForecastingService remaining branches
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [True, "30", 0.5, 0, 366])
def test_period_rejects_bool_non_int_and_out_of_bounds(tenant_id, value):
    with pytest.raises(CRMServiceError, match="Period must be from"):
        ForecastingService._period(tenant_id, value)


def test_period_defaults_when_none_supplied(tenant_id):
    assert ForecastingService._period(tenant_id, None) == 90


def test_get_win_rate_with_zero_closed_opportunities_is_zero_not_a_division_error(tenant_id):
    rate = ForecastingService.get_win_rate(tenant_id, period_days=30)
    assert rate.win_rate == Decimal("0")
    assert rate.total_closed == 0


def test_open_queryset_filters_by_owner_only_when_supplied(tenant_id):
    account = AccountFactory(tenant_id=tenant_id)
    owner = uuid.uuid4()
    OpportunityFactory(tenant_id=tenant_id, account_id=account.id, owner_id=owner)
    OpportunityFactory(tenant_id=tenant_id, account_id=account.id, owner_id=uuid.uuid4())
    all_open = ForecastingService._open_queryset(tenant_id, None, 90)
    assert all_open.count() == 2
    owned_only = ForecastingService._open_queryset(tenant_id, owner, 90)
    assert owned_only.count() == 1


def test_predict_revenue_translates_invalid_provider_response(monkeypatch, tenant_id, actor_id):
    from src.modules.crm.integrations import InvalidIntegrationResponse

    class BrokenPredictor:
        def predict_revenue(self, payload, *, correlation_id):
            raise InvalidIntegrationResponse("malformed payload")

    monkeypatch.setattr(services, "get_revenue_prediction_client", lambda: BrokenPredictor())
    result = ForecastingService.predict_revenue(
        tenant_id, period_days=30, actor_id=actor_id, correlation_id="prediction-invalid"
    )
    assert result.status == "failed"
    assert result.http_status == 503


# ---------------------------------------------------------------------------
# CRMIdempotencyService remaining branches
# ---------------------------------------------------------------------------


def test_idempotency_begin_rejects_blank_and_oversized_keys(tenant_id):
    with pytest.raises(CRMServiceError, match="A bounded Idempotency-Key is required"):
        CRMIdempotencyService.begin(tenant_id, key="   ", method="POST", path="/x", payload={})
    with pytest.raises(CRMServiceError, match="A bounded Idempotency-Key is required"):
        CRMIdempotencyService.begin(tenant_id, key="x" * 181, method="POST", path="/x", payload={})


def test_idempotency_complete_rejects_out_of_range_status(tenant_id):
    record = CRMIdempotencyService.begin(tenant_id, key="status-bounds", method="POST", path="/x", payload={})
    with pytest.raises(CRMServiceError, match="Response status is invalid"):
        CRMIdempotencyService.complete(tenant_id, record_id=record.id, response_status=99, response_body={})
    with pytest.raises(CRMServiceError, match="Response status is invalid"):
        CRMIdempotencyService.complete(tenant_id, record_id=record.id, response_status=600, response_body={})
    # Exact boundaries are accepted.
    CRMIdempotencyService.complete(tenant_id, record_id=record.id, response_status=100, response_body={})
    record.refresh_from_db()
    assert record.response_status == 100
    assert record.completed is True


def test_idempotency_complete_does_not_overwrite_an_already_completed_record(tenant_id):
    record = CRMIdempotencyService.begin(tenant_id, key="no-overwrite", method="POST", path="/x", payload={})
    CRMIdempotencyService.complete(tenant_id, record_id=record.id, response_status=200, response_body={"a": 1})
    CRMIdempotencyService.complete(tenant_id, record_id=record.id, response_status=500, response_body={"a": 2})
    record.refresh_from_db()
    assert record.response_status == 200
    assert record.response_body == {"a": 1}


# ---------------------------------------------------------------------------
# IntegrationService legacy facade
# ---------------------------------------------------------------------------


def test_legacy_facade_skips_qualify_transition_for_already_qualified_leads(tenant_id, actor_id):
    lead = _qualified_lead(tenant_id, actor_id, company="Already Qualified Co")
    result = IntegrationService.convert_lead_to_opportunity(
        lead.id,
        tenant_id,
        {"amount": Decimal("1000"), "currency": "USD", "close_date": timezone.localdate() + timedelta(days=10)},
        actor_id,
    )
    assert result["lead"].status == LeadStatus.CONVERTED
