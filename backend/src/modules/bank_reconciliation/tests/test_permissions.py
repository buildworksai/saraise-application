from __future__ import annotations

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
