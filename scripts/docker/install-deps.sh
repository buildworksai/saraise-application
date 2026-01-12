#!/bin/bash
# Install/update dependencies in Docker container

set -euo pipefail

CONTAINER_NAME=${1:-api}

echo "📦 Installing dependencies in container: $CONTAINER_NAME"

docker exec -it "$CONTAINER_NAME" pip install -e .[dev]

echo "✅ Dependencies installed"
