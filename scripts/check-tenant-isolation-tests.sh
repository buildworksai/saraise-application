#!/bin/bash
# SARAISE Tenant Isolation Test Checker
# 
# This script verifies that every module with tenant-scoped models
# has a corresponding test_isolation.py file.
#
# Rule: SARAISE-33004
# Authority: rules/agent-rules/33-tenant-isolation-enforcement.md
#
# Usage:
#   ./scripts/check-tenant-isolation-tests.sh
#
# Exit codes:
#   0 - All modules have isolation tests
#   1 - One or more modules missing isolation tests

set -e

echo "🔍 SARAISE Tenant Isolation Test Check"
echo "======================================="
echo ""

FAILED=0
CHECKED=0
PASSED=0

# Skip these modules (non-tenant-scoped or special)
SKIP_MODULES="core __pycache__ __init__"

for module_dir in backend/src/modules/*/; do
    module_name=$(basename "$module_dir")
    
    # Check if module should be skipped
    skip=false
    for skip_module in $SKIP_MODULES; do
        if [[ "$module_name" == "$skip_module" ]]; then
            skip=true
            break
        fi
    done
    
    if [[ "$skip" == "true" ]]; then
        continue
    fi
    
    # Check if module has models.py
    if [[ -f "${module_dir}models.py" ]]; then
        # Check if models contain tenant_id (indicating tenant-scoped)
        if grep -q "tenant_id" "${module_dir}models.py" 2>/dev/null; then
            CHECKED=$((CHECKED + 1))
            
            # Check for test_isolation.py
            if [[ -f "${module_dir}tests/test_isolation.py" ]]; then
                echo "✅ ${module_name}: test_isolation.py found"
                PASSED=$((PASSED + 1))
            else
                echo "❌ ${module_name}: MISSING test_isolation.py"
                echo "   Required at: ${module_dir}tests/test_isolation.py"
                FAILED=$((FAILED + 1))
            fi
        fi
    fi
done

echo ""
echo "======================================="
echo "Summary:"
echo "  Modules checked: $CHECKED"
echo "  Passed: $PASSED"
echo "  Failed: $FAILED"
echo ""

if [[ $FAILED -gt 0 ]]; then
    echo "❌ Tenant isolation test check FAILED"
    echo ""
    echo "Every module with tenant_id in models.py MUST have:"
    echo "  tests/test_isolation.py"
    echo ""
    echo "See: saraise-documentation/rules/agent-rules/33-tenant-isolation-enforcement.md"
    echo ""
    exit 1
fi

if [[ $CHECKED -eq 0 ]]; then
    echo "⚠️  No tenant-scoped modules found to check"
    exit 0
fi

echo "✅ All tenant isolation tests present"
exit 0
