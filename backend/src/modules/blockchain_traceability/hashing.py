"""Deterministic hashing primitives for traceability evidence.

Version 1 event hashes deliberately depend only on the documented canonical
fields.  Persisted hashes are never recomputed during ordinary model saves;
the append service is the sole authority that creates them.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any
from uuid import UUID


class CanonicalizationError(ValueError):
    """Raised when a value cannot be represented by the canonical JSON contract."""


EVENT_HASH_SCHEMA_VERSION = 1
EVENT_HASH_ALGORITHM = "sha256"


def normalize_utc_timestamp(value: datetime) -> str:
    """Return an aware datetime as an RFC 3339 UTC timestamp."""

    if not isinstance(value, datetime):
        raise CanonicalizationError("timestamp must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise CanonicalizationError("timestamp must include a timezone")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _validate_json_value(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalizationError(f"{path} contains a non-finite number")
        return
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise CanonicalizationError(f"{path} contains a non-string object key")
            _validate_json_value(nested, f"{path}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, nested in enumerate(value):
            _validate_json_value(nested, f"{path}[{index}]")
        return
    raise CanonicalizationError(f"{path} contains unsupported type {type(value).__name__}")


def canonical_json(value: Any) -> bytes:
    """Serialize JSON data using the module's byte-for-byte canonical form."""

    _validate_json_value(value)
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise CanonicalizationError("value cannot be encoded as canonical JSON") from exc
    return encoded.encode("utf-8")


def sha256_hex(value: bytes | str) -> str:
    """Return the lowercase SHA-256 digest for bytes or UTF-8 text."""

    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def canonical_event_document(
    *,
    tenant_id: UUID | str,
    asset_id: UUID | str,
    sequence: int,
    event_type: str,
    schema_version: int,
    occurred_at: datetime,
    actor_ref: str,
    location: Mapping[str, Any],
    payload: Mapping[str, Any],
    previous_hash: str,
) -> dict[str, Any]:
    """Build the exact versioned document hashed for one event."""

    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        raise CanonicalizationError("sequence must be a positive integer")
    if schema_version != EVENT_HASH_SCHEMA_VERSION:
        raise CanonicalizationError(f"unsupported event hash schema_version {schema_version}")
    if not isinstance(location, Mapping) or not isinstance(payload, Mapping):
        raise CanonicalizationError("location and payload must be JSON objects")
    return {
        "tenant_id": str(tenant_id),
        "asset_id": str(asset_id),
        "sequence": sequence,
        "event_type": event_type,
        "schema_version": schema_version,
        "occurred_at": normalize_utc_timestamp(occurred_at),
        "actor_ref": actor_ref,
        "location": dict(location),
        "payload": dict(payload),
        "previous_hash": previous_hash,
    }


def compute_event_hash(**fields: Any) -> str:
    """Compute a schema-v1 event hash from canonical fields."""

    return sha256_hex(canonical_json(canonical_event_document(**fields)))


def compute_merkle_root(event_hashes: Sequence[str]) -> str:
    """Compute a deterministic binary Merkle root, duplicating odd leaves."""

    if not event_hashes:
        raise CanonicalizationError("at least one event hash is required")
    level: list[bytes] = []
    for digest in event_hashes:
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise CanonicalizationError("event hashes must be lowercase SHA-256 hexadecimal")
        level.append(bytes.fromhex(digest))
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [hashlib.sha256(level[index] + level[index + 1]).digest() for index in range(0, len(level), 2)]
    return level[0].hex()

