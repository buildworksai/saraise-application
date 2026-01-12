#!/bin/bash
# Run migrations in Docker container

set -euo pipefail

CONTAINER_NAME=${1:-api}

echo "🔄 Running migrations in container: $CONTAINER_NAME"

docker exec -it "$CONTAINER_NAME" python manage.py migrate --noinput

echo "✅ Migrations complete"
