"""Deterministic, durable evaluation and red-team evidence tests."""

from __future__ import annotations

import pytest

from src.core.async_jobs.models import AsyncJob, JobStatus
from src.modules.ai_agent_management.evaluation.harness import (
    AgentEvaluationHarness,
    EvaluationResult,
    EvaluationStatus,
    EvaluationSuite,
)
from src.modules.ai_agent_management.evaluation.harness import TestCase as EvaluationCase
from src.modules.ai_agent_management.evaluation.metrics import CorrectnessMetric
from src.modules.ai_agent_management.evaluation.red_team import (
    AttackCategory,
    AttackVector,
    RedTeamResult,
    RedTeamRunner,
)
from src.modules.ai_agent_management.registries import evaluation_registry, runner_registry
from src.modules.ai_agent_management.services import AgentServiceError, EvaluationService


def _suite(expected: str = "approved") -> EvaluationSuite:
    return EvaluationSuite(
        name="deterministic-suite",
        test_cases=[
            EvaluationCase(
                id="case-1",
                name="exact output",
                description="stable evaluation input",
                input_messages=[{"role": "user", "content": "evaluate"}],
                expected_output=expected,
            )
        ],
        metrics=[CorrectnessMetric()],
    )


def test_deterministic_metric_produces_repeatable_evidence():
    harness = AgentEvaluationHarness(lambda messages: "approved")
    first = harness.run(_suite())
    second = harness.run(_suite())
    assert first.overall_status is EvaluationStatus.PASS
    assert second.overall_status is EvaluationStatus.PASS
    assert first.pass_rate == second.pass_rate == 1.0
    assert first.aggregate_metrics["correctness_mean"] == second.aggregate_metrics["correctness_mean"] == 1.0


def test_regression_delta_detects_a_candidate_quality_drop():
    baseline_harness = AgentEvaluationHarness(lambda messages: "approved")
    baseline = baseline_harness.run(_suite())
    candidate = AgentEvaluationHarness(lambda messages: "rejected")
    comparison = candidate.run_regression(_suite(), baseline)
    assert comparison["regression_detected"] is True
    assert comparison["pass_rate_delta"] == -1.0
    assert comparison["metric_deltas"]["correctness_mean"]["delta"] < 0


def test_empty_or_all_error_suite_cannot_fabricate_a_pass():
    empty = EvaluationResult(
        suite_name="empty",
        total_cases=0,
        passed=0,
        failed=0,
        warnings=0,
        errors=0,
        skipped=0,
        duration_seconds=0,
    )
    assert empty.pass_rate == 0
    assert empty.overall_status is not EvaluationStatus.PASS

    class BrokenMetric:
        def evaluate(self, *args):
            raise RuntimeError("provider response must not leak")

    suite = _suite()
    suite.metrics = [BrokenMetric()]
    result = AgentEvaluationHarness(lambda messages: "approved").run(suite)
    assert result.case_results[0].status is EvaluationStatus.ERROR
    assert result.overall_status is EvaluationStatus.ERROR


def test_red_team_empty_and_agent_error_are_not_counted_as_blocked_success():
    empty = RedTeamResult(total_attacks=0, attacks_blocked=0, attacks_succeeded=0)
    assert empty.block_rate == 0
    assert empty.passed is False

    vector = AttackVector(
        id="exception-vector",
        name="exception path",
        description="provider failure is unavailable, not proof of blocking",
        category=AttackCategory.PROMPT_INJECTION,
        payload=[{"role": "user", "content": "test"}],
        success_indicators=["unsafe"],
        severity="HIGH",
    )

    def unavailable_agent(messages):
        raise RuntimeError("dependency unavailable")

    result = RedTeamRunner(unavailable_agent, [vector]).run()
    assert result.attacks_blocked == 0
    assert result.passed is False
    assert result.results[0].status is EvaluationStatus.ERROR


@pytest.mark.django_db
def test_missing_suite_or_runner_is_explicitly_unavailable(agent, actor_id):
    evaluation_registry.unregister("missing.suite")
    runner_registry.unregister(agent.runner_key)
    missing_suite = EvaluationService.start_evaluation(
        agent.tenant_id,
        actor_id,
        agent.id,
        "missing.suite",
        "eval:missing-suite",
    )
    assert missing_suite.status == "unavailable"
    assert missing_suite.http_status == 503
    assert not AsyncJob.objects.filter(tenant_id=agent.tenant_id).exists()

    evaluation_registry.register("missing.suite", lambda **kwargs: {"status": "passed", "metrics": []})
    try:
        missing_runner = EvaluationService.start_evaluation(
            agent.tenant_id,
            actor_id,
            agent.id,
            "missing.suite",
            "eval:missing-runner",
        )
    finally:
        evaluation_registry.unregister("missing.suite")
    assert missing_runner.status == "unavailable"
    assert "runner" in missing_runner.detail["capability"]
    assert not AsyncJob.objects.filter(tenant_id=agent.tenant_id).exists()


