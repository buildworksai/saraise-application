#!/bin/bash
# Stop SARAISE development environment

set -e

echo "🛑 Stopping SARAISE Development Environment..."

# Stop services
docker-compose -f docker-compose.dev.yml down

echo ""
echo "✅ SARAISE Development Environment stopped!"
echo ""
echo "💡 To remove volumes (database data):"
echo "   docker-compose -f docker-compose.dev.yml down -v"
