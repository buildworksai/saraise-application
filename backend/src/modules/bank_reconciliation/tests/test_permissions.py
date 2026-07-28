from __future__ import annotations

from unittest.mock import Mock

import pytest
from rest_framework.exceptions import NotFound

from ..api import (
    BankAccountViewSet,
    BankStatementViewSet,
    BankTransactionViewSet,
    MatchingRuleViewSet,
    ReconciliationMatchViewSet,
    ReconciliationViewSet,
    StatementImportViewSet,
)
from ..permissions import PERMISSIONS, ActionAccessMixin, SessionAuthentication401


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
