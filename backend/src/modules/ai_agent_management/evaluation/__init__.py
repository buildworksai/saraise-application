"""
AI Agent Evaluation and Testing Framework.

Provides systematic quality measurement, regression testing,
and automated red-teaming for SARAISE AI agents.
"""

from .harness import (
    AgentEvaluationHarness,
    EvaluationResult,
    EvaluationStatus,
    EvaluationSuite,
    MetricResult,
    TestCase,
    TestCaseResult,
)
from .metrics import (
    CorrectnessMetric,
    HallucinationMetric,
    LatencyMetric,
    SafetyMetric,
    TokenEfficiencyMetric,
)
from .red_team import AttackCategory, AttackVector, RedTeamResult, RedTeamRunner

__all__ = [
    "AgentEvaluationHarness",
    "EvaluationResult",
    "EvaluationSuite",
    "TestCase",
    "TestCaseResult",
    "MetricResult",
    "EvaluationStatus",
    "CorrectnessMetric",
    "HallucinationMetric",
    "LatencyMetric",
    "TokenEfficiencyMetric",
    "SafetyMetric",
    "RedTeamRunner",
    "AttackVector",
    "RedTeamResult",
    "AttackCategory",
]
