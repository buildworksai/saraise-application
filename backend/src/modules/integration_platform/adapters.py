"""Versioned connector SPI for reviewed open and paid adapters.

Adapters receive typed, immutable values and return ``OperationResult`` with
provider evidence.  The SPI intentionally has no ORM dependency, allowing paid
modules to register implementations without reaching into this module's data.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from src.core.api.results import OperationResult

from .configuration import DEFAULT_CONFIGURATION

_ADAPTER_POLICY = DEFAULT_CONFIGURATION["adapter"]
assert isinstance(_ADAPTER_POLICY, Mapping)
SPI_VERSION: Final = str(_ADAPTER_POLICY["spi_version"])
SUPPORTED_CAPABILITIES: Final = frozenset(str(value) for value in _ADAPTER_POLICY["capabilities"])
ADAPTER_KEY_MAX_LENGTH: Final = int(_ADAPTER_POLICY["adapter_key_max_length"])
CURSOR_MAX_LENGTH: Final = int(_ADAPTER_POLICY["cursor_max_length"])


@dataclass(frozen=True, slots=True)
class AdapterDescriptor:
    """Immutable compatibility and provenance identity for an adapter."""

    key: str
    implementation_version: str
    capabilities: frozenset[str]
    spi_version: str = SPI_VERSION
    description: str = ""

    def __post_init__(self) -> None:
        if not self.key or len(self.key) > ADAPTER_KEY_MAX_LENGTH or any(character.isspace() for character in self.key):
            raise ValueError("Adapter key must be a non-empty, whitespace-free identifier")
        if self.spi_version != SPI_VERSION:
            raise ValueError(f"Unsupported connector SPI version {self.spi_version!r}")
        if not self.implementation_version:
            raise ValueError("implementation_version is required")
        unknown = set(self.capabilities) - SUPPORTED_CAPABILITIES
        if unknown:
            raise ValueError(f"Unsupported adapter capabilities: {', '.join(sorted(unknown))}")

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(
            {
                "key": self.key,
                "spi_version": self.spi_version,
                "implementation_version": self.implementation_version,
                "capabilities": sorted(self.capabilities),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class AdapterExecutionContext:
    """Trace, deadline, and cancellation context supplied by durable workers."""

    tenant_id: UUID
    job_id: UUID
    correlation_id: str
    deadline: datetime | None = None
    cancellation_requested: bool = False


@dataclass(frozen=True, slots=True)
class CredentialBundle:
    """Short-lived decrypted bundle; callers must discard it after invocation."""

    credential_type: str
    value: object
    version: int
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class RecordCursor:
    """Opaque, bounded continuation token owned by the adapter."""

    value: str = ""

    def __post_init__(self) -> None:
        if len(self.value) > CURSOR_MAX_LENGTH:
            raise ValueError(f"Cursor exceeds {CURSOR_MAX_LENGTH} characters")


@dataclass(frozen=True, slots=True)
class RecordBatch:
    """A proven batch, including explicit evidence when the source is empty."""

    records: tuple[Mapping[str, object], ...]
    cursor: RecordCursor = field(default_factory=RecordCursor)
    source_exhausted: bool = False
    source_count: int = 0

    def __post_init__(self) -> None:
        if self.source_count != len(self.records):
            raise ValueError("source_count must equal the number of returned records")
        if not self.records and not self.source_exhausted:
            raise ValueError("An empty batch must prove that the source is exhausted")


@dataclass(frozen=True, slots=True)
class PushEvidence:
    accepted_count: int
    rejected_count: int
    provider_reference: str = ""

    def __post_init__(self) -> None:
        if self.accepted_count < 0 or self.rejected_count < 0:
            raise ValueError("Record counts cannot be negative")


class ConnectorAdapter(ABC):
    """Stable adapter protocol.  Implementations must perform real operations."""

    descriptor: AdapterDescriptor

    @abstractmethod
    def validate_config(self, config: Mapping[str, object]) -> OperationResult[Mapping[str, object]]:
        """Validate and normalize non-secret connector configuration."""

    @abstractmethod
    def test_connection(self, config: Mapping[str, object], credential: CredentialBundle | None) -> OperationResult[object]:
        """Perform a real provider connection check."""

    @abstractmethod
    def pull(
        self,
        config: Mapping[str, object],
        credential: CredentialBundle | None,
        cursor: RecordCursor,
        limit: int,
    ) -> OperationResult[RecordBatch]:
        """Read at most ``limit`` records with explicit empty-source evidence."""

    @abstractmethod
    def push(
        self,
        config: Mapping[str, object],
        credential: CredentialBundle | None,
        records: Sequence[Mapping[str, object]],
        idempotency_key: str,
    ) -> OperationResult[PushEvidence]:
        """Write the supplied records idempotently and return provider evidence."""

    @abstractmethod
    def health(self) -> OperationResult[Mapping[str, object]]:
        """Probe the adapter and its governed dependency path."""


__all__ = [
    "AdapterDescriptor",
    "AdapterExecutionContext",
    "ConnectorAdapter",
    "CredentialBundle",
    "PushEvidence",
    "RecordBatch",
    "RecordCursor",
    "SPI_VERSION",
]
