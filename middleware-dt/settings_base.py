# middleware-dt/settings.py
import os
from datetime import timedelta
from neomodel import config

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SECRET_KEY = os.getenv("SECRET_KEY", "")

DEBUG = os.getenv("DEBUG", "True").lower() in ("1", "true", "yes", "on")
import socket


# sensible defaults for local/testing environments; can be overridden via .env
# Prefer explicit `ALLOWED_HOSTS` from env. If not set, try to discover a useful
# host IP to include so remote test machines can access the site without editing
# code. You can also provide `HOST_IP` in the .env to force the value.
def _detect_host_ip():
    ip = os.getenv("HOST_IP")
    if ip:
        return ip
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"

_detected_ip = _detect_host_ip()
DEFAULT_ALLOWED = ["localhost", "127.0.0.1", _detected_ip]
ALLOWED_HOSTS = [h for h in os.getenv("ALLOWED_HOSTS", ",".join(DEFAULT_ALLOWED)).split(",") if h]

# CSRF trusted origins must include scheme; build sensible defaults including
# the detected host IP and configured `MIDDLEWARE_PORT` (overridable via env).
MIDDLEWARE_PORT = os.getenv("MIDDLEWARE_PORT", "8000")
csrf_candidates = {
    "localhost",
    "127.0.0.1",
    _detected_ip,
}
for host in ALLOWED_HOSTS:
    h = host.strip()
    if h and h != "*":
        csrf_candidates.add(h)

default_csrf = []
for host in sorted(csrf_candidates):
    default_csrf.append(f"http://{host}")
    default_csrf.append(f"http://{host}:{MIDDLEWARE_PORT}")

CSRF_TRUSTED_ORIGINS = [o for o in os.getenv("CSRF_TRUSTED_ORIGINS", ",".join(default_csrf)).split(",") if o]

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
    'core.middleware.JWTAuthMiddleware',
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


def _env_bool(name, default=False):
    return str(os.getenv(name, str(default))).strip().lower() in ("1", "true", "yes", "on")


USE_INFLUX_TO_EVALUATE = _env_bool("USE_INFLUX_TO_EVALUATE", True)
ENABLE_INFLUX_LATENCY_MEASUREMENTS = _env_bool("ENABLE_INFLUX_LATENCY_MEASUREMENTS", False)
DTDL_PARSER_URL = os.getenv("DTDL_PARSER_URL", "http://parser:8080/api/DTDLModels/parse/")

# Device type mapping configuration: when True, the orchestrator will
# attempt to create properties from a static mapping file. For testing we
# allow disabling this so telemetry-based inference is used alone.
DEVICE_TYPE_MAPPING_ENABLED = _env_bool('DEVICE_TYPE_MAPPING_ENABLED', True)

# Digital Twin Settings
DEFAULT_INACTIVITY_TIMEOUT = 60
# Controla integração com Neo4j. Por padrão desabilitado para evitar tentativas
# de conexão em ambientes que não têm Neo4j disponível.
USE_NEO4J = _env_bool('USE_NEO4J', False)

# Cypher query execution settings: timeout (seconds) and maximum rows returned
# These can be overridden via environment variables `CYPHER_QUERY_TIMEOUT` and
# `CYPHER_QUERY_MAX_ROWS`.
# Default timeout increased to 30s to accommodate potentially slower Neo4j responses.
CYPHER_QUERY_TIMEOUT = int(os.getenv('CYPHER_QUERY_TIMEOUT', 30))
CYPHER_QUERY_MAX_ROWS = int(os.getenv('CYPHER_QUERY_MAX_ROWS', 1000))
