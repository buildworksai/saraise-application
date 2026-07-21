"""Bounded-cardinality Prometheus instruments owned by this module."""

from prometheus_client import Counter, Gauge, Histogram

REQUESTS = Counter(
    "saraise_document_intelligence_requests_total",
    "Document-intelligence requests by operation and accepted outcome.",
    ("operation", "outcome"),
)
PAGES_PROCESSED = Counter(
    "saraise_document_intelligence_pages_processed_total",
    "Pages with validated provider evidence.",
    ("engine", "outcome"),
)
PROCESSING_DURATION = Histogram(
    "saraise_document_intelligence_processing_duration_seconds",
    "Validated processing duration by operation.",
    ("operation", "engine"),
    buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 900),
)
QUEUE_AGE = Histogram(
    "saraise_document_intelligence_queue_age_seconds",
    "Age of work when claimed by a worker.",
    ("command",),
    buckets=(1, 5, 15, 30, 60, 300, 900, 3600, 21600, 86400),
)
LOW_CONFIDENCE = Counter(
    "saraise_document_intelligence_low_confidence_total",
    "Validated low-confidence outcomes.",
    ("operation",),
)
MANUAL_REVIEW_BACKLOG = Gauge(
    "saraise_document_intelligence_manual_review_backlog",
    "Current number of pending classification reviews.",
)
PROVIDER_FAILURES = Counter(
    "saraise_document_intelligence_provider_failures_total",
    "Provider failures by bounded adapter and stable code.",
    ("adapter", "code"),
)
CIRCUIT_STATE = Gauge(
    "saraise_document_intelligence_circuit_state",
    "Provider circuit state (0 closed, 0.5 half-open, 1 open).",
    ("adapter",),
)
ACTIVE_JOBS = Gauge(
    "saraise_document_intelligence_active_jobs",
    "Active domain work by bounded command.",
    ("command",),
)
TEMPLATE_MATCHES = Counter(
    "saraise_document_intelligence_template_matches_total",
    "Template matching outcomes.",
    ("engine", "outcome"),
)


def observe_provider_failure(adapter: str, code: str) -> None:
    """Record stable adapter failure dimensions; never record tenant data."""
    PROVIDER_FAILURES.labels(adapter=adapter[:80], code=code[:40]).inc()


__all__ = [
    "ACTIVE_JOBS",
    "CIRCUIT_STATE",
    "LOW_CONFIDENCE",
    "MANUAL_REVIEW_BACKLOG",
    "PAGES_PROCESSED",
    "PROCESSING_DURATION",
    "PROVIDER_FAILURES",
    "QUEUE_AGE",
    "REQUESTS",
    "TEMPLATE_MATCHES",
    "observe_provider_failure",
]
