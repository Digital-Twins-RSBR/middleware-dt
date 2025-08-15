#!/usr/bin/env python3
"""Django's command-line utility for administrative tasks."""
import os
import sys
from pathlib import Path

def _load_env_file():
    """Carrega .env manualmente (sem depender de python-dotenv)."""
    base_dir = Path(__file__).resolve().parent
    env_path = base_dir / '.env'
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text().splitlines():
            if not line or line.strip().startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            k = k.strip(); v = v.strip()
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:
        pass


def main():
    """Run administrative tasks."""
    _load_env_file()
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'middleware_dt.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
