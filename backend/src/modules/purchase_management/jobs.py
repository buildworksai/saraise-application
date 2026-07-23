"""Tenant-scoped durable job handlers for procurement side effects."""

from __future__ import annotations

from src.core.async_jobs.services import register_handler
from src.core.tenancy import tenant_context_worker

from .integrations import get_adapter

COMMAND_ADAPTERS = {
    "purchase.rfq.publish.v1": "supplier-delivery@v1",
    "purchase.order.dispatch.v1": "supplier-delivery@v1",
    "purchase.inventory.post-receipt.v1": "inventory@v1",
    "purchase.accounting.project.v1": "accounting@v1",
    "purchase.integration.retry.v1": "integration-retry@v1",
}


@tenant_context_worker
def _execute_for_tenant(job, *, tenant_id):
    adapter = get_adapter(COMMAND_ADAPTERS[job.command])
    return dict(adapter.execute(tenant_id, job.payload, job.correlation_id, str(job.id)))


def _handler(job):
    return _execute_for_tenant(job, tenant_id=job.tenant_id)


def register_job_handlers() -> None:
    for command in COMMAND_ADAPTERS:
        register_handler(command, _handler, replace=True)
