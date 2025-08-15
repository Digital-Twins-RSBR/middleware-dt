"""Settings wrapper that loads .env manually (without python-dotenv) before importing base settings."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / '.env'

def _load_env_file(path):
    if not path.exists():
        return
    try:
        for line in path.read_text().splitlines():
            if not line or line.strip().startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            k = k.strip(); v = v.strip()
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:
        pass

_load_env_file(ENV_FILE)

from .settings_base import *  # noqa

# Garantia de SECRET_KEY (para comandos manage.py fora do entrypoint)
if not SECRET_KEY:  # type: ignore  # noqa
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-temporary-secret-key'  # noqa
