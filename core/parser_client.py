from django.conf import settings


def get_dtdl_parser_url() -> str:
    parser_url = getattr(settings, 'DTDL_PARSER_URL', '').strip()
    if not parser_url:
        raise RuntimeError('DTDL_PARSER_URL is not configured.')
    return parser_url
