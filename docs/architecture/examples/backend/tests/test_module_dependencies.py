# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ REQUIRED: Module dependency testing
# backend/src/modules/module_name/tests/test_dependencies.py
import pytest
from src.core.module_registry import module_registry
from src.core.module_dependency_resolver import ModuleDependencyResolver
from src.core.module_conflict_resolver import ModuleConflictResolver

@pytest.mark.asyncio
def test_module_dependencies():
    """Test module dependencies are satisfied"""
    resolver = ModuleDependencyResolver()

    # Add dependencies
    resolver.add_dependency("module_name", "base")
    resolver.add_dependency("module_name", "auth")
    resolver.add_dependency("module_name", "billing")

    # Resolve dependencies
    dependencies = resolver.resolve_dependencies("module_name")

    assert "base" in dependencies
    assert "auth" in dependencies
    assert "billing" in dependencies

    # Check for circular dependencies
    cycles = resolver.check_circular_dependencies()
    assert len(cycles) == 0

@pytest.mark.asyncio
def test_module_conflicts():
    """Test module conflicts are detected"""
    resolver = ModuleConflictResolver()
    resolver.register_conflict("module_name", "legacy_module")

    conflicts = resolver.check_conflicts(["module_name", "legacy_module"])
    assert len(conflicts) > 0

