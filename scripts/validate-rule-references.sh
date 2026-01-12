#!/bin/bash
# Script to validate all file references in .agents/rules

echo "Validating file references in .agents/rules..."
echo ""

errors=0
warnings=0

# Find all markdown files in .agents/rules
for rule_file in .agents/rules/*.md; do
    echo "Checking: $rule_file"

    # Extract all file references (docs/... or paths with .md/.py/.ts/.tsx)
    grep -oE 'docs/[^`\s)]+\.(md|py|ts|tsx|sh|yml|yaml)' "$rule_file" | while read -r ref; do
        # Remove markdown link syntax if present
        clean_ref=$(echo "$ref" | sed 's/\[.*\](//' | sed 's/)$//')

        # Check if file exists
        if [ ! -f "$clean_ref" ]; then
            echo "  ❌ BROKEN: $clean_ref"
            errors=$((errors + 1))
        else
            echo "  ✅ OK: $clean_ref"
        fi
    done
    echo ""
done

echo "Validation complete."
echo "Errors: $errors"
echo "Warnings: $warnings"

if [ $errors -gt 0 ]; then
    exit 1
fi
