# --- HTTP session helper for gateway requests (moved out of models for reuse) ---
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- Small helpers to format InfluxDB line protocol safely ---
def _escape_tag(v):
    s = str(v)
    return s.replace('\\', '\\\\').replace(' ', '\\ ').replace(',', '\\,').replace('=', '\\=')


def _format_field_value(v):
    try:
        from decimal import Decimal
    except Exception:
        Decimal = None
    # Allow explicit 'raw' integer-suffixed strings (e.g. '0i') to pass through
    # (keeps backwards compatibility for intentionally crafted literals)
    if isinstance(v, str) and v.endswith('i'):
        core = v[:-1]
        if core.lstrip('-').isdigit():
            return v
    # Normalize booleans and integers to floats to avoid Influx field-type conflicts
    if isinstance(v, bool):
        return str(1.0 if v else 0.0)
    if isinstance(v, int):
        return str(float(v))
    if Decimal and isinstance(v, Decimal):
        return str(float(v))
    try:
        if isinstance(v, float):
            return str(v)
    except Exception:
        pass
    esc = str(v).replace('"', '\\"')
    return f'"{esc}"'


def format_influx_line(measurement, tags: dict, fields: dict, timestamp=None):
    mt = str(measurement).replace(' ', '\\ ').replace(',', '\\,')
    tag_parts = []
    for k, val in (tags or {}).items():
        tag_parts.append(f"{k}={_escape_tag(val)}")
    field_parts = []
    for k, val in (fields or {}).items():
        field_parts.append(f"{k}={_format_field_value(val)}")
    if tag_parts:
        left = f"{mt},{','.join(tag_parts)}"
    else:
        left = mt
    right = ','.join(field_parts)
    if timestamp is not None:
        return f"{left} {right} {timestamp}"
    return f"{left} {right}"

# Module-level cache for sessions keyed by gateway id
_SESSIONS = {}

def get_session_for_gateway(gateway_id: int):
    """Return a configured requests.Session for the gateway id (cached)."""
    if gateway_id in _SESSIONS:
        return _SESSIONS[gateway_id]
    s = requests.Session()
    retries = Retry(total=2, backoff_factor=0.5, status_forcelist=(502, 503, 504), allowed_methods=frozenset(['GET','POST']))
    adapter = HTTPAdapter(max_retries=retries)
    s.mount('http://', adapter)
    s.mount('https://', adapter)
    _SESSIONS[gateway_id] = s
    return s
