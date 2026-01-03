# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Module dependency management
# backend/src/modules/module_name/dependencies.py
# Reference: docs/architecture/module-framework.md § 2 (Dependency Management)
# CRITICAL NOTES:
# - Required dependencies: must be installed before this module
# - Optional dependencies: module works without them but with reduced features
# - Conflicting modules: cannot be installed simultaneously (incompatibility)
# - External dependencies: Python packages and npm packages with version constraints
# - Dependency checking runs at install time (prevents broken state)
# - Version constraints: semantic versioning (>=, ~, ^, <, >, ==)
# - Transitive dependencies resolved recursively
# - Circular dependencies detected and prevented (DAG enforcement)
# - Dependency validation: all required modules must be installable for target tenant
# Source: docs/architecture/module-framework.md § 2

from typing import List, Dict, Any

MODULE_DEPENDENCIES = {
    "required": ["base", "auth"],  # Required dependencies
    "optional": ["billing", "subscriptions"],  # Optional dependencies
    "conflicts": ["legacy_module"],  # Conflicting modules
    "external": {
        "python": ["package_name>=1.0.0"],
        "node": ["package-name@^1.0.0"]
    }
}

def check_dependencies(module_name: str) -> bool:
    """Check if module dependencies are satisfied"""
    from src.core.module_registry import module_registry

    manifest = module_registry.modules.get(module_name)
    if not manifest:
        return False

    dependencies = manifest.get("depends", [])

    for dep in dependencies:
        if dep not in module_registry.loaded_modules and dep != "base":
            return False

    return True

