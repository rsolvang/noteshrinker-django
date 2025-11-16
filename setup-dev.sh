#!/bin/bash
# Development setup script for noteshrinker-django
# This script sets up the development environment with proper static files

set -e

echo "=================================="
echo "NoteShrinker Development Setup"
echo "=================================="
echo ""

# Check if virtualenv is active
if [ -z "$VIRTUAL_ENV" ]; then
    echo "⚠️  Warning: No virtual environment detected"
    echo "   It's recommended to use a virtual environment"
    echo "   Run: virtualenv venv && source venv/bin/activate"
    echo ""
fi

# Set DEBUG to True for development
export DEBUG=True
export DJANGO_SECRET_KEY="dev-secret-key-change-in-production"
export ALLOWED_HOSTS="localhost,127.0.0.1"

echo "📦 Installing dependencies..."
pip install -r requirements.txt

echo ""
echo "🗄️  Running database migrations..."
python manage.py migrate

echo ""
echo "📁 Collecting static files..."
python manage.py collectstatic --noinput

echo ""
echo "✅ Setup complete!"
echo ""
echo "To start the development server, run:"
echo "  export DEBUG=True"
echo "  python manage.py runserver"
echo ""
echo "Then visit: http://localhost:8000"
echo ""
