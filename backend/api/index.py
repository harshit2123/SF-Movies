"""
Vercel serverless entrypoint.

Vercel's Python runtime looks for a WSGI/ASGI callable named `app` in this file.
Everything else about the project is unchanged — this is a thin adapter, not a
second copy of the application.

The database ships inside the deployment bundle, built during `vercel build`
(see build.sh and ADR-0007). At runtime the filesystem is read-only, which is
fine because the API never writes: data arrives only through the sync command,
which runs at build time.
"""

import os
import sys
from pathlib import Path

# The Django project lives one level up from this file.
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.wsgi import get_wsgi_application  # noqa: E402

app = get_wsgi_application()
