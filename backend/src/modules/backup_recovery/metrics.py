"""Low-cardinality Prometheus metrics for backup-recovery operations."""

from prometheus_client import Counter, Gauge, Histogram

BACKUP_REQUESTS = Counter("saraise_backup_requests_total", "Durable backup requests", ("backup_type", "scope_type"))
BACKUP_OUTCOMES = Counter(
    "saraise_backup_outcomes_total",
    "Terminal backup outcomes",
    ("status", "adapter_key", "error_code"),
)
BACKUP_DURATION = Histogram(
    "saraise_backup_duration_seconds", "Backup execution duration", ("adapter_key", "backup_type")
)
BACKUP_SIZE = Histogram(
    "saraise_backup_size_bytes",
    "Captured artifact sizes",
    ("adapter_key", "backup_type"),
    buckets=(0, 1024, 1024**2, 10 * 1024**2, 100 * 1024**2, 1024**3, 10 * 1024**3),
)
VERIFICATION_OUTCOMES = Counter(
    "saraise_backup_verification_outcomes_total",
    "Artifact verification outcomes",
    ("status", "adapter_key"),
)
ARTIFACT_EXPIRY = Counter("saraise_backup_artifact_expiry_total", "Artifacts moved to expired lifecycle")
PURGE_FAILURES = Counter(
    "saraise_backup_purge_failures_total",
    "Provider-side artifact purge failures",
    ("adapter_key", "error_code"),
)
SCHEDULE_LAG = Histogram("saraise_backup_schedule_lag_seconds", "Delay between due time and schedule claim")
ADAPTER_HEALTH = Gauge(
    "saraise_backup_adapter_healthy", "Configured adapter health (1 healthy, 0 degraded)", ("adapter_key",)
)
