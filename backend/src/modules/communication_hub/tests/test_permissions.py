"""
Tests for Communication Hub permission classes.

Exercises every branch of IsCommunicationUser.has_permission():
- request.user is None
- request.user is falsy (e.g. AnonymousUser-like falsy sentinel)
- request.user is truthy but not authenticated
- request.user is truthy and authenticated
"""

from types import SimpleNamespace

import pytest

from src.modules.communication_hub.permissions import IsCommunicationUser


class _FalsyUser:
    """A user-like object that is falsy in a boolean context.

    Used to prove the permission check relies on ``request.user`` truthiness
    (short-circuit `and`), not merely on attribute presence.
    """

    is_authenticated = True

    def __bool__(self):
        return False


@pytest.fixture
def permission():
    return IsCommunicationUser()


class TestIsCommunicationUser:
    def test_docstring_present(self):
        assert IsCommunicationUser.__doc__ == "Permission check for communication module access."
        assert IsCommunicationUser.has_permission.__doc__ == "Check if user has communication permissions."

    def test_user_none_denied(self, permission):
        request = SimpleNamespace(user=None)
        result = permission.has_permission(request, view=None)
        assert not result
        # `None and X` short-circuits to None itself (falsy), not to False.
        assert result is None

    def test_user_missing_attribute_denied(self, permission):
        """request.user attribute absent entirely -> getattr-style falsy path."""
        request = SimpleNamespace()
        request.user = None
        result = permission.has_permission(request, view=None)
        assert not result
        assert result is None

    def test_authenticated_user_true_allowed(self, permission):
        request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True))
        assert permission.has_permission(request, view=None) is True

    def test_authenticated_user_false_denied(self, permission):
        request = SimpleNamespace(user=SimpleNamespace(is_authenticated=False))
        assert permission.has_permission(request, view=None) is False

    def test_falsy_user_object_denied_even_if_is_authenticated_true(self, permission):
        """Proves the `and` short-circuits on request.user truthiness first.

        A falsy user object with is_authenticated=True must still be denied:
        `request.user and request.user.is_authenticated` short-circuits and
        returns the falsy `request.user` object itself.
        """
        falsy_user = _FalsyUser()
        request = SimpleNamespace(user=falsy_user)
        result = permission.has_permission(request, view=None)
        assert not result
        assert result is falsy_user

    def test_return_value_is_exact_boolean_for_authenticated(self, permission):
        request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True))
        result = permission.has_permission(request, view=None)
        assert result is True
        assert type(result) is bool

    def test_return_value_is_exact_boolean_for_denied(self, permission):
        """When request.user is truthy but is_authenticated is False, the
        `and` expression evaluates to the right operand, which is the exact
        bool False."""
        request = SimpleNamespace(user=SimpleNamespace(is_authenticated=False))
        result = permission.has_permission(request, view=None)
        assert result is False
        assert type(result) is bool

    def test_view_argument_is_irrelevant_to_decision(self, permission):
        """The permission decision must not depend on the view argument at all."""
        request_authed = SimpleNamespace(user=SimpleNamespace(is_authenticated=True))
        assert permission.has_permission(request_authed, view="anything") is True
        assert permission.has_permission(request_authed, view=None) is True

        request_denied = SimpleNamespace(user=SimpleNamespace(is_authenticated=False))
        assert permission.has_permission(request_denied, view="anything") is False
        assert permission.has_permission(request_denied, view=object()) is False

    def test_is_instance_of_base_permission(self):
        from rest_framework import permissions

        assert isinstance(permission_instance(), permissions.BasePermission)


def permission_instance():
    return IsCommunicationUser()
