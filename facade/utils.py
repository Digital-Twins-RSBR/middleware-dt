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
    if isinstance(v, str) and v.endswith('i'):
        # accept negative integers as well
        core = v[:-1]
        if core.lstrip('-').isdigit():
            return v
    if isinstance(v, bool):
        return f"{1 if v else 0}i"
    if isinstance(v, int):
        return f"{v}i"
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
