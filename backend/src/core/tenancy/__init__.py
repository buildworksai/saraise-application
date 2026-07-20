"""Public tenancy foundation for SARAISE modules."""

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
]
