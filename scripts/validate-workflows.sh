#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# ===================================
# SARAISE Workflow Validation Script
# ===================================
# Validates GitHub Actions workflow syntax
# ===================================

set -e

echo "🔍 Validating GitHub Actions workflows..."
echo "========================================"

# Check if actionlint is available
if ! command -v actionlint &> /dev/null; then
    echo "📦 Installing actionlint..."
    if command -v brew &> /dev/null; then
        brew install actionlint
    else
        echo "⚠️  actionlint not found. Install with: brew install actionlint"
        echo "   Or download from: https://github.com/rhymond/actionlint"
        exit 1
    fi
fi

# Validate all workflow files
WORKFLOW_DIR=".github/workflows"
ERRORS=0

for workflow in "$WORKFLOW_DIR"/*.yml "$WORKFLOW_DIR"/*.yaml; do
    if [ -f "$workflow" ]; then
        echo "🔍 Checking: $workflow"
        if actionlint "$workflow"; then
            echo "   ✅ Valid"
        else
            echo "   ❌ Invalid"
            ERRORS=$((ERRORS + 1))
        fi
    fi
done

# Also check YAML syntax with yamllint if available
if command -v yamllint &> /dev/null; then
    echo ""
    echo "🔍 Checking YAML syntax..."
    for workflow in "$WORKFLOW_DIR"/*.yml "$WORKFLOW_DIR"/*.yaml; do
        if [ -f "$workflow" ]; then
            if yamllint "$workflow" 2>/dev/null; then
                echo "   ✅ $workflow: YAML syntax valid"
            else
                echo "   ⚠️  $workflow: YAML syntax issues (non-blocking)"
            fi
        fi
    done
fi

if [ $ERRORS -eq 0 ]; then
    echo ""
    echo "✅ All workflows are valid"
    exit 0
else
    echo ""
    echo "❌ Found $ERRORS workflow(s) with errors"
    exit 1
fi
