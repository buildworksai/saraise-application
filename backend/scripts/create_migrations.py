#!/usr/bin/env python3
"""
Create migrations for new modules, handling billing_subscriptions separately.
"""
import os
import sys
import django
from django.core.management import call_command
from django.core.management.base import CommandError

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "saraise_backend.settings")
django.setup()

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

def main():
    print("🔄 Creating migrations for billing_subscriptions first...")
    try:
        # Handle billing_subscriptions with default value
        call_command("makemigrations", "billing_subscriptions", interactive=False, 
                    default_timezone_now=True)
        print("✅ billing_subscriptions migration created")
    except Exception as e:
        print(f"⚠️  billing_subscriptions: {e}")
        # Continue anyway
    
    print(f"\n🔄 Creating migrations for {len(NEW_MODULES)} new modules...")
    for module in NEW_MODULES:
        try:
            call_command("makemigrations", module, interactive=False)
            print(f"✅ {module}: Migration created")
        except Exception as e:
            print(f"❌ {module}: {e}")
            return 1
    
    print("\n✅ All migrations created successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
