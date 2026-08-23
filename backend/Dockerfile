# Django API for Fly.io. SQLite lives on a mounted volume at /data (ADR-0005),
# so the sync command's writes survive restarts and redeploys.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Collected at build time so the container starts without doing extra work.
RUN DJANGO_SECRET_KEY=build-only DJANGO_DEBUG=false \
    python manage.py collectstatic --noinput

EXPOSE 8000

# Migrate on boot, then serve. Idempotent, so a redeploy is safe.
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 60"]
