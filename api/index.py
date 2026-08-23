"""
Vercel serverless entrypoint.

Vercel's Python runtime discovers functions in a top-level `api/` directory and
looks for a WSGI/ASGI callable named `app`. This is a thin adapter — the Django
project itself stays in `backend/` and is unchanged.

The database ships inside the deployment bundle, built during `vercel build`
(see backend/build.sh and ADR-0007). At runtime the filesystem is read-only,
which suits an API that never writes: data arrives only through the sync
command, which runs at build time.
"""

import os
import sys
from pathlib import Path

# The Django project lives in backend/, a sibling of this directory.
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.wsgi import get_wsgi_application  # noqa: E402

app = get_wsgi_application()
