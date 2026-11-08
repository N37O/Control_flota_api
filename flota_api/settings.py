import os
from pathlib import Path
from datetime import timedelta
from django.core.exceptions import ImproperlyConfigured

try:
    import pymysql
    pymysql.install_as_MySQLdb()
except ImportError:
    pymysql = None

BASE_DIR = Path(__file__).resolve().parent.parent

def _env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {'1', 'true', 'yes', 'on'}:
        return True
    if normalized in {'0', 'false', 'no', 'off'}:
        return False
    raise ImproperlyConfigured(f'{name} debe ser un valor booleano.')


def _env_list(name, default=()):
    return [
        value.strip()
        for value in os.getenv(name, '').split(',')
        if value.strip()
    ] or list(default)


MEDIA_URL = '/media/'
MEDIA_ROOT = Path(os.getenv('MEDIA_ROOT', BASE_DIR / 'media'))

DEBUG = _env_bool('DJANGO_DEBUG', False)

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured(
            'Define DJANGO_SECRET_KEY con una clave aleatoria y privada.'
        )
    SECRET_KEY = 'dev-only-not-for-production'
elif not DEBUG and len(SECRET_KEY) < 50:
    raise ImproperlyConfigured(
        'DJANGO_SECRET_KEY debe tener al menos 50 caracteres en producción.'
    )

ALLOWED_HOSTS = _env_list(
    'DJANGO_ALLOWED_HOSTS',
    default=('localhost', '127.0.0.1') if DEBUG else (),
)
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        'Define DJANGO_ALLOWED_HOSTS con los dominios/IP del servidor.'
    )

INSTALLED_APPS = [
    'drf_spectacular',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'django_filters',
    'usuarios',
    'unidades',
    'viajes',
    'reportes',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'flota_api.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'flota_api.wsgi.application'

db_engine = os.getenv(
    'DB_ENGINE',
    'sqlite3' if DEBUG else 'mysql',
).strip().lower()
use_sqlite_for_tests = _env_bool('USE_SQLITE_FOR_TESTS')

if db_engine == 'sqlite3' or use_sqlite_for_tests:
    if not DEBUG and not use_sqlite_for_tests:
        raise ImproperlyConfigured(
            'SQLite no está permitido en producción; configura MySQL.'
        )
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': os.getenv('DB_NAME', str(BASE_DIR / 'db.sqlite3')),
        }
    }
elif db_engine == 'mysql':
    required_database_settings = ('DB_NAME', 'DB_USER', 'DB_PASSWORD', 'DB_HOST')
    if not DEBUG:
        missing_settings = [
            name for name in required_database_settings
            if not os.getenv(name)
        ]
        if missing_settings:
            raise ImproperlyConfigured(
                'Faltan variables de MySQL: '
                + ', '.join(missing_settings)
            )
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.getenv('DB_NAME', 'control_flota'),
            'USER': os.getenv('DB_USER', 'root'),
            'PASSWORD': os.getenv('DB_PASSWORD', ''),
            'HOST': os.getenv('DB_HOST', 'localhost'),
            'PORT': os.getenv('DB_PORT', '3306'),
            'OPTIONS': {
                'charset': 'utf8mb4',
                'connect_timeout': 10,
            }
        }
    }
else:
    raise ImproperlyConfigured(
        'DB_ENGINE debe ser mysql o sqlite3.'
    )
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'es'
TIME_ZONE = 'America/El_Salvador'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = Path(os.getenv('STATIC_ROOT', BASE_DIR / 'staticfiles'))
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': (
            'whitenoise.storage.CompressedManifestStaticFilesStorage'
        ),
    },
}

SECURE_SSL_REDIRECT = _env_bool(
    'DJANGO_SECURE_SSL_REDIRECT',
    default=not DEBUG,
)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'
SECURE_HSTS_SECONDS = int(os.getenv(
    'DJANGO_SECURE_HSTS_SECONDS',
    '31536000' if not DEBUG else '0',
))
SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool(
    'DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS',
    default=False,
)
SECURE_HSTS_PRELOAD = _env_bool(
    'DJANGO_SECURE_HSTS_PRELOAD',
    default=False,
)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SIMPLE_JWT = {
    'USER_ID_FIELD': 'id_usuario',      
    'USER_ID_CLAIM': 'user_id',         
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=8),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
}

CORS_ALLOWED_ORIGINS = _env_list(
    'CORS_ALLOWED_ORIGINS',
    default=(
        'http://localhost:8080',
        'http://127.0.0.1:8080',
        'http://localhost:3000',
    ) if DEBUG else (),
)
CORS_ALLOW_ALL_ORIGINS = False
CSRF_TRUSTED_ORIGINS = _env_list(
    'CSRF_TRUSTED_ORIGINS',
    default=(
        'http://localhost:8080',
        'http://127.0.0.1:8080',
        'http://localhost:3000',
    ) if DEBUG else (),
)

# 🔑 Indica a Django que use nuestro modelo personalizado
AUTH_USER_MODEL = 'usuarios.Usuario'
