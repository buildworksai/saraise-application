#!/bin/bash
# Start all SARAISE services (Phase 1-6) in consolidated docker-compose
# All services use single saraise-network
# Application external ports use the 2xxxx range to avoid local platform/Aptivra conflicts.

set -e

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

if [ -f .env ]; then
    set -a
    . ./.env
    set +a
fi

: "${POSTGRES_PORT:=25432}"
: "${REDIS_PORT:=26379}"
: "${BACKEND_PORT:=28000}"
: "${FRONTEND_PORT:=25173}"
: "${PROMETHEUS_PORT:=29090}"
: "${GRAFANA_PORT:=23000}"
: "${JAEGER_UI_PORT:=26686}"

echo "🚀 Starting SARAISE Consolidated Development Environment..."
echo "📋 Using single network: saraise-network"
echo "🔌 Application ports: ${BACKEND_PORT} (backend), ${FRONTEND_PORT} (frontend), ${POSTGRES_PORT} (PostgreSQL), ${REDIS_PORT} (Redis)"

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
POSTGRES_PORT=${POSTGRES_PORT}

# Redis
REDIS_PORT=${REDIS_PORT}

# Backend (application external port)
BACKEND_PORT=${BACKEND_PORT}
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')

# Frontend (application external port)
FRONTEND_PORT=${FRONTEND_PORT}
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
echo "   - PostgreSQL: localhost:${POSTGRES_PORT} (saraise-db)"
echo "   - Redis: localhost:${REDIS_PORT} (saraise-redis)"
echo ""
echo "   Phase 2 Services:"
echo "   - Auth Service: http://localhost:18001"
echo "   - Runtime Service: http://localhost:18002"
echo "   - Policy Engine: http://localhost:18003"
echo "   - Control Plane: http://localhost:18004"
echo ""
echo "   Phase 4/5 Services:"
echo "   - Backend (Legacy): removed; use Application API"
echo ""
echo "   Phase 6 Services:"
echo "   - Application API: http://localhost:${BACKEND_PORT}"
echo "   - Frontend UI: http://localhost:${FRONTEND_PORT}"
echo ""
echo "   Observability:"
echo "   - Prometheus: http://localhost:${PROMETHEUS_PORT}"
echo "   - Grafana: http://localhost:${GRAFANA_PORT}"
echo "   - Jaeger UI: http://localhost:${JAEGER_UI_PORT}"
echo ""
echo "🌐 Network: saraise-network (all services)"
echo ""
echo "📝 Logs:"
echo "   docker-compose -f docker-compose.dev.yml logs -f [service_name]"
echo ""
echo "🛑 Stop:"
echo "   docker-compose -f docker-compose.dev.yml down"
