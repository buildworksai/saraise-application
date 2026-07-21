"""Low-cardinality Prometheus telemetry for orchestration operations."""

from prometheus_client import Counter, Gauge, Histogram

RUNS = Counter(
    "saraise_orchestration_runs_total",
    "Orchestration runs by lifecycle outcome.",
    ("outcome",),
)
TASKS = Counter(
    "saraise_orchestration_tasks_total",
    "Orchestration task state transitions.",
    ("transition",),
)
RETRIES = Counter(
    "saraise_orchestration_retries_total",
    "Orchestration retry outcomes.",
    ("outcome",),
)
NODE_EXECUTIONS = Counter(
    "saraise_orchestration_node_executions_total",
    "Node executions by stable handler key and outcome.",
    ("handler", "outcome"),
)
DEPENDENCY_FAILURES = Counter(
    "saraise_orchestration_dependency_failures_total",
    "Dependency failures without tenant labels.",
    ("dependency", "reason"),
)
RUN_DURATION = Histogram(
    "saraise_orchestration_run_duration_seconds",
    "Wall-clock duration of terminal orchestration runs.",
)
TASK_DURATION = Histogram(
    "saraise_orchestration_task_duration_seconds",
    "Wall-clock duration of physical node attempts.",
)
TASK_QUEUE_WAIT = Histogram(
    "saraise_orchestration_task_queue_wait_seconds",
    "Delay between an attempt becoming available and starting.",
)
SCHEDULE_LAG = Histogram(
    "saraise_orchestration_schedule_lag_seconds",
    "Delay between scheduled and claimed execution.",
)
ACTIVE_RUNS = Gauge(
    "saraise_orchestration_active_runs",
    "Current active orchestration runs across the runtime.",
)

__all__ = [
    "ACTIVE_RUNS",
    "DEPENDENCY_FAILURES",
    "NODE_EXECUTIONS",
    "RETRIES",
    "RUNS",
    "RUN_DURATION",
    "SCHEDULE_LAG",
    "TASKS",
    "TASK_DURATION",
    "TASK_QUEUE_WAIT",
]
