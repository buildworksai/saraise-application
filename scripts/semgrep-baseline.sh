#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# ===================================
# SARAISE Semgrep Baseline Establishment
# ===================================
# Creates baseline for Semgrep to ignore known findings
# ===================================

set -e

echo "🔍 Establishing Semgrep baseline..."
echo "=================================="

# Try to find Semgrep in various locations
SEMGREP_CMD=""
if command -v semgrep &> /dev/null; then
    SEMGREP_CMD="semgrep"
elif [ -f ~/.local/bin/semgrep ]; then
    SEMGREP_CMD="$HOME/.local/bin/semgrep"
elif python3 -m semgrep --version &> /dev/null 2>&1; then
    SEMGREP_CMD="python3 -m semgrep"
elif pipx run semgrep --version &> /dev/null 2>&1; then
    SEMGREP_CMD="pipx run semgrep"
fi

# Install Semgrep if not found
if [ -z "$SEMGREP_CMD" ]; then
    echo "📦 Installing Semgrep..."
    
    # Try pipx first (recommended for applications)
    if command -v pipx &> /dev/null; then
        echo "   Using pipx to install Semgrep..."
        pipx install semgrep || {
            echo "⚠️  pipx installation failed, trying --user install..."
            python3 -m pip install --user semgrep --quiet || {
                echo "❌ Could not install Semgrep locally."
                echo "   Semgrep will be installed automatically in CI/CD."
                echo "   For local testing, install manually:"
                echo "     - pipx install semgrep (recommended)"
                echo "     - pip install --user semgrep"
                echo ""
                echo "   Creating placeholder baseline file..."
                echo '{"version": "0.0.0", "results": [], "errors": []}' > semgrep-baseline.json
                echo "✅ Placeholder baseline created. Run Semgrep in CI/CD for actual results."
                exit 0
            }
        }
        SEMGREP_CMD="pipx run semgrep"
    else
        # Fallback to --user install
        python3 -m pip install --user semgrep --quiet || {
            echo "❌ Could not install Semgrep."
            echo "   Install pipx: brew install pipx"
            echo "   Or install Semgrep: pip install --user semgrep"
            exit 1
        }
        SEMGREP_CMD="$HOME/.local/bin/semgrep"
    fi
fi

# Verify Semgrep works
if ! $SEMGREP_CMD --version &> /dev/null; then
    echo "❌ Semgrep installation verification failed"
    exit 1
fi

echo "✅ Using Semgrep: $SEMGREP_CMD"

# Run Semgrep with auto-config and custom rules
echo "🔍 Running Semgrep scan..."
$SEMGREP_CMD --config=auto \
        --config=.semgrep/custom-rules.yaml \
        --json \
        --output=semgrep-baseline.json \
        --error || true

# Check if baseline file exists
if [ -f semgrep-baseline.json ]; then
    echo "✅ Baseline scan complete"
    echo "   Results saved to: semgrep-baseline.json"
    
    # Count findings by severity (if jq is available)
    if command -v jq &> /dev/null; then
        CRITICAL=$(jq '[.results[] | select(.extra.severity == "ERROR")] | length' semgrep-baseline.json 2>/dev/null || echo "0")
        HIGH=$(jq '[.results[] | select(.extra.severity == "WARNING")] | length' semgrep-baseline.json 2>/dev/null || echo "0")
        
        echo ""
        echo "📊 Baseline Summary:"
        echo "   Critical/High findings: $CRITICAL"
        echo "   Medium/Low findings: $HIGH"
    else
        echo ""
        echo "📊 Baseline file created (install jq for detailed summary)"
    fi
    
    echo ""
    echo "⚠️  Review semgrep-baseline.json and address critical findings"
    echo "   Then update .semgrep/custom-rules.yaml to ignore false positives"
else
    echo "❌ Baseline scan failed - no output file generated"
    exit 1
fi
