#!/bin/bash
# Run tests in Docker container

set -euo pipefail

CONTAINER_NAME=${1:-api}
TEST_PATH=${2:-tests/}

echo "🧪 Running tests in container: $CONTAINER_NAME"
echo "   Test path: $TEST_PATH"

docker exec -it "$CONTAINER_NAME" pytest "$TEST_PATH" -v --cov=src --cov-report=term-missing --cov-report=html

echo "✅ Tests complete"