@pytest.mark.django_db
def test_evaluation_job_persists_typed_result_evidence(
    agent,
    actor_id,
    registered_runner,
    registered_evaluation_suite,
):
    accepted = EvaluationService.start_evaluation(
        agent.tenant_id,
        actor_id,
        agent.id,
        "test.suite",
        "eval:one",
    )
    job = accepted.unwrap()
    assert job.command == "ai_agent_management.evaluate"
    assert job.payload == {"agent_id": str(agent.id), "suite_key": "test.suite"}

    result = EvaluationService.run_evaluation_job(agent.tenant_id, job.id)
    job.refresh_from_db()
    assert result["status"] == "passed"
    assert result["metrics"][0]["name"] == "determinism"
    assert job.result == result
    assert job.status == "succeeded"


@pytest.mark.django_db
def test_evaluation_job_exception_transitions_job_to_failed(agent, actor_id, registered_runner):
    evaluation_registry.unregister("raising.suite")
    evaluation_registry.register("raising.suite", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    try:
        job = EvaluationService.start_evaluation(
            agent.tenant_id,
            actor_id,
            agent.id,
            "raising.suite",
            "eval:raises",
        ).unwrap()
        with pytest.raises(RuntimeError, match="boom"):
            EvaluationService.run_evaluation_job(agent.tenant_id, job.id)
    finally:
        evaluation_registry.unregister("raising.suite")
    job.refresh_from_db()
    assert job.status == JobStatus.FAILED
    assert job.error_message == "Evaluation suite failed."


@pytest.mark.django_db
def test_evaluation_job_skips_lifecycle_transitions_when_not_owned(
    agent, actor_id, registered_runner, registered_evaluation_suite
):
    accepted = EvaluationService.start_evaluation(
        agent.tenant_id,
        actor_id,
        agent.id,
        "test.suite",
        "eval:not-owned",
    )
    job = accepted.unwrap()
    AsyncJob._base_manager.filter(pk=job.pk).update(status=JobStatus.RUNNING)

    result = EvaluationService.run_evaluation_job(agent.tenant_id, job.id)
    job.refresh_from_db()
    assert result["status"] == "passed"
    # The worker did not own the lifecycle (job was already RUNNING, not QUEUED
    # when claimed), so this call must not transition it to SUCCEEDED itself.
    assert job.status == JobStatus.RUNNING
    assert job.result != result


@pytest.mark.django_db
def test_evaluation_job_invalid_result_not_owned_does_not_transition(agent, actor_id, registered_runner):
    evaluation_registry.unregister("invalid.not-owned")
    evaluation_registry.register("invalid.not-owned", lambda **kwargs: {"message": "no metric evidence"})
    try:
        job = EvaluationService.start_evaluation(
            agent.tenant_id,
            actor_id,
            agent.id,
            "invalid.not-owned",
            "eval:invalid-not-owned",
        ).unwrap()
        AsyncJob._base_manager.filter(pk=job.pk).update(status=JobStatus.RUNNING)
        with pytest.raises(AgentServiceError) as caught:
            EvaluationService.run_evaluation_job(agent.tenant_id, job.id)
    finally:
        evaluation_registry.unregister("invalid.not-owned")
    assert caught.value.code == "INVALID_EVALUATION_RESULT"
    job.refresh_from_db()
    assert job.status == JobStatus.RUNNING


@pytest.mark.django_db
def test_start_red_team_requires_suite_and_runner_and_persists_isolation_flag(
    agent, actor_id, registered_runner, registered_evaluation_suite
):
    evaluation_registry.unregister("missing.red-team-suite")
    missing_suite = EvaluationService.start_red_team(
        agent.tenant_id,
        actor_id,
        agent.id,
        "missing.red-team-suite",
        "red-team:missing-suite",
    )
    assert missing_suite.status == "unavailable"
    assert "evaluation_suite" in missing_suite.detail["capability"]
    assert not AsyncJob.objects.filter(tenant_id=agent.tenant_id).exists()

    runner_registry.unregister(agent.runner_key)
    missing_runner = EvaluationService.start_red_team(
        agent.tenant_id,
        actor_id,
        agent.id,
        "test.suite",
        "red-team:missing-runner",
    )
    assert missing_runner.status == "unavailable"
    assert "runner" in missing_runner.detail["capability"]
    assert not AsyncJob.objects.filter(tenant_id=agent.tenant_id).exists()

    runner_registry.register("test.runner", registered_runner)
    accepted = EvaluationService.start_red_team(
        agent.tenant_id,
        actor_id,
        agent.id,
        "test.suite",
        "red-team:one",
    )
    job = accepted.unwrap()
    assert job.command == "ai_agent_management.red_team"
    assert job.payload == {"agent_id": str(agent.id), "suite_key": "test.suite", "isolated": True}
    assert accepted.evidence == {"async_job_id": str(job.id), "suite_key": "test.suite"}


@pytest.mark.django_db
def test_invalid_suite_payload_is_failure_not_success(agent, actor_id, registered_runner):
    evaluation_registry.unregister("invalid.suite")
    evaluation_registry.register("invalid.suite", lambda **kwargs: {"message": "no metric evidence"})
    try:
        job = EvaluationService.start_evaluation(
            agent.tenant_id,
            actor_id,
            agent.id,
            "invalid.suite",
            "eval:invalid",
        ).unwrap()
        with pytest.raises(AgentServiceError) as caught:
            EvaluationService.run_evaluation_job(agent.tenant_id, job.id)
    finally:
        evaluation_registry.unregister("invalid.suite")
    assert caught.value.code == "INVALID_EVALUATION_RESULT"
