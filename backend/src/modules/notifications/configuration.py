"""Public configuration schema helpers for extensions and operators."""

from __future__ import annotations

from copy import deepcopy
from typing import Mapping
from uuid import UUID


def safe_default_document() -> dict[str, object]:
    from .services import NotificationConfigurationService

    return deepcopy(NotificationConfigurationService.safe_default())


def validate_configuration(tenant_id: UUID, document: Mapping[str, object]) -> dict[str, str]:
    from .services import NotificationConfigurationService

    return NotificationConfigurationService.validate_document(tenant_id, document)


__all__ = ["safe_default_document", "validate_configuration"]
