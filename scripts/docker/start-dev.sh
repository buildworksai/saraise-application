#!/bin/bash
# Start SARAISE development environment
# All containers use single saraise-network
# Application external ports use the 2xxxx range to avoid local platform/Aptivra conflicts.

set -e

if [ -f .env ]; then
    set -a
    . ./.env
    set +a
fi

: "${POSTGRES_PORT:=25432}"
: "${REDIS_PORT:=26379}"
: "${BACKEND_PORT:=28000}"
: "${FRONTEND_PORT:=25173}"

echo "🚀 Starting SARAISE Development Environment..."
echo "📋 Using single network: saraise-network"
echo "🔌 External ports: ${BACKEND_PORT} (backend), ${FRONTEND_PORT} (frontend)"

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

# Ensure saraise-network exists (create if it doesn't)
if ! docker network ls | grep -q 'saraise-network'; then
    echo "📡 Creating saraise-network..."
    docker network create saraise-network || true
fi

# Check for existing postgres and redis containers
echo "🔍 Checking for existing infrastructure containers..."
if docker ps --format '{{.Names}}' | grep -q '^saraise-db$'; then
    echo "✅ Found existing postgres container (saraise-db) - will reuse it"
    USE_EXISTING_DB=true
else
    echo "ℹ️  No existing postgres container found - will create new one"
    USE_EXISTING_DB=false
fi

if docker ps --format '{{.Names}}' | grep -q '^saraise-redis$'; then
    echo "✅ Found existing redis container (saraise-redis) - will reuse it"
    USE_EXISTING_REDIS=true
else
    echo "ℹ️  No existing redis container found - will create new one"
    USE_EXISTING_REDIS=false
fi

# Check for application port conflicts.
if lsof -i :"${BACKEND_PORT}" > /dev/null 2>&1; then
    echo "⚠️  Port ${BACKEND_PORT} is already in use. Please stop the service using it or change BACKEND_PORT in .env"
    exit 1
fi

if lsof -i :"${FRONTEND_PORT}" > /dev/null 2>&1; then
    echo "⚠️  Port ${FRONTEND_PORT} is already in use. Please stop the service using it or change FRONTEND_PORT in .env"
    exit 1
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
docker-compose -f docker-compose.dev.yml up -d

echo "⏳ Waiting for services to be healthy..."
sleep 5

# Check service health
echo "🔍 Checking service health..."
docker-compose -f docker-compose.dev.yml ps

echo ""
echo "✅ SARAISE Development Environment is running!"
echo ""
echo "📋 Services:"
echo "   - Backend API: http://localhost:${BACKEND_PORT:-28000}"
echo "   - Frontend UI: http://localhost:${FRONTEND_PORT:-25173}"
echo "   - PostgreSQL: localhost:${POSTGRES_PORT:-25432} (saraise-db)"
echo "   - Redis: localhost:${REDIS_PORT:-26379} (saraise-redis)"
echo ""
echo "🌐 Network: saraise-network (shared with all SARAISE services)"
echo ""
echo "📝 Logs:"
echo "   docker-compose -f docker-compose.dev.yml logs -f"
echo ""
echo "🛑 Stop:"
echo "   docker-compose -f docker-compose.dev.yml down"
