#!/usr/bin/env python3
"""
SPDX-License-Identifier: Apache-2.0
===================================
SARAISE GCR Entity Population Script
===================================
Registers all modules, endpoints, and artifacts in GCR
===================================
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

# Paths
REPO_ROOT = Path(__file__).parent.parent
DOCS_ROOT = REPO_ROOT.parent / "saraise-documentation"
GCR_ROOT = DOCS_ROOT / ".governance" / "entities"

# Module definitions
BACKEND_MODULES = [
    {
        "id": "mod:crm",
        "name": "CRM Module",
        "path": "backend/src/modules/crm",
        "tier": "tier2",
        "owner": "@saraise/backend-team",
    },
    {
        "id": "mod:platform_management",
        "name": "Platform Management",
        "path": "backend/src/modules/platform_management",
        "tier": "tier1",
        "owner": "@saraise/platform-owners",
    },
    {
        "id": "mod:tenant_management",
        "name": "Tenant Management",
        "path": "backend/src/modules/tenant_management",
        "tier": "tier1",
        "owner": "@saraise/platform-owners",
    },
    {
        "id": "mod:security_access_control",
        "name": "Security Access Control",
        "path": "backend/src/modules/security_access_control",
        "tier": "tier0",
        "owner": "@saraise/security-team",
    },
    {
        "id": "mod:ai_agent_management",
        "name": "AI Agent Management",
        "path": "backend/src/modules/ai_agent_management",
        "tier": "tier2",
        "owner": "@saraise/backend-team",
    },
    {
        "id": "mod:ai_provider_configuration",
        "name": "AI Provider Configuration",
        "path": "backend/src/modules/ai_provider_configuration",
        "tier": "tier2",
        "owner": "@saraise/backend-team",
    },
    {
        "id": "mod:workflow_automation",
        "name": "Workflow Automation",
        "path": "backend/src/modules/workflow_automation",
        "tier": "tier2",
        "owner": "@saraise/backend-team",
    },
    {
        "id": "mod:api_management",
        "name": "API Management",
        "path": "backend/src/modules/api_management",
        "tier": "tier1",
        "owner": "@saraise/platform-owners",
    },
    {
        "id": "mod:billing_subscriptions",
        "name": "Billing Subscriptions",
        "path": "backend/src/modules/billing_subscriptions",
        "tier": "tier1",
        "owner": "@saraise/platform-owners",
    },
    {
        "id": "mod:metadata_modeling",
        "name": "Metadata Modeling",
        "path": "backend/src/modules/metadata_modeling",
        "tier": "tier2",
        "owner": "@saraise/backend-team",
    },
    {
        "id": "mod:customization_framework",
        "name": "Customization Framework",
        "path": "backend/src/modules/customization_framework",
        "tier": "tier2",
        "owner": "@saraise/backend-team",
    },
    {
        "id": "mod:data_migration",
        "name": "Data Migration",
        "path": "backend/src/modules/data_migration",
        "tier": "tier2",
        "owner": "@saraise/backend-team",
    },
    {
        "id": "mod:dms",
        "name": "Document Management System",
        "path": "backend/src/modules/dms",
        "tier": "tier2",
        "owner": "@saraise/backend-team",
    },
    {
        "id": "mod:backup_disaster_recovery",
        "name": "Backup Disaster Recovery",
        "path": "backend/src/modules/backup_disaster_recovery",
        "tier": "tier1",
        "owner": "@saraise/platform-ops",
    },
    {
        "id": "mod:backup_recovery",
        "name": "Backup Recovery",
        "path": "backend/src/modules/backup_recovery",
        "tier": "tier1",
        "owner": "@saraise/platform-ops",
    },
    {
        "id": "mod:performance_monitoring",
        "name": "Performance Monitoring",
        "path": "backend/src/modules/performance_monitoring",
        "tier": "tier1",
        "owner": "@saraise/platform-ops",
    },
    {
        "id": "mod:localization",
        "name": "Localization",
        "path": "backend/src/modules/localization",
        "tier": "tier2",
        "owner": "@saraise/backend-team",
    },
    {
        "id": "mod:regional",
        "name": "Regional",
        "path": "backend/src/modules/regional",
        "tier": "tier2",
        "owner": "@saraise/backend-team",
    },
    {
        "id": "mod:integration_platform",
        "name": "Integration Platform",
        "path": "backend/src/modules/integration_platform",
        "tier": "tier1",
        "owner": "@saraise/platform-owners",
    },
    {
        "id": "mod:automation_orchestration",
        "name": "Automation Orchestration",
        "path": "backend/src/modules/automation_orchestration",
        "tier": "tier2",
        "owner": "@saraise/backend-team",
    },
    {
        "id": "mod:document_intelligence",
        "name": "Document Intelligence",
        "path": "backend/src/modules/document_intelligence",
        "tier": "tier2",
        "owner": "@saraise/backend-team",
    },
    {
        "id": "mod:process_mining",
        "name": "Process Mining",
        "path": "backend/src/modules/process_mining",
        "tier": "tier2",
        "owner": "@saraise/backend-team",
    },
    {
        "id": "mod:blockchain_traceability",
        "name": "Blockchain Traceability",
        "path": "backend/src/modules/blockchain_traceability",
        "tier": "tier2",
        "owner": "@saraise/backend-team",
    },
]

FRONTEND_MODULES = [
    {
        "id": "mod-frontend:crm",
        "name": "CRM Module (Frontend)",
        "path": "frontend/src/modules/crm",
        "tier": "tier2",
        "owner": "@saraise/frontend-team",
    },
    # Add other frontend modules as needed
]

# Core infrastructure (Tier 0)
CORE_ARTIFACTS = [
    {
        "id": "core:auth_middleware",
        "name": "Mode-Aware Session Middleware",
        "path": "backend/src/core/auth/middleware.py",
        "tier": "tier0",
        "owner": "@saraise/security-team",
    },
    {
        "id": "core:auth_mode",
        "name": "Authentication Mode Detection",
        "path": "backend/src/core/auth/mode.py",
        "tier": "tier0",
        "owner": "@saraise/security-team",
    },
    {
        "id": "core:auth_saas",
        "name": "SaaS Authentication Delegation",
        "path": "backend/src/core/auth/saas.py",
        "tier": "tier0",
        "owner": "@saraise/security-team",
    },
    {
        "id": "core:authentication",
        "name": "Authentication Core",
        "path": "backend/src/core/authentication.py",
        "tier": "tier0",
        "owner": "@saraise/security-team",
    },
    {
        "id": "core:licensing",
        "name": "Licensing Subsystem",
        "path": "backend/src/core/licensing",
        "tier": "tier0",
        "owner": "@saraise/platform-owners",
    },
    {
        "id": "core:encryption",
        "name": "Encryption Service",
        "path": "backend/src/core/encryption",
        "tier": "tier0",
        "owner": "@saraise/security-team",
    },
]


def create_entity_file(entity: Dict, entity_type: str):
    """Create entity YAML file in GCR."""
    entity_dir = GCR_ROOT / entity_type
    entity_dir.mkdir(parents=True, exist_ok=True)
    
    entity_file = entity_dir / f"{entity['id']}.yaml"
    
    entity_data = {
        "id": entity["id"],
        "type": entity_type,
        "name": entity["name"],
        "repository": "saraise-application",
        "path": entity["path"],
        "tier": entity["tier"],
        "owner": entity["owner"],
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    
    # Convert to YAML format
    yaml_content = f"""# SPDX-License-Identifier: PROPRIETARY
