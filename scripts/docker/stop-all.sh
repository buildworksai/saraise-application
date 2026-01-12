#!/bin/bash
# Stop all SARAISE services

set -e

echo "🛑 Stopping SARAISE Consolidated Development Environment..."

# Navigate to project root
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
PROJECT_ROOT=$(dirname "$(dirname "$SCRIPT_DIR")")
cd "$PROJECT_ROOT" || { echo "Error: Could not navigate to project root."; exit 1; }

docker-compose -f docker-compose.dev.yml down

echo "✅ All services stopped."
