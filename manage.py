#!/usr/bin/env python3
"""Django's command-line utility for administrative tasks."""
import os
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
            k = k.strip()
            v = v.strip()
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:
        pass


def main():
    """Run administrative tasks."""
    _load_env_file()
    # Auto-detect the package folder that contains settings.py. This allows the
    # project to run whether the folder is named 'middleware_dt' or 'middleware-dt'
    # (the latter is not a valid python module name). If the folder name contains
    # invalid module characters (like '-'), we expose it under an importable
    # name by creating a synthetic package module in sys.modules with the
    # hyphen replaced by underscore.
    import re
    import sys
    import types

    def _discover_settings_package():
        base_dir = Path(__file__).resolve().parent
        for child in base_dir.iterdir():
            if child.is_dir() and (child / 'settings.py').exists():
                pkg_name = child.name
                # make a valid module name
                mod_name = pkg_name if re.match(r'^[A-Za-z_]\w*$', pkg_name) else pkg_name.replace('-', '_')
                if mod_name not in sys.modules:
                    module = types.ModuleType(mod_name)
                    # ensure import system can find submodules like 'settings'
                    module.__path__ = [str(child)]
                    sys.modules[mod_name] = module
                return mod_name
        # fallback (legacy)
        return 'middleware_dt'

    settings_pkg = _discover_settings_package()
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', f"{settings_pkg}.settings")
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
