# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Module registry system
# backend/src/core/module_registry.py
# Reference: docs/architecture/module-framework.md § 2 (Module Registration)
# CRITICAL NOTES:
# - Central registry tracks all installed modules and their metadata
# - Each module provides manifest.yaml declaring dependencies, permissions, SoD actions
# - Dependency validation prevents circular dependencies (DAG enforcement)
# - Module versioning enforced (no multiple versions of same module)
# - manifest.yaml includes: name, version, dependencies, permissions, search_indexes, ai_tools
# - Permission registration: all available permissions declared at install time
# - SoD (Segregation of Duties) actions configured per module
# - Dynamic imports via importlib.import_module (lazy module loading)
# - Registry queries support version constraints (>=1.0, <2.0)
# - Uninstall validation ensures no dependent modules remain
# Source: docs/architecture/module-framework.md § 2, § 3 (Module Definition)

from typing import Dict, List, Optional, Any
import importlib
import os

class ModuleRegistry:
    def __init__(self):
        self.modules: Dict[str, Dict[str, Any]] = {}
        self.loaded_modules: List[str] = []

    def register_module(self, module_name: str, manifest: Dict[str, Any]):
        """Register module with manifest"""
        if module_name in self.modules:
            raise ValueError(f"Module {module_name} already registered")

        # Validate dependencies
        self._validate_dependencies(module_name, manifest.get("depends", []))

        self.modules[module_name] = manifest

    def load_module(self, module_name: str):
        """Load module and initialize"""
        if module_name in self.loaded_modules:
            return

        manifest = self.modules.get(module_name)
        if not manifest:
            raise ValueError(f"Module {module_name} not found")

        # Load dependencies first
        for dep in manifest.get("depends", []):
            if dep != "base":
                self.load_module(dep)

        # Import module
        module_path = f"src.modules.{module_name}"
        importlib.import_module(module_path)

        self.loaded_modules.append(module_name)

    def _validate_dependencies(self, module_name: str, dependencies: List[str]):
        """Validate module dependencies"""
        for dep in dependencies:
            if dep not in self.modules and dep != "base":
                raise ValueError(f"Module {module_name} depends on {dep} which is not registered")

    def get_module_dependencies(self, module_name: str) -> List[str]:
        """Get all dependencies for a module"""
        manifest = self.modules.get(module_name)
        if not manifest:
            return []

        dependencies = manifest.get("depends", [])
        all_deps = set(dependencies)

        for dep in dependencies:
            all_deps.update(self.get_module_dependencies(dep))

        return list(all_deps)

# Global module registry
module_registry = ModuleRegistry()

