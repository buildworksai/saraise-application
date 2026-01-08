#!/bin/bash
# =============================================================================
# SARAISE API Contract Sync Script
# =============================================================================
#
# This script synchronizes API types and contracts between backend and frontend.
#
# Usage:
#   ./scripts/sync-api-contracts.sh [--check]
#
# Options:
#   --check   Only verify contracts are in sync (for CI), don't regenerate
#
# What it does:
#   1. Generate OpenAPI schema from Django backend
#   2. Generate TypeScript types from OpenAPI schema
#   3. Validate contracts.ts files reference correct types
#   4. Report any drift between backend and frontend
#
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
SCHEMA_FILE="$BACKEND_DIR/schema.yml"
TYPES_FILE="$FRONTEND_DIR/src/types/api.ts"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}              SARAISE API Contract Sync                              ${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

CHECK_ONLY=false
if [[ "$1" == "--check" ]]; then
    CHECK_ONLY=true
    echo -e "${YELLOW}Running in CHECK mode - will not modify files${NC}"
    echo ""
fi

# Step 1: Generate OpenAPI schema from Django
echo -e "${BLUE}[1/4] Generating OpenAPI schema from Django backend...${NC}"
cd "$BACKEND_DIR"

if [ ! -f "manage.py" ]; then
    echo -e "${RED}ERROR: manage.py not found in $BACKEND_DIR${NC}"
    exit 1
fi

# Activate virtual environment if exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Generate schema
python manage.py spectacular --file "$SCHEMA_FILE" --validate 2>/dev/null || {
    echo -e "${RED}ERROR: Failed to generate OpenAPI schema${NC}"
    echo -e "${YELLOW}Make sure drf-spectacular is installed and configured${NC}"
    exit 1
}

SCHEMA_LINES=$(wc -l < "$SCHEMA_FILE")
echo -e "${GREEN}✓ Generated schema.yml ($SCHEMA_LINES lines)${NC}"

# Step 2: Generate TypeScript types
echo ""
echo -e "${BLUE}[2/4] Generating TypeScript types from OpenAPI schema...${NC}"
cd "$FRONTEND_DIR"

if [ ! -f "package.json" ]; then
    echo -e "${RED}ERROR: package.json not found in $FRONTEND_DIR${NC}"
    exit 1
fi

# Check if openapi-typescript is installed
if ! npx openapi-typescript --version >/dev/null 2>&1; then
    echo -e "${YELLOW}Installing openapi-typescript...${NC}"
    npm install --save-dev openapi-typescript
fi

# Generate types
if [ "$CHECK_ONLY" = true ]; then
    # Generate to temp file for comparison
    TEMP_TYPES=$(mktemp)
    npx openapi-typescript "$SCHEMA_FILE" -o "$TEMP_TYPES" 2>/dev/null
    
    if ! diff -q "$TEMP_TYPES" "$TYPES_FILE" >/dev/null 2>&1; then
        echo -e "${RED}ERROR: TypeScript types are out of sync!${NC}"
        echo -e "${YELLOW}Run './scripts/sync-api-contracts.sh' to regenerate${NC}"
        rm "$TEMP_TYPES"
        exit 1
    fi
    rm "$TEMP_TYPES"
    echo -e "${GREEN}✓ TypeScript types are in sync${NC}"
else
    npx openapi-typescript "$SCHEMA_FILE" -o "$TYPES_FILE" 2>/dev/null
    TYPES_LINES=$(wc -l < "$TYPES_FILE")
    echo -e "${GREEN}✓ Generated api.ts ($TYPES_LINES lines)${NC}"
fi

# Step 3: Validate contracts.ts files
echo ""
echo -e "${BLUE}[3/4] Validating module contracts...${NC}"

MODULES_DIR="$FRONTEND_DIR/src/modules"
CONTRACTS_ERRORS=0

for MODULE_DIR in "$MODULES_DIR"/*/; do
    MODULE_NAME=$(basename "$MODULE_DIR")
    CONTRACT_FILE="$MODULE_DIR/contracts.ts"
    
    if [ -f "$CONTRACT_FILE" ]; then
        # Check if contract file imports from @/types/api
        if grep -q "from '@/types/api'" "$CONTRACT_FILE"; then
            echo -e "${GREEN}  ✓ $MODULE_NAME/contracts.ts${NC}"
        else
            echo -e "${YELLOW}  ⚠ $MODULE_NAME/contracts.ts - missing @/types/api import${NC}"
        fi
        
        # Verify TypeScript compilation
        if npx tsc --noEmit "$CONTRACT_FILE" 2>/dev/null; then
            : # Silent success
        else
            echo -e "${RED}  ✗ $MODULE_NAME/contracts.ts - TypeScript errors${NC}"
            CONTRACTS_ERRORS=$((CONTRACTS_ERRORS + 1))
        fi
    else
        echo -e "${YELLOW}  ⚠ $MODULE_NAME - no contracts.ts file${NC}"
    fi
done

if [ $CONTRACTS_ERRORS -gt 0 ]; then
    echo -e "${RED}ERROR: $CONTRACTS_ERRORS contract(s) have TypeScript errors${NC}"
    exit 1
fi

# Step 4: Check for hardcoded endpoints
echo ""
echo -e "${BLUE}[4/4] Checking for hardcoded API endpoints...${NC}"

# Find files with hardcoded /api/v1/ that are NOT in contracts.ts
HARDCODED=$(grep -rn "/api/v1/" "$MODULES_DIR" \
    --include="*.ts" --include="*.tsx" \
    --exclude="*contracts.ts" \
    --exclude="*-service.ts" \
    --exclude="*-service.test.ts" \
    2>/dev/null || true)

if [ -n "$HARDCODED" ]; then
    echo -e "${YELLOW}WARNING: Found hardcoded API endpoints:${NC}"
    echo "$HARDCODED" | head -20
    HARDCODED_COUNT=$(echo "$HARDCODED" | wc -l)
    if [ "$HARDCODED_COUNT" -gt 20 ]; then
        echo -e "${YELLOW}  ... and $((HARDCODED_COUNT - 20)) more${NC}"
    fi
    echo ""
    echo -e "${YELLOW}Consider using ENDPOINTS from contracts.ts instead${NC}"
else
    echo -e "${GREEN}✓ No hardcoded endpoints in page/component files${NC}"
fi

# Summary
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
if [ "$CHECK_ONLY" = true ]; then
    echo -e "${GREEN}✓ API contract validation passed${NC}"
else
    echo -e "${GREEN}✓ API contracts synchronized successfully${NC}"
fi
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

