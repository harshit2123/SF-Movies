#!/usr/bin/env bash
# Vercel build.
#
# Runs both halves in one step: the database is created and loaded from DataSF,
# then the SPA is built. Keeping this at the repository root gives the platform
# a single unambiguous entrypoint rather than two sibling directories that look
# like independent services.

set -euo pipefail

echo "==> Backend: database"
cd backend
# Homebrew Python marks its environment externally managed (PEP 668), which
# blocks a plain `pip install` when this script is run locally. The flag is
# accepted and ignored by pip versions that predate PEP 668, and is harmless on
# Vercel's build image, so it is passed unconditionally rather than detected.
python3 -m pip install --quiet --break-system-packages -r requirements.txt 2>/dev/null \
  || python3 -m pip install --quiet -r requirements.txt
python3 manage.py migrate --noinput
# A failed sync fails the build: an empty database would deploy "healthy" and
# serve an empty map.
python3 manage.py sync_film_locations
python3 manage.py collectstatic --noinput
python3 -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
django.setup()
from films.models import Film, FilmLocation
print(f'    {Film.objects.count()} films, {FilmLocation.objects.count()} locations')
"
cd ..

echo "==> Frontend: SPA"
cd frontend
npm run build
cd ..

echo "==> Build complete"
