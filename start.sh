#!/bin/bash
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

# Install/update Python and Node dependencies if running outside the pre-built
# image (e.g. local dev with a mounted workspace and fresh requirements).
if [ "${SKIP_INSTALL:-0}" != "1" ]; then
  echo "==> Installing Python dependencies..."
  pip install -r "$REPO_DIR/requirements.txt" --quiet

  echo "==> Installing Node dependencies..."
  cd "$REPO_DIR"
  npm install --silent

  echo "==> Building CSS..."
  npm run build:css
fi

echo "==> Running database migrations..."
cd "$REPO_DIR/webapp"
python manage.py migrate --noinput

echo "==> Collecting static files..."
python manage.py collectstatic --noinput --ignore input.css

echo "==> Starting daphne on port 8100..."
exec daphne core.asgi:application \
    --bind 0.0.0.0 \
    --port 8100 \
    --access-log -
