#!/bin/sh
set -eu

cd "$(dirname "$0")/.."

docker compose -f docker-compose.prod.yml logs --tail="${1:-100}" -f
