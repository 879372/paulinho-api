#!/bin/sh
set -eu
python manage.py migrate --noinput
python manage.py bootstrap_admin
exec gunicorn config.wsgi:application --bind "[::]:${PORT:-8000}" --workers 2 --threads 4 --timeout 120 --access-logfile - --error-logfile - --capture-output
