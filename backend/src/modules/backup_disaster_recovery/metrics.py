"""Low-cardinality Prometheus metrics for disaster-recovery operations."""

from prometheus_client import Counter, Gauge, Histogram

BDR_BACKUP_REQUESTS = Counter(
    "bdr_backup_requests_total",
    "Backup execution requests by durable outcome.",
    ("result",),
)
BDR_RECOVERY_POINTS = Gauge(
    "bdr_recovery_points_total",
    "Current recovery points by lifecycle state.",
    ("status",),
)
BDR_RESTORE_RUNS = Gauge(
    "bdr_restore_runs_total",
    "Current restore runs by lifecycle state and target class.",
    ("status", "target_environment"),
)
BDR_RESTORE_DURATION = Histogram(
    "bdr_restore_duration_seconds",
    "End-to-end restore execution duration.",
)
BDR_EXERCISES = Gauge(
    "bdr_exercises_total",
    "Current disaster-recovery exercises by state and type.",
    ("status", "type"),
)
BDR_EXERCISE_DURATION = Histogram(
    "bdr_exercise_duration_seconds",
    "End-to-end disaster-recovery exercise duration.",
)
BDR_RPO_BREACHES = Counter("bdr_rpo_breaches_total", "Measured recovery-point-objective breaches.")
BDR_RTO_BREACHES = Counter("bdr_rto_breaches_total", "Measured recovery-time-objective breaches.")
BDR_PROVIDER_FAILURES = Counter(
    "bdr_provider_failures_total",
    "Sanitized provider failures by adapter and stable error class.",
    ("adapter", "error_class"),
)
BDR_JOB_QUEUE_DELAY = Histogram(
    "bdr_job_queue_delay_seconds",
    "Delay from durable enqueue to worker claim.",
)

# Descriptive aliases keep the public metric names easy to discover while the
# uppercase names follow Python constant conventions.
bdr_backup_requests_total = BDR_BACKUP_REQUESTS
bdr_recovery_points_total = BDR_RECOVERY_POINTS
bdr_restore_runs_total = BDR_RESTORE_RUNS
bdr_restore_duration_seconds = BDR_RESTORE_DURATION
bdr_exercises_total = BDR_EXERCISES
bdr_exercise_duration_seconds = BDR_EXERCISE_DURATION
bdr_rpo_breaches_total = BDR_RPO_BREACHES
bdr_rto_breaches_total = BDR_RTO_BREACHES
bdr_provider_failures_total = BDR_PROVIDER_FAILURES
bdr_job_queue_delay_seconds = BDR_JOB_QUEUE_DELAY

__all__ = [name for name in globals() if name.startswith("BDR_") or name.startswith("bdr_")]
