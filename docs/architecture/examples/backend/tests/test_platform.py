# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Platform Testing with Policy Engine
# backend/tests/modules/platform/test_platform.py
# Reference: docs/architecture/policy-engine-spec.md § 4

import pytest
from django.db import transaction
from src.modules.platform.services.platform_config_service import PlatformConfigService
from src.modules.platform.services.platform_health_service import PlatformHealthService
from src.core.policy_engine import PolicyEngine

@pytest.mark.django_db
def test_platform_settings_authorized(
    platform_owner_user,
    policy_engine: PolicyEngine
):
    # ✅ CORRECT: Django ORM - use Model.objects directly, no Session parameter needed
    """Test platform settings via Policy Engine authorization.
    
    Policy Engine evaluates platform_owner permissions at request time.
    See docs/architecture/policy-engine-spec.md § 1, § 4.
    """
    # Service receives tenant_id=None for platform operations
    service = PlatformConfigService(tenant_id=None)

    # Authorization check via Policy Engine
    decision = policy_engine.evaluate(
        user_id=platform_owner_user.id,
        tenant_id=None,  # Platform operation
        resource="platform.settings",
        action="update",
        context={"setting_key": "test_key"}
    )
    assert decision.allowed, "Platform owner should be authorized"

    # Set setting
    service.set_setting("test_key", {"value": "test_value"})

    # Get setting
    value = service.get_setting("test_key")
    assert value == {"value": "test_value"}

@pytest.mark.django_db
def test_platform_health(
    platform_operator_user,
    policy_engine: PolicyEngine
):
    # ✅ CORRECT: Django ORM - use Model.objects directly, no Session parameter needed
    """Test platform health check via Policy Engine.
    
    Platform operators can view health metrics.
    """
    # Authorization check
    decision = policy_engine.evaluate(
        user_id=platform_operator_user.id,
        tenant_id=None,  # Platform operation
        resource="platform.health",
        action="read",
        context={}
    )
    assert decision.allowed, "Platform operator should be authorized"

    service = PlatformHealthService(tenant_id=None)
    health = service.get_platform_health()

    assert health["status"] in ["healthy", "degraded"]
    assert "services" in health
    assert "metrics" in health

