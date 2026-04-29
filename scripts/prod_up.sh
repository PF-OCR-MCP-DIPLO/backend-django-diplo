#!/bin/sh
set -eu

cd "$(dirname "$0")/.."

set -a
. ./.env.production
. ../Frontend-diplo/.env.production
set +a

docker compose -f docker-compose.prod.yml up -d --build
