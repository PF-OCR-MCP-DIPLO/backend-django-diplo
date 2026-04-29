#!/bin/sh
set -eu

backend_url="${BACKEND_HEALTH_URL:-http://localhost/api/health/}"
frontend_url="${FRONTEND_URL:-http://localhost/}"

printf 'Checking backend: %s\n' "$backend_url"
curl --fail --silent --show-error "$backend_url" >/dev/null

printf 'Checking frontend: %s\n' "$frontend_url"
curl --fail --silent --show-error "$frontend_url" >/dev/null

printf 'Smoke test passed.\n'
