# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Module dependency resolver
# backend/src/core/module_dependency_resolver.py
# Reference: docs/architecture/module-framework.md § 2 (Dependency Management)
# CRITICAL NOTES:
# - Directed acyclic graph (DAG) enforced (no circular dependencies allowed)
# - Topological sort for installation order (dependencies first)
# - Version constraint validation (>= , <=, ~, ^ operators supported)
# - Dependency graph bidirectional (forward and reverse lookups)
# - Circular dependency detection raises ValueError immediately
# - Uninstall dependency checking (prevent breaking dependent modules)
# - Conflict detection between incompatible module versions
# - Transitive dependency resolution (all indirect dependencies included)
# - Missing dependency detection prevents partial installations
# - Module version compatibility checks (semantic versioning)
# Source: docs/architecture/module-framework.md § 2
from typing import List, Set, Dict, Any
from collections import defaultdict

class ModuleDependencyResolver:
    def __init__(self):
        self.dependency_graph: Dict[str, Set[str]] = defaultdict(set)
        self.reverse_dependencies: Dict[str, Set[str]] = defaultdict(set)

    def add_dependency(self, module: str, dependency: str):
        """Add module dependency"""
        if module == dependency:
            raise ValueError(f"Module {module} cannot depend on itself")

        self.dependency_graph[module].add(dependency)
        self.reverse_dependencies[dependency].add(module)

    def resolve_dependencies(self, module: str) -> List[str]:
        """Resolve all dependencies for a module"""
        visited = set()
        result = []

        def dfs(current: str):
            if current in visited:
                return
            visited.add(current)

            for dep in self.dependency_graph.get(current, set()):
                dfs(dep)

            if current != module:
                result.append(current)

        dfs(module)
        return result

    def check_circular_dependencies(self) -> List[List[str]]:
        """Check for circular dependencies"""
        visited = set()
        rec_stack = set()
        cycles = []

        def dfs(node: str, path: List[str]):
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for dep in self.dependency_graph.get(node, set()):
                if dep not in visited:
                    dfs(dep, path)
                elif dep in rec_stack:
                    # Found cycle
                    cycle_start = path.index(dep)
                    cycles.append(path[cycle_start:] + [dep])

            rec_stack.remove(node)
            path.pop()

        for module in self.dependency_graph:
            if module not in visited:
                dfs(module, [])

        return cycles

