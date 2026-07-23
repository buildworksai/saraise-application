"""Stable adapter registry for optional free and paid procurement integrations."""

from __future__ import annotations

from typing import Any, Mapping, Protocol
from uuid import UUID


class IntegrationUnavailable(RuntimeError):
    pass


class ProcurementAdapter(Protocol):
    def execute(
        self, tenant_id: UUID, payload: Mapping[str, Any], correlation_id: str, idempotency_key: str
    ) -> Mapping[str, Any]: ...


_adapters: dict[str, ProcurementAdapter] = {}


def register_adapter(owner: str, version: str, adapter: ProcurementAdapter, *, replace: bool = False) -> None:
    key = f"{owner.strip()}@{version.strip()}"
    if not owner.strip() or not version.strip():
        raise ValueError("Adapter owner and version are required")
    if key in _adapters and not replace:
        raise ValueError(f"Adapter {key} is already registered")
    _adapters[key] = adapter


def get_adapter(key: str) -> ProcurementAdapter:
    try:
        return _adapters[key]
    except KeyError as exc:
        raise IntegrationUnavailable(f"Integration adapter {key!r} is unavailable") from exc


def adapter_status() -> dict[str, bool]:
    return {name: True for name in sorted(_adapters)}
