#!/bin/bash
# Migration Creation Helper Script for AI Agent Management Module
# This script helps create Django migrations when the environment is ready

set -e

MODULE_NAME="ai_agent_management"
BACKEND_DIR="backend"

echo "🚀 Creating migrations for ${MODULE_NAME} module..."
echo ""

# Check if we're in the right directory
if [ ! -d "${BACKEND_DIR}" ]; then
    echo "❌ Error: ${BACKEND_DIR} directory not found"
    echo "   Please run this script from the project root"
    exit 1
fi

cd "${BACKEND_DIR}"

# Check if Django is available
if ! python manage.py --version > /dev/null 2>&1; then
    echo "❌ Error: Django not found or manage.py not working"
    echo "   Please set up your Django environment first:"
    echo "   - Activate virtual environment"
    echo "   - Install dependencies: pip install -e .[dev]"
    exit 1
fi

echo "✅ Django environment detected"
echo ""

# Create migrations
echo "📦 Creating migrations..."
python manage.py makemigrations ${MODULE_NAME}

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Migrations created successfully!"
    echo ""
    echo "📋 Next steps:"
    echo "   1. Review migration files in: backend/src/modules/${MODULE_NAME}/migrations/"
    echo "   2. Apply migrations: python manage.py migrate"
    echo "   3. Verify tables: python manage.py dbshell"
    echo "      Then run: \\dt ai_*"
else
    echo ""
    echo "❌ Migration creation failed"
    echo "   Check the error messages above"
    exit 1
fi

