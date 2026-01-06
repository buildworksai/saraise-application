#!/bin/bash
# Start SARAISE development environment
# All containers use single saraise-network
# External ports start with "1" prefix (18000, 15173, etc.)

set -e

echo "🚀 Starting SARAISE Development Environment..."
echo "📋 Using single network: saraise-network"
echo "🔌 External ports: 18000 (backend), 15173 (frontend)"

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

# Check for port conflicts (using ports starting with 1)
if lsof -i :18000 > /dev/null 2>&1; then
    echo "⚠️  Port 18000 is already in use. Please stop the service using it or change BACKEND_PORT in .env"
    exit 1
fi

if lsof -i :15173 > /dev/null 2>&1; then
    echo "⚠️  Port 15173 is already in use. Please stop the service using it or change FRONTEND_PORT in .env"
    exit 1
fi

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    cat > .env << EOF
# Database
POSTGRES_PORT=5432

# Redis
REDIS_PORT=6379

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
echo "   - Backend API: http://localhost:${BACKEND_PORT:-18000}"
echo "   - Frontend UI: http://localhost:${FRONTEND_PORT:-15173}"
echo "   - PostgreSQL: localhost:${POSTGRES_PORT:-5432} (saraise-db)"
echo "   - Redis: localhost:${REDIS_PORT:-6379} (saraise-redis)"
echo ""
echo "🌐 Network: saraise-network (shared with all SARAISE services)"
echo ""
echo "📝 Logs:"
echo "   docker-compose -f docker-compose.dev.yml logs -f"
echo ""
echo "🛑 Stop:"
echo "   docker-compose -f docker-compose.dev.yml down"

