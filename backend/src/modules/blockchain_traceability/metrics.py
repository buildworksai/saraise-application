"""Required low-cardinality Prometheus instruments for traceability."""

from prometheus_client import Counter, Gauge, Histogram

EVENTS_APPENDED = Counter(
    "blockchain_traceability_events_appended_total",
    "Durably appended traceability events by bounded outcome.",
    ("outcome",),
)
CHAIN_VERIFICATIONS = Counter(
    "blockchain_traceability_chain_verifications_total",
    "Local hash-chain verification outcomes.",
    ("outcome",),
)
ANCHOR_REQUESTS = Counter(
    "blockchain_traceability_anchor_requests_total",
    "Durable external-anchor requests by outcome.",
    ("outcome",),
)
ANCHOR_FAILURES = Counter(
    "blockchain_traceability_anchor_failures_total",
    "External-anchor failures by stable reason.",
    ("reason",),
)
ANCHOR_LATENCY = Histogram(
    "blockchain_traceability_anchor_latency_seconds",
    "Bounded ledger-provider submission latency.",
    ("outcome",),
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 30),
)
AUTHENTICITY_CHECKS = Counter(
    "blockchain_traceability_authenticity_checks_total",
    "Authenticity verification outcomes.",
    ("outcome",),
)
INVALID_PROOFS = Counter(
    "blockchain_traceability_invalid_proofs_total",
    "Invalid proof evidence by verification type.",
    ("verification_type",),
)
PROVIDER_UNAVAILABLE = Counter(
    "blockchain_traceability_provider_unavailable_total",
    "Unavailable configured dependency calls by bounded capability.",
    ("capability",),
)
HASH_CHAIN_LENGTH = Gauge(
    "blockchain_traceability_hash_chain_length",
    "Length of the most recently mutated or verified local traceability chain.",
)
OUTBOX_AGE = Gauge(
    "blockchain_traceability_outbox_age_seconds",
    "Age of the most recently persisted pending traceability outbox evidence.",
)

__all__ = [
    "ANCHOR_FAILURES",
    "ANCHOR_LATENCY",
    "ANCHOR_REQUESTS",
    "AUTHENTICITY_CHECKS",
    "CHAIN_VERIFICATIONS",
    "EVENTS_APPENDED",
    "HASH_CHAIN_LENGTH",
    "INVALID_PROOFS",
    "OUTBOX_AGE",
    "PROVIDER_UNAVAILABLE",
]
