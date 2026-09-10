from __future__ import annotations

from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import pytest
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated

from src.core.access.permissions import RequiresAccess

from ..api import (
    BankAccountViewSet,
    BankStatementViewSet,
    BankTransactionViewSet,
    MatchingRuleViewSet,
    ReconciliationMatchViewSet,
    ReconciliationViewSet,
    StatementImportViewSet,
)
from ..permissions import PERMISSIONS, READ_ACTIONS, ActionAccessMixin, IsBankUser, SessionAuthentication401


def test_every_controller_action_has_a_declared_permission() -> None:
    controllers = (
        BankAccountViewSet,
        BankStatementViewSet,
        BankTransactionViewSet,
        StatementImportViewSet,
        MatchingRuleViewSet,
        ReconciliationViewSet,
        ReconciliationMatchViewSet,
    )
    for controller in controllers:
        assert controller.action_permissions
        assert all(value in PERMISSIONS for value in controller.action_permissions.values())


def test_missing_action_metadata_is_fail_closed() -> None:
    assert ActionAccessMixin.action_permissions.get("missing") is None


def test_session_authentication_enforces_csrf_and_advertises_401() -> None:
    assert SessionAuthentication401().authenticate_header(object()) == "Session"


def test_malformed_detail_identifier_fails_closed_before_querying() -> None:
    view = BankAccountViewSet()
    view.kwargs = {"pk": "__uat_invalid_id__"}
    queryset = Mock()

    with pytest.raises(NotFound):
        view.object_or_404(queryset)

    queryset.filter.assert_not_called()


def _mixin_with_action(action: str) -> ActionAccessMixin:
    """Build a bare ActionAccessMixin instance stamped with a DRF-style action/request."""
    mixin = ActionAccessMixin()
    mixin.action = action
    mixin.request = Mock()
    mixin.request.user = Mock()
    return mixin


class _ConcreteAccess(ActionAccessMixin):
    action_permissions = {
        "retrieve": "bank_reconciliation.account:read",
        "create": "bank_reconciliation.account:create",
    }
    action_quotas = {"create": "bank_reconciliation.custom_quota"}


def test_get_permissions_returns_exactly_one_authenticated_and_one_access_check() -> None:
    mixin = _mixin_with_action("list")
    with patch("src.modules.bank_reconciliation.permissions.get_user_tenant_id", return_value=None):
        result = mixin.get_permissions()
    assert len(result) == 2
    assert isinstance(result[0], IsAuthenticated)
    assert isinstance(result[1], RequiresAccess)


def test_get_permissions_sets_required_permission_from_action_map() -> None:
    mixin = _ConcreteAccess()
    mixin.action = "retrieve"
    mixin.request = Mock()
    mixin.request.user = Mock()
    with patch("src.modules.bank_reconciliation.permissions.get_user_tenant_id", return_value=None):
        mixin.get_permissions()
    assert mixin.required_permission == "bank_reconciliation.account:read"
    assert mixin.required_entitlement == "bank_reconciliation.account:read"


def test_get_permissions_unmapped_action_yields_none_permission_fail_closed() -> None:
    mixin = _ConcreteAccess()
    mixin.action = "some_unlisted_action"
    mixin.request = Mock()
    mixin.request.user = Mock()
    with patch("src.modules.bank_reconciliation.permissions.get_user_tenant_id", return_value=None):
        mixin.get_permissions()
    assert mixin.required_permission is None
    assert mixin.required_entitlement is None


@pytest.mark.parametrize("action", sorted(READ_ACTIONS))
def test_default_quota_resource_is_reads_for_every_read_action(action: str) -> None:
    mixin = _mixin_with_action(action)
    with patch("src.modules.bank_reconciliation.permissions.get_user_tenant_id", return_value=None):
        mixin.get_permissions()
    assert mixin.quota_resource == "bank_reconciliation.api_reads"


@pytest.mark.parametrize("action", ["create", "update", "destroy", "partial_update", "confirm", "finalize"])
def test_default_quota_resource_is_writes_for_non_read_actions(action: str) -> None:
    assert action not in READ_ACTIONS
    mixin = _mixin_with_action(action)
    with patch("src.modules.bank_reconciliation.permissions.get_user_tenant_id", return_value=None):
        mixin.get_permissions()
    assert mixin.quota_resource == "bank_reconciliation.api_writes"


