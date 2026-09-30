#!/bin/sh
set -e

python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py ensure_superuser
python manage.py seed_payment_methods
# Demo data is no longer auto-seeded — this is a live deployment now.
# To load demo data again for testing, run manually:
#   docker compose exec backend python manage.py seed_demo_data --force

exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3
