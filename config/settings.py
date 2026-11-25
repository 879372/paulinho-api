import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


def load_dotenv(path):
    """Carrega .env local sem sobrescrever variáveis definidas pelo Railway."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def env_bool(name, default=False):
    return os.getenv(name, str(default)).lower() in ('1', 'true', 'yes', 'on')


def env_list(name, default=None):
    return [item.strip() for item in os.getenv(name, '').split(',') if item.strip()] or (default or [])


load_dotenv(BASE_DIR / '.env')

DEBUG = env_bool('DEBUG', default=False)
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', '')
if not SECRET_KEY:
    raise RuntimeError('DJANGO_SECRET_KEY é obrigatório.')
if not DEBUG and (len(SECRET_KEY) < 50 or SECRET_KEY.startswith('dev-only')):
    raise RuntimeError('Defina um DJANGO_SECRET_KEY forte para produção.')

ALLOWED_HOSTS = env_list('ALLOWED_HOSTS')
if not DEBUG and not ALLOWED_HOSTS:
    raise RuntimeError('ALLOWED_HOSTS é obrigatório em produção.')
ALLOWED_HOSTS = [*ALLOWED_HOSTS, 'healthcheck.railway.app']

INSTALLED_APPS = [
    'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles',
    'corsheaders', 'rest_framework', 'core', 'operacoes',
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware', 'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware', 'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [], 'APP_DIRS': True,
              'OPTIONS': {'context_processors': ['django.template.context_processors.request', 'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION = 'config.wsgi.application'
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}}
if os.getenv('DATABASE_URL'):
    import dj_database_url
    DATABASES['default'] = dj_database_url.parse(os.environ['DATABASE_URL'], conn_max_age=600, conn_health_checks=True)
elif not DEBUG:
    raise RuntimeError('DATABASE_URL é obrigatório em produção.')
AUTH_PASSWORD_VALIDATORS = []
LANGUAGE_CODE, TIME_ZONE, USE_I18N, USE_TZ = 'pt-br', 'America/Fortaleza', True, True
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
CORS_ALLOWED_ORIGINS = env_list('CORS_ALLOWED_ORIGINS')
CSRF_TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS')
if not DEBUG and (not CORS_ALLOWED_ORIGINS or not CSRF_TRUSTED_ORIGINS):
    raise RuntimeError('CORS_ALLOWED_ORIGINS e CSRF_TRUSTED_ORIGINS são obrigatórios em produção.')
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ('rest_framework_simplejwt.authentication.JWTAuthentication',),
    'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticated',),
    'DEFAULT_PAGINATION_CLASS': 'core.api.common.pagination.DefaultPagination',
    'DEFAULT_THROTTLE_CLASSES': ('rest_framework.throttling.UserRateThrottle', 'rest_framework.throttling.AnonRateThrottle'),
    'DEFAULT_THROTTLE_RATES': {'user': '500/day', 'anon': '30/day', 'login': '10/hour'},
}
EVOLUTION_API_URL = os.getenv(
    'EVOLUTION_API_URL',
    '',
).rstrip('/')
EVOLUTION_API_KEY = os.getenv('EVOLUTION_API_KEY', '')
EVOLUTION_INSTANCE = os.getenv('EVOLUTION_INSTANCE', '')
OWNER_WHATSAPP = os.getenv('OWNER_WHATSAPP', '')
COMPANY_NAME = os.getenv('COMPANY_NAME', 'Gestão de Operações')
COMPANY_LEGAL_NAME = os.getenv('COMPANY_LEGAL_NAME', '')
COMPANY_CNPJ = os.getenv('COMPANY_CNPJ', '')
COMPANY_IE = os.getenv('COMPANY_IE', '')
COMPANY_ADDRESS = os.getenv('COMPANY_ADDRESS', '')
COMPANY_PHONE = os.getenv('COMPANY_PHONE', '')
COMPANY_LOGO_PATH = os.getenv('COMPANY_LOGO_PATH', '')

# Assinatura eletrônica (Autentique). Token em https://painel.autentique.com.br/perfil/api
AUTENTIQUE_TOKEN = os.getenv('AUTENTIQUE_TOKEN', '')
AUTENTIQUE_SANDBOX = os.getenv('AUTENTIQUE_SANDBOX', 'true').lower() == 'true'
# E-mail da empresa para receber o pedido de assinatura; vazio = link de assinatura exibido no app.
AUTENTIQUE_EMAIL_EMPRESA = os.getenv('AUTENTIQUE_EMAIL_EMPRESA', '')
SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'false').lower() == 'true'
SECURE_REDIRECT_EXEMPT = [r'^api/health/$']
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
else:
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_HSTS_SECONDS = 0

SENTRY_DSN = os.getenv('SENTRY_DSN', '')
if SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=os.getenv('SENTRY_ENVIRONMENT', 'production'),
        traces_sample_rate=float(os.getenv('SENTRY_TRACES_SAMPLE_RATE', '0.05')),
        send_default_pii=False,
    )

# A imagem de produção inclui a interface e a API no mesmo domínio.
FRONTEND_DIST = BASE_DIR.parent / 'frontend' / 'dist'
SERVE_FRONTEND = env_bool('SERVE_FRONTEND')
if SERVE_FRONTEND:
    WHITENOISE_ROOT = FRONTEND_DIST
