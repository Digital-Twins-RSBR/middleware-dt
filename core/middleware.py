from rest_framework_simplejwt.authentication import JWTAuthentication


class JWTAuthMiddleware:
    """Middleware to authenticate JWT access tokens (SimpleJWT) for plain
    Django request objects so `request.user` is populated for Ninja views.

    This calls `JWTAuthentication().authenticate(request)` which returns
    `(user, validated_token)` when a valid Authorization header is present.
    Any authentication error is ignored so anonymous access continues to
    work where allowed.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self._auth = JWTAuthentication()

    def __call__(self, request):
        try:
            auth_result = self._auth.authenticate(request)
            if auth_result is not None:
                user, _ = auth_result
                request.user = user
        except Exception:
            # Ignore errors and leave request.user as-is (anonymous)
            pass
        return self.get_response(request)
