#!/bin/sh
set -eu

cd /app

mkdir -p /app/media /app/staticfiles

python - <<'PY'
import os
import sys
import time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "MCP_back.settings")

import django

django.setup()

from django.db import connection
from django.db.utils import OperationalError

max_retries = int(os.environ.get("DB_WAIT_MAX_RETRIES", "30"))
retry_delay = int(os.environ.get("DB_WAIT_RETRY_DELAY", "2"))

for attempt in range(1, max_retries + 1):
    try:
        connection.ensure_connection()
        print("Database connection ready.")
        break
    except OperationalError as exc:
        if attempt == max_retries:
            print(f"Database connection failed after {max_retries} attempts: {exc}")
            sys.exit(1)
        print(
            f"Waiting for database ({attempt}/{max_retries})... retrying in {retry_delay}s"
        )
        time.sleep(retry_delay)
PY

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec "$@"
