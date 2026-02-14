#!/bin/bash
# Generate migrations for all new modules

set -euo pipefail

cd "$(dirname "$0")/.."

MODULES=(
    "accounting_finance"
    "inventory_management"
    "human_resources"
    "purchase_management"
    "sales_management"
    "project_management"
    "master_data_management"
    "multi_company"
    "asset_management"
    "bank_reconciliation"
    "budget_management"
    "business_intelligence"
    "communication_hub"
    "compliance_management"
    "compliance_risk_management"
    "email_marketing"
    "fixed_assets"
)

echo "🔄 Generating migrations for ${#MODULES[@]} modules..."
echo ""

for module in "${MODULES[@]}"; do
    echo "📦 Creating migrations for: $module"
    python manage.py makemigrations "$module" --noinput || {
        echo "❌ Failed to create migrations for $module"
        exit 1
    }
done

echo ""
echo "✅ All migrations generated successfully!"
echo ""
echo "Next steps:"
echo "  1. Review migrations: ls src/modules/*/migrations/"
echo "  2. Run migrations: python manage.py migrate"
echo "  3. Verify: python manage.py showmigrations"
