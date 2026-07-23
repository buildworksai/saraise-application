"""Durable job registry and explicit dependency-failure proofs."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.core.async_jobs.services import get_handler
from src.modules.purchase_management.integrations import IntegrationUnavailable


def test_delivery_job_fails_explicitly_without_adapter():
    handler = get_handler("purchase.order.dispatch.v1")
    job = SimpleNamespace(
        command="purchase.order.dispatch.v1", tenant_id=uuid4(), payload={}, correlation_id="corr", id=uuid4()
    )
    with pytest.raises(IntegrationUnavailable):
        handler(job)
