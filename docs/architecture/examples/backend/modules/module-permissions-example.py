# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Module Permission Structure
# backend/src/modules/module_name/permissions.py
# Reference: docs/architecture/module-framework.md § 3 (Module Permissions)
# Also: docs/architecture/policy-engine-spec.md § 2 (Permission System)
# 
# CRITICAL NOTES:
# - Permissions defined in module's manifest.yaml (not hardcoded)
# - Policy Engine evaluates ALL authorization decisions per-request
# - Permission names follow pattern: {module}.{resource}:{action}
# - Roles combine multiple permissions (role = set of permissions)

from typing import Dict, List

MODULE_PERMISSIONS = {
    "module_name.view": {
        "roles": ["tenant_user", "tenant_viewer", "tenant_admin"],
        "description": "View module items"
    },
    "module_name.create": {
        "roles": ["tenant_user", "tenant_admin"],
        "description": "Create module items"
    },
    "module_name.update": {
        "roles": ["tenant_user", "tenant_admin"],
        "description": "Update module items"
    },
    "module_name.delete": {
        "roles": ["tenant_admin"],
        "description": "Delete module items"
    }
}

def check_module_permission(permission: str, user_roles: List[str]) -> bool:
    """Check if user has module permission"""
    perm_config = MODULE_PERMISSIONS.get(permission)
    if not perm_config:
        return False

    required_roles = perm_config.get("roles", [])
    return any(role in user_roles for role in required_roles)

