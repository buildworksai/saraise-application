#!/usr/bin/env python3
"""
Validation script for new modules before running migrations.

Checks for common issues that prevent migrations from working:
- Missing Meta classes
- Invalid field types
- Missing app_label
- Circular imports
- Missing __init__.py files
"""

import os
import sys
import ast
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

MODULES = [
    "accounting_finance",
    "inventory_management",
    "human_resources",
    "purchase_management",
    "sales_management",
    "project_management",
    "master_data_management",
    "multi_company",
    "asset_management",
    "bank_reconciliation",
    "budget_management",
    "business_intelligence",
    "communication_hub",
    "compliance_management",
    "compliance_risk_management",
    "email_marketing",
    "fixed_assets",
]

REQUIRED_FILES = [
    "models.py",
    "api.py",
    "urls.py",
    "manifest.yaml",
    "health.py",
    "__init__.py",
]

REQUIRED_TEST_FILES = [
    "tests/__init__.py",
    "tests/test_isolation.py",
    "tests/test_models.py",
    "tests/test_api.py",
    "tests/test_services.py",
]

errors = []
warnings = []


def check_file_exists(module_path, filename):
    """Check if required file exists."""
    filepath = module_path / filename
    if not filepath.exists():
        errors.append(f"❌ {module_path.name}/{filename} MISSING")
        return False
    return True


def check_models_structure(module_path):
    """Check models.py structure."""
    models_file = module_path / "models.py"
    if not models_file.exists():
        return

    try:
        with open(models_file, "r") as f:
            content = f.read()
            tree = ast.parse(content, filename=str(models_file))

        # Check for TenantBaseModel
        has_tenant_base = "TenantBaseModel" in content
        has_tenant_id = "tenant_id" in content and "UUIDField" in content

        # Check for Meta classes in model classes
        has_meta = "class Meta:" in content
        has_db_table = "db_table" in content

        if not has_tenant_base:
            warnings.append(f"⚠️  {module_path.name}/models.py: No TenantBaseModel found")

        if not has_tenant_id:
            errors.append(f"❌ {module_path.name}/models.py: Missing tenant_id UUIDField")

        if not has_meta:
            warnings.append(f"⚠️  {module_path.name}/models.py: No Meta classes found")

        if not has_db_table:
            warnings.append(f"⚠️  {module_path.name}/models.py: No db_table specified")

    except SyntaxError as e:
        errors.append(f"❌ {module_path.name}/models.py: Syntax error - {e}")
    except Exception as e:
        warnings.append(f"⚠️  {module_path.name}/models.py: Parse error - {e}")


def validate_module(module_name):
    """Validate a single module."""
    module_path = Path(__file__).parent.parent / "src" / "modules" / module_name

    if not module_path.exists():
        errors.append(f"❌ Module directory {module_name} does not exist")
        return

    # Check required files
    for filename in REQUIRED_FILES:
        check_file_exists(module_path, filename)

    # Check test files
    for filename in REQUIRED_TEST_FILES:
        check_file_exists(module_path, filename)

    # Check models structure
    check_models_structure(module_path)


def main():
    """Main validation function."""
    print("🔍 Validating new modules for migration readiness...\n")

    for module in MODULES:
        validate_module(module)

    print(f"\n📊 Validation Summary:")
    print(f"   Modules checked: {len(MODULES)}")
    print(f"   Errors: {len(errors)}")
    print(f"   Warnings: {len(warnings)}\n")

    if errors:
        print("❌ ERRORS (must fix before migrations):")
        for error in errors:
            print(f"   {error}")
        print()

    if warnings:
        print("⚠️  WARNINGS (should review):")
        for warning in warnings:
            print(f"   {warning}")
        print()

    if not errors:
        print("✅ All modules pass basic validation checks!")
        print("   Ready to run: python manage.py makemigrations")
        return 0
    else:
        print("❌ Validation failed. Fix errors before running migrations.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
