#!/bin/bash
# Start all SARAISE services (Phase 1-6) in consolidated docker-compose
# All services use single saraise-network
# External ports start with "1" prefix

set -e

echo "🚀 Starting SARAISE Consolidated Development Environment..."
echo "📋 Using single network: saraise-network"
echo "🔌 External ports start with '1' prefix"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker and try again."
    exit 1
fi

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null && ! docker compose version > /dev/null 2>&1; then
    echo "❌ docker-compose is not installed. Please install docker-compose and try again."
    exit 1
fi

# Navigate to project root
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
PROJECT_ROOT=$(dirname "$(dirname "$SCRIPT_DIR")")
cd "$PROJECT_ROOT" || { echo "Error: Could not navigate to project root."; exit 1; }

# Ensure saraise-network exists
if ! docker network ls | grep -q 'saraise-network'; then
    echo "📡 Creating saraise-network..."
    docker network create saraise-network || true
fi

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    cat > .env << EOF
# Database
POSTGRES_PORT=15432

# Redis
REDIS_PORT=16379

# Backend (external port starts with 1)
BACKEND_PORT=18000
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')

# Frontend (external port starts with 1)
FRONTEND_PORT=15173
EOF
    echo "✅ Created .env file"
fi

# Start services
echo "🐳 Starting Docker containers..."
docker-compose -f docker-compose.dev.yml up -d --build

echo "⏳ Waiting for services to be healthy..."
sleep 10

# Check service health
echo "🔍 Checking service health..."
docker-compose -f docker-compose.dev.yml ps

echo ""
echo "✅ SARAISE Consolidated Development Environment started successfully!"
echo ""
echo "📋 Services:"
echo "   Infrastructure:"
echo "   - PostgreSQL: localhost:15432 (saraise-db)"
echo "   - Redis: localhost:16379 (saraise-redis)"
echo ""
echo "   Phase 2 Services:"
echo "   - Auth Service: http://localhost:18001"
echo "   - Runtime Service: http://localhost:18002"
echo "   - Policy Engine: http://localhost:18003"
echo "   - Control Plane: http://localhost:18004"
echo ""
echo "      Phase 4/5 Services:"
   echo "   - Backend (Legacy): http://localhost:18005"
   echo ""
   echo "   Phase 6 Services:"
   echo "   - Platform API: http://localhost:18000"
echo "   - Frontend UI: http://localhost:15173"
echo ""
echo "   Observability:"
echo "   - Prometheus: http://localhost:19090"
echo "   - Grafana: http://localhost:13000"
echo "   - Jaeger UI: http://localhost:116686"
echo ""
echo "🌐 Network: saraise-network (all services)"
echo ""
echo "📝 Logs:"
echo "   docker-compose -f docker-compose.dev.yml logs -f [service_name]"
echo ""
echo "🛑 Stop:"
echo "   docker-compose -f docker-compose.dev.yml down"
