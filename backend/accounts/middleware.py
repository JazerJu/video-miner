from django.conf import settings
from django.http import JsonResponse
from rest_framework.authtoken.models import Token


class TokenAuthenticationMiddleware:
    """
    Middleware to authenticate requests using API Token.
    
    Token is passed via Authorization header:
        Authorization: Bearer <token>
    
    If valid token is found, sets request.user to the token's user
    and skips CSRF validation.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        
        if auth_header.startswith('Bearer '):
            token_key = auth_header[7:].strip()
            
            if token_key:
                try:
                    token = Token.objects.select_related('user').get(key=token_key)
                    request.user = token.user
                    request._dont_enforce_csrf_checks = True
                except Token.DoesNotExist:
                    pass

        response = self.get_response(request)
        return response


class ApiLoginRequiredMiddleware:
    """
    With settings.API_LOGIN_REQUIRED on, answer 401 to any /api/ request whose user is not
    logged in (session cookie or Bearer token), except the endpoints the login page needs.
    /api/auth/register/ is not among them, so strangers cannot sign themselves up;
    root adds users through /api/auth/create-user/.
    """

    OPEN_PATHS = (
        "/api/get_csrf_token/",
        "/api/auth/login/",
        "/api/auth/logout/",
        "/api/auth/profile/",
        "/api/auth/check-root/",
        "/api/auth/register-root/",  # refuses once a root user exists
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            settings.API_LOGIN_REQUIRED
            and request.path.startswith("/api/")
            and request.path not in self.OPEN_PATHS
            and not request.user.is_authenticated
        ):
            return JsonResponse({"error": "Not authenticated"}, status=401)
        return self.get_response(request)
