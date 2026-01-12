#!/bin/bash
# View SARAISE development environment logs

set -e

SERVICE=${1:-""}

if [ -z "$SERVICE" ]; then
    echo "📋 Viewing logs for all services..."
    echo "💡 Usage: $0 [service_name] to view specific service logs"
    echo ""
    docker-compose -f docker-compose.dev.yml logs -f
else
    echo "📋 Viewing logs for service: $SERVICE"
    echo ""
    docker-compose -f docker-compose.dev.yml logs -f "$SERVICE"
fi
