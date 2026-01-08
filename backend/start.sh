#!/bin/bash
# Startup script for backend container
# Handles migrations and seeding gracefully

set -euo pipefail

echo "🚀 Starting SARAISE Backend..."

# Install dependencies
echo "📦 Installing dependencies..."
pip install -e .[dev] || {
    echo "❌ Failed to install dependencies"
    exit 1
}
echo "✅ Dependencies installed"

# Wait for database to be ready (with timeout)
echo "⏳ Waiting for database..."
MAX_ATTEMPTS=30
ATTEMPT=0
while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if python -c "import psycopg2; conn = psycopg2.connect(dbname='saraise', user='postgres', password='postgres', host='postgres', connect_timeout=2); conn.close()" 2>/dev/null; then
        echo "✅ Database is ready"
        break
    fi
    ATTEMPT=$((ATTEMPT + 1))
    echo "   Database not ready, waiting... ($ATTEMPT/$MAX_ATTEMPTS)"
    sleep 2
done

if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
    echo "❌ Database connection timeout after $MAX_ATTEMPTS attempts"
    echo "   Continuing anyway - migrations will fail if DB is not ready"
fi

# Run migrations
echo "🔄 Running migrations..."
python manage.py migrate --noinput || {
    echo "❌ Migrations failed"
    exit 1
}
echo "✅ Migrations complete"

# Seed default users (disabled temporarily for testing)
# echo "🌱 Seeding default users..."
# python manage.py seed_default_users || {
#     echo "⚠️  Warning: seed_default_users failed, but continuing..."
# }

# Start server
echo "🌐 Starting Django development server on 0.0.0.0:8000..."
exec python manage.py runserver 0.0.0.0:8000

