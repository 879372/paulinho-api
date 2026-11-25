from .local import *  # noqa: F403
# Cache isolado: a cota de login de um teste não afeta os seguintes.
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}}
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