# Auto-generated by populate-gcr-entities.py
# Do not edit manually - regenerate to update

id: {entity_data['id']}
type: {entity_data['type']}
name: {entity_data['name']}
repository: {entity_data['repository']}
path: {entity_data['path']}
tier: {entity_data['tier']}
owner: {entity_data['owner']}
created_at: {entity_data['created_at']}
updated_at: {entity_data['updated_at']}
"""
    
    entity_file.write_text(yaml_content)
    print(f"✅ Created: {entity_file.relative_to(DOCS_ROOT)}")


def main():
    """Main entry point."""
    if not DOCS_ROOT.exists():
        print(f"❌ Documentation root not found: {DOCS_ROOT}")
        print("   Make sure saraise-documentation repository is available")
        sys.exit(1)
    
    print("📝 Populating GCR entities...")
    print("=" * 60)
    
    # Register backend modules
    print("\n📦 Backend Modules:")
    for module in BACKEND_MODULES:
        module_path = REPO_ROOT / module["path"]
        if module_path.exists():
            create_entity_file(module, "module")
        else:
            print(f"⚠️  Skipping (not found): {module['path']}")
    
    # Register frontend modules
    print("\n📦 Frontend Modules:")
    for module in FRONTEND_MODULES:
        module_path = REPO_ROOT / module["path"]
        if module_path.exists():
            create_entity_file(module, "module")
        else:
            print(f"⚠️  Skipping (not found): {module['path']}")
    
    # Register core artifacts
    print("\n🔒 Core Artifacts (Tier 0):")
    for artifact in CORE_ARTIFACTS:
        artifact_path = REPO_ROOT / artifact["path"]
        if artifact_path.exists() or artifact_path.is_dir():
            create_entity_file(artifact, "artifact")
        else:
            print(f"⚠️  Skipping (not found): {artifact['path']}")
    
    print("\n✅ GCR entity population complete")
    print(f"   Entities stored in: {GCR_ROOT.relative_to(DOCS_ROOT)}")


if __name__ == "__main__":
    main()
