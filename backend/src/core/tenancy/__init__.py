"""Public tenancy foundation for SARAISE modules (models, scope registry, RLS)."""

from .models import TenantQuerySet, TenantScopedModel, TimestampedModel
from .registry import (
    HYBRID,
    PLATFORM_GLOBAL,
    TENANT_SCOPED,
    TenantScope,
    get_model_scope,
    register_model_scope,
    tenancy_scope,
)
from .rls import (
    InvalidTenantContext,
    MissingTenantContext,
    get_current_tenant_id,
    tenant_context,
    tenant_context_worker,
)

__all__ = [
    "HYBRID",
    "PLATFORM_GLOBAL",
    "TENANT_SCOPED",
    "TenantQuerySet",
    "TenantScope",
    "TenantScopedModel",
    "TimestampedModel",
    "get_model_scope",
    "register_model_scope",
    "tenancy_scope",
    "InvalidTenantContext",
    "MissingTenantContext",
    "get_current_tenant_id",
    "tenant_context",
    "tenant_context_worker",
]
