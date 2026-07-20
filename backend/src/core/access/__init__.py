"""Fail-closed access-control primitives for SARAISE runtime execution.

SPDX-License-Identifier: Apache-2.0

The package intentionally exposes the decision pipeline without importing its
Django models at module import time.  This keeps ``import src.core.access`` safe
for tooling while Django discovers the entitlement and quota models through
``src.core.models``.
"""

from .decision import (
    AccessDecision,
    AccessDecisionPipeline,
    AccessReasonCode,
    HttpPolicyEvaluator,
    PolicyEvaluation,
)
from .permissions import RequiresAccess

__all__ = [
    "AccessDecision",
    "AccessDecisionPipeline",
    "AccessReasonCode",
    "HttpPolicyEvaluator",
    "PolicyEvaluation",
    "RequiresAccess",
]
