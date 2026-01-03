#!/bin/bash
# ✅ APPROVED: Development Setup Script
# scripts/dev-setup.sh
# Reference: docs/architecture/operational-runbooks.md § 1 (Setup)

set -e

echo "🚀 Setting up SARAISE development environment..."

# Check prerequisites
command -v docker >/dev/null 2>&1 || { echo "Docker is required but not installed. Aborting." >&2; exit 1; }
command -v docker-compose >/dev/null 2>&1 || { echo "Docker Compose is required but not installed. Aborting." >&2; exit 1; }

# Create necessary directories
mkdir -p logs
mkdir -p data/postgres
mkdir -p data/redis

# Copy environment files
if [ ! -f .env ]; then
    cp .env.example .env
    echo "📝 Created .env file from .env.example"
fi

if [ ! -f frontend/.env.local ]; then
    cp frontend/.env.local.example frontend/.env.local
    echo "📝 Created frontend/.env.local from .env.local.example"
fi

# Build and start services
echo "🔨 Building and starting services..."
docker-compose -f docker-compose.dev.yml up -d --build

# Wait for services to be ready
echo "⏳ Waiting for services to be ready..."
sleep 10

# Run database migrations
echo "🗄️ Running database migrations..."
docker-compose -f docker-compose.dev.yml exec api python manage.py migrate

# Initialize database
echo "🔧 Initializing database..."
docker-compose -f docker-compose.dev.yml exec api python scripts/init_db.py

# Check service health
echo "🏥 Checking service health..."
curl -f http://localhost:${API_HOST_PORT:-30000}/health || echo "❌ API health check failed"
curl -f http://localhost:${FRONTEND_HOST_PORT:-20000} || echo "❌ Frontend health check failed"

echo "✅ Development environment setup complete!"
echo "🌐 Frontend: ${DEV_FRONTEND_URL:-http://localhost:${FRONTEND_HOST_PORT:-20000}}"
echo "🔌 API: ${DEV_API_URL:-http://localhost:${API_HOST_PORT:-30000}}"
echo "📧 MailHog: ${DEV_MAILHOG_URL:-http://localhost:${MAILHOG_UI_HOST_PORT:-18025}}"
echo "🔐 Vault: ${DEV_VAULT_URL:-http://localhost:${VAULT_HOST_PORT:-18200}}"