def test_action_quotas_override_takes_precedence_over_default_bucket() -> None:
    mixin = _ConcreteAccess()
    mixin.action = "create"
    mixin.request = Mock()
    mixin.request.user = Mock()
    with patch("src.modules.bank_reconciliation.permissions.get_user_tenant_id", return_value=None):
        mixin.get_permissions()
    assert mixin.quota_resource == "bank_reconciliation.custom_quota"
    assert mixin.quota_resource != "bank_reconciliation.api_writes"


def test_valid_tenant_id_is_coerced_to_uuid_on_request() -> None:
    mixin = _mixin_with_action("list")
    tenant_uuid = uuid4()
    with patch("src.modules.bank_reconciliation.permissions.get_user_tenant_id", return_value=str(tenant_uuid)):
        mixin.get_permissions()
    assert mixin.request.tenant_id == tenant_uuid
    assert isinstance(mixin.request.tenant_id, UUID)


def test_malformed_tenant_id_fails_closed_to_none_not_raise() -> None:
    mixin = _mixin_with_action("list")
    with patch(
        "src.modules.bank_reconciliation.permissions.get_user_tenant_id",
        return_value="__not_a_uuid__",
    ):
        mixin.get_permissions()
    assert mixin.request.tenant_id is None


def test_none_tenant_id_does_not_set_tenant_id_attribute() -> None:
    mixin = _mixin_with_action("list")
    request = Mock(spec=["user"])
    request.user = Mock()
    mixin.request = request
    with patch("src.modules.bank_reconciliation.permissions.get_user_tenant_id", return_value=None):
        mixin.get_permissions()
    assert not hasattr(request, "tenant_id")


def test_is_bank_user_alias_is_requires_access() -> None:
    assert IsBankUser is RequiresAccess


def test_permissions_tuple_contains_exact_expected_actions_per_resource() -> None:
    expected = {
        "bank_reconciliation.account:read",
        "bank_reconciliation.account:create",
        "bank_reconciliation.account:update",
        "bank_reconciliation.account:archive",
        "bank_reconciliation.account:reveal",
        "bank_reconciliation.statement:read",
        "bank_reconciliation.statement:create",
        "bank_reconciliation.statement:void",
        "bank_reconciliation.transaction:read",
        "bank_reconciliation.transaction:create",
        "bank_reconciliation.transaction:update",
        "bank_reconciliation.import:read",
        "bank_reconciliation.import:create",
        "bank_reconciliation.import:retry",
        "bank_reconciliation.import:cancel",
        "bank_reconciliation.rule:read",
        "bank_reconciliation.rule:create",
        "bank_reconciliation.rule:update",
        "bank_reconciliation.rule:delete",
        "bank_reconciliation.reconciliation:read",
        "bank_reconciliation.reconciliation:create",
        "bank_reconciliation.reconciliation:update",
        "bank_reconciliation.reconciliation:review",
        "bank_reconciliation.reconciliation:finalize",
        "bank_reconciliation.reconciliation:void",
        "bank_reconciliation.reconciliation:export",
        "bank_reconciliation.match:read",
        "bank_reconciliation.match:create",
        "bank_reconciliation.match:confirm",
        "bank_reconciliation.match:reverse",
        "bank_reconciliation.health:read",
    }
    assert set(PERMISSIONS) == expected
    assert len(PERMISSIONS) == len(expected)


def test_read_actions_frozenset_is_exact() -> None:
    assert READ_ACTIONS == frozenset({"list", "retrieve", "transactions", "report", "summary", "health"})


def test_action_access_mixin_default_permission_classes_are_authenticated_and_access() -> None:
    assert ActionAccessMixin.permission_classes == (IsAuthenticated, RequiresAccess)


def test_action_access_mixin_default_authentication_classes() -> None:
    assert ActionAccessMixin.authentication_classes == (SessionAuthentication401,)


def test_action_access_mixin_base_action_permissions_and_quotas_are_empty() -> None:
    assert ActionAccessMixin.action_permissions == {}
    assert ActionAccessMixin.action_quotas == {}
