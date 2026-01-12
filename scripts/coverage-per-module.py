#!/usr/bin/env python3
"""
SPDX-License-Identifier: Apache-2.0
===================================
SARAISE Per-Module Coverage Verification
===================================
Verifies that each module meets the ≥90% coverage threshold.
BLOCKING: Any module below threshold blocks merge.
===================================
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

THRESHOLD = 90.0

# Backend modules
BACKEND_MODULES = [
    "backend/src/modules/crm",
    "backend/src/modules/platform_management",
    "backend/src/modules/tenant_management",
    "backend/src/modules/security_access_control",
    "backend/src/modules/ai_agent_management",
    "backend/src/modules/ai_provider_configuration",
    "backend/src/modules/workflow_automation",
    "backend/src/modules/api_management",
    "backend/src/modules/billing_subscriptions",
    "backend/src/modules/metadata_modeling",
    "backend/src/modules/customization_framework",
    "backend/src/modules/data_migration",
    "backend/src/modules/dms",
    "backend/src/modules/backup_disaster_recovery",
    "backend/src/modules/backup_recovery",
    "backend/src/modules/performance_monitoring",
    "backend/src/modules/localization",
    "backend/src/modules/regional",
    "backend/src/modules/integration_platform",
    "backend/src/modules/automation_orchestration",
    "backend/src/modules/document_intelligence",
    "backend/src/modules/process_mining",
    "backend/src/modules/blockchain_traceability",
]

# Frontend modules
FRONTEND_MODULES = [
    "frontend/src/modules/crm",
    "frontend/src/modules/platform_management",
    "frontend/src/modules/tenant_management",
    "frontend/src/modules/security_access_control",
    "frontend/src/modules/ai_agent_management",
    "frontend/src/modules/ai_provider_configuration",
    "frontend/src/modules/workflow_automation",
    "frontend/src/modules/api_management",
    "frontend/src/modules/billing_subscriptions",
    "frontend/src/modules/metadata_modeling",
    "frontend/src/modules/customization_framework",
    "frontend/src/modules/data_migration",
    "frontend/src/modules/dms",
    "frontend/src/modules/backup_disaster_recovery",
    "frontend/src/modules/backup_recovery",
    "frontend/src/modules/performance_monitoring",
    "frontend/src/modules/localization",
    "frontend/src/modules/regional",
    "frontend/src/modules/integration_platform",
    "frontend/src/modules/automation_orchestration",
    "frontend/src/modules/document_intelligence",
    "frontend/src/modules/process_mining",
    "frontend/src/modules/blockchain_traceability",
]


def parse_coverage_xml(coverage_file: Path) -> Dict[str, float]:
    """Parse Python coverage XML report."""
    try:
        # Use defusedxml for secure XML parsing
        try:
            from defusedxml.ElementTree import parse as safe_parse
        except ImportError:
            # Fallback to standard library if defusedxml not available
            import xml.etree.ElementTree as ET
            safe_parse = ET.parse

        tree = safe_parse(coverage_file)
        root = tree.getroot()

        module_coverage = {}
        for package in root.findall(".//package"):
            package_name = package.get("name", "")
            line_rate = float(package.get("line-rate", 0)) * 100

            # Map package names to module paths
            for module_path in BACKEND_MODULES:
                if package_name.replace("/", ".") in module_path or module_path.endswith(
                    package_name.replace(".", "/")
                ):
                    module_coverage[module_path] = line_rate

        return module_coverage
    except Exception as e:
        print(f"⚠️  Error parsing XML coverage: {e}", file=sys.stderr)
        return {}


def parse_coverage_json(coverage_file: Path) -> Dict[str, float]:
    """Parse TypeScript coverage JSON report."""
    try:
        with open(coverage_file) as f:
            data = json.load(f)

        module_coverage = {}
        # Coverage JSON structure: { "total": {...}, "path/to/file": {...} }
        for file_path, coverage_data in data.items():
            if file_path == "total":
                continue

            # Extract module path from file path
            for module_path in FRONTEND_MODULES:
                if file_path.startswith(module_path):
                    if module_path not in module_coverage:
                        module_coverage[module_path] = []
                    # Collect line coverage percentage
                    if "lines" in coverage_data and "pct" in coverage_data["lines"]:
                        module_coverage[module_path].append(coverage_data["lines"]["pct"])

        # Average coverage per module
        result = {}
        for module_path, coverages in module_coverage.items():
            if coverages:
                result[module_path] = sum(coverages) / len(coverages)

        return result
    except Exception as e:
        print(f"⚠️  Error parsing JSON coverage: {e}", file=sys.stderr)
        return {}


def check_backend_coverage() -> Tuple[List[str], List[str]]:
    """Check backend module coverage."""
    coverage_file = Path("backend/coverage.xml")
    if not coverage_file.exists():
        print("⚠️  Backend coverage file not found. Skipping backend check.")
        return [], []

    module_coverage = parse_coverage_xml(coverage_file)
    failures = []
    passing = []

    for module_path in BACKEND_MODULES:
        module_dir = Path(module_path)
        if not module_dir.exists():
            continue  # Skip non-existent modules

        coverage = module_coverage.get(module_path, 0.0)
        if coverage < THRESHOLD:
            failures.append((module_path, coverage))
        else:
            passing.append((module_path, coverage))

    return failures, passing


def check_frontend_coverage() -> Tuple[List[str], List[str]]:
    """Check frontend module coverage."""
    coverage_file = Path("frontend/coverage/coverage-summary.json")
    if not coverage_file.exists():
        print("⚠️  Frontend coverage file not found. Skipping frontend check.")
        return [], []

    module_coverage = parse_coverage_json(coverage_file)
    failures = []
    passing = []

    for module_path in FRONTEND_MODULES:
        module_dir = Path(module_path)
        if not module_dir.exists():
            continue  # Skip non-existent modules

        coverage = module_coverage.get(module_path, 0.0)
        if coverage < THRESHOLD:
            failures.append((module_path, coverage))
        else:
            passing.append((module_path, coverage))

    return failures, passing


def main():
    """Main entry point."""
    print(f"🔍 Checking per-module coverage (threshold: {THRESHOLD}%)")
    print("=" * 60)

    backend_failures, backend_passing = check_backend_coverage()
    frontend_failures, frontend_passing = check_frontend_coverage()

    all_failures = backend_failures + frontend_failures
    all_passing = backend_passing + frontend_passing

    # Print results
    if all_passing:
        print(f"\n✅ Passing modules ({len(all_passing)}):")
        for module_path, coverage in sorted(all_passing):
            print(f"  ✓ {module_path}: {coverage:.1f}%")

    if all_failures:
        print(f"\n❌ Failing modules ({len(all_failures)}):")
        for module_path, coverage in sorted(all_failures):
            print(f"  ✗ {module_path}: {coverage:.1f}% < {THRESHOLD}%")

    # Exit with error if any failures
    if all_failures:
        print(f"\n❌ {len(all_failures)} module(s) below {THRESHOLD}% coverage threshold")
        sys.exit(1)
    else:
        print(f"\n✅ All modules meet {THRESHOLD}% coverage threshold")
        sys.exit(0)


if __name__ == "__main__":
    main()
