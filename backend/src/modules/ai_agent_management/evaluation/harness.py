"""
Core evaluation harness for systematic AI agent quality measurement.

Supports:
- Correctness evaluation (expected vs actual output)
- Hallucination detection (claims not supported by context)
- Latency profiling (p50, p95, p99)
- Token efficiency (output quality per token)
- Safety evaluation (refusal of harmful requests)
- Regression testing (compare baseline vs candidate)
- A/B comparison between model versions

Usage:
    harness = AgentEvaluationHarness()
    suite = EvaluationSuite(
        name="Invoice Agent v2 Regression",
        test_cases=[...],
        metrics=[CorrectnessMetric(), LatencyMetric()],
    )
    results = harness.run(suite)
    harness.report(results)
"""

from __future__ import annotations

import logging
import statistics
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger("saraise.ai.evaluation")


class EvaluationStatus(Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    ERROR = "error"
    SKIP = "skip"


@dataclass
class TestCase:
    """A single evaluation test case."""

    id: str
    name: str
    description: str
    input_messages: list[dict[str, str]]
    expected_output: Optional[str] = None
    expected_contains: Optional[list[str]] = None
    expected_not_contains: Optional[list[str]] = None
    context: Optional[str] = None  # For hallucination checking
    max_latency_ms: Optional[float] = None
    max_tokens: Optional[int] = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MetricResult:
    """Result of a single metric evaluation."""

    metric_name: str
    score: float  # 0.0 to 1.0
    status: EvaluationStatus
    details: str = ""
    raw_value: Any = None


@dataclass
class TestCaseResult:
    """Result of evaluating a single test case."""

    test_case_id: str
    test_case_name: str
    status: EvaluationStatus
    metrics: list[MetricResult] = field(default_factory=list)
    actual_output: str = ""
    latency_ms: float = 0.0
    tokens_used: int = 0
    error: Optional[str] = None


@dataclass
class EvaluationResult:
    """Aggregate result of an evaluation suite."""

    suite_name: str
    total_cases: int
    passed: int
    failed: int
    warnings: int
    errors: int
    skipped: int
    duration_seconds: float
    case_results: list[TestCaseResult] = field(default_factory=list)
    aggregate_metrics: dict[str, float] = field(default_factory=dict)

    @property
    def pass_rate(self) -> float:
        if self.total_cases == 0:
            return 0.0
        return self.passed / self.total_cases

    @property
    def overall_status(self) -> EvaluationStatus:
        if self.errors > 0:
            return EvaluationStatus.ERROR
        if self.failed > 0:
            return EvaluationStatus.FAIL
        if self.warnings > 0:
            return EvaluationStatus.WARN
        return EvaluationStatus.PASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "overall_status": self.overall_status.value,
            "pass_rate": round(self.pass_rate, 4),
            "total_cases": self.total_cases,
            "passed": self.passed,
            "failed": self.failed,
            "warnings": self.warnings,
            "errors": self.errors,
            "duration_seconds": round(self.duration_seconds, 2),
            "aggregate_metrics": self.aggregate_metrics,
        }


@dataclass
class EvaluationSuite:
    """A collection of test cases with metrics to evaluate."""

    name: str
    test_cases: list[TestCase]
    metrics: list[Any]  # List of metric instances
    description: str = ""
    tags: list[str] = field(default_factory=list)
    # Thresholds
    min_pass_rate: float = 0.9  # 90% pass rate required
    max_p95_latency_ms: float = 5000.0


