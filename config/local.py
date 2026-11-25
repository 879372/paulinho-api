"""Ambiente local isolado. Não usar em produção."""
import os
os.environ.update(DEBUG='true', DJANGO_SECRET_KEY='dev-only-gestao-operacoes-local-not-for-production-12345', DATABASE_URL='', SENTRY_DSN='', EVOLUTION_API_URL='', EVOLUTION_API_KEY='', EVOLUTION_INSTANCE='', OWNER_WHATSAPP='', SECURE_SSL_REDIRECT='false', CORS_ALLOWED_ORIGINS='http://127.0.0.1:5175,http://localhost:5175', CSRF_TRUSTED_ORIGINS='http://127.0.0.1:8015,http://localhost:8015')
from .settings import *  # noqa: F403
ALLOWED_HOSTS = ['localhost', '127.0.0.1', 'testserver']
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'gestao-local.sqlite3'}}
