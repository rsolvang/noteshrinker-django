"""
Production settings for noteshrinker_django project.

Usage:
    export DJANGO_SETTINGS_MODULE=noteshrinker_django.settings_production
    python manage.py runserver

Or with gunicorn:
    gunicorn noteshrinker_django.wsgi:application --bind 0.0.0.0:8000
"""

from .settings import *  # noqa

# SECURITY: Override development settings for production
DEBUG = False

# SECURITY: Must be set via environment variable in production
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("DJANGO_SECRET_KEY environment variable must be set in production")

# SECURITY: Must be set via environment variable in production
ALLOWED_HOSTS_STR = os.environ.get('ALLOWED_HOSTS', '')
if not ALLOWED_HOSTS_STR:
    raise ValueError("ALLOWED_HOSTS environment variable must be set in production")
ALLOWED_HOSTS = ALLOWED_HOSTS_STR.split(',')

# SECURITY: Enable HTTPS-only features
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Static files (for production with WhiteNoise or similar)
# Uncomment when using WhiteNoise:
# STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
# MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')

# Database
# Consider using PostgreSQL in production instead of SQLite
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.postgresql',
#         'NAME': os.environ.get('DB_NAME'),
#         'USER': os.environ.get('DB_USER'),
#         'PASSWORD': os.environ.get('DB_PASSWORD'),
#         'HOST': os.environ.get('DB_HOST', 'localhost'),
#         'PORT': os.environ.get('DB_PORT', '5432'),
#     }
# }

# Logging - Production level
LOGGING['loggers']['django']['level'] = 'WARNING'
LOGGING['loggers']['noteshrinker']['level'] = 'INFO'
LOGGING['root']['level'] = 'WARNING'

# Email configuration (for error reporting)
# ADMINS = [('Admin Name', 'admin@example.com')]
# SERVER_EMAIL = 'server@example.com'
# EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
# EMAIL_HOST = os.environ.get('EMAIL_HOST')
# EMAIL_PORT = os.environ.get('EMAIL_PORT', 587)
# EMAIL_USE_TLS = True
# EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER')
# EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')
