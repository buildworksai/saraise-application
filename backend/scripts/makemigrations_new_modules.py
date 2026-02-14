#!/usr/bin/env python3
"""
Generate migrations for new modules, handling interactive prompts.
"""
import subprocess
import sys
import os

# Set Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "saraise_backend.settings")

# New modules only (excluding billing_subscriptions which has existing migrations)
NEW_MODULES = [
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

def run_makemigrations(modules):
    """Run makemigrations for specified modules."""
    cmd = ["python", "manage.py", "makemigrations"] + modules
    
    # Provide default answers for interactive prompts
    # 1 = Provide one-off default
    # timezone.now = default value
    input_data = "1\ntimezone.now\n" * 10  # Multiple prompts might occur
    
    try:
        result = subprocess.run(
            cmd,
            input=input_data.encode(),
            capture_output=True,
            text=True,
            cwd="/app"
        )
        
        if result.returncode == 0:
            print(result.stdout)
            return True
        else:
            # If it still fails, try without billing_subscriptions detection
            print("Attempting with explicit module list...")
            print(result.stderr)
            return False
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    print(f"🔄 Generating migrations for {len(NEW_MODULES)} new modules...")
    success = run_makemigrations(NEW_MODULES)
    sys.exit(0 if success else 1)
