# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ REQUIRED: Module conflict resolution
# backend/src/core/module_conflict_resolver.py
from typing import List, Dict, Set, Tuple

class ModuleConflictResolver:
    def __init__(self):
        self.conflicts: Dict[str, Set[str]] = {}

    def register_conflict(self, module1: str, module2: str):
        """Register module conflict"""
        if module1 not in self.conflicts:
            self.conflicts[module1] = set()
        if module2 not in self.conflicts:
            self.conflicts[module2] = set()

        self.conflicts[module1].add(module2)
        self.conflicts[module2].add(module1)

    def check_conflicts(self, modules: List[str]) -> List[Tuple[str, str]]:
        """Check for conflicts in module list"""
        conflicts = []
        for i, module1 in enumerate(modules):
            for module2 in modules[i+1:]:
                if module2 in self.conflicts.get(module1, set()):
                    conflicts.append((module1, module2))
        return conflicts

