#!/bin/bash
# Generate TypeScript types from OpenAPI schema

set -e

echo "🔍 Generating TypeScript types from OpenAPI schema..."

# Check if backend is running (using port 18000)
if ! curl -s http://localhost:18000/api/schema/ > /dev/null 2>&1; then
    echo "❌ Backend API is not running. Please start the backend first:"
    echo "   docker-compose -f docker-compose.dev.yml up -d backend"
    echo "   Backend should be accessible at http://localhost:18000"
    exit 1
fi

# Navigate to project root
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
PROJECT_ROOT=$(dirname "$(dirname "$SCRIPT_DIR")")
cd "$PROJECT_ROOT" || { echo "Error: Could not navigate to project root."; exit 1; }

# Generate types
cd frontend
npm run generate-types

if [ $? -eq 0 ]; then
    echo "✅ TypeScript types generated successfully!"
    echo "   File: frontend/src/types/api.ts"
else
    echo "❌ Failed to generate types"
    exit 1
fi