class AgentEvaluationHarness:
    """
    Core evaluation harness for SARAISE AI agents.

    Orchestrates test execution, metric evaluation, and result aggregation.
    """

    def __init__(
        self,
        agent_callable: Optional[Callable] = None,
    ) -> None:
        """
        Initialize harness.

        Args:
            agent_callable: Function that takes messages and returns response string.
                           Signature: (messages: list[dict]) -> str
        """
        self._agent_callable = agent_callable

    def set_agent(self, agent_callable: Callable) -> None:
        """Set or change the agent under test."""
        self._agent_callable = agent_callable

    def run(self, suite: EvaluationSuite) -> EvaluationResult:
        """Run all test cases in the suite and return aggregate results."""
        if not self._agent_callable:
            raise ValueError("No agent callable set. Use set_agent() first.")

        logger.info("Starting evaluation suite: %s (%d cases)", suite.name, len(suite.test_cases))
        start_time = time.monotonic()

        case_results: list[TestCaseResult] = []
        passed = failed = warnings = errors = skipped = 0

        for tc in suite.test_cases:
            try:
                result = self._evaluate_case(tc, suite.metrics)
                case_results.append(result)

                if result.status == EvaluationStatus.PASS:
                    passed += 1
                elif result.status == EvaluationStatus.FAIL:
                    failed += 1
                elif result.status == EvaluationStatus.WARN:
                    warnings += 1
                elif result.status == EvaluationStatus.ERROR:
                    errors += 1
                else:
                    skipped += 1

            except Exception as exc:
                logger.error("Error evaluating case %s: %s", tc.id, exc)
                case_results.append(
                    TestCaseResult(
                        test_case_id=tc.id,
                        test_case_name=tc.name,
                        status=EvaluationStatus.ERROR,
                        error=str(exc),
                    )
                )
                errors += 1

        duration = time.monotonic() - start_time

        # Compute aggregate metrics
        aggregate = self._compute_aggregates(case_results)

        result = EvaluationResult(
            suite_name=suite.name,
            total_cases=len(suite.test_cases),
            passed=passed,
            failed=failed,
            warnings=warnings,
            errors=errors,
            skipped=skipped,
            duration_seconds=duration,
            case_results=case_results,
            aggregate_metrics=aggregate,
        )

        logger.info(
            "Suite '%s' complete: %d/%d passed (%.1f%%) in %.2fs",
            suite.name,
            passed,
            len(suite.test_cases),
            result.pass_rate * 100,
            duration,
        )

        return result

    def run_regression(
        self,
        suite: EvaluationSuite,
        baseline_results: EvaluationResult,
    ) -> dict[str, Any]:
        """
        Run regression test: compare current results against baseline.

        Returns comparison with per-metric deltas.
        """
        current = self.run(suite)

        comparison = {
            "baseline_pass_rate": baseline_results.pass_rate,
            "current_pass_rate": current.pass_rate,
            "pass_rate_delta": current.pass_rate - baseline_results.pass_rate,
            "regression_detected": current.pass_rate < baseline_results.pass_rate,
            "metric_deltas": {},
        }

        for metric_name in current.aggregate_metrics:
            baseline_val = baseline_results.aggregate_metrics.get(metric_name, 0.0)
            current_val = current.aggregate_metrics[metric_name]
            comparison["metric_deltas"][metric_name] = {
                "baseline": baseline_val,
                "current": current_val,
                "delta": current_val - baseline_val,
            }

        return comparison

    def _evaluate_case(
        self,
        tc: TestCase,
        metrics: list[Any],
    ) -> TestCaseResult:
        """Evaluate a single test case against all metrics."""
        # Call agent
        start = time.monotonic()
        try:
            actual_output = self._agent_callable(tc.input_messages)
        except Exception as exc:
            return TestCaseResult(
                test_case_id=tc.id,
                test_case_name=tc.name,
                status=EvaluationStatus.ERROR,
                error=f"Agent call failed: {exc}",
            )
        latency_ms = (time.monotonic() - start) * 1000

        # Evaluate each metric
        metric_results: list[MetricResult] = []
        for metric in metrics:
            try:
                mr = metric.evaluate(tc, actual_output, latency_ms)
                metric_results.append(mr)
            except Exception as exc:
                metric_results.append(
                    MetricResult(
                        metric_name=type(metric).__name__,
                        score=0.0,
                        status=EvaluationStatus.ERROR,
                        details=f"Metric evaluation failed: {exc}",
                    )
                )

        # Determine overall status
        if any(m.status == EvaluationStatus.FAIL for m in metric_results):
            status = EvaluationStatus.FAIL
        elif any(m.status == EvaluationStatus.WARN for m in metric_results):
            status = EvaluationStatus.WARN
        else:
            status = EvaluationStatus.PASS

        return TestCaseResult(
            test_case_id=tc.id,
            test_case_name=tc.name,
            status=status,
            metrics=metric_results,
            actual_output=actual_output,
            latency_ms=latency_ms,
        )

    def _compute_aggregates(
        self,
        results: list[TestCaseResult],
    ) -> dict[str, float]:
        """Compute aggregate metrics across all test cases."""
        if not results:
            return {}

        aggregates: dict[str, list[float]] = {}
        latencies = []

        for r in results:
            if r.latency_ms > 0:
                latencies.append(r.latency_ms)
            for m in r.metrics:
                if m.metric_name not in aggregates:
                    aggregates[m.metric_name] = []
                aggregates[m.metric_name].append(m.score)

        result = {}
        for name, scores in aggregates.items():
            result[f"{name}_mean"] = round(statistics.mean(scores), 4)
            if len(scores) > 1:
                result[f"{name}_stdev"] = round(statistics.stdev(scores), 4)

        if latencies:
            sorted_lat = sorted(latencies)
            result["latency_p50_ms"] = round(sorted_lat[len(sorted_lat) // 2], 2)
            result["latency_p95_ms"] = round(sorted_lat[int(len(sorted_lat) * 0.95)], 2)
            result["latency_p99_ms"] = round(sorted_lat[int(len(sorted_lat) * 0.99)], 2)

        return result

    def report(self, result: EvaluationResult) -> str:
        """Generate a human-readable evaluation report."""
        lines = [
            f"=== Evaluation Report: {result.suite_name} ===",
            f"Status: {result.overall_status.value.upper()}",
            f"Pass Rate: {result.pass_rate:.1%} ({result.passed}/{result.total_cases})",
            f"Duration: {result.duration_seconds:.2f}s",
            "",
            "Aggregate Metrics:",
        ]

        for name, value in sorted(result.aggregate_metrics.items()):
            lines.append(f"  {name}: {value}")

        if result.failed > 0:
            lines.append("")
            lines.append("Failed Cases:")
            for cr in result.case_results:
                if cr.status == EvaluationStatus.FAIL:
                    lines.append(f"  - {cr.test_case_id}: {cr.test_case_name}")
                    for m in cr.metrics:
                        if m.status == EvaluationStatus.FAIL:
                            lines.append(f"    {m.metric_name}: {m.details}")

        report_text = "\n".join(lines)
        logger.info(report_text)
        return report_text
