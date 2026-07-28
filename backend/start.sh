#!/bin/bash
# Startup script for backend container
# Handles migrations and seeding gracefully

set -euo pipefail

echo "🚀 Starting SARAISE Backend..."

DB_NAME="${DB_NAME:-saraise}"
DB_HOST="${DB_HOST:-application-db}"
DB_PORT="${DB_PORT:-5432}"
DB_MIGRATION_USER="${DB_MIGRATION_USER:-postgres}"
DB_MIGRATION_PASSWORD="${DB_MIGRATION_PASSWORD:-postgres}"
DB_RUNTIME_USER="${DB_RUNTIME_USER:-saraise_app}"
DB_RUNTIME_PASSWORD="${DB_RUNTIME_PASSWORD:-saraise_app}"

export DB_NAME DB_HOST DB_PORT DB_MIGRATION_USER DB_MIGRATION_PASSWORD DB_RUNTIME_USER DB_RUNTIME_PASSWORD

mkdir -p \
    /app/runtime/document-intelligence/artifacts \
    /app/runtime/bdr/storage \
    /app/runtime/bdr/restore

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
    if python - <<'PY' 2>/dev/null
import os
import psycopg2

conn = psycopg2.connect(
    dbname=os.environ["DB_NAME"],
    user=os.environ["DB_MIGRATION_USER"],
    password=os.environ["DB_MIGRATION_PASSWORD"],
    host=os.environ["DB_HOST"],
    port=os.environ["DB_PORT"],
    connect_timeout=2,
)
conn.close()
PY
    then
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

echo "🔐 Ensuring runtime database role..."
python - <<'PY'
import os
import psycopg2
from psycopg2 import sql

runtime_user = os.environ["DB_RUNTIME_USER"]
runtime_password = os.environ["DB_RUNTIME_PASSWORD"]

with psycopg2.connect(
    dbname=os.environ["DB_NAME"],
    user=os.environ["DB_MIGRATION_USER"],
    password=os.environ["DB_MIGRATION_PASSWORD"],
    host=os.environ["DB_HOST"],
    port=os.environ["DB_PORT"],
) as conn:
    conn.autocommit = True
    with conn.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [runtime_user])
        if cursor.fetchone() is None:
            cursor.execute(
                sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD %s").format(
                    sql.Identifier(runtime_user)
                ),
                [runtime_password],
            )
        else:
            cursor.execute(
                sql.SQL("ALTER ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD %s").format(
                    sql.Identifier(runtime_user)
                ),
                [runtime_password],
            )
PY

# Run migrations
echo "🔄 Running migrations..."
DB_USER="$DB_MIGRATION_USER" DB_PASSWORD="$DB_MIGRATION_PASSWORD" python manage.py migrate --noinput || {
    echo "❌ Migrations failed"
    exit 1
}
echo "✅ Migrations complete"

echo "🔐 Granting runtime database privileges..."
python - <<'PY'
import os
import psycopg2
from psycopg2 import sql

runtime_user = os.environ["DB_RUNTIME_USER"]

with psycopg2.connect(
    dbname=os.environ["DB_NAME"],
    user=os.environ["DB_MIGRATION_USER"],
    password=os.environ["DB_MIGRATION_PASSWORD"],
    host=os.environ["DB_HOST"],
    port=os.environ["DB_PORT"],
) as conn:
    conn.autocommit = True
    with conn.cursor() as cursor:
        role = sql.Identifier(runtime_user)
        cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role))
        cursor.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}").format(role))
        cursor.execute(sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(role))
        cursor.execute(
            sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}").format(
                role
            )
        )
        cursor.execute(
            sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {}").format(role)
        )
PY

# Seed default users (disabled temporarily for testing)
# echo "🌱 Seeding default users..."
# python manage.py seed_default_users || {
#     echo "⚠️  Warning: seed_default_users failed, but continuing..."
# }

# Start server
echo "🌐 Starting Django development server on 0.0.0.0:8000..."
exec env DB_USER="$DB_RUNTIME_USER" DB_PASSWORD="$DB_RUNTIME_PASSWORD" python manage.py runserver 0.0.0.0:8000
