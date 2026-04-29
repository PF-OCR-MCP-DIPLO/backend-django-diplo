#!/bin/sh
set -eu

cd "$(dirname "$0")/.."

docker compose -f docker-compose.prod.yml down
