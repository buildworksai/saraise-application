"""Fail-closed action metadata proofs."""

import uuid
from types import SimpleNamespace

from src.modules.purchase_management import permissions as permissions_module
from src.modules.purchase_management.permissions import (
    ACTION_ACCESS,
    PurchaseRequiresAccess,
)


def test_every_mutating_controller_action_has_access_metadata():
    required = {
        "create",
        "update",
        "partial_update",
        "destroy",
        "submit",
        "approve",
        "reject",
        "cancel",
        "publish",
        "award",
        "dispatch",
        "complete",
        "preview",
        "rollback",
    }
    assert required <= ACTION_ACCESS.keys()
    assert all(ACTION_ACCESS[action] for action in required)


def test_action_access_is_exactly_the_declared_mapping():
    # Pins every action -> permission-verb mapping exactly, so a mutant that
    # swaps, drops, or corrupts any single entry is caught.
    assert ACTION_ACCESS == {
        "list": "read",
        "retrieve": "read",
        "create": "create",
        "update": "update",
        "partial_update": "update",
        "destroy": "delete",
        "submit": "submit",
        "approve": "approve",
        "reject": "reject",
        "revise": "update",
        "cancel": "cancel",
        "activate": "archive",
        "deactivate": "archive",
        "convert_to_order": "convert",
        "publish": "publish",
        "close": "close",
        "compare_quotes": "compare",
        "award": "award",
        "withdraw": "submit",
        "dispatch": "dispatch",
        "dispatch_order": "dispatch",
        "acknowledge": "acknowledge",
        "complete": "complete",
        "preview": "preview",
        "active": "read",
        "versions": "read",
        "activate_version": "activate",
        "rollback": "rollback",
        "export_configuration": "export",
        "import_configuration": "import",
    }


def test_action_access_has_no_extraneous_entries():
    # Guards against a mutant (or accidental edit) that adds a stray key,
    # which the exact-equality test above would also catch, but this makes
    # the length assertion explicit and independently mutation-killable.
    assert len(ACTION_ACCESS) == 30


class _StubPipeline:
    """Records the tenant_id it was invoked with and returns a fixed decision."""

    def __init__(self, decision):
        self.decision = decision
        self.calls = []

    def decide(self, tenant_id, user, required_permission, **kwargs):
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "user": user,
                "required_permission": required_permission,
                **kwargs,
            }
        )
        return self.decision


def _allow_decision():
    return SimpleNamespace(allowed=True)


def _deny_decision():
    return SimpleNamespace(allowed=False)


def _make_permission(decision):
    perm = PurchaseRequiresAccess("purchase_management:read")
    perm.pipeline = _StubPipeline(decision)
    return perm


def test_has_permission_populates_missing_tenant_id_from_user(monkeypatch):
    expected_tenant_id = str(uuid.uuid4())
    monkeypatch.setattr(
        permissions_module,
        "get_user_tenant_id",
        lambda user: expected_tenant_id,
    )
    user = SimpleNamespace(id=uuid.uuid4())
    request = SimpleNamespace(user=user)
    view = SimpleNamespace(required_permission="purchase_management:read")
    perm = _make_permission(_allow_decision())

    result = perm.has_permission(request, view)

    assert result is True
    assert request.tenant_id == expected_tenant_id
    assert perm.pipeline.calls[0]["tenant_id"] == expected_tenant_id
    assert perm.pipeline.calls[0]["user"] is user


def test_has_permission_does_not_overwrite_existing_truthy_tenant_id(monkeypatch):
    calls = []
    monkeypatch.setattr(
        permissions_module,
        "get_user_tenant_id",
        lambda user: calls.append(user) or "should-not-be-used",
    )
    existing_tenant_id = str(uuid.uuid4())
    request = SimpleNamespace(user=SimpleNamespace(id=uuid.uuid4()), tenant_id=existing_tenant_id)
    view = SimpleNamespace(required_permission="purchase_management:read")
    perm = _make_permission(_allow_decision())

    result = perm.has_permission(request, view)

    assert result is True
    # get_user_tenant_id must not be consulted when a truthy tenant_id is
    # already present on the request.
    assert calls == []
    assert request.tenant_id == existing_tenant_id
    assert perm.pipeline.calls[0]["tenant_id"] == existing_tenant_id


def test_has_permission_treats_falsy_tenant_id_as_missing(monkeypatch):
    expected_tenant_id = str(uuid.uuid4())
    monkeypatch.setattr(
        permissions_module,
        "get_user_tenant_id",
        lambda user: expected_tenant_id,
    )
    # An empty-string tenant_id is falsy and must be re-resolved, not trusted.
    request = SimpleNamespace(user=SimpleNamespace(id=uuid.uuid4()), tenant_id="")
    view = SimpleNamespace(required_permission="purchase_management:read")
    perm = _make_permission(_allow_decision())

    perm.has_permission(request, view)

    assert request.tenant_id == expected_tenant_id


def test_has_permission_handles_request_without_user_attribute(monkeypatch):
    seen_users = []
    monkeypatch.setattr(
        permissions_module,
        "get_user_tenant_id",
        lambda user: seen_users.append(user) or str(uuid.uuid4()),
    )
    request = SimpleNamespace()  # no `user` attribute at all
    view = SimpleNamespace(required_permission="purchase_management:read")
    perm = _make_permission(_allow_decision())

    perm.has_permission(request, view)

    assert seen_users == [None]


def test_has_permission_denies_when_pipeline_denies(monkeypatch):
    monkeypatch.setattr(
        permissions_module,
        "get_user_tenant_id",
        lambda user: str(uuid.uuid4()),
    )
    request = SimpleNamespace(user=SimpleNamespace(id=uuid.uuid4()))
    view = SimpleNamespace(required_permission="purchase_management:read")
    perm = _make_permission(_deny_decision())

    result = perm.has_permission(request, view)

    assert result is False
    # The decision must still be recorded on the request by the base class.
    assert request.access_decision.allowed is False


def test_has_permission_denies_closed_when_no_required_permission(monkeypatch):
    monkeypatch.setattr(
        permissions_module,
        "get_user_tenant_id",
        lambda user: str(uuid.uuid4()),
    )
    request = SimpleNamespace(user=SimpleNamespace(id=uuid.uuid4()))
    view = SimpleNamespace()  # no required_permission declared anywhere
    perm = PurchaseRequiresAccess()
    perm.pipeline = _StubPipeline(_allow_decision())

    result = perm.has_permission(request, view)

    assert result is False
    assert request.tenant_id is not None
