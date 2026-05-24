# Deploy BudgetWiseBackend to Render

This document describes the production deployment of BudgetWiseBackend as a Render Docker Web Service.

## Services

Use two Render services:

1. Render PostgreSQL database.
2. Docker Web Service for the Django backend.

The local `docker-compose.yml` remains for development only. On Render the backend container connects to Render PostgreSQL through `DATABASE_URL`.

## Required Render environment variables

```env
DJANGO_SETTINGS_MODULE=config.settings.prod
SECRET_KEY=<generate-a-strong-secret>
DEBUG=False
DATABASE_URL=<Render PostgreSQL internal database URL>
DB_CONN_MAX_AGE=60
ALLOWED_HOSTS=<your-backend-name>.onrender.com
CSRF_TRUSTED_ORIGINS=https://<your-backend-name>.onrender.com
CORS_ALLOWED_ORIGINS=https://<frontend-domain>
CORS_ALLOW_CREDENTIALS=False
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=31536000
PORT=10000
GUNICORN_WORKERS=2
GUNICORN_TIMEOUT=120
```

Additional optional variables:

```env
METRICS_ACCESS_TOKEN=<secret-token>
PROVERKACHEKA_ENABLED=False
PROVERKACHEKA_API_TOKEN=
CURRENCY_RATES_ENABLED=True
PWA_PUSH_SUBSCRIPTIONS_ENABLED=True
PWA_PUSH_SEND_ENABLED=False
PWA_PUSH_PROVIDER=web_push
PWA_VAPID_PUBLIC_KEY=
PWA_VAPID_PRIVATE_KEY=
PWA_VAPID_SUBJECT=mailto:your-email@example.com
PWA_MAX_PUSH_SUBSCRIPTIONS_PER_USER=10
PWA_BACKGROUND_SYNC_ENABLED=True
PWA_BACKGROUND_SYNC_RETRY_SECONDS=30
PWA_PUSH_TTL_SECONDS=60
```

## Docker startup

The container start command is defined in `Dockerfile`:

```sh
python manage.py migrate --noinput && \
python manage.py collectstatic --noinput && \
gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-10000}
```

This means migrations and static collection run automatically before Gunicorn starts.

## Health check

Use this health check path in Render:

```text
/health/
```

The endpoint checks that the backend is alive and that the database connection works.

## Static and media files

Static files are served through WhiteNoise after `collectstatic`.

Media files are stored in `/app/media`. For stable uploaded files on Render, attach a persistent disk and mount it to `/app/media`. Without a persistent disk, uploaded files may be lost after rebuilds or container replacement.

## Frontend integration

After the backend is deployed, update frontend environment variables to use:

```text
https://<your-backend-name>.onrender.com
```

Then add the frontend domain to `CORS_ALLOWED_ORIGINS` and, if cookie-based flows are introduced later, to `CSRF_TRUSTED_ORIGINS` as well.
