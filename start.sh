#!/bin/bash
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Installing Python dependencies..."
pip install -r "$REPO_DIR/requirements.txt" --quiet

echo "==> Installing Node dependencies..."
cd "$REPO_DIR"
npm install --silent

echo "==> Building CSS..."
npm run build:css

echo "==> Running database migrations..."
cd "$REPO_DIR/webapp"
python manage.py migrate --noinput

echo "==> Collecting static files..."
python manage.py collectstatic --noinput --ignore input.css

echo "==> Starting gunicorn on port 8100..."
exec gunicorn core.wsgi:application \
    --bind 0.0.0.0:8100 \
    --workers 3 \
    --access-logfile - \
    --error-logfile -
