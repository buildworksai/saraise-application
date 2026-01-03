# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ REQUIRED: Module version compatibility
# backend/src/core/module_compatibility.py
from typing import Dict, Tuple

class ModuleCompatibilityChecker:
    def __init__(self):
        self.compatibility_matrix: Dict[Tuple[str, str], bool] = {}

    def check_compatibility(self, module1: str, version1: str, module2: str, version2: str) -> bool:
        """Check if two module versions are compatible"""
        key = (f"{module1}@{version1}", f"{module2}@{version2}")
        return self.compatibility_matrix.get(key, True)

    def register_compatibility(self, module1: str, version1: str, module2: str, version2: str, compatible: bool):
        """Register module version compatibility"""
        key = (f"{module1}@{version1}", f"{module2}@{version2}")
        self.compatibility_matrix[key] = compatible

