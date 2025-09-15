# middleware-dt/settings.py
import os
from datetime import timedelta
from neomodel import config

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SECRET_KEY = os.getenv("SECRET_KEY", "")

DEBUG = os.getenv("DEBUG", "True").lower() in ("1", "true", "yes", "on")
ALLOWED_HOSTS = [h for h in os.getenv("ALLOWED_HOSTS", "*").split(",") if h]
CSRF_TRUSTED_ORIGINS = [o for o in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if o]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'django_extensions',
    'ninja',
    'ninja_extra',
    'corsheaders',
    'core',
    'facade',
    'orchestrator',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'corsheaders.middleware.CorsMiddleware',
]

ROOT_URLCONF = 'middleware_dt.urls'


TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
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

WSGI_APPLICATION = 'middleware_dt.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('POSTGRES_DB', 'middts'),
        'USER': os.getenv('POSTGRES_USER', 'postgres'),
        'PASSWORD': os.getenv('POSTGRES_PASSWORD', 'tb'),
        'HOST': os.getenv('POSTGRES_HOST', '10.10.2.10'),
        'PORT': os.getenv('POSTGRES_PORT', '5432'),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
}

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR + "/" + "static/" 

#### Configuração do NEO4J

NEO4J_URL = os.getenv("NEO4J_URL", "localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# Build neomodel DATABASE_URL robustly. Accept NEO4J_URL in forms:
#   - host:port
#   - bolt://host:port
#   - neo4j://host:port
#   - bolt://user:pass@host:port
from urllib.parse import urlsplit

_raw_neo = NEO4J_URL
_parsed = urlsplit(_raw_neo)
if _parsed.scheme:
    # NEO4J_URL already contains a scheme. If it already contains credentials,
    # keep them, otherwise inject NEO4J_USER/NEO4J_PASSWORD.
    scheme = _parsed.scheme
    netloc = _parsed.netloc
    path = _parsed.path or ''
    if '@' in netloc:
        config.DATABASE_URL = f"{scheme}://{netloc}{path}"
    else:
        config.DATABASE_URL = f"{scheme}://{NEO4J_USER}:{NEO4J_PASSWORD}@{netloc}{path}"
else:
    # NEO4J_URL has no scheme, assume bolt
    config.DATABASE_URL = f"bolt://{NEO4J_USER}:{NEO4J_PASSWORD}@{_raw_neo}"

SESSION_COOKIE_NAME = 'sessionid_middts'
CSRF_COOKIE_NAME = 'csrftoken_middts'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv("POSTGRES_DB", "middts"),
        'USER': os.getenv("POSTGRES_USER", "postgres"),
        'PASSWORD': os.getenv("POSTGRES_PASSWORD", "postgres"),
        'HOST': os.getenv("POSTGRES_HOST", "middleware-dt-db-1'"),
        'PORT': os.getenv("POSTGRES_PORT", "5432"),
    }
}

# InfluxDB Configuration
#INFLUXDB_HOST = os.getenv("INFLUXDB_HOST", "localhost")
INFLUXDB_HOST = os.getenv("INFLUXDB_HOST", "influxdb")
INFLUXDB_PORT = int(os.getenv("INFLUXDB_PORT", 8086))
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "iot_data")
INFLUXDB_ORGANIZATION = os.getenv("INFLUXDB_ORGANIZATION", "middts")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "xxx")
USE_INFLUX_TO_EVALUATE = True

# Digital Twin Settings
DEFAULT_INACTIVITY_TIMEOUT = 60
# Controla integração com Neo4j. Por padrão desabilitado para evitar tentativas
# de conexão em ambientes que não têm Neo4j disponível.
USE_NEO4J = os.getenv('USE_NEO4J', 'False').lower() in ('1', 'true', 'yes', 'on')
