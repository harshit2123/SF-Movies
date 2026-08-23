#!/usr/bin/env bash
# Vercel build step.
#
# Creates the database and loads it from DataSF at build time, then bakes the
# file into the deployment bundle. At runtime the filesystem is read-only, which
# suits an API that never writes (ADR-0007).
#
# Refreshing the data therefore means redeploying rather than running a command
# against production — the tradeoff that decision records.

set -euo pipefail

echo "--> Installing dependencies"
python3 -m pip install --quiet --upgrade pip
python3 -m pip install --quiet -r requirements.txt

echo "--> Applying migrations"
python3 manage.py migrate --noinput

echo "--> Loading film locations from DataSF"
# A failed sync must fail the build: shipping an empty database would produce a
# deployment that looks healthy and serves an empty map.
python3 manage.py sync_film_locations

echo "--> Collecting static files"
python3 manage.py collectstatic --noinput

echo "--> Build complete"
python3 -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from films.models import Film, FilmLocation
print(f'    {Film.objects.count()} films, {FilmLocation.objects.count()} locations')
"
