"""Focused transport-level security regressions for CRM evidence endpoints."""

import pytest
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from src.modules.crm.api import ActivityViewSet


def test_activity_delete_is_prohibited_before_lookup_or_role_evaluation() -> None:
    request = Request(APIRequestFactory().delete("/api/v2/crm/activities/irrelevant/"))
    with pytest.raises(MethodNotAllowed, match="append-only") as raised:
        ActivityViewSet().destroy(request, pk="irrelevant")
    assert raised.value.status_code == 405
