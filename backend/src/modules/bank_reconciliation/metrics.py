"""Bounded-cardinality Prometheus instruments for bank reconciliation."""

from prometheus_client import Counter, Gauge, Histogram

IMPORT_REQUESTS = Counter(
    "saraise_bank_reconciliation_import_requests_total",
    "Statement import requests and durable outcomes.",
    ("format", "outcome"),
)
IMPORT_DURATION = Histogram(
    "saraise_bank_reconciliation_import_duration_seconds",
    "Statement import execution duration by built-in or registered format.",
    ("format",),
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 900),
)
IMPORT_REJECTED_ROWS = Histogram(
    "saraise_bank_reconciliation_import_rejected_rows",
    "Rejected row count on failed imports.",
    ("format",),
    buckets=(0, 1, 2, 5, 10, 25, 50, 100, 500, 1000, 10000),
)
CANDIDATE_DURATION = Histogram(
    "saraise_bank_reconciliation_candidate_duration_seconds",
    "Candidate generation duration by bounded provider key.",
    ("provider",),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)
CANDIDATE_PROPOSALS = Histogram(
    "saraise_bank_reconciliation_candidate_proposals",
    "Candidate proposal count per deterministic run.",
    ("provider",),
    buckets=(0, 1, 2, 5, 10, 25, 50, 100, 500, 1000, 5000),
)
DETERMINISTIC_MATCHES = Counter(
    "saraise_bank_reconciliation_deterministic_matches_total",
    "Core candidate outcomes at the configured threshold.",
    ("outcome",),
)
WORKFLOW_ACTIONS = Counter(
    "saraise_bank_reconciliation_workflow_actions_total",
    "Financial workflow outcomes by bounded action.",
    ("action", "outcome"),
)
RECONCILIATION_AGE = Histogram(
    "saraise_bank_reconciliation_age_seconds",
    "Age of a reconciliation when measured or finalized.",
    buckets=(60, 300, 900, 3600, 21600, 86400, 259200, 604800, 2592000),
)
ABSOLUTE_DIFFERENCE = Histogram(
    "saraise_bank_reconciliation_absolute_difference",
    "Absolute session difference in account currency units.",
    buckets=(0, 0.01, 0.1, 1, 10, 100, 1000, 10000, 100000, 1000000),
)
API_LATENCY = Histogram(
    "saraise_bank_reconciliation_api_latency_seconds",
    "API latency by normalized route and method.",
    ("route", "method"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
API_ERRORS = Counter(
    "saraise_bank_reconciliation_api_errors_total",
    "API failures by normalized route and stable error code.",
    ("route", "code"),
)
ASYNC_BACKLOG = Gauge(
    "saraise_bank_reconciliation_async_backlog",
    "Current module async job backlog by bounded command.",
    ("command",),
)
ASYNC_FAILURES = Counter(
    "saraise_bank_reconciliation_async_failures_total",
    "Durable module async failures by command and stable code.",
    ("command", "code"),
)
OUTBOX_BACKLOG = Gauge("saraise_bank_reconciliation_outbox_backlog", "Current undispatched module outbox events.")
OUTBOX_FAILURES = Counter(
    "saraise_bank_reconciliation_outbox_failures_total",
    "Outbox dispatch failures by stable code.",
    ("code",),
)

ALLOWED_FORMATS = frozenset({"csv", "ofx", "qif", "bai2", "mt940", "camt053", "manual", "extension"})
ALLOWED_ACTIONS = frozenset({"confirm", "reject", "reverse", "submit_review", "return_to_work", "finalize", "void"})


def bounded_format(value: str) -> str:
    normalized = str(value).lower()
    return normalized if normalized in ALLOWED_FORMATS else "extension"


def bounded_action(value: str) -> str:
    normalized = str(value).lower()
    return normalized if normalized in ALLOWED_ACTIONS else "unknown"


def bounded_label(value: str, maximum: int = 80) -> str:
    """Bound length for registry-defined labels; callers still use route names."""
    return str(value)[:maximum] or "unknown"


__all__ = [
    "ABSOLUTE_DIFFERENCE",
    "API_ERRORS",
    "API_LATENCY",
    "ASYNC_BACKLOG",
    "ASYNC_FAILURES",
    "CANDIDATE_DURATION",
    "CANDIDATE_PROPOSALS",
    "DETERMINISTIC_MATCHES",
    "IMPORT_DURATION",
    "IMPORT_REJECTED_ROWS",
    "IMPORT_REQUESTS",
    "OUTBOX_BACKLOG",
    "OUTBOX_FAILURES",
    "RECONCILIATION_AGE",
    "WORKFLOW_ACTIONS",
    "bounded_action",
    "bounded_format",
    "bounded_label",
]
